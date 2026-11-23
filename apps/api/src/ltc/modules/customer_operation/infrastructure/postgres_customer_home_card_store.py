from __future__ import annotations

from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings
from ltc.platform.db.customer_visibility import (
    clean_customer_company_clause,
    sales_visible_company_clause,
    sales_visible_company_params,
)


_TAG_LABELS = {
    "TMC": "差旅平台",
    "TRAVEL_OTA": "差旅OTA",
    "FINTECH": "金融科技",
    "OTHER": "其他",
}


def _tag_from_industry(industry_code: str | None) -> str:
    return _TAG_LABELS.get(str(industry_code or "").strip().upper(), "其他")


def _valid_customer_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "@" in text or text.lower().startswith(("http://", "https://")):
        return ""
    if text.lower() in {"待确认", "待补齐", "未知", "unknown", "n/a", "-"}:
        return ""
    if "." in text and " " not in text and text.rsplit(".", 1)[-1].lower() in {
        "com", "net", "org", "io", "co", "cn", "jp", "kr"
    }:
        return ""
    return text


def _display_name(*candidates: Any) -> str:
    for candidate in candidates:
        valid = _valid_customer_name(candidate)
        if valid:
            return valid
    return ""


def _progress_from_stage(stage: str) -> float:
    return {
        "assigned": 8.5,
        "emailed": 25,
        "replied": 42,
        "meeting": 58.5,
        "proposal": 75.5,
        "won": 100,
    }.get(stage, 8.5)


def _stage_from_dates(*, won_at: Any, proposal_at: Any, meeting_at: Any, replied_at: Any, emailed_at: Any) -> str:
    if won_at:
        return "won"
    if proposal_at:
        return "proposal"
    if meeting_at:
        return "meeting"
    if replied_at:
        return "replied"
    if emailed_at:
        return "emailed"
    return "assigned"


class PostgresCustomerHomeCardStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return all([self.settings.db_host, self.settings.db_name, self.settings.db_user, self.settings.db_password])

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    def list_home_cards(
        self, *, limit: int = 500, owner_user_id: str | None = None
    ) -> list[dict[str, Any]]:
        if not self.is_configured():
            return []

        with self._connect() as conn:
            cur = conn.cursor()
            owner_filter = ""
            params: list[Any] = []
            if owner_user_id:
                owner_filter = sales_visible_company_clause()
                params.extend(sales_visible_company_params(owner_user_id))
            clean_filter = clean_customer_company_clause()
            params.append(limit)
            cur.execute(
                f"""
                SELECT c.company_id, c.company_name, c.legal_name, c.website,
                       c.country_code, c.region_code, c.city, c.industry_code,
                       c.created_at, c.created_by, u.display_name
                FROM ltc.company c
                LEFT JOIN ltc.user_account u ON u.user_id = c.created_by
                WHERE c.archived_at IS NULL
                  {clean_filter}
                  AND lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name)) <> 'exmail.weixin.qq.com'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ltc.user_mailbox internal_mailbox
                      WHERE lower(split_part(internal_mailbox.email_address, '@', 2)) =
                            lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name))
                  )
                {owner_filter}
                ORDER BY c.created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()

            items: list[dict[str, Any]] = []
            for (
                company_id,
                company_name,
                legal_name,
                website,
                country_code,
                region_code,
                city,
                industry_code,
                created_at,
                created_by,
                owner_name,
            ) in rows:
                cur.execute(
                    """
                    SELECT count(*)::int,
                           count(*) FILTER (WHERE NULLIF(trim(primary_email), '') IS NOT NULL)::int,
                           min(full_name)
                    FROM ltc.contact
                    WHERE company_id=%s AND status <> 'archived'
                    """,
                    (company_id,),
                )
                contact_count, contact_email_count, contact_name = cur.fetchone()

                cur.execute(
                    """
                    SELECT ia.total_score, ia.grade
                    FROM ltc.sales_lead sl
                    JOIN ltc.lead_icp_assessment ia
                      ON ia.icp_assessment_id = sl.adopted_icp_assessment_id
                    WHERE sl.company_id = %s
                      AND sl.allocation_status <> 'archived'
                    ORDER BY sl.updated_at DESC, ia.scored_at DESC
                    LIMIT 1
                    """,
                    (company_id,),
                )
                adopted_icp = cur.fetchone()
                icp_score = float(adopted_icp[0]) if adopted_icp and adopted_icp[0] is not None else None
                icp_grade = str(adopted_icp[1]) if adopted_icp and adopted_icp[1] else None

                email_owner_filter = "AND e.sales_user_id = %s" if owner_user_id else ""
                email_params = (company_id, owner_user_id) if owner_user_id else (company_id,)
                cur.execute(
                    f"""
                    SELECT
                        count(*)::int,
                        count(*) FILTER (WHERE direction = 'outbound')::int,
                        count(*) FILTER (
                            WHERE direction = 'inbound' AND message_category = 'customer_reply'
                        )::int,
                        min(COALESCE(sent_at, created_at)) FILTER (WHERE direction = 'outbound'),
                        min(COALESCE(received_at, replied_at, created_at)) FILTER (
                            WHERE direction = 'inbound' AND message_category = 'customer_reply'
                        )
                    FROM ltc.email_message e
                    WHERE e.company_id = %s
                    {email_owner_filter}
                      AND NOT EXISTS (
                          SELECT 1
                          FROM ltc.user_mailbox internal_mailbox
                          WHERE e.direction = 'inbound'
                            AND (
                                lower(trim(e.from_address)) = lower(internal_mailbox.email_address)
                                OR lower(e.from_address) LIKE '%%<' || lower(internal_mailbox.email_address) || '>%%'
                            )
                            AND NOT EXISTS (
                                SELECT 1
                                FROM ltc.contact explicit_contact
                                WHERE explicit_contact.contact_id = e.contact_id
                                  AND explicit_contact.company_id = e.company_id
                                  AND explicit_contact.source = 'manual'
                                  AND explicit_contact.status = 'active'
                                  AND lower(explicit_contact.primary_email) = lower(internal_mailbox.email_address)
                            )
                      )
                    """,
                    email_params,
                )
                email_count, outbound_email_count, inbound_email_count, emailed_at, replied_at = cur.fetchone()

                meeting_owner_filter = "AND owner_user_id = %s" if owner_user_id else ""
                meeting_params = (company_id, owner_user_id) if owner_user_id else (company_id,)
                cur.execute(
                    f"""
                    SELECT count(*)::int, min(meeting_started_at)
                    FROM ltc.meeting
                    WHERE company_id=%s AND deleted_at IS NULL
                      {meeting_owner_filter}
                    """,
                    meeting_params,
                )
                meeting_count, meeting_at = cur.fetchone()

                task_owner_filter = "AND assignee_user_id = %s" if owner_user_id else ""
                task_params = (company_id, owner_user_id) if owner_user_id else (company_id,)
                cur.execute(
                    f"""
                    SELECT count(*)::int
                    FROM ltc.follow_up_task
                    WHERE company_id = %s
                      {task_owner_filter}
                    """,
                    task_params,
                )
                task_count = cur.fetchone()[0]
                cur.execute(
                    f"""
                    SELECT task_id, task_type, description, due_at, status
                    FROM ltc.follow_up_task
                    WHERE company_id = %s
                      {task_owner_filter}
                    ORDER BY due_at NULLS LAST, created_at
                    LIMIT 20
                    """,
                    task_params,
                )
                tasks = [
                    {
                        "task_id": str(row[0]),
                        "task_type": str(row[1]),
                        "description": str(row[2] or ""),
                        "due_date": row[3].date().isoformat() if row[3] else None,
                        "status": str(row[4]),
                    }
                    for row in cur.fetchall()
                ]

                cur.execute(
                    f"""
                    SELECT
                        min(COALESCE(e.received_at, e.sent_at, e.created_at)) FILTER (WHERE e.intent_level = 'proposal'),
                        min(COALESCE(e.received_at, e.sent_at, e.created_at)) FILTER (WHERE e.intent_level = 'won')
                    FROM ltc.email_message e
                    WHERE e.company_id = %s
                    {email_owner_filter}
                    """,
                    email_params,
                )
                proposal_at, won_at = cur.fetchone()

                activity_owner_filter = "" if not owner_user_id else """
                      AND (
                            ca.actor_user_id = %s
                            OR EXISTS (
                                SELECT 1 FROM ltc.email_message e
                                WHERE e.company_id = ca.company_id
                                  AND e.email_id::text = ca.payload->>'email_id'
                                  AND e.sales_user_id = %s
                            )
                            OR EXISTS (
                                SELECT 1 FROM ltc.meeting m
                                WHERE m.company_id = ca.company_id
                                  AND m.meeting_id::text = ca.payload->>'meeting_id'
                                  AND m.owner_user_id = %s
                            )
                            OR EXISTS (
                                SELECT 1 FROM ltc.follow_up_task t
                                WHERE t.company_id = ca.company_id
                                  AND t.task_id::text = ca.payload->>'task_id'
                                  AND t.assignee_user_id = %s
                            )
                      )"""
                activity_params = (company_id, owner_user_id, owner_user_id, owner_user_id, owner_user_id) if owner_user_id else (company_id,)
                cur.execute(
                    f"""
                    SELECT count(*)::int, min(occurred_at)
                    FROM ltc.customer_activity ca
                    WHERE ca.company_id=%s
                      {activity_owner_filter}
                    """,
                    activity_params,
                )
                activity_count, acquired_at = cur.fetchone()
                acquired_at = acquired_at or created_at


                cur.execute(
                    f"""
                    SELECT ca.subject, ca.body, ca.occurred_at
                    FROM ltc.customer_activity ca
                    WHERE ca.company_id = %s
                      {activity_owner_filter}
                    ORDER BY occurred_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    activity_params,
                )
                activity_latest = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT subject, body_text, COALESCE(sent_at, received_at, created_at) AS occurred_at
                    FROM ltc.email_message e
                    WHERE e.company_id = %s
                    {email_owner_filter}
                      AND NOT EXISTS (
                          SELECT 1
                          FROM ltc.user_mailbox internal_mailbox
                          WHERE e.direction = 'inbound'
                            AND (
                                lower(trim(e.from_address)) = lower(internal_mailbox.email_address)
                                OR lower(e.from_address) LIKE '%%<' || lower(internal_mailbox.email_address) || '>%%'
                            )
                            AND NOT EXISTS (
                                SELECT 1
                                FROM ltc.contact explicit_contact
                                WHERE explicit_contact.contact_id = e.contact_id
                                  AND explicit_contact.company_id = e.company_id
                                  AND explicit_contact.source = 'manual'
                                  AND explicit_contact.status = 'active'
                                  AND lower(explicit_contact.primary_email) = lower(internal_mailbox.email_address)
                            )
                      )
                    ORDER BY COALESCE(sent_at, received_at, created_at) DESC
                    LIMIT 1
                    """,
                    email_params,
                )
                email_latest = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT e.subject, e.body_text, e.intent_level,
                           COALESCE(e.received_at, e.created_at)
                    FROM ltc.email_message e
                    WHERE e.company_id = %s
                      AND e.direction = 'inbound'
                      AND e.message_category = 'customer_reply'
                      AND e.replied_at IS NULL
                      {email_owner_filter}
                    ORDER BY COALESCE(e.received_at, e.created_at) DESC
                    LIMIT 1
                    """,
                    email_params,
                )
                latest_inbound_reply = cur.fetchone()

                cur.execute(
                    f"""
                    SELECT title, COALESCE(transcript_text, summary_payload::text, title) AS body,
                           COALESCE(meeting_started_at, created_at) AS occurred_at
                    FROM ltc.meeting
                    WHERE company_id = %s AND deleted_at IS NULL
                      {meeting_owner_filter}
                    ORDER BY COALESCE(meeting_started_at, created_at) DESC
                    LIMIT 1
                    """,
                    meeting_params,
                )
                meeting_latest = cur.fetchone()

                latest_candidates = [item for item in [activity_latest, email_latest, meeting_latest] if item and item[2] is not None]
                latest_candidates.sort(key=lambda item: item[2], reverse=True)
                latest_title, latest_body, latest_at = latest_candidates[0] if latest_candidates else ("", "", None)

                stage = _stage_from_dates(
                    won_at=won_at,
                    proposal_at=proposal_at,
                    meeting_at=meeting_at,
                    replied_at=replied_at,
                    emailed_at=emailed_at,
                )
                stage_dates = {
                    "acquiredAt": acquired_at.isoformat() if acquired_at else None,
                    "emailedAt": emailed_at.isoformat() if emailed_at else None,
                    "repliedAt": replied_at.isoformat() if replied_at else None,
                    "meetingAt": meeting_at.isoformat() if meeting_at else None,
                    "proposalAt": proposal_at.isoformat() if proposal_at else None,
                    "wonAt": won_at.isoformat() if won_at else None,
                }
                tag = _tag_from_industry(industry_code)
                display_name = _display_name(legal_name, company_name)
                if not display_name:
                    continue
                contact = str(contact_name or owner_name or created_by or "").strip() or "-"

                items.append(
                    {
                        "companyId": str(company_id),
                        "companyName": str(company_name),
                        "customerName": display_name,
                        "display_name": display_name,
                        "company_id": str(company_id),
                        "tag": tag,
                        "contact": contact,
                        "ownerName": str(owner_name or ""),
                        "assigned_to": str(owner_name or ""),
                        "industryCode": industry_code,
                        "stage": stage,
                        "stageDates": stage_dates,
                        "progress": _progress_from_stage(stage),
                        "latestTitle": str(latest_title or company_name),
                        "latestTime": latest_at.isoformat() if latest_at else None,
                        "latestBody": str(latest_body or ""),
                        "latestInboundReply": {
                            "subject": str(latest_inbound_reply[0] or ""),
                            "body": str(latest_inbound_reply[1] or ""),
                            "intent": str(latest_inbound_reply[2] or ""),
                            "receivedAt": latest_inbound_reply[3].isoformat() if latest_inbound_reply[3] else None,
                        } if latest_inbound_reply else None,
                        "tasks": tasks,
                        "signal": f"{int(email_count or 0)}封邮件 · {int(meeting_count or 0)}场会议",
                        "outboundEmailCount": int(outbound_email_count or 0),
                        "inboundEmailCount": int(inbound_email_count or 0),
                        "showEmailRecord": int(email_count or 0) > 0,
                        "contactEmailCount": int(contact_email_count or 0),
                        "icpScore": icp_score,
                        "icpGrade": icp_grade,
                        "payload": {
                            "company_name": company_name,
                            "legal_name": legal_name,
                            "website": website,
                            "country": country_code,
                            "country_code": country_code,
                            "region": region_code,
                            "region_code": region_code,
                            "city": city,
                            "industry": industry_code,
                            "tag": tag,
                            "stage": stage,
                            "assigned_to": owner_name,
                            "stage_dates": stage_dates,
                            "contact_count": int(contact_count or 0),
                            "contact_email_count": int(contact_email_count or 0),
                            "email_count": int(email_count or 0),
                            "icp_score": icp_score,
                            "icp_grade": icp_grade,
                            "outbound_email_count": int(outbound_email_count or 0),
                            "inbound_email_count": int(inbound_email_count or 0),
                            "meeting_count": int(meeting_count or 0),
                            "task_count": int(task_count or 0),
                            "activity_count": int(activity_count or 0),
                        },
                    }
                )

        return items
