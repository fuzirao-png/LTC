from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from pg8000 import dbapi

from ltc.modules.customer_operation.domain.read_models import (
    Company,
    Contact,
    CustomerActivity,
    EmailAttachmentRecord,
    EmailRecord,
    FollowUpTask,
    MeetingActionItem,
    MeetingRecord,
    MeetingSummary,
    OperationDetailResponse,
)
from ltc.platform.config import get_settings
from ltc.platform.db.customer_visibility import sales_visible_company_clause, sales_visible_company_params
from ltc.platform.contact_ordering import contact_order_sql


def _json_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _map_stage(*, emails: list[EmailRecord], meetings: list[MeetingRecord], tasks: list[FollowUpTask]) -> str:
    if any(email.intent_level == "won" for email in emails):
        return "won"
    if any(email.intent_level == "proposal" for email in emails):
        return "proposal"
    if meetings:
        return "meeting"
    if any(email.status == "replied" for email in emails):
        return "replied"
    if any(email.status == "sent" for email in emails):
        return "emailed"
    return "assigned"


def _map_email_status(direction: str, status: str, intent_level: str | None) -> str:
    if direction == "inbound":
        return "unsubscribed" if intent_level == "unsubscribe" else "replied"
    if status in {"sent", "delivered", "opened", "clicked"}:
        return "sent"
    if status in {"bounced", "failed"}:
        return "bounced"
    return "draft"


def _map_task_status(status: str) -> str:
    return {
        "completed": "done",
        "cancelled": "cancelled",
        "in_progress": "in_progress",
        "pending": "pending",
    }.get(status, "pending")


def _map_activity_type(row_activity_type: str, payload: dict[str, Any]) -> str:
    event_type = str(payload.get("event_type") or "").strip()
    return {
        "customer_assigned": "customer_assigned",
        "email_sent": "email_sent",
        "email_received": "email_replied",
        "task_created": "task_created",
        "task_completed": "task_completed",
        "task_cancelled": "task_cancelled",
        "meeting_completed": "meeting_completed",
        "manual_note": "manual_note",
    }.get(event_type, "customer_assigned" if row_activity_type == "system" else "customer_assigned")


def _summary_from_payload(payload: dict[str, Any]) -> MeetingSummary | None:
    if not payload:
        return None
    action_items = []
    for item in _as_list(payload.get("action_items")):
        if not isinstance(item, dict):
            continue
        due_at = item.get("due_at")
        due_date = None
        if isinstance(due_at, str) and len(due_at) >= 10:
            try:
                due_date = date.fromisoformat(due_at[:10])
            except ValueError:
                due_date = None
        action_items.append(
            MeetingActionItem(
                owner=str(item.get("owner") or "sales"),
                text=str(item.get("task") or item.get("text") or ""),
                due_date=due_date,
            )
        )
    return MeetingSummary(
        customer_needs=[str(item) for item in _as_list(payload.get("customer_needs"))],
        pain_points=[str(item) for item in _as_list(payload.get("pain_points"))],
        buying_signals=[str(item) for item in _as_list(payload.get("buying_signals"))],
        risks=[str(item) for item in _as_list(payload.get("risks"))],
        action_items=action_items,
        next_step=str(payload.get("next_step") or ""),
    )


