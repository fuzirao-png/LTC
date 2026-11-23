from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Literal
from uuid import UUID

from psycopg.rows import dict_row

from ltc.modules.sales_crm.domain.contact_priority import (
    RANKING_VERSION,
    ScoredContact,
    score_contact,
    select_top_contacts,
)
from ltc.platform.db import PostgresDatabase


RosterAction = Literal["activate", "backup", "pin", "unpin", "move"]


class ContactRosterError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContactRosterService:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get_roster(self, company_id: UUID) -> dict[str, Any]:
        with self._database.transaction() as connection:
            company = self._require_company(connection, company_id)
            rows = self._contact_rows(connection, company_id)
            if self._needs_refresh(company, rows):
                self._recalculate_locked(connection, company_id, company, rows, actor_user_id=None)
                rows = self._contact_rows(connection, company_id)
            return self._roster_payload_from_rows(rows, company_id)

    def recalculate(self, company_id: UUID, actor_user_id: UUID | None) -> dict[str, Any]:
        with self._database.transaction() as connection:
            company = self._require_company(connection, company_id, lock=True)
            rows = self._contact_rows(connection, company_id)
            return self._recalculate_locked(connection, company_id, company, rows, actor_user_id=actor_user_id)

    def mutate(
        self,
        company_id: UUID,
        contact_id: UUID,
        *,
        action: RosterAction,
        actor_user_id: UUID | None,
        position: int | None = None,
        replace_contact_id: UUID | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        with self._database.transaction() as connection:
            self._require_company(connection, company_id, lock=True)
            roster = self._locked_roster(connection, company_id)
            if not roster:
                raise ContactRosterError("ROSTER_NOT_INITIALIZED", "请先重新计算联系人排序。")
            before = self._roster_summary(roster)
            target = next((row for row in roster if str(row["contact_id"]) == str(contact_id)), None)
            if target is None:
                contact = next(
                    (
                        row for row in self._contact_rows(connection, company_id)
                        if str(row["contact_id"]) == str(contact_id)
                    ),
                    None,
                )
                if contact is not None:
                    self._upsert_score(
                        connection,
                        company_id=company_id,
                        item=score_contact(contact),
                        position=None,
                        actor_user_id=actor_user_id,
                    )
                    roster = self._locked_roster(connection, company_id)
                    target = next(
                        (row for row in roster if str(row["contact_id"]) == str(contact_id)),
                        None,
                    )
            if target is None:
                raise ContactRosterError("CONTACT_NOT_FOUND", "联系人不属于当前公司。")

            if action == "activate":
                self._activate(
                    connection,
                    company_id,
                    target,
                    actor_user_id=actor_user_id,
                    replace_contact_id=replace_contact_id,
                    reason=reason,
                )
            elif action == "backup":
                self._move_to_backup(connection, target, reason=reason)
            elif action == "pin":
                self._pin_to_top(
                    connection,
                    company_id,
                    target,
                    actor_user_id=actor_user_id,
                    reason=reason,
                )
            elif action == "unpin":
                connection.execute(
                    "UPDATE ltc.company_contact_roster "
                    "SET is_pinned=%s, override_reason=%s, selected_by=%s, "
                    "version=version+1, updated_at=clock_timestamp() "
                    "WHERE company_id=%s AND contact_id=%s",
                    (
                        False,
                        reason,
                        str(actor_user_id) if actor_user_id else None,
                        str(company_id),
                        str(contact_id),
                    ),
                )
            elif action == "move":
                if position is None or not 1 <= position <= 5:
                    raise ContactRosterError("INVALID_POSITION", "联系人顺位必须在1到5之间。")
                self._move_position(connection, company_id, target, position, actor_user_id, reason)
            else:
                raise ContactRosterError("INVALID_ACTION", "不支持的联系人操作。")

            after_payload = self._roster_payload(connection, company_id)
            self._audit(
                connection,
                actor_user_id=actor_user_id,
                company_id=company_id,
                action=f"contact_roster.{action}",
                before=before,
                after=self._payload_summary(after_payload),
                metadata={
                    "contact_id": str(contact_id),
                    "replace_contact_id": str(replace_contact_id) if replace_contact_id else None,
                    "reason": reason,
                },
            )
            return after_payload

    def _activate(
        self,
        connection: Any,
        company_id: UUID,
        target: dict[str, Any],
        *,
        actor_user_id: UUID | None,
        replace_contact_id: UUID | None,
        reason: str | None,
    ) -> None:
        if target.get("blocked_reason"):
            raise ContactRosterError("CONTACT_INELIGIBLE", str(target["blocked_reason"]))
        if not _has_usable_email(target):
            raise ContactRosterError("CONTACT_MISSING_EMAIL", "CONTACT_MISSING_EMAIL")
        if target["roster_status"] == "active":
            return

        active = [row for row in self._locked_roster(connection, company_id) if row["roster_status"] == "active"]
        if len(active) >= 5:
            if replace_contact_id is None:
                raise ContactRosterError("REPLACEMENT_REQUIRED", "联系人已满5人，请选择替换对象。")
            replacement = next((row for row in active if str(row["contact_id"]) == str(replace_contact_id)), None)
            if replacement is None:
                raise ContactRosterError("REPLACEMENT_NOT_FOUND", "替换对象不在当前联系人列表。")
            if replacement["is_pinned"] or replacement["engagement_locked"]:
                raise ContactRosterError("CONTACT_LOCKED", "已置顶、已回复或已参会联系人不能被替换。")
            if not _text(reason):
                raise ContactRosterError("REPLACEMENT_REASON_REQUIRED", "替换联系人必须填写原因。")
            target_position = int(replacement["position"])
            connection.execute(
                "UPDATE ltc.company_contact_roster SET roster_status='backup', position=NULL, "
                "override_reason=%s, version=version+1, updated_at=clock_timestamp() "
                "WHERE company_id=%s AND contact_id=%s",
                (reason, str(company_id), str(replace_contact_id)),
            )
        else:
            used_positions = {int(row["position"]) for row in active if row.get("position") is not None}
            target_position = next(position for position in range(1, 6) if position not in used_positions)

        connection.execute(
            "UPDATE ltc.company_contact_roster SET roster_status='active', position=%s, "
            "override_reason=%s, selected_by=%s, selected_at=clock_timestamp(), "
            "version=version+1, updated_at=clock_timestamp() "
            "WHERE company_id=%s AND contact_id=%s",
            (
                target_position,
                reason,
                str(actor_user_id) if actor_user_id else None,
                str(company_id),
                str(target["contact_id"]),
            ),
        )

    @staticmethod
    def _move_to_backup(connection: Any, target: dict[str, Any], *, reason: str | None) -> None:
        if target["is_pinned"] or target["engagement_locked"]:
            raise ContactRosterError("CONTACT_LOCKED", "已置顶、已回复或已参会联系人不能移出。")
        if not _text(reason):
            raise ContactRosterError("REMOVAL_REASON_REQUIRED", "移出联系人必须填写原因。")
        connection.execute(
            "UPDATE ltc.company_contact_roster SET roster_status='backup', position=NULL, "
            "override_reason=%s, version=version+1, updated_at=clock_timestamp() "
            "WHERE company_id=%s AND contact_id=%s",
            (reason, str(target["company_id"]), str(target["contact_id"])),
        )

    @staticmethod
    def _pin_to_top(
        connection: Any,
        company_id: UUID,
        target: dict[str, Any],
        *,
        actor_user_id: UUID | None,
        reason: str | None,
    ) -> None:
        if not _has_usable_email(target):
            raise ContactRosterError("CONTACT_MISSING_EMAIL", "CONTACT_MISSING_EMAIL")
        if target["roster_status"] != "active":
            raise ContactRosterError("CONTACT_NOT_ACTIVE", "备用联系人不能置顶。")

        old_position = int(target["position"])
        if old_position > 1:
            # Release the target position first so each following update keeps
            # the active-position unique index valid throughout the operation.
            connection.execute(
                "UPDATE ltc.company_contact_roster SET roster_status='backup', position=NULL, "
                "version=version+1, updated_at=clock_timestamp() "
                "WHERE company_id=%s AND contact_id=%s",
                (str(company_id), str(target["contact_id"])),
            )
            for current_position in range(old_position - 1, 0, -1):
                connection.execute(
                    "UPDATE ltc.company_contact_roster SET position=%s, "
                    "version=version+1, updated_at=clock_timestamp() "
                    "WHERE company_id=%s AND roster_status='active' AND position=%s",
                    (current_position + 1, str(company_id), current_position),
                )

        connection.execute(
            "UPDATE ltc.company_contact_roster SET roster_status='active', position=1, "
            "is_pinned=true, override_reason=%s, selected_by=%s, "
            "version=version+1, updated_at=clock_timestamp() "
            "WHERE company_id=%s AND contact_id=%s",
            (
                reason,
                str(actor_user_id) if actor_user_id else None,
                str(company_id),
                str(target["contact_id"]),
            ),
        )

    @staticmethod
    def _move_position(
        connection: Any,
        company_id: UUID,
        target: dict[str, Any],
        position: int,
        actor_user_id: UUID | None,
        reason: str | None,
    ) -> None:
        if not _has_usable_email(target):
            raise ContactRosterError("CONTACT_MISSING_EMAIL", "CONTACT_MISSING_EMAIL")
        if target["roster_status"] != "active":
            raise ContactRosterError("CONTACT_NOT_ACTIVE", "备用联系人不能调整顺位。")
        old_position = int(target["position"])
        if old_position == position:
            return
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT contact_id FROM ltc.company_contact_roster "
                "WHERE company_id=%s AND roster_status='active' AND position=%s FOR UPDATE",
                (str(company_id), position),
            )
            displaced = cursor.fetchone()
        if displaced:
            connection.execute(
                "UPDATE ltc.company_contact_roster SET roster_status='backup', position=NULL "
                "WHERE company_id=%s AND contact_id=%s",
                (str(company_id), str(displaced["contact_id"])),
            )
        connection.execute(
            "UPDATE ltc.company_contact_roster SET position=%s, override_reason=%s, selected_by=%s, "
            "version=version+1, updated_at=clock_timestamp() WHERE company_id=%s AND contact_id=%s",
            (
                position,
                reason,
                str(actor_user_id) if actor_user_id else None,
                str(company_id),
                str(target["contact_id"]),
            ),
        )
        if displaced:
            connection.execute(
                "UPDATE ltc.company_contact_roster SET roster_status='active', position=%s, "
                "version=version+1, updated_at=clock_timestamp() WHERE company_id=%s AND contact_id=%s",
                (old_position, str(company_id), str(displaced["contact_id"])),
            )

    def _upsert_score(
        self,
        connection: Any,
        *,
        company_id: UUID,
        item: ScoredContact,
        position: int | None,
        actor_user_id: UUID | None,
    ) -> None:
        roster_status = "active" if position is not None else "backup"
        connection.execute(
            """
            INSERT INTO ltc.company_contact_roster (
                company_id, contact_id, roster_status, position, role_group,
                priority_score, score_breakdown, recommendation_reason,
                ranking_version, is_pinned, engagement_locked, outreach_status,
                last_engagement_at, selected_by, selected_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())
            ON CONFLICT (company_id, contact_id) DO UPDATE SET
                roster_status=EXCLUDED.roster_status,
                position=EXCLUDED.position,
                role_group=EXCLUDED.role_group,
                priority_score=EXCLUDED.priority_score,
                score_breakdown=EXCLUDED.score_breakdown,
                recommendation_reason=EXCLUDED.recommendation_reason,
                ranking_version=EXCLUDED.ranking_version,
                engagement_locked=(
                    ltc.company_contact_roster.engagement_locked
                    OR EXCLUDED.engagement_locked
                ),
                outreach_status=EXCLUDED.outreach_status,
                last_engagement_at=EXCLUDED.last_engagement_at,
                selected_by=CASE WHEN EXCLUDED.roster_status='active' THEN EXCLUDED.selected_by ELSE ltc.company_contact_roster.selected_by END,
                selected_at=CASE WHEN EXCLUDED.roster_status='active' THEN EXCLUDED.selected_at ELSE ltc.company_contact_roster.selected_at END,
                version=ltc.company_contact_roster.version+1,
                updated_at=clock_timestamp()
            """,
            (
                str(company_id),
                str(item.contact["contact_id"]),
                roster_status,
                position,
                item.role_group,
                item.score,
                json.dumps(item.breakdown, ensure_ascii=False),
                "；".join(item.reasons),
                RANKING_VERSION,
                bool(item.contact.get("is_pinned")),
                bool(item.contact.get("has_reply") or item.contact.get("has_meeting")),
                _outreach_status(item.contact),
                item.contact.get("last_engagement_at"),
                str(actor_user_id) if actor_user_id and position is not None else None,
                datetime.now(timezone.utc) if position is not None else None,
            ),
        )

    def _roster_payload(self, connection: Any, company_id: UUID) -> dict[str, Any]:
        rows = self._contact_rows(connection, company_id)
        return self._roster_payload_from_rows(rows, company_id)

    def _roster_payload_from_rows(self, rows: list[dict[str, Any]], company_id: UUID) -> dict[str, Any]:
        active = [row for row in rows if row.get("roster_status") == "active"]
        backup = [row for row in rows if row.get("roster_status") != "active"]
        active.sort(key=lambda row: int(row.get("position") or 99))
        backup.sort(key=lambda row: float(row.get("priority_score") or 0), reverse=True)
        return {
            "company_id": str(company_id),
            "initialized": any(row.get("ranking_version") for row in rows),
            "active": [self._public_row(row) for row in active],
            "backup": [self._public_row(row) for row in backup],
            "total": len(rows),
            "limit": 5,
            "ranking_version": RANKING_VERSION,
        }

    def _recalculate_locked(
        self,
        connection: Any,
        company_id: UUID,
        company: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        actor_user_id: UUID | None,
    ) -> dict[str, Any]:
        before = self._roster_summary(rows)
        scored = [
            self._score_contact_for_company(company, row)
            for row in rows
        ]
        selected = select_top_contacts(scored)
        selected_positions = {
            _text(item.contact.get("contact_id")): position
            for position, item in enumerate(selected, start=1)
        }
        selected_scores = {
            _text(item.contact.get("contact_id")): item
            for item in selected
        }

        connection.execute(
            "UPDATE ltc.company_contact_roster "
            "SET roster_status='backup', position=NULL, version=version+1, updated_at=clock_timestamp() "
            "WHERE company_id=%s",
            (str(company_id),),
        )
        for item in scored:
            contact_id = _text(item.contact.get("contact_id"))
            effective = selected_scores.get(contact_id, item)
            position = selected_positions.get(contact_id)
            self._upsert_score(
                connection,
                company_id=company_id,
                item=effective,
                position=position,
                actor_user_id=actor_user_id,
            )

        after_payload = self._roster_payload(connection, company_id)
        self._audit(
            connection,
            actor_user_id=actor_user_id,
            company_id=company_id,
            action="contact_roster.recalculated",
            before=before,
            after=self._payload_summary(after_payload),
            metadata={"ranking_version": RANKING_VERSION},
        )
        return after_payload

    def _contact_rows(self, connection: Any, company_id: UUID) -> list[dict[str, Any]]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    ct.*,
                    cc.email AS source_primary_email,
                    cc.normalized_email AS source_normalized_email,
                    cc.email_status AS source_email_status,
                    cc.last_seen_at AS source_last_seen_at,
                    r.roster_status, r.position, r.role_group, r.priority_score,
                    r.score_breakdown, r.recommendation_reason, r.ranking_version,
                    COALESCE(r.is_pinned, false) AS is_pinned,
                    COALESCE(r.engagement_locked, false) AS engagement_locked,
                    r.outreach_status, r.last_engagement_at, r.override_reason,
                    r.version AS roster_version,
                    EXISTS (
                        SELECT 1 FROM ltc.email_suppression es
                        WHERE es.normalized_email=ct.normalized_email AND es.status='active'
                    ) AS is_suppressed,
                    EXISTS (
                        SELECT 1 FROM ltc.email_message em
                        WHERE em.contact_id=ct.contact_id AND em.direction='inbound'
                    ) AS has_reply,
                    EXISTS (
                        SELECT 1 FROM ltc.email_message em
                        WHERE em.contact_id=ct.contact_id AND em.status='opened'
                    ) AS has_open,
                    EXISTS (
                        SELECT 1 FROM ltc.email_message em
                        WHERE em.contact_id=ct.contact_id AND em.status='clicked'
                    ) AS has_click,
                    EXISTS (
                        SELECT 1 FROM ltc.meeting m
                        WHERE m.primary_contact_id=ct.contact_id AND m.processing_status='completed'
                    ) AS has_meeting,
                    GREATEST(
                        ct.last_contacted_at,
                        (SELECT max(COALESCE(em.received_at, em.sent_at, em.created_at)) FROM ltc.email_message em WHERE em.contact_id=ct.contact_id),
                        (SELECT max(COALESCE(m.meeting_started_at, m.created_at)) FROM ltc.meeting m WHERE m.primary_contact_id=ct.contact_id)
                    ) AS computed_last_engagement_at
                FROM ltc.contact ct
                LEFT JOIN LATERAL (
                    SELECT
                        cc.candidate_contact_id,
                        cc.email,
                        cc.normalized_email,
                        cc.email_status,
                        cc.last_seen_at
                    FROM ltc.candidate_contact cc
                    JOIN ltc.company company_source
                        ON company_source.company_id = ct.company_id
                    WHERE
                        cc.candidate_contact_id = ct.source_candidate_contact_id
                        OR (
                            company_source.origin_candidate_id IS NOT NULL
                            AND cc.candidate_id = company_source.origin_candidate_id
                            AND (
                                (ct.normalized_email IS NOT NULL AND cc.normalized_email = ct.normalized_email)
                                OR cc.normalized_name = ct.normalized_name
                            )
                        )
                    ORDER BY
                        (cc.candidate_contact_id = ct.source_candidate_contact_id) DESC,
                        (company_source.origin_candidate_id IS NOT NULL
                            AND cc.candidate_id = company_source.origin_candidate_id
                            AND cc.normalized_email = ct.normalized_email) DESC,
                        (company_source.origin_candidate_id IS NOT NULL
                            AND cc.candidate_id = company_source.origin_candidate_id
                            AND cc.normalized_name = ct.normalized_name) DESC,
                        cc.last_seen_at DESC
                    LIMIT 1
                ) cc ON TRUE
                LEFT JOIN ltc.company_contact_roster r
                    ON r.company_id=ct.company_id AND r.contact_id=ct.contact_id
                WHERE ct.company_id=%s AND ct.status <> 'archived'
                ORDER BY r.position NULLS LAST, r.priority_score DESC NULLS LAST, ct.created_at DESC
                """,
                (str(company_id),),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            self._backfill_contact_email_fields(connection, row)
            row["last_engagement_at"] = row.get("computed_last_engagement_at") or row.get("last_engagement_at")
            if not row.get("ranking_version"):
                scored = score_contact(row)
                row.update({
                    "role_group": scored.role_group,
                    "priority_score": scored.score,
                    "score_breakdown": scored.breakdown,
                    "recommendation_reason": "；".join(scored.reasons),
                    "blocked_reason": scored.blocked_reason,
                    "outreach_status": _outreach_status(row),
                })
            else:
                row["blocked_reason"] = score_contact(row).blocked_reason
        return rows

    @staticmethod
    def _backfill_contact_email_fields(connection: Any, row: dict[str, Any]) -> None:
        source_primary_email = _text(row.get("source_primary_email"))
        if not source_primary_email:
            return

        source_normalized_email = _text(row.get("source_normalized_email")) or source_primary_email.casefold()
        source_email_status = _text(row.get("source_email_status")).casefold()
        source_last_seen_at = row.get("source_last_seen_at")

        primary_email = _text(row.get("primary_email"))
        normalized_email = _text(row.get("normalized_email"))
        email_status = _text(row.get("email_status")).casefold()

        needs_update = False
        if not primary_email:
            row["primary_email"] = source_primary_email
            needs_update = True
        if not normalized_email:
            row["normalized_email"] = source_normalized_email
            needs_update = True
        if not email_status or email_status == "unknown":
            row["email_status"] = source_email_status or "valid"
            needs_update = True
        if not row.get("last_verified_at") and source_last_seen_at:
            row["last_verified_at"] = source_last_seen_at
            needs_update = True

        if not needs_update:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ltc.contact
                   SET primary_email = COALESCE(primary_email, %s),
                       normalized_email = COALESCE(normalized_email, %s),
                       email_status = CASE
                           WHEN email_status IS NULL OR email_status = 'unknown'
                               THEN COALESCE(%s, 'valid')
                           ELSE email_status
                       END,
                       last_verified_at = COALESCE(last_verified_at, %s),
                       updated_at = clock_timestamp(),
                       version = version + 1
                 WHERE contact_id = %s
                   AND company_id = %s
                """,
                (
                    row.get("primary_email"),
                    row.get("normalized_email"),
                    row.get("email_status"),
                    row.get("last_verified_at"),
                    str(row.get("contact_id")),
                    str(row.get("company_id")),
                ),
            )

    @staticmethod
    def _score_contact_for_company(company: dict[str, Any], contact: dict[str, Any]) -> ScoredContact:
        return score_contact(
            contact,
            employee_count=company.get("employee_count"),
            scene_text=" ".join(
                _text(value)
                for value in (
                    company.get("company_intro"),
                    company.get("integration"),
                    company.get("esim_scenario"),
                )
            ),
        )

    def _needs_refresh(self, company: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
        for row in rows:
            if not row.get("ranking_version"):
                return True
            if row.get("ranking_version") != RANKING_VERSION:
                return True
            current = self._score_contact_for_company(company, row)
            if row.get("roster_status") == "active" and not current.eligible:
                return True
            stored_score = float(row.get("priority_score") or 0)
            if round(current.score, 2) != round(stored_score, 2):
                return True
            if current.breakdown != row.get("score_breakdown"):
                return True
        return False

    @staticmethod
    def _public_row(row: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "contact_id", "company_id", "full_name", "title", "title_normalized",
            "department", "relationship_role", "primary_email", "source_primary_email", "email_status",
            "email_score", "phone", "linkedin_url", "source", "employment_status",
            "legal_basis_status", "last_verified_at", "roster_status", "position",
            "role_group", "priority_score", "score_breakdown", "recommendation_reason",
            "ranking_version", "is_pinned", "engagement_locked", "outreach_status",
            "last_engagement_at", "override_reason", "roster_version", "version", "blocked_reason",
        )
        return {key: row.get(key) for key in keys}

    @staticmethod
    def _require_company(connection: Any, company_id: UUID, lock: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE OF c" if lock else ""
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT c.*, cp.integration, cp.esim_scenario
                FROM ltc.company c
                LEFT JOIN ltc.customer_profile cp ON cp.company_id=c.company_id
                WHERE c.company_id=%s AND c.archived_at IS NULL
                """ + suffix,
                (str(company_id),),
            )
            row = cursor.fetchone()
        if row is None:
            raise ContactRosterError("COMPANY_NOT_FOUND", "客户不存在。")
        return dict(row)

    @staticmethod
    def _locked_roster(connection: Any, company_id: UUID) -> list[dict[str, Any]]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT r.*, ct.primary_email, ct.email_status, ct.employment_status, ct.legal_basis_status,
                       CASE
                           WHEN ct.status <> 'active' THEN '联系人非活跃状态'
                           WHEN ct.employment_status='departed' THEN '联系人已离职'
                           WHEN ct.legal_basis_status='blocked' THEN '缺少合法触达依据'
                           WHEN ct.email_status IN ('invalid','bounced','opted_out') THEN '邮箱退信、退订或无效'
                           WHEN EXISTS (
                               SELECT 1 FROM ltc.email_suppression es
                               WHERE es.normalized_email=ct.normalized_email AND es.status='active'
                           ) THEN '邮箱已进入全局抑制名单'
                       END AS blocked_reason
                FROM ltc.company_contact_roster r
                JOIN ltc.contact ct ON ct.contact_id=r.contact_id AND ct.company_id=r.company_id
                WHERE r.company_id=%s
                ORDER BY r.position NULLS LAST, r.priority_score DESC
                FOR UPDATE OF r
                """,
                (str(company_id),),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _audit(
        connection: Any,
        *,
        actor_user_id: UUID | None,
        company_id: UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO ltc.audit_log (
                actor_user_id, action, resource_type, resource_id,
                before_data, after_data, metadata
            )
            VALUES (%s,%s,'contact_roster',%s,%s::jsonb,%s::jsonb,%s::jsonb)
            """,
            (
                str(actor_user_id) if actor_user_id else None,
                action,
                str(company_id),
                json.dumps(before, default=str, ensure_ascii=False) if before is not None else None,
                json.dumps(after, default=str, ensure_ascii=False) if after is not None else None,
                json.dumps(metadata, default=str, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _roster_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "active": [
                {"contact_id": str(row["contact_id"]), "position": row.get("position")}
                for row in rows if row.get("roster_status") == "active"
            ],
            "total": len(rows),
        }

    @staticmethod
    def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "active": [
                {"contact_id": str(row["contact_id"]), "position": row.get("position")}
                for row in payload["active"]
            ],
            "total": payload["total"],
        }


def _has_usable_email(contact: dict[str, Any]) -> bool:
    return bool(_text(contact.get("primary_email")))

def _outreach_status(contact: dict[str, Any]) -> str:
    email_status = _text(contact.get("email_status")).casefold()
    if email_status == "bounced":
        return "bounced"
    if email_status == "opted_out" or contact.get("is_suppressed"):
        return "opted_out"
    if contact.get("has_reply"):
        return "replied"
    if contact.get("has_meeting"):
        return "meeting"
    if contact.get("last_contacted_at") or contact.get("last_engagement_at"):
        return "sent"
    return _text(contact.get("outreach_status") or "not_contacted")


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()
