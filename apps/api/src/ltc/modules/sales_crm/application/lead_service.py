"""Sales CRM lead commands and queries."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
from typing import Any, Iterator, Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.domain.models import CurrentActor
from ltc.platform.db import PostgresDatabase
from ltc.platform.pagination import stable_advisory_key


_logger = logging.getLogger(__name__)


class AnalysisTriggerPort(Protocol):
    def request_analysis(
        self,
        company_id: UUID,
        *,
        trigger_type: str,
    ) -> Any: ...


class SalesLeadClaimConflict(AuthenticationError):
    def __init__(
        self,
        owner_user_id: UUID | None,
        owner_display_name: str | None,
    ) -> None:
        super().__init__("SALES_LEAD_NOT_CLAIMABLE")
        self.owner_user_id = owner_user_id
        self.owner_display_name = owner_display_name


@dataclass(frozen=True)
class AssignLeadCommand:
    lead_id: UUID
    expected_version: int
    assignee_user_id: UUID
    assignment_type: str
    reason_code: str
    reason_text: str | None
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class ReleaseLeadCommand:
    lead_id: UUID
    expected_version: int
    reason_code: str
    reason_text: str | None
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class TransferLeadCommand:
    lead_id: UUID
    expected_version: int
    to_assignee_user_id: UUID
    reason_code: str
    reason_text: str | None
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class LeadCommandResult:
    lead_id: UUID
    allocation_status: str
    assignment_id: UUID | None
    previous_assignment_id: UUID | None
    owner_user_id: UUID | None
    from_owner_user_id: UUID | None
    assigned_at: datetime | None
    sla_due_at: datetime | None
    pipeline_stage: str
    version: int

    def to_dict(self) -> dict[str, object]:
        return {
            "lead_id": str(self.lead_id),
            "allocation_status": self.allocation_status,
            "assignment_id": str(self.assignment_id) if self.assignment_id else None,
            "previous_assignment_id": str(self.previous_assignment_id) if self.previous_assignment_id else None,
            "owner_user_id": str(self.owner_user_id) if self.owner_user_id else None,
            "from_owner_user_id": str(self.from_owner_user_id) if self.from_owner_user_id else None,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "sla_due_at": self.sla_due_at.isoformat() if self.sla_due_at else None,
            "pipeline_stage": self.pipeline_stage,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "LeadCommandResult":
        def parse_uuid(raw: object) -> UUID | None:
            return UUID(str(raw)) if raw else None

        def parse_time(raw: object) -> datetime | None:
            return datetime.fromisoformat(str(raw)) if raw else None

        return cls(
            lead_id=UUID(str(value["lead_id"])),
            allocation_status=str(value["allocation_status"]),
            assignment_id=parse_uuid(value.get("assignment_id")),
            previous_assignment_id=parse_uuid(value.get("previous_assignment_id")),
            owner_user_id=parse_uuid(value.get("owner_user_id")),
            from_owner_user_id=parse_uuid(value.get("from_owner_user_id")),
            assigned_at=parse_time(value.get("assigned_at")),
            sla_due_at=parse_time(value.get("sla_due_at")),
            pipeline_stage=str(value["pipeline_stage"]),
            version=int(value["version"]),
        )


def _hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _require_strategic(actor: CurrentActor) -> None:
    if actor.account_type != "strategic":
        raise AuthenticationError("FORBIDDEN_STRATEGIC_REQUIRED")


def _require_sales(actor: CurrentActor) -> None:
    if actor.account_type != "sales":
        raise AuthenticationError("FORBIDDEN_SALES_REQUIRED")
    if actor.sales_tier is None or actor.region_code is None:
        raise AuthenticationError("FORBIDDEN_SALES_REQUIRED")


def _add_business_days(value: datetime, days: int) -> datetime:
    local = value.astimezone(ZoneInfo("Asia/Shanghai"))
    remaining = days
    while remaining:
        local += timedelta(days=1)
        if local.weekday() < 5:
            remaining -= 1
    return local.astimezone(timezone.utc)


def _sla_due(now: datetime, lead: dict[str, object] | None = None) -> datetime:
    """Apply the v3.6 first-touch SLA matrix without changing old Lead snapshots."""
    if lead and lead.get("icp_grade") in {"A", "B"}:
        scale = lead.get("scale_tier")
        if lead.get("icp_grade") == "A" and scale == "large":
            return now + timedelta(hours=24)
        if scale in {"large", "medium"}:
            return now + timedelta(hours=48)
    return _add_business_days(now, 3)


class SalesLeadService:
    def __init__(
        self,
        database: PostgresDatabase,
        analysis_trigger: AnalysisTriggerPort | None = None,
    ) -> None:
        self._database = database
        self._analysis_trigger = analysis_trigger

    def set_analysis_trigger(self, analysis_trigger: AnalysisTriggerPort | None) -> None:
        self._analysis_trigger = analysis_trigger

    def _trigger_claim_analysis(self, company_id: UUID) -> None:
        if self._analysis_trigger is None:
            return
        try:
            self._analysis_trigger.request_analysis(
                company_id,
                trigger_type="assignment",
            )
        except Exception:
            _logger.exception(
                "Lead claim succeeded but customer analysis could not be queued company_id=%s",
                company_id,
            )

    @contextmanager
    def _transaction(self, pinned_connection: object | None = None) -> Iterator[object]:
        if pinned_connection is None:
            with self._database.transaction() as connection:
                yield connection
        else:
            with pinned_connection.transaction():
                yield pinned_connection

    def list_pool_for_actor(self, actor: CurrentActor) -> list[dict[str, object]]:
        if actor.account_type != "sales" or actor.sales_tier is None or actor.region_code is None:
            raise AuthenticationError("SALES_POOL_REQUIRED")
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT sl.lead_id, sl.company_id, c.company_name,
                           c.website, c.company_intro, c.industry_code, c.country_code, c.city,
                           ia.total_score AS icp_score, ia.grade AS icp_grade,
                           sl.required_sales_tier, sl.pool_region_code,
                           sl.allocation_status, sl.pipeline_stage,
                           sl.sla_due_at, sl.current_owner_user_id,
                           sl.last_activity_at, sl.updated_at, sl.version
                    FROM ltc.sales_lead sl
                    JOIN ltc.company c ON c.company_id = sl.company_id
                    LEFT JOIN ltc.lead_icp_assessment ia
                      ON ia.icp_assessment_id = sl.adopted_icp_assessment_id
                    WHERE sl.allocation_status='claimable'
                      AND sl.data_completion_pool IS DISTINCT FROM 'region_unknown'
                      AND sl.pool_region_code=%s
                      AND sl.required_sales_tier=%s
                      AND NOT (sl.data_completion_pool = 'scale_unknown' AND %s != 'A')
                      AND (
                        SELECT COUNT(*) FROM ltc.lead_assignment la
                        WHERE la.assignee_user_id=%s AND la.status='active'
                      ) < COALESCE((SELECT capacity_limit FROM ltc.user_account WHERE user_id=%s), 0)
                    ORDER BY sl.created_at, sl.lead_id
                    """,
                    (actor.region_code, actor.sales_tier, actor.sales_tier, actor.user_id, actor.user_id),
                )
                return list(cursor.fetchall())

    def list_handover(self, actor: CurrentActor) -> list[dict[str, object]]:
        _require_strategic(actor)
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT sl.lead_id, sl.company_id, c.company_name,
                           ua.user_id AS departed_user_id, ua.display_name AS departed_user_name,
                           ua.sales_tier, ua.region_code,
                           sl.required_sales_tier,
                           CASE sl.required_sales_tier
                             WHEN 'MA' THEN 'A'
                             WHEN 'SA' THEN 'B'
                             WHEN 'A' THEN 'C'
                           END AS customer_grade,
                           sl.pool_region_code AS customer_region_code,
                           c.country_code, country.country_name,
                           sl.pipeline_stage,
                           sl.allocation_status, sl.version
                    FROM ltc.lead_assignment la
                    JOIN ltc.sales_lead sl ON sl.lead_id = la.lead_id
                    JOIN ltc.company c ON c.company_id = sl.company_id
                    JOIN ltc.user_account ua ON ua.user_id = la.assignee_user_id
                    LEFT JOIN ltc.ref_region_country country ON country.country_code = c.country_code
                    WHERE la.status='active' AND la.handover_pending=true
                      AND ua.status='departed' AND sl.allocation_status='claimed'
                      AND sl.current_owner_user_id=ua.user_id
                    ORDER BY ua.display_name, sl.created_at, sl.lead_id
                    """
                )
                return list(cursor.fetchall())

    def return_handover_to_pool(self, actor: CurrentActor, departed_user_id: UUID, idempotency_key: str, request_id: UUID) -> dict[str, object]:
        _require_strategic(actor)
        now = datetime.now(timezone.utc)
        payload = {"departed_user_id": str(departed_user_id)}
        request_hash = _hash(payload)
        with self._database.transaction() as connection:
            scope = "return_departed_sales_leads"
            existing = self._read_json_idempotency(connection, scope, actor, idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, scope, idempotency_key, request_hash, now)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT user_id, display_name, status FROM ltc.user_account WHERE user_id=%s FOR UPDATE",
                    (departed_user_id,),
                )
                user = cursor.fetchone()
            if not user:
                raise AuthenticationError("USER_NOT_FOUND")
            if user["status"] != "departed":
                raise AuthenticationError("USER_NOT_DEPARTED")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT la.assignment_id, la.lead_id, sl.company_id, c.company_name,
                           sl.pipeline_stage, sl.version, sl.current_owner_user_id
                    FROM ltc.lead_assignment la
                    JOIN ltc.sales_lead sl ON sl.lead_id=la.lead_id
                    JOIN ltc.company c ON c.company_id=sl.company_id
                    WHERE la.assignee_user_id=%s AND la.status='active' AND la.handover_pending=true
                      AND sl.pipeline_stage='new'
                    ORDER BY la.lead_id
                    FOR UPDATE OF la, sl
                    """,
                    (departed_user_id,),
                )
                assignments = list(cursor.fetchall())
            returned: list[dict[str, object]] = []
            for row in assignments:
                if row["current_owner_user_id"] != departed_user_id:
                    raise AuthenticationError("VERSION_CONFLICT")
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        """
                        UPDATE ltc.lead_assignment
                        SET status='released', handover_pending=false,
                            reason_code='handover_return_to_pool', ended_at=%s, version=version+1
                        WHERE assignment_id=%s AND status='active' AND handover_pending=true
                        """,
                        (now, row["assignment_id"]),
                    )
                    new_version = int(row["version"]) + 1
                    cursor.execute(
                        """
                        UPDATE ltc.sales_lead
                        SET allocation_status='claimable', current_owner_user_id=NULL,
                            current_assignment_started_at=NULL, sla_due_at=NULL,
                            released_reason='handover_return_to_pool', version=%s, updated_at=%s
                        WHERE lead_id=%s AND allocation_status='claimed'
                        """,
                        (new_version, now, row["lead_id"]),
                    )
                    cursor.execute(
                        """
                        INSERT INTO ltc.lead_stage_transition
                        (company_id, lead_id, assignment_id, event_type,
                         from_allocation_status, to_allocation_status,
                         from_pipeline_stage, to_pipeline_stage,
                         from_owner_user_id, to_owner_user_id, actor_user_id,
                         source_type, reason_code, reason_text, metadata, occurred_at)
                        VALUES (%s,%s,%s,'release','claimed','claimable',%s,%s,%s,NULL,%s,
                                'user','handover_return_to_pool','Returned by management',%s::jsonb,%s)
                        """,
                        (row["company_id"], row["lead_id"], row["assignment_id"],
                         row["pipeline_stage"], row["pipeline_stage"], departed_user_id,
                         actor.user_id, json.dumps({"request_id": str(request_id), "handover": True}), now),
                    )
                    cursor.execute(
                        """
                        INSERT INTO ltc.outbox_event
                        (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                        VALUES ('crm.lead_released.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s)
                        """,
                        (row["lead_id"], new_version, json.dumps({
                            "company_id": str(row["company_id"]), "lead_id": str(row["lead_id"]),
                            "assignment_id": str(row["assignment_id"]), "released_by": str(actor.user_id),
                            "reason_code": "handover_return_to_pool", "released_at": now.isoformat(),
                        }), request_id),
                    )
                finally:
                    cursor.close()
                returned.append({"lead_id": str(row["lead_id"]), "company_id": str(row["company_id"]), "company_name": row["company_name"], "version": new_version})
            result = {"departed_user_id": str(departed_user_id), "returned_count": len(returned), "leads": returned}
            self._complete_json_idempotency(connection, actor, scope, idempotency_key, result)
            return result

    def list_mine(self, actor: CurrentActor, pipeline_stage: str | None, allocation_status: str | None, cursor: tuple[datetime, UUID] | None, limit: int) -> list[dict[str, object]]:
        if actor.account_type != "sales":
            raise AuthenticationError("FORBIDDEN_SALES_REQUIRED")
        predicates = [
            "sl.current_owner_user_id=%s",
            "btrim(c.company_name) <> ''",
            "lower(btrim(c.company_name)) NOT IN ('待确认','待补齐','未知','unknown','n/a','-')",
        ]
        params: list[object] = [actor.user_id]
        if pipeline_stage:
            predicates.append("sl.pipeline_stage=%s")
            params.append(pipeline_stage)
        if allocation_status:
            predicates.append("sl.allocation_status=%s")
            params.append(allocation_status)
        if cursor:
            predicates.append("(sl.updated_at < %s OR (sl.updated_at = %s AND sl.lead_id > %s))")
            params.extend((cursor[0], cursor[0], cursor[1]))
        params.append(limit)
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"""
                    SELECT sl.lead_id, sl.company_id, c.company_name,
                           c.website, c.company_intro, c.industry_code, c.country_code, c.city,
                           ia.total_score AS icp_score, ia.grade AS icp_grade,
                           sl.required_sales_tier, sl.pool_region_code,
                           sl.allocation_status, sl.pipeline_stage,
                           sl.sla_due_at, sl.current_owner_user_id,
                           owner.display_name AS owner_name, owner.username AS owner_username,
                           adopted_icp.total_score AS icp_score,
                           adopted_icp.grade AS icp_grade,
                           CASE adopted_scale.effective_tier
                             WHEN 'large' THEN 'A'
                             WHEN 'medium' THEN 'B'
                             WHEN 'small' THEN 'C'
                             ELSE NULL
                           END AS customer_size_grade,
                           sl.last_activity_at, sl.updated_at, sl.version
                    FROM ltc.sales_lead sl
                    JOIN ltc.company c ON c.company_id=sl.company_id
                    LEFT JOIN ltc.lead_icp_assessment ia
                      ON ia.icp_assessment_id = sl.adopted_icp_assessment_id
                    LEFT JOIN ltc.user_account owner ON owner.user_id=sl.current_owner_user_id
                    LEFT JOIN ltc.lead_icp_assessment adopted_icp
                      ON adopted_icp.icp_assessment_id=sl.adopted_icp_assessment_id
                    LEFT JOIN ltc.customer_scale_assessment adopted_scale
                      ON adopted_scale.scale_assessment_id=sl.adopted_scale_assessment_id
                    WHERE {' AND '.join(predicates)}
                    ORDER BY sl.updated_at DESC, sl.lead_id
                    LIMIT %s
                    """,
                    params,
                )
                return list(cursor.fetchall())

    def list_all(self, actor: CurrentActor, allocation_status: str | None, owner_user_id: str | None, required_sales_tier: str | None, pool_region_code: str | None, cursor: tuple[datetime, UUID] | None, limit: int) -> list[dict[str, object]]:
        _require_strategic(actor)
        predicates = [
            "btrim(c.company_name) <> ''",
            "lower(btrim(c.company_name)) NOT IN ('待确认','待补齐','未知','unknown','n/a','-')",
        ]
        params: list[object] = []
        if allocation_status:
            predicates.append("sl.allocation_status=%s")
            params.append(allocation_status)
        if required_sales_tier:
            predicates.append("sl.required_sales_tier=%s")
            params.append(required_sales_tier)
        if pool_region_code:
            predicates.append("sl.pool_region_code=%s")
            params.append(pool_region_code)
        if owner_user_id == "unassigned":
            predicates.append("sl.current_owner_user_id IS NULL")
        elif owner_user_id:
            predicates.append("sl.current_owner_user_id=%s")
            params.append(owner_user_id)
        if cursor:
            predicates.append("(sl.updated_at < %s OR (sl.updated_at = %s AND sl.lead_id > %s))")
            params.extend((cursor[0], cursor[0], cursor[1]))
        params.append(limit)
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"""
                    SELECT sl.lead_id, sl.company_id, c.company_name,
                           c.website, c.company_intro, c.industry_code, c.country_code, c.city,
                           ia.total_score AS icp_score, ia.grade AS icp_grade,
                           sl.required_sales_tier, sl.pool_region_code,
                           sl.allocation_status, sl.pipeline_stage,
                           sl.sla_due_at, sl.current_owner_user_id,
                           owner.display_name AS owner_name, owner.username AS owner_username,
                           adopted_icp.total_score AS icp_score,
                           adopted_icp.grade AS icp_grade,
                           CASE adopted_scale.effective_tier
                             WHEN 'large' THEN 'A'
                             WHEN 'medium' THEN 'B'
                             WHEN 'small' THEN 'C'
                             ELSE NULL
                           END AS customer_size_grade,
                           sl.last_activity_at, sl.updated_at, sl.version
                    FROM ltc.sales_lead sl
                    JOIN ltc.company c ON c.company_id=sl.company_id
                    LEFT JOIN ltc.lead_icp_assessment ia
                      ON ia.icp_assessment_id=sl.adopted_icp_assessment_id
                    LEFT JOIN ltc.user_account owner ON owner.user_id=sl.current_owner_user_id
                    LEFT JOIN ltc.lead_icp_assessment adopted_icp
                      ON adopted_icp.icp_assessment_id=sl.adopted_icp_assessment_id
                    LEFT JOIN ltc.customer_scale_assessment adopted_scale
                      ON adopted_scale.scale_assessment_id=sl.adopted_scale_assessment_id
                    WHERE {' AND '.join(predicates)}
                    ORDER BY sl.updated_at DESC, sl.lead_id
                    LIMIT %s
                    """,
                    params,
                )
                return list(cursor.fetchall())

    def get_detail(self, actor: CurrentActor, lead_id: UUID) -> dict[str, object]:
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT sl.lead_id, sl.company_id, c.company_name,
                           sl.required_sales_tier, sl.pool_region_code,
                           sl.allocation_status, sl.pipeline_stage,
                           sl.sla_due_at, sl.last_activity_at,
                           sl.current_owner_user_id, sl.current_assignment_started_at,
                           sl.first_touch_at, sl.version,
                           la.assignment_id, la.assignee_user_id, la.assigned_at,
                           la.assignment_type, la.status AS assignment_status
                    FROM ltc.sales_lead sl
                    JOIN ltc.company c ON c.company_id=sl.company_id
                    LEFT JOIN ltc.lead_assignment la
                      ON la.lead_id=sl.lead_id AND la.status='active'
                    WHERE sl.lead_id=%s
                    """,
                    (lead_id,),
                )
                row = cursor.fetchone()
        if not row:
            raise AuthenticationError("SALES_LEAD_NOT_FOUND")
        if actor.account_type == "sales":
            is_owner = row["current_owner_user_id"] == actor.user_id
            is_visible_pool = (
                row["allocation_status"] == "claimable"
                and row["pool_region_code"] == actor.region_code
                and row["required_sales_tier"] == actor.sales_tier
            )
            if not is_owner and not is_visible_pool:
                raise AuthenticationError("FORBIDDEN_LEAD_ACCESS")
        return row

    def get_adopted_icp(self, actor: CurrentActor, lead_id: UUID) -> dict[str, object]:
        self.get_detail(actor, lead_id)
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT ia.icp_assessment_id, ia.scene_code, ia.rule_version,
                              ia.d1_score, ia.d2_score, ia.d3_score, ia.d4_score,
                              ia.total_score, ia.grade, ia.hard_gate_passed,
                              ia.score_breakdown, ia.explanations, ia.scored_at
                       FROM ltc.sales_lead sl
                       JOIN ltc.lead_icp_assessment ia
                         ON ia.icp_assessment_id=sl.adopted_icp_assessment_id
                      WHERE sl.lead_id=%s""",
                    (lead_id,),
                )
                row = cursor.fetchone()
        if not row:
            raise AuthenticationError("SALES_LEAD_NOT_FOUND")
        return row

    def get_adopted_scale(self, actor: CurrentActor, lead_id: UUID) -> dict[str, object]:
        self.get_detail(actor, lead_id)
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT sa.scale_assessment_id, sa.rule_version,
                              sa.d1_scale_score, sa.d2_commercial_score, sa.d3_coverage_score,
                              sa.total_score, sa.computed_tier, sa.effective_tier,
                              sa.required_sales_tier, sa.decision_source, sa.assessment_payload,
                              sa.assessed_at
                       FROM ltc.sales_lead sl
                       JOIN ltc.customer_scale_assessment sa
                         ON sa.scale_assessment_id=sl.adopted_scale_assessment_id
                      WHERE sl.lead_id=%s""",
                    (lead_id,),
                )
                row = cursor.fetchone()
        if not row:
            raise AuthenticationError("SALES_LEAD_NOT_FOUND")
        return row

    @staticmethod
    def _can_operate(actor: CurrentActor, lead: dict[str, object]) -> None:
        if actor.account_type == "strategic":
            return
        if actor.account_type != "sales" or lead["current_owner_user_id"] != actor.user_id:
            raise AuthenticationError("FORBIDDEN_LEAD_OWNER_REQUIRED")

    @staticmethod
    def _stage_rank(stage: str) -> int:
        return {"new": 0, "contacted": 1, "engaged": 2, "meeting": 3, "proposal": 4, "won": 5, "lost": 5, "dormant": 0}.get(stage, -1)

    def first_touch(
        self,
        actor: CurrentActor,
        lead_id: UUID,
        expected_version: int,
        contact_id: UUID,
        channel: str,
        occurred_at: datetime,
        note: str | None,
        idempotency_key: str,
        request_id: UUID,
    ) -> dict[str, object]:
        if actor.account_type not in {"sales", "strategic"}:
            raise AuthenticationError("FORBIDDEN")
        scope = "first_touch_sales_lead"
        request_hash = _hash({"lead_id": lead_id, "expected_version": expected_version, "contact_id": contact_id, "channel": channel, "occurred_at": occurred_at, "note": note})
        now = datetime.now(timezone.utc)
        with self._database.transaction() as connection:
            existing = self._read_json_idempotency(connection, scope, actor, idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, scope, idempotency_key, request_hash, now)
            lead = self._lock_lead(connection, lead_id)
            if int(lead["version"]) != expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            self._can_operate(actor, lead)
            if lead["allocation_status"] != "claimed":
                raise AuthenticationError("SALES_LEAD_NOT_CLAIMED")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT contact_id FROM ltc.contact WHERE contact_id=%s AND company_id=%s AND status='active'", (contact_id, lead["company_id"]))
                if cursor.fetchone() is None:
                    raise AuthenticationError("CONTACT_NOT_FOUND")
                cursor.execute("SELECT assignment_id FROM ltc.lead_assignment WHERE lead_id=%s AND status='active' FOR UPDATE", (lead_id,))
                assignment = cursor.fetchone()
            if assignment is None:
                raise AuthenticationError("ASSIGNMENT_NOT_FOUND")
            old_stage = str(lead["pipeline_stage"])
            target_stage = old_stage if self._stage_rank(old_stage) >= self._stage_rank("contacted") else "contacted"
            new_version = int(lead["version"]) + 1
            connection.execute(
                """UPDATE ltc.sales_lead SET first_touch_at=COALESCE(first_touch_at,%s),
                   last_activity_at=%s, sla_due_at=NULL, pipeline_stage=%s,
                   version=%s, updated_at=%s WHERE lead_id=%s""",
                (occurred_at, occurred_at, target_stage, new_version, now, lead_id),
            )
            connection.execute(
                """UPDATE ltc.lead_assignment SET first_touch_at=COALESCE(first_touch_at,%s), version=version+1
                   WHERE assignment_id=%s""",
                (occurred_at, assignment["assignment_id"]),
            )
            transition = connection.execute(
                """INSERT INTO ltc.lead_stage_transition
                   (company_id, lead_id, assignment_id, event_type,
                    from_allocation_status, to_allocation_status, from_pipeline_stage,
                    to_pipeline_stage, from_owner_user_id, to_owner_user_id,
                    actor_user_id, source_type, reason_code, reason_text, metadata, occurred_at)
                   VALUES (%s,%s,%s,'first_touch','claimed','claimed',%s,%s,%s,%s,%s,'user','first_touch',%s,%s::jsonb,%s)
                   RETURNING transition_id""",
                (lead["company_id"], lead_id, assignment["assignment_id"], old_stage, target_stage,
                 lead["current_owner_user_id"], lead["current_owner_user_id"], actor.user_id,
                 note, json.dumps({"channel": channel, "contact_id": str(contact_id), "request_id": str(request_id)}), occurred_at),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO ltc.outbox_event
                   (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                   VALUES ('crm.pipeline_changed.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s)""",
                (lead_id, new_version, json.dumps({"company_id": str(lead["company_id"]), "lead_id": str(lead_id), "from_stage": old_stage, "to_stage": target_stage, "source_type": "user", "source_resource_id": str(contact_id), "occurred_at": occurred_at.isoformat()}), request_id),
            )
            result = {"lead_id": str(lead_id), "transition_id": str(transition), "contact_id": str(contact_id), "first_touch_at": occurred_at.isoformat(), "pipeline_stage": target_stage, "version": new_version}
            self._complete_json_idempotency(connection, actor, scope, idempotency_key, result)
            return result

    def change_stage(
        self,
        actor: CurrentActor,
        lead_id: UUID,
        expected_version: int,
        target_stage: str,
        reason_code: str,
        reason_text: str | None,
        closed_at: datetime | None,
        idempotency_key: str,
        request_id: UUID,
    ) -> dict[str, object]:
        if actor.account_type not in {"sales", "strategic"}:
            raise AuthenticationError("FORBIDDEN")
        valid_stages = {"new", "contacted", "engaged", "meeting", "proposal", "won", "lost", "dormant"}
        if target_stage not in valid_stages:
            raise AuthenticationError("INVALID_PIPELINE_STAGE")
        scope = "change_pipeline_stage"
        request_hash = _hash({"lead_id": lead_id, "expected_version": expected_version, "target_stage": target_stage, "reason_code": reason_code, "reason_text": reason_text, "closed_at": closed_at})
        now = datetime.now(timezone.utc)
        with self._database.transaction() as connection:
            existing = self._read_json_idempotency(connection, scope, actor, idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, scope, idempotency_key, request_hash, now)
            lead = self._lock_lead(connection, lead_id)
            if int(lead["version"]) != expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            self._can_operate(actor, lead)
            if lead["allocation_status"] != "claimed":
                raise AuthenticationError("SALES_LEAD_NOT_CLAIMED")
            old_stage = str(lead["pipeline_stage"])
            if target_stage not in {old_stage, "dormant"} and target_stage not in {"won", "lost"} and self._stage_rank(target_stage) < self._stage_rank(old_stage):
                raise AuthenticationError("PIPELINE_STAGE_REGRESSION")
            if target_stage in {"won", "lost"} and not reason_code:
                raise AuthenticationError("PIPELINE_REASON_REQUIRED")
            if target_stage in {"won", "lost"} and old_stage in {"won", "lost"} and target_stage != old_stage:
                raise AuthenticationError("PIPELINE_TERMINAL")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT assignment_id FROM ltc.lead_assignment WHERE lead_id=%s AND status='active' FOR UPDATE", (lead_id,))
                assignment = cursor.fetchone()
            if assignment is None:
                raise AuthenticationError("ASSIGNMENT_NOT_FOUND")
            final_closed_at = closed_at or (now if target_stage in {"won", "lost"} else None)
            new_version = int(lead["version"]) + 1
            connection.execute(
                """UPDATE ltc.sales_lead SET pipeline_stage=%s,
                   won_reason_code=CASE WHEN %s='won' THEN %s ELSE won_reason_code END,
                   lost_reason_code=CASE WHEN %s='lost' THEN %s ELSE lost_reason_code END,
                   closed_at=CASE WHEN %s IN ('won','lost') THEN %s ELSE closed_at END,
                   closed_note=COALESCE(%s, closed_note), version=%s, updated_at=%s
                   WHERE lead_id=%s""",
                (target_stage, target_stage, reason_code, target_stage, reason_code, target_stage, final_closed_at, reason_text, new_version, now, lead_id),
            )
            transition_type = "won" if target_stage == "won" else "lost" if target_stage == "lost" else "stage_change"
            transition = connection.execute(
                """INSERT INTO ltc.lead_stage_transition
                   (company_id, lead_id, assignment_id, event_type,
                    from_allocation_status, to_allocation_status, from_pipeline_stage,
                    to_pipeline_stage, from_owner_user_id, to_owner_user_id,
                    actor_user_id, source_type, reason_code, reason_text, metadata, occurred_at)
                   VALUES (%s,%s,%s,%s,'claimed','claimed',%s,%s,%s,%s,%s,'user',%s,%s,%s::jsonb,%s)
                   RETURNING transition_id""",
                (lead["company_id"], lead_id, assignment["assignment_id"], transition_type, old_stage, target_stage,
                 lead["current_owner_user_id"], lead["current_owner_user_id"], actor.user_id, reason_code, reason_text,
                 json.dumps({"request_id": str(request_id)}), now),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO ltc.outbox_event
                   (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                   VALUES ('crm.pipeline_changed.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s)""",
                (lead_id, new_version, json.dumps({"company_id": str(lead["company_id"]), "lead_id": str(lead_id), "from_stage": old_stage, "to_stage": target_stage, "source_type": "user", "occurred_at": now.isoformat()}), request_id),
            )
            result = {"lead_id": str(lead_id), "transition_id": str(transition), "from_stage": old_stage, "to_stage": target_stage, "occurred_at": now.isoformat(), "version": new_version}
            self._complete_json_idempotency(connection, actor, scope, idempotency_key, result)
            return result

    def _idempotent_result(self, connection: object, scope: str, actor: CurrentActor, key: str, request_hash: str) -> LeadCommandResult | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT request_hash, state, response_body FROM ltc.idempotency_record
                   WHERE scope=%s AND principal_type='user' AND principal_id=%s FOR UPDATE""",
                (scope, str(actor.user_id)),
            )
        # The caller performs the keyed lookup so this helper is intentionally unused.
        return None

    def _read_idempotency(self, connection: object, scope: str, actor: CurrentActor, key: str, request_hash: str) -> LeadCommandResult | None:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT request_hash, state, response_body FROM ltc.idempotency_record
                   WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s
                   FOR UPDATE""",
                (scope, str(actor.user_id), key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if row[0] != request_hash:
            raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
        if row[1] == "completed" and isinstance(row[2], dict):
            return LeadCommandResult.from_dict(row[2])
        raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")

    def _create_idempotency(self, connection: object, actor: CurrentActor, scope: str, key: str, request_hash: str, now: datetime) -> None:
        connection.execute(
            """INSERT INTO ltc.idempotency_record
               (scope, principal_type, principal_id, actor_user_id, idempotency_key, request_hash, state, expires_at)
               VALUES (%s,'user',%s,%s,%s,%s,'in_progress',%s)""",
            (scope, str(actor.user_id), actor.user_id, key, request_hash, now + timedelta(days=1)),
        )

    def _complete_idempotency(self, connection: object, actor: CurrentActor, scope: str, key: str, result: LeadCommandResult) -> None:
        connection.execute(
            """UPDATE ltc.idempotency_record SET state='completed', response_status=200,
               response_body=%s::jsonb, updated_at=clock_timestamp()
               WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s""",
            (json.dumps(result.to_dict()), scope, str(actor.user_id), key),
        )

    def _read_json_idempotency(self, connection: object, scope: str, actor: CurrentActor, key: str, request_hash: str) -> dict[str, object] | None:
        """Idempotency read for methods that return a plain dict (first_touch, change_stage)."""
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT request_hash, state, response_body FROM ltc.idempotency_record
                   WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s
                   FOR UPDATE""",
                (scope, str(actor.user_id), key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if row[0] != request_hash:
            raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
        if row[1] == "completed" and isinstance(row[2], dict):
            return dict(row[2])
        raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")

    def _complete_json_idempotency(self, connection: object, actor: CurrentActor, scope: str, key: str, result: dict[str, object]) -> None:
        """Idempotency completion for methods that return a plain dict (first_touch, change_stage)."""
        connection.execute(
            """UPDATE ltc.idempotency_record SET state='completed', response_status=200,
               response_body=%s::jsonb, updated_at=clock_timestamp()
               WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s""",
            (json.dumps(result), scope, str(actor.user_id), key),
        )

    def _lock_lead(self, connection: object, lead_id: UUID) -> dict[str, object]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT sl.lead_id, sl.company_id, sl.allocation_status, sl.pipeline_stage,
                          sl.current_owner_user_id, sl.current_assignment_started_at,
                          sl.first_touch_at, sl.sla_due_at, sl.required_sales_tier,
                          sl.pool_region_code, sl.data_completion_pool, sl.version,
                          ia.grade AS icp_grade, sa.effective_tier AS scale_tier
                   FROM ltc.sales_lead sl
                   JOIN ltc.lead_icp_assessment ia ON ia.icp_assessment_id=sl.adopted_icp_assessment_id
                   LEFT JOIN ltc.customer_scale_assessment sa ON sa.scale_assessment_id=sl.adopted_scale_assessment_id
                   WHERE sl.lead_id=%s FOR UPDATE OF sl""",
                (lead_id,),
            )
            row = cursor.fetchone()
        if not row:
            raise AuthenticationError("SALES_LEAD_NOT_FOUND")
        return row

    def _lock_user(self, connection: object, user_id: UUID) -> dict[str, object]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT user_id, account_type, status, sales_tier, region_code, capacity_limit, version
                   FROM ltc.user_account WHERE user_id=%s FOR UPDATE""",
                (user_id,),
            )
            row = cursor.fetchone()
        if not row:
            raise AuthenticationError("USER_NOT_FOUND")
        return row

    def _read_lead_owner(self, connection: object, lead_id: UUID) -> UUID | None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_owner_user_id FROM ltc.sales_lead WHERE lead_id=%s", (lead_id,))
            row = cursor.fetchone()
        return row[0] if row else None

    def _read_owner_display_name(self, connection: object, owner_user_id: UUID | None) -> str | None:
        if owner_user_id is None:
            return None
        with connection.cursor() as cursor:
            cursor.execute("SELECT display_name FROM ltc.user_account WHERE user_id=%s", (owner_user_id,))
            row = cursor.fetchone()
        return str(row[0]) if row and row[0] else None

    def _check_capacity(self, connection: object, user: dict[str, object]) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ltc.lead_assignment WHERE assignee_user_id=%s AND status='active'", (user["user_id"],))
            count = int(cursor.fetchone()[0])
        if user["capacity_limit"] is not None and count >= int(user["capacity_limit"]):
            raise AuthenticationError("SALES_CAPACITY_EXCEEDED")

    def _check_eligibility(self, lead: dict[str, object], user: dict[str, object]) -> None:
        if user["status"] != "active" or user["account_type"] != "sales":
            raise AuthenticationError("TARGET_NOT_ACTIVE_SALES")
        if lead["data_completion_pool"] == "region_unknown":
            raise AuthenticationError("SALES_REGION_MISMATCH")
        # PRD §2.3: scale_unknown leads require A-tier (any region)
        if lead["data_completion_pool"] == "scale_unknown" and user["sales_tier"] != "A":
            raise AuthenticationError("SCALE_UNKNOWN_REQUIRES_A_TIER")
        if lead["required_sales_tier"] != user["sales_tier"]:
            raise AuthenticationError("SALES_TIER_MISMATCH")
        if lead["pool_region_code"] != user["region_code"]:
            raise AuthenticationError("SALES_REGION_MISMATCH")

    def _insert_assignment(self, connection: object, lead: dict[str, object], user: dict[str, object], assigned_by: UUID | None, assignment_type: str, now: datetime, sla_due: datetime | None, previous_assignment_id: UUID | None = None) -> UUID:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ltc.lead_assignment
                   (lead_id, assignee_user_id, assigned_by, assignment_type, previous_assignment_id,
                    status, assigned_at, sla_due_at)
                   VALUES (%s,%s,%s,%s,%s,'active',%s,%s) RETURNING assignment_id""",
                (lead["lead_id"], user["user_id"], assigned_by, assignment_type, previous_assignment_id, now, sla_due),
            )
            return cursor.fetchone()[0]

    def _append_transition_and_event(self, connection: object, lead: dict[str, object], assignment_id: UUID | None, actor_id: UUID, event_type: str, from_status: str, to_status: str, from_owner: UUID | None, to_owner: UUID | None, reason_code: str | None, reason_text: str | None, version: int, request_id: UUID, now: datetime, event_payload: dict[str, object]) -> None:
        event_names = {
            "claim": "crm.lead_assigned.v1",
            "assign": "crm.lead_assigned.v1",
            "release": "crm.lead_released.v1",
            "transfer": "crm.lead_transferred.v1",
        }
        connection.execute(
            """INSERT INTO ltc.lead_stage_transition
               (company_id, lead_id, assignment_id, event_type, from_allocation_status,
                to_allocation_status, from_pipeline_stage, to_pipeline_stage,
                from_owner_user_id, to_owner_user_id, actor_user_id, source_type,
                reason_code, reason_text, metadata, occurred_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'user',%s,%s,%s::jsonb,%s)""",
            (lead["company_id"], lead["lead_id"], assignment_id, event_type, from_status, to_status,
             lead["pipeline_stage"], lead["pipeline_stage"], from_owner, to_owner, actor_id,
             reason_code, reason_text, json.dumps({"request_id": str(request_id)}), now),
        )
        connection.execute(
            """INSERT INTO ltc.outbox_event
               (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
               VALUES (%s,'sales_crm','sales_lead',%s,%s,%s::jsonb,%s)""",
            (event_names[event_type], lead["lead_id"], version, json.dumps(event_payload), request_id),
        )

    def claim(self, actor: CurrentActor, command: AssignLeadCommand) -> LeadCommandResult:
        _require_sales(actor)
        return self._assign(actor, command)

    def assign(self, actor: CurrentActor, command: AssignLeadCommand) -> LeadCommandResult:
        _require_strategic(actor)
        return self._assign(actor, command)

    def _assign(self, actor: CurrentActor, command: AssignLeadCommand) -> LeadCommandResult:
        now = datetime.now(timezone.utc)
        request_hash = _hash(command)
        with self._database.transaction() as connection:
            existing = self._read_idempotency(connection, "claim_sales_lead" if command.assignment_type == "claim" else "assign_sales_lead", actor, command.idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, "claim_sales_lead" if command.assignment_type == "claim" else "assign_sales_lead", command.idempotency_key, request_hash, now)
            target_id = actor.user_id if command.assignment_type == "claim" else command.assignee_user_id
            user = self._lock_user(connection, target_id)
            lead = self._lock_lead(connection, command.lead_id)
            if lead["allocation_status"] != "claimable":
                raw_owner_user_id = lead["current_owner_user_id"]
                owner_user_id = raw_owner_user_id if isinstance(raw_owner_user_id, UUID) else None
                raise SalesLeadClaimConflict(
                    owner_user_id,
                    self._read_owner_display_name(connection, owner_user_id),
                )
            if lead["version"] != command.expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            self._check_eligibility(lead, user)
            self._check_capacity(connection, user)
            assigned_at = now
            sla_due = _sla_due(now, lead)
            assignment_id = self._insert_assignment(connection, lead, user, actor.user_id if command.assignment_type == "manual" else None, command.assignment_type, assigned_at, sla_due)
            new_version = int(lead["version"]) + 1
            connection.execute(
                """UPDATE ltc.sales_lead SET allocation_status='claimed', current_owner_user_id=%s,
                   current_assignment_started_at=%s, sla_due_at=%s, version=%s, updated_at=%s
                   WHERE lead_id=%s""",
                (target_id, assigned_at, sla_due, new_version, now, command.lead_id),
            )
            event_type = "crm.lead_assigned.v1"
            self._append_transition_and_event(
                connection, lead, assignment_id, actor.user_id, "claim" if command.assignment_type == "claim" else "assign",
                "claimable", "claimed", None, target_id, command.reason_code, command.reason_text, new_version,
                UUID(command.request_id), now,
                {"company_id": str(lead["company_id"]), "lead_id": str(command.lead_id), "assignment_id": str(assignment_id), "assignee_user_id": str(target_id), "assigned_by": str(actor.user_id) if command.assignment_type == "manual" else None, "assignment_type": command.assignment_type, "assigned_at": assigned_at.isoformat()},
            )
            result = LeadCommandResult(command.lead_id, "claimed", assignment_id, None, target_id, None, assigned_at, sla_due, str(lead["pipeline_stage"]), new_version)
            self._complete_idempotency(connection, actor, "claim_sales_lead" if command.assignment_type == "claim" else "assign_sales_lead", command.idempotency_key, result)
        if command.assignment_type == "claim":
            self._trigger_claim_analysis(lead["company_id"])
        return result

    def release(self, actor: CurrentActor, command: ReleaseLeadCommand) -> LeadCommandResult:
        if actor.account_type not in {"sales", "strategic"}:
            raise AuthenticationError("FORBIDDEN")
        now = datetime.now(timezone.utc)
        request_hash = _hash(command)
        with self._database.transaction() as connection:
            scope = "release_sales_lead"
            existing = self._read_idempotency(connection, scope, actor, command.idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, scope, command.idempotency_key, request_hash, now)
            lead = self._lock_lead(connection, command.lead_id)
            if int(lead["version"]) != command.expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            if lead["allocation_status"] != "claimed" or not lead["current_owner_user_id"]:
                raise AuthenticationError("SALES_LEAD_NOT_CLAIMED")
            if actor.account_type == "sales" and lead["current_owner_user_id"] != actor.user_id:
                raise AuthenticationError("FORBIDDEN_LEAD_OWNER_REQUIRED")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT assignment_id FROM ltc.lead_assignment WHERE lead_id=%s AND status='active' FOR UPDATE", (command.lead_id,))
                assignment = cursor.fetchone()
            if not assignment:
                raise AuthenticationError("ASSIGNMENT_NOT_FOUND")
            assignment_id = assignment["assignment_id"]
            connection.execute("UPDATE ltc.lead_assignment SET status='released', reason_code=%s, reason_text=%s, ended_at=%s, version=version+1 WHERE assignment_id=%s", (command.reason_code, command.reason_text, now, assignment_id))
            new_version = int(lead["version"]) + 1
            connection.execute("UPDATE ltc.sales_lead SET allocation_status='claimable', current_owner_user_id=NULL, current_assignment_started_at=NULL, sla_due_at=NULL, released_reason=%s, version=%s, updated_at=%s WHERE lead_id=%s", (command.reason_text or command.reason_code, new_version, now, command.lead_id))
            self._append_transition_and_event(connection, lead, assignment_id, actor.user_id, "release", "claimed", "claimable", lead["current_owner_user_id"], None, command.reason_code, command.reason_text, new_version, UUID(command.request_id), now, {"company_id": str(lead["company_id"]), "lead_id": str(command.lead_id), "assignment_id": str(assignment_id), "released_by": str(actor.user_id), "reason_code": command.reason_code, "reason_text": command.reason_text, "released_at": now.isoformat()})
            result = LeadCommandResult(command.lead_id, "claimable", None, assignment_id, None, lead["current_owner_user_id"], None, None, str(lead["pipeline_stage"]), new_version)
            self._complete_idempotency(connection, actor, scope, command.idempotency_key, result)
            return result

    def transfer(self, actor: CurrentActor, command: TransferLeadCommand) -> LeadCommandResult:
        return self._transfer(actor, command, "transfer_sales_lead")

    def assign_handover(self, actor: CurrentActor, command: TransferLeadCommand) -> LeadCommandResult:
        """Assign one pending departed-sales lead to an active sales user."""
        _require_strategic(actor)
        return self._transfer(actor, command, "handover_assign_sales_lead", require_handover_pending=True)

    def _transfer(
        self,
        actor: CurrentActor,
        command: TransferLeadCommand,
        scope: str,
        pinned_connection: object | None = None,
        require_handover_pending: bool = False,
    ) -> LeadCommandResult:
        if actor.account_type not in {"sales", "strategic"}:
            raise AuthenticationError("FORBIDDEN")
        now = datetime.now(timezone.utc)
        request_hash = _hash(command)
        with self._transaction(pinned_connection) as connection:
            existing = self._read_idempotency(connection, scope, actor, command.idempotency_key, request_hash)
            if existing:
                return existing
            self._create_idempotency(connection, actor, scope, command.idempotency_key, request_hash, now)
            source_id = self._read_lead_owner(connection, command.lead_id)
            if source_id is None:
                lead = self._lock_lead(connection, command.lead_id)
                raise AuthenticationError("SALES_LEAD_NOT_CLAIMED")
            # Depart and Transfer both lock Sales Users before the Lead.
            user_ids = sorted({source_id, command.to_assignee_user_id}, key=str)
            locked_users = {user_id: self._lock_user(connection, user_id) for user_id in user_ids}
            target = locked_users[command.to_assignee_user_id]
            lead = self._lock_lead(connection, command.lead_id)
            if lead["current_owner_user_id"] != source_id:
                raise AuthenticationError("VERSION_CONFLICT")
            if int(lead["version"]) != command.expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            if lead["allocation_status"] != "claimed" or not lead["current_owner_user_id"]:
                raise AuthenticationError("SALES_LEAD_NOT_CLAIMED")
            if actor.account_type == "sales" and lead["current_owner_user_id"] != actor.user_id:
                raise AuthenticationError("FORBIDDEN_LEAD_OWNER_REQUIRED")
            if lead["current_owner_user_id"] == command.to_assignee_user_id:
                raise AuthenticationError("TRANSFER_TARGET_SAME_OWNER")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT assignment_id, assignee_user_id, handover_pending
                       FROM ltc.lead_assignment
                       WHERE lead_id=%s AND status='active' FOR UPDATE""",
                    (command.lead_id,),
                )
                previous = cursor.fetchone()
            if not previous:
                raise AuthenticationError("ASSIGNMENT_NOT_FOUND")
            if require_handover_pending and (
                not previous["handover_pending"]
                or locked_users[source_id]["status"] != "departed"
                or previous["assignee_user_id"] != source_id
            ):
                raise AuthenticationError("HANDOVER_LEAD_NOT_PENDING")
            self._check_eligibility(lead, target)
            self._check_capacity(connection, target)
            previous_id = previous["assignment_id"]
            connection.execute("UPDATE ltc.lead_assignment SET status='transferred', handover_pending=false, reason_code=%s, reason_text=%s, ended_at=%s, version=version+1 WHERE assignment_id=%s", (command.reason_code, command.reason_text, now, previous_id))
            assigned_at = now
            sla_due = None if lead["first_touch_at"] else _sla_due(now, lead)
            new_id = self._insert_assignment(connection, lead, target, actor.user_id, "transfer", assigned_at, sla_due, previous_id)
            new_version = int(lead["version"]) + 1
            connection.execute("UPDATE ltc.sales_lead SET current_owner_user_id=%s, current_assignment_started_at=%s, sla_due_at=%s, version=%s, updated_at=%s WHERE lead_id=%s", (command.to_assignee_user_id, assigned_at, sla_due, new_version, now, command.lead_id))
            self._append_transition_and_event(connection, lead, new_id, actor.user_id, "transfer", "claimed", "claimed", lead["current_owner_user_id"], command.to_assignee_user_id, command.reason_code, command.reason_text, new_version, UUID(command.request_id), now, {"company_id": str(lead["company_id"]), "lead_id": str(command.lead_id), "previous_assignment_id": str(previous_id), "new_assignment_id": str(new_id), "from_assignee_user_id": str(lead["current_owner_user_id"]), "to_assignee_user_id": str(command.to_assignee_user_id), "transferred_by": str(actor.user_id), "reason_code": command.reason_code, "transferred_at": now.isoformat()})
            result = LeadCommandResult(command.lead_id, "claimed", new_id, previous_id, command.to_assignee_user_id, lead["current_owner_user_id"], assigned_at, sla_due, str(lead["pipeline_stage"]), new_version)
            self._complete_idempotency(connection, actor, scope, command.idempotency_key, result)
            return result

    def batch_transfer(self, actor: CurrentActor, items: list[dict[str, object]], idempotency_key: str, request_id: UUID) -> dict[str, list[dict[str, object]]]:
        _require_strategic(actor)
        if len({str(item["lead_id"]) for item in items}) != len(items):
            raise AuthenticationError("DUPLICATE_LEAD_ID")
        lock_key = stable_advisory_key("user", str(actor.user_id), "lead_batch_transfer", idempotency_key)
        with self._database.advisory_lock(lock_key) as (connection, acquired):
            if not acquired:
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            return self._batch_transfer_locked(connection, actor, items, idempotency_key, request_id)

    def _batch_transfer_locked(self, connection: object, actor: CurrentActor, items: list[dict[str, object]], idempotency_key: str, request_id: UUID) -> dict[str, list[dict[str, object]]]:
        request_hash = _hash(items)
        now = datetime.now(timezone.utc)
        with self._transaction(connection):
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT request_hash, state, response_body FROM ltc.idempotency_record WHERE scope='lead_batch_transfer' AND principal_type='user' AND principal_id=%s AND idempotency_key=%s FOR UPDATE", (str(actor.user_id), idempotency_key))
                parent = cursor.fetchone()
            if parent:
                if parent["request_hash"] != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if parent["state"] == "completed" and isinstance(parent["response_body"], dict):
                    return dict(parent["response_body"])
            else:
                connection.execute("INSERT INTO ltc.idempotency_record (scope, principal_type, principal_id, actor_user_id, idempotency_key, request_hash, state, expires_at) VALUES ('lead_batch_transfer','user',%s,%s,%s,%s,'in_progress',%s)", (str(actor.user_id), actor.user_id, idempotency_key, request_hash, now + timedelta(days=1)))

        succeeded: list[dict[str, object]] = []
        failed: list[dict[str, object]] = []
        for item in items:
            lead_id = UUID(str(item["lead_id"]))
            command = TransferLeadCommand(
                lead_id=lead_id,
                expected_version=int(item["expected_version"]),
                to_assignee_user_id=UUID(str(item["to_assignee_user_id"])),
                reason_code=str(item["reason_code"]),
                reason_text=str(item["reason_text"]) if item.get("reason_text") else None,
                idempotency_key=f"{idempotency_key}:{lead_id}",
                request_id=str(request_id),
            )
            try:
                result = self._transfer(actor, command, "lead_batch_transfer_item", pinned_connection=connection)
                succeeded.append({"lead_id": str(result.lead_id), "previous_assignment_id": str(result.previous_assignment_id), "new_assignment_id": str(result.assignment_id), "version": result.version})
            except AuthenticationError as error:
                failed.append({"lead_id": str(lead_id), "code": error.code, "message": error.code})

        response = {"succeeded": succeeded, "failed": failed}
        with self._transaction(connection):
            connection.execute("UPDATE ltc.idempotency_record SET state='completed', response_status=200, response_body=%s::jsonb, updated_at=clock_timestamp() WHERE scope='lead_batch_transfer' AND principal_type='user' AND principal_id=%s AND idempotency_key=%s", (json.dumps(response), str(actor.user_id), idempotency_key))
        return response