class PostgresCustomerOperationRepository:
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

    def can_sales_access_company(self, company_id: str, sales_user_id: str) -> bool:
        if not self.is_configured() or not _is_uuid(company_id) or not _is_uuid(sales_user_id):
            return False
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT 1
                FROM ltc.company c
                WHERE c.company_id = %s
                  AND c.archived_at IS NULL
                  {sales_visible_company_clause("c")}
                LIMIT 1
                """,
                (company_id, *sales_visible_company_params(sales_user_id)),
            )
            return cur.fetchone() is not None

    def get_customer_operations(self, company_id: UUID, sales_user_id: str | None = None) -> dict | None:
        if not self.is_configured() or not _is_uuid(str(company_id)):
            return None
        with self._connect() as conn:
            cur = conn.cursor()
            company = self._get_company(cur, str(company_id))
            if company is None:
                return None
            contacts = self._list_contacts(cur, str(company_id))
            emails = self._list_emails(cur, str(company_id), sales_user_id)
            meetings = self._list_meetings(cur, str(company_id), sales_user_id)
            tasks = self._list_tasks(cur, str(company_id), sales_user_id)
            activities = self._list_activities(cur, str(company_id), sales_user_id)
            return OperationDetailResponse(
                company=company,
                contacts=contacts,
                emails=emails,
                meetings=meetings,
                tasks=tasks,
                activities=activities,
                stage=_map_stage(emails=emails, meetings=meetings, tasks=tasks),
            ).model_dump(mode="json")

    def company_exists(self, company_id: str) -> bool:
        if not self.is_configured() or not _is_uuid(company_id):
            return False
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM ltc.company WHERE company_id = %s AND archived_at IS NULL", (company_id,))
            return cur.fetchone() is not None

    def list_activities(self, company_id: str, sales_user_id: str | None = None) -> list[CustomerActivity]:
        if not self.is_configured() or not _is_uuid(company_id):
            return []
        with self._connect() as conn:
            return self._list_activities(conn.cursor(), company_id, sales_user_id)

    def list_tasks(self, company_id: str, sales_user_id: str | None = None) -> list[FollowUpTask]:
        if not self.is_configured() or not _is_uuid(company_id):
            return []
        with self._connect() as conn:
            return self._list_tasks(conn.cursor(), company_id, sales_user_id)

    def list_emails(self, company_id: str, sales_user_id: str | None = None) -> list[dict[str, Any]]:
        if not self.is_configured() or not _is_uuid(company_id):
            return []
        with self._connect() as conn:
            return [item.model_dump(mode="json") for item in self._list_emails(conn.cursor(), company_id, sales_user_id)]

    def _get_company(self, cur, company_id: str) -> Company | None:
        cur.execute(
            """
            SELECT company_id, company_name, industry_code, country_code, created_by
            FROM ltc.company
            WHERE company_id = %s
              AND archived_at IS NULL
            """,
            (company_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return Company(
            company_id=str(row[0]),
            company_name=str(row[1]),
            industry=row[2],
            country=row[3],
            assigned_to=str(row[4] or "unassigned"),
            stage="assigned",
        )

    def _list_contacts(self, cur, company_id: str) -> list[Contact]:
        ordering = contact_order_sql("ct.title")
        cur.execute(
            f"""
            SELECT ct.contact_id, ct.company_id, ct.full_name, ct.title,
                   COALESCE(ct.primary_email, cc.email), ct.relationship_role
            FROM ltc.contact ct
            LEFT JOIN ltc.candidate_contact cc
              ON cc.candidate_contact_id = ct.source_candidate_contact_id
             AND cc.status = 'active'
            WHERE ct.company_id = %s
              AND ct.status <> 'archived'
            ORDER BY {ordering}, ct.created_at DESC
            """,
            (company_id,),
        )
        rows = [
            Contact(
                contact_id=str(row[0]),
                company_id=str(row[1]),
                name=str(row[2]),
                title=row[3],
                email=str(row[4] or ""),
                role=row[5],
            )
            for row in cur.fetchall()
        ]
        if any(not contact.email for contact in rows):
            rows = self._fill_missing_contact_emails(cur, company_id, rows)
        return rows

    @staticmethod
    def _fill_missing_contact_emails(cur, company_id: str, contacts: list[Contact]) -> list[Contact]:
        emails = PostgresCustomerOperationRepository._raw_candidate_emails(cur, company_id)
        if not emails:
            return contacts
        missing_contacts = [contact for contact in contacts if not contact.email]
        if len(emails) != len(missing_contacts):
            return contacts
        filled: list[Contact] = []
        email_index = 0
        for contact in contacts:
            email = contact.email
            if not email:
                if email_index < len(emails):
                    email = emails[email_index]
                    email_index += 1
            filled.append(Contact(
                contact_id=contact.contact_id,
                company_id=contact.company_id,
                name=contact.name,
                title=contact.title,
                email=email,
                role=contact.role,
            ))
        return filled

    @staticmethod
    def _raw_candidate_emails(cur, company_id: str) -> list[str]:
        cur.execute(
            """
            SELECT co.origin_candidate_id::text
            FROM ltc.company co
            WHERE co.company_id = %s
            """,
            (company_id,),
        )
        row = cur.fetchone()
        candidate_id = str(row[0]) if row and row[0] else ""
        if not candidate_id:
            return []
        cur.execute(
            """
            SELECT raw_extraction_payload
            FROM ltc.candidate_observation
            WHERE candidate_id = %s
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (candidate_id,),
        )
        observation = cur.fetchone()
        if not observation:
            return []
        return _extract_emails_from_payload(observation[0])

    def _list_email_attachments(self, cur, *, company_id: str, email_id: str) -> list[EmailAttachmentRecord]:
        cur.execute(
            """
            SELECT ea.email_attachment_id, ea.filename, ma.mime_type, ma.size_bytes
            FROM ltc.email_attachment ea
            JOIN ltc.media_asset ma ON ma.media_asset_id = ea.media_asset_id
            WHERE ea.company_id = %s AND ea.email_id = %s AND ma.status = 'ready'
            ORDER BY ea.created_at, ea.email_attachment_id
            """,
            (company_id, email_id),
        )
        return [
            EmailAttachmentRecord(
                attachment_id=str(row[0]),
                filename=str(row[1] or "attachment.bin"),
                content_type=str(row[2] or "application/octet-stream"),
                size_bytes=int(row[3] or 0),
                download_url=f"/api/v1/customers/{company_id}/emails/{email_id}/attachments/{row[0]}/download",
            )
            for row in cur.fetchall()
        ]

    def get_email_attachment(
        self,
        *,
        company_id: str,
        email_id: str,
        attachment_id: str,
        sales_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        owner_filter = "AND e.sales_user_id = %s" if sales_user_id else ""
        params = (company_id, email_id, attachment_id, sales_user_id) if sales_user_id else (company_id, email_id, attachment_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT ea.filename, ma.mime_type, ma.size_bytes, ma.storage_key
                FROM ltc.email_attachment ea
                JOIN ltc.email_message e ON e.email_id = ea.email_id AND e.company_id = ea.company_id
                JOIN ltc.media_asset ma ON ma.media_asset_id = ea.media_asset_id AND ma.company_id = ea.company_id
                WHERE ea.company_id = %s
                  AND ea.email_id = %s
                  AND ea.email_attachment_id = %s
                  AND ma.status = 'ready'
                  {owner_filter}
                """,
                params,
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "filename": str(row[0] or "attachment.bin"),
            "content_type": str(row[1] or "application/octet-stream"),
            "size_bytes": int(row[2] or 0),
            "storage_key": str(row[3]),
        }

    def _list_emails(self, cur, company_id: str, sales_user_id: str | None = None) -> list[EmailRecord]:
        owner_filter = "AND e.sales_user_id = %s" if sales_user_id else ""
        params = (company_id, sales_user_id) if sales_user_id else (company_id,)
        cur.execute(
            f"""
            SELECT e.email_id, e.company_id, e.contact_id, e.subject, e.body_text, e.purpose,
                   e.status, e.direction, e.sent_at, e.received_at, e.replied_at,
                   e.intent_level, e.next_action, e.from_address,
                   COALESCE(e.delivered_to_address, e.intended_to_address),
                   e.message_id_header, c.full_name, c.primary_email
            FROM ltc.email_message e
            LEFT JOIN ltc.contact c ON c.contact_id = e.contact_id
            WHERE e.company_id = %s
              {owner_filter}
              AND (e.direction = 'outbound' OR e.message_category = 'customer_reply')
              AND (
                  (e.direction = 'inbound' AND e.status = 'processed')
                  OR
                  (e.direction = 'outbound' AND e.status IN ('sent', 'smtp_submitted', 'delivery_confirmed', 'delivered', 'opened', 'clicked', 'replied', 'bounced'))
              )
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
            ORDER BY COALESCE(e.received_at, e.sent_at, e.created_at) DESC
            """,
            params,
        )
        emails = []
        for row in cur.fetchall():
            direction = str(row[7])
            intent_level = row[11]
            emails.append(
                EmailRecord(
                    email_id=str(row[0]),
                    company_id=str(row[1]),
                    contact_id=str(row[2] or ""),
                    direction=direction,
                    subject=str(row[3] or ""),
                    body=str(row[4] or ""),
                    purpose=row[5] or "first_touch",
                    status=_map_email_status(direction, str(row[6]), intent_level),
                    sent_at=row[8],
                    reply_content=str(row[4] or "") if direction == "inbound" else None,
                    replied_at=row[9] if direction == "inbound" else row[10],
                    intent_level=intent_level,
                    next_action=row[12],
                    from_address=str(row[13] or ""),
                    to_address=str(row[14] or ""),
                    message_id=str(row[15] or "") or None,
                    contact_name=str(row[16] or "") or None,
                    contact_email=str(row[17] or "") or None,
                    attachments=self._list_email_attachments(cur, company_id=str(row[1]), email_id=str(row[0])),
                )
            )
        return emails

    def _list_meetings(self, cur, company_id: str, sales_user_id: str | None = None) -> list[MeetingRecord]:
        owner_filter = "AND owner_user_id = %s" if sales_user_id else ""
        params = (company_id, sales_user_id) if sales_user_id else (company_id,)
        cur.execute(
            f"""
            SELECT meeting_id, company_id, owner_user_id, meeting_started_at, transcript_status,
                   transcript_text, summary_payload
            FROM ltc.meeting
            WHERE company_id = %s
              AND deleted_at IS NULL
              {owner_filter}
            ORDER BY COALESCE(meeting_started_at, created_at) DESC
            """,
            params,
        )
        meetings = []
        for row in cur.fetchall():
            meetings.append(
                MeetingRecord(
                    meeting_id=str(row[0]),
                    company_id=str(row[1]),
                    sales_id=str(row[2] or ""),
                    meeting_time=row[3] or datetime.now(timezone.utc),
                    audio_url=f"/api/v1/meeting/audio?id={row[0]}",
                    transcript_status="done" if row[4] == "done" else "processing",
                    transcript=row[5],
                    summary=_summary_from_payload(_json_obj(row[6])),
                )
            )
        return meetings

    def _list_tasks(self, cur, company_id: str, sales_user_id: str | None = None) -> list[FollowUpTask]:
        owner_filter = "AND assignee_user_id = %s" if sales_user_id else ""
        params = (company_id, sales_user_id) if sales_user_id else (company_id,)
        cur.execute(
            f"""
            SELECT task_id, company_id, assignee_user_id, task_type, description, due_at, status
            FROM ltc.follow_up_task
            WHERE company_id = %s
              {owner_filter}
            ORDER BY created_at
            """,
            params,
        )
        return [
            FollowUpTask(
                task_id=str(row[0]),
                company_id=str(row[1]),
                sales_id=str(row[2] or ""),
                task_type=row[3] if row[3] in {"email", "meeting", "proposal"} else "email",
                description=str(row[4] or ""),
                due_date=row[5].date() if row[5] else None,
                status=_map_task_status(str(row[6])),
            )
            for row in cur.fetchall()
        ]

    def _list_activities(self, cur, company_id: str, sales_user_id: str | None = None) -> list[CustomerActivity]:
        owner_filter = "" if not sales_user_id else """
              AND (
                    actor_user_id = %s
                    OR EXISTS (
                        SELECT 1 FROM ltc.email_message e
                        WHERE e.company_id = customer_activity.company_id
                          AND e.email_id::text = customer_activity.payload->>'email_id'
                          AND e.sales_user_id = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM ltc.meeting m
                        WHERE m.company_id = customer_activity.company_id
                          AND m.meeting_id::text = customer_activity.payload->>'meeting_id'
                          AND m.owner_user_id = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM ltc.follow_up_task t
                        WHERE t.company_id = customer_activity.company_id
                          AND t.task_id::text = customer_activity.payload->>'task_id'
                          AND t.assignee_user_id = %s
                    )
              )"""
        params = (company_id, sales_user_id, sales_user_id, sales_user_id, sales_user_id) if sales_user_id else (company_id,)
        cur.execute(
            f"""
            SELECT activity_id, company_id, activity_type, direction, subject, body,
                   source_type, source_external_key, payload, occurred_at
            FROM ltc.customer_activity
            WHERE company_id = %s
              {owner_filter}
            ORDER BY occurred_at DESC, created_at DESC
            """,
            params,
        )
        activities = []
        for row in cur.fetchall():
            payload = _json_obj(row[8])
            source_id = payload.get("email_id") or payload.get("task_id") or payload.get("meeting_id") or row[7]
            activities.append(
                CustomerActivity(
                    activity_id=str(row[0]),
                    company_id=str(row[1]),
                    activity_type=_map_activity_type(str(row[2]), payload),
                    direction=row[3],
                    subject=row[4],
                    body=row[5],
                    source_type="system",
                    source_id=str(source_id or ""),
                    occurred_at=row[9],
                )
            )
        return activities


_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.IGNORECASE)
_NON_EMAIL_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico"}


def _extract_emails_from_payload(payload: Any) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, str):
            for match in _EMAIL_RE.findall(item):
                email = match.strip().casefold()
                tld = email.rsplit(".", 1)[-1]
                if email.endswith("@51tgt.com") or tld in _NON_EMAIL_TLDS or email in seen:
                    continue
                seen.add(email)
                emails.append(email)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(payload)
    return emails
