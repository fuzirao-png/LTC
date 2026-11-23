from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from hashlib import sha256
from html import escape
import json
from typing import Any
from uuid import uuid4

from pg8000 import dbapi

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.application.reply_intent_agent import classify_progress_evidence, classify_reply
from ltc.modules.customer_operation.application.email_analysis import (
    analyze_inbound_email,
    classify_email_category,
    parse_delivery_notification as parse_email_delivery_notification,
)
from ltc.modules.customer_operation.application.reply_follow_up_cadence import (
    ReplyFollowUpCadencePlan,
    build_reply_follow_up_cadence,
)
from ltc.modules.customer_operation.infrastructure.email_attachment_service import EmailAttachmentInput, EmailAttachmentService


def _parse_delivery_notification_parts(subject: str, body_text: str, attachments: list[Any] | None = None) -> str:
    parts = [str(subject or ""), str(body_text or "")]
    for attachment in attachments or []:
        content_type = str(getattr(attachment, "content_type", "") or "").lower()
        content = getattr(attachment, "content", b"")
        if content_type == "message/rfc822" or str(getattr(attachment, "filename", "") or "").lower().endswith((".eml", ".msg")):
            if isinstance(content, bytes):
                parts.append(content.decode("utf-8", errors="replace"))
            else:
                parts.append(str(content or ""))
    return "\n".join(parts)


def _looks_like_delivery_notification(subject: str, body_text: str, attachments: list[Any] | None = None) -> bool:
    haystack = _parse_delivery_notification_parts(subject, body_text, attachments).lower()
    return any(token in haystack for token in (
        "mailer-daemon", "postmaster", "delivery status notification",
        "delivery report", "mail delivery failed", "undeliverable",
        "final-recipient", "action: failed", "action: delayed", "action: delivered",
        "邮件被退回", "退信通知", "退信原因", "无法发送到", "被退回邮件",
    ))


def _parse_delivery_notification(subject: str, body_text: str, attachments: list[Any] | None = None) -> dict[str, Any]:
    parsed = parse_email_delivery_notification(subject, body_text, attachments)
    result = {
        "message_ids": parsed["message_ids"],
        "recipients": parsed["recipients"],
        "status": parsed["status"],
        "bounce_type": parsed["bounce_type"],
    }
    if parsed.get("original_subject"):
        result["original_subject"] = parsed["original_subject"]
    if parsed.get("reason"):
        result["reason"] = parsed["reason"]
    return result


_PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "qq.com", "outlook.com", "hotmail.com",
    "live.com", "yahoo.com", "icloud.com", "proton.me", "protonmail.com",
}


def _is_personal_email_domain(value: str) -> bool:
    normalized = _normalize_email(value)
    domain = normalized.rsplit("@", 1)[-1] if "@" in normalized else ""
    return domain in _PERSONAL_EMAIL_DOMAINS


def classify_inbound_message(
    *, subject: str, body_text: str, from_email: str = "", attachments: list[Any] | None = None
) -> str:
    """Return the stable inbound category used by storage and reporting."""
    return classify_email_category(
        subject=subject,
        body_text=body_text,
        from_email=from_email,
        attachments=attachments,
    )


def _normalize_email(value: str) -> str:
    # A raw From header can be "Display Name <addr@host>" or just "addr@host".
    # parseaddr extracts the bare address so the same sender is not fragmented
    # into multiple contacts/companies by differing display-name prefixes.
    raw = str(value or "").strip()
    _, addr = parseaddr(raw)
    return (addr or raw).strip().lower()


def _normalize_message_id_token(value: str) -> str:
    return str(value or "").strip().strip("<>").strip().lower()


def _message_id_matches(in_reply_to: str, message_id_header: str) -> bool:
    parent_token = _normalize_message_id_token(message_id_header)
    if not parent_token or "@" not in parent_token:
        return False
    parent_local, parent_domain = parent_token.rsplit("@", 1)
    reply_tokens = re.findall(r"<([^>\s]+)>|([^\s,]+@[^\s,]+)", str(in_reply_to or ""))
    for wrapped, bare in reply_tokens:
        reply_token = _normalize_message_id_token(wrapped or bare)
        if reply_token == parent_token:
            return True
        if "@" not in reply_token:
            continue
        reply_local, reply_domain = reply_token.rsplit("@", 1)
        if reply_domain == parent_domain and reply_local.endswith(f"+{parent_local}"):
            return True
    return False


_REPLY_SUBJECT_PREFIX = re.compile(
    r"^(?:(?:re|fw|fwd|aw|sv|\u7b54\u590d|\u56de\u590d|r\u00e9ponse automatique|risposta automatica|"
    r"automatic reply|auto reply|out of office|ooo)\s*[:\u003a\u00ff-]\s*)+",
    re.IGNORECASE,
)
_OUT_OF_OFFICE_REPLY_CHAIN_PREFIX = re.compile(
    r"^(?:out of office|ooo)\s+(?=(?:re|fw|fwd|aw|sv)\s*[:\u003a\u00ff-])",
    re.IGNORECASE,
)


def _normalize_reply_subject(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    previous = None
    while normalized and normalized != previous:
        previous = normalized
        normalized = _OUT_OF_OFFICE_REPLY_CHAIN_PREFIX.sub("", normalized).strip()
        normalized = _REPLY_SUBJECT_PREFIX.sub("", normalized).strip()
    return normalized.casefold()


def _split_sender(value: str) -> tuple[str, str]:
    # Returns (display_name, normalized_address) from a raw From header.
    raw = str(value or "").strip()
    name, addr = parseaddr(raw)
    return name.strip(), (addr or raw).strip().lower()


def _normalize_company_name(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(frozen=True)
class StoredMailContext:
    company_id: str | None
    contact_id: str | None
    email_id: str
    delivery_attempt_id: str
    created: bool = True


class PostgresMailStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.attachment_service = EmailAttachmentService()

    def is_configured(self) -> bool:
        return all([self.settings.db_host, self.settings.db_name, self.settings.db_user, self.settings.db_password])

    def _store_email_attachments(
        self,
        cur,
        *,
        company_id: str,
        email_id: str,
        attachments: list[EmailAttachmentInput],
        source: str,
    ) -> list[dict[str, str]]:
        if sum(len(attachment.content) for attachment in attachments) > self.attachment_service.max_message_bytes:
            raise ValueError("Attachment message size exceeds the configured limit.")

        records: list[dict[str, str]] = []
        for attachment in attachments:
            stored = self.attachment_service.store(attachment, scope_key=email_id)
            cur.execute(
                """
                INSERT INTO ltc.media_asset (
                    company_id, asset_kind, storage_backend, storage_key, original_filename,
                    mime_type, size_bytes, sha256, status, validation_payload
                )
                VALUES (%s, 'email_attachment', 'local', %s, %s, %s, %s, %s, 'ready', %s)
                RETURNING media_asset_id
                """,
                (
                    company_id,
                    stored.storage_key,
                    stored.safe_filename,
                    stored.content_type,
                    stored.size_bytes,
                    stored.sha256,
                    json.dumps({
                        "source": source,
                        "extraction_status": stored.extraction_status,
                        "extracted_text": stored.extracted_text,
                    }),
                ),
            )
            media_asset_id = str(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO ltc.email_attachment (
                    company_id, email_id, media_asset_id, disposition, filename
                )
                VALUES (%s, %s, %s, 'attachment', %s)
                RETURNING email_attachment_id
                """,
                (company_id, email_id, media_asset_id, stored.safe_filename),
            )
            attachment_id = str(cur.fetchone()[0])
            records.append({
                "attachment_id": attachment_id,
                "media_asset_id": media_asset_id,
                "filename": stored.safe_filename,
                "extracted_text": stored.extracted_text,
                "extraction_status": stored.extraction_status,
            })
        return records

    def _assign_operation_owner(self, cur, *, company_id: str, sales_user_id: str) -> None:
        if not sales_user_id:
            return
        cur.execute(
            """
            INSERT INTO ltc.customer_operation_owner (
                company_id, sales_user_id, ownership_source, assigned_at, updated_at
            )
            SELECT c.company_id, %s, 'mailbox', now(), now()
            FROM ltc.company c
            WHERE c.company_id = %s
              AND lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name)) <> 'exmail.weixin.qq.com'
              AND NOT EXISTS (
                  SELECT 1
                  FROM ltc.user_mailbox um
                  WHERE lower(split_part(um.email_address, '@', 2)) =
                        lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name))
              )
            ON CONFLICT (company_id) DO UPDATE SET
                sales_user_id = EXCLUDED.sales_user_id,
                ownership_source = EXCLUDED.ownership_source,
                assigned_at = EXCLUDED.assigned_at,
                updated_at = EXCLUDED.updated_at
            """,
            (sales_user_id, company_id),
        )

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    def _ensure_company(self, cur, *, company_name: str, recipient_email: str) -> str:
        normalized_company_name = _normalize_company_name(company_name) or "Unknown Company"
        normalized_recipient = _normalize_email(recipient_email)
        domain = normalized_recipient.split("@", 1)[1] if "@" in normalized_recipient else None

        cur.execute(
            """
            SELECT company_id
            FROM ltc.company
            WHERE normalized_company_name = %s
              AND lifecycle_status <> 'archived'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized_company_name.lower(),),
        )
        existing = cur.fetchone()
        if existing:
            return str(existing[0])

        if domain:
            cur.execute(
                """
                SELECT company_id
                FROM ltc.company
                WHERE primary_domain = %s
                  AND lifecycle_status <> 'archived'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (domain,),
            )
            existing = cur.fetchone()
            if existing:
                return str(existing[0])

        cur.execute(
            """
            INSERT INTO ltc.company (
                company_name,
                normalized_company_name,
                primary_domain,
                lifecycle_status
            )
            VALUES (%s, %s, %s, 'prospect')
            RETURNING company_id
            """,
            (company_name or normalized_company_name, normalized_company_name.lower(), domain),
        )
        row = cur.fetchone()
        return str(row[0])

    def _ensure_contact(self, cur, *, company_id: str, contact_name: str, recipient_email: str) -> str:
        normalized_email = _normalize_email(recipient_email)
        if self._is_internal_mailbox_address(cur, normalized_email):
            raise ValueError("Internal mailbox cannot be used as a customer contact.")
        cur.execute(
            """
            SELECT contact_id
            FROM ltc.contact
            WHERE company_id = %s
              AND lower(primary_email) = %s
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (company_id, normalized_email),
        )
        existing = cur.fetchone()
        if existing:
            return str(existing[0])

        normalized_name = _normalize_name(contact_name) or normalized_email or "Unknown Contact"
        cur.execute(
            """
            INSERT INTO ltc.contact (
                company_id,
                full_name,
                normalized_name,
                primary_email,
                normalized_email,
                email_status,
                source,
                status
            )
            VALUES (%s, %s, %s, %s, %s, 'valid', 'operation', 'active')
            RETURNING contact_id
            """,
            (company_id, normalized_name, normalized_name.lower(), normalized_email, normalized_email),
        )
        row = cur.fetchone()
        return str(row[0])

    def _find_email_context_by_message_id(
        self, cur, message_id: str
    ) -> tuple[str, str, str | None] | None:
        if not message_id:
            return None
        cur.execute(
            """
            SELECT email_id, company_id, contact_id
            FROM ltc.email_message
            WHERE message_id_header = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (message_id,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                SELECT email_id, company_id, contact_id, message_id_header
                FROM ltc.email_message
                WHERE direction = 'outbound'
                  AND message_id_header IS NOT NULL
                ORDER BY created_at DESC
                """
            )
            matches = [
                candidate
                for candidate in cur.fetchall()
                if _message_id_matches(message_id, str(candidate[3] or ""))
            ]
            row = matches[0][:3] if len(matches) == 1 else None
        return (str(row[0]), str(row[1]), str(row[2]) if row[2] else None) if row else None

    def _find_inbound_email_by_mailbox(
        self, cur, *, message_id_header: str, mailbox_address: str
    ) -> tuple[str, str | None, str | None] | None:
        if not message_id_header:
            return None
        cur.execute(
            """
            SELECT email_id, company_id, contact_id
            FROM ltc.email_message
            WHERE direction = 'inbound'
              AND message_id_header = %s
              AND lower(trim(intended_to_address)) = lower(trim(%s))
            ORDER BY created_at
            LIMIT 1
            """,
            (message_id_header, mailbox_address),
        )
        row = cur.fetchone()
        return (str(row[0]), str(row[1]), str(row[2]) if row[2] else None) if row else None

    def _is_internal_mailbox_address(self, cur, email_address: str) -> bool:
        normalized_email = _normalize_email(email_address)
        if not normalized_email:
            return False
        cur.execute(
            """
            SELECT 1
            FROM ltc.user_mailbox
            WHERE lower(email_address) = %s
            LIMIT 1
            """,
            (normalized_email,),
        )
        return cur.fetchone() is not None

    def _find_explicit_manual_contact_by_email(
        self, cur, email_address: str
    ) -> tuple[str, str] | None:
        normalized_email = _normalize_email(email_address)
        if not normalized_email:
            return None
        cur.execute(
            """
            SELECT c.company_id, ct.contact_id
            FROM ltc.contact ct
            JOIN ltc.company c ON c.company_id = ct.company_id
            WHERE lower(ct.primary_email) = %s
              AND ct.source = 'manual'
              AND ct.status = 'active'
              AND c.archived_at IS NULL
            ORDER BY ct.created_at DESC
            LIMIT 1
            """,
            (normalized_email,),
        )
        row = cur.fetchone()
        return (str(row[0]), str(row[1])) if row else None

    def _resolve_inbound_context(
        self, cur, *, from_email: str, in_reply_to: str | None
    ) -> tuple[str | None, str | None, str | None] | None:
        parent_context = self._find_email_context_by_message_id(cur, in_reply_to or "")
        if self._is_internal_mailbox_address(cur, from_email):
            explicit_contact = self._find_explicit_manual_contact_by_email(cur, from_email)
            if explicit_contact is None:
                return None
            company_id, contact_id = explicit_contact
            parent_email_id = (
                parent_context[0]
                if parent_context is not None and parent_context[1] == company_id
                else None
            )
            return parent_email_id, company_id, contact_id

        if parent_context:
            parent_email_id, company_id, _ = parent_context
            contact_id = self._find_contact_by_company_email(cur, company_id, from_email)
            return parent_email_id, company_id, contact_id
        company_id, contact_id = self._find_company_contact_by_email(cur, from_email)
        return None, company_id, contact_id

    def _resolve_outbound_target(
        self,
        cur,
        company_id: str,
        contact_id: str,
        *,
        purpose: str = "first_touch",
        enforce_guards: bool = True,
    ) -> tuple[str, str, str]:
        cur.execute(
            """
            SELECT c.company_name, ct.full_name, ct.primary_email,
                   ct.email_status, ct.employment_status, ct.legal_basis_status
            FROM ltc.contact ct
            JOIN ltc.company c ON c.company_id = ct.company_id
            WHERE ct.contact_id = %s
              AND ct.company_id = %s
              AND ct.status = 'active'
              AND c.archived_at IS NULL
            """,
            (contact_id, company_id),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("Selected contact does not belong to the selected active company.")
        email = _normalize_email(str(row[2] or ""))
        if not email:
            raise ValueError("Selected contact has no email address.")
        if enforce_guards:
            email_status = str(row[3] or "unknown")
            if email_status in {"invalid", "bounced", "opted_out"}:
                raise ValueError("Selected contact email is invalid, bounced, or opted out.")
            if str(row[4] or "unknown") == "departed":
                raise ValueError("Selected contact has departed and cannot be contacted.")
            if str(row[5] or "unknown") == "blocked":
                raise ValueError("Selected contact has no legal outreach basis.")
            cur.execute(
                "SELECT 1 FROM ltc.email_suppression "
                "WHERE normalized_email=%s AND status='active' LIMIT 1",
                (email,),
            )
            if cur.fetchone():
                raise ValueError("Selected contact is suppressed and cannot be contacted.")
        return str(row[0]), str(row[1]), email

    def resolve_outbound_target(
        self,
        company_id: str,
        contact_id: str,
        purpose: str = "first_touch",
    ) -> tuple[str, str, str]:
        if not self.is_configured():
            raise RuntimeError("Database settings are not configured.")
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                return self._resolve_outbound_target(
                    cur,
                    company_id,
                    contact_id,
                    purpose=purpose,
                )
            finally:
                cur.close()

    def _find_company_contact_by_email(self, cur, email_address: str) -> tuple[str | None, str | None]:
        normalized_email = _normalize_email(email_address)
        if not normalized_email:
            return None, None
        cur.execute(
            """
            SELECT c.company_id, ct.contact_id
            FROM ltc.contact ct
            JOIN ltc.company c ON c.company_id = ct.company_id
            WHERE lower(ct.primary_email) = %s
              AND ct.status = 'active'
              AND c.archived_at IS NULL
            ORDER BY ct.created_at DESC
            LIMIT 1
            """,
            (normalized_email,),
        )
        row = cur.fetchone()
        if row:
            return str(row[0]), str(row[1])
        return None, None

    def _find_contact_by_company_email(self, cur, company_id: str, email_address: str) -> str | None:
        normalized_email = _normalize_email(email_address)
        if not normalized_email:
            return None
        cur.execute(
            """
            SELECT contact_id
            FROM ltc.contact
            WHERE company_id = %s
              AND lower(primary_email) = %s
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (company_id, normalized_email),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def _record_customer_activity(
        self,
        cur,
        *,
        company_id: str,
        direction: str,
        subject: str,
        body: str,
        source_external_key: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO ltc.customer_activity (
                company_id,
                activity_type,
                direction,
                subject,
                body,
                source_type,
                source_external_key,
                payload,
                occurred_at
            )
            VALUES (%s, 'system', %s, %s, %s, 'system', %s, %s, %s)
            ON CONFLICT (source_type, company_id, source_external_key)
            WHERE source_external_key IS NOT NULL
            DO NOTHING
            """,
            (
                company_id,
                direction,
                subject,
                body[:2000],
                source_external_key,
                json.dumps({"event_type": event_type, **(payload or {})}),
                occurred_at or datetime.now(timezone.utc),
            ),
        )

    def _cancel_reply_follow_up_cadence(
        self,
        cur,
        *,
        company_id: str,
        sales_user_id: str,
        source_email_id: str,
    ) -> int:
        if not sales_user_id:
            return 0
        cur.execute(
            """
            UPDATE ltc.follow_up_task
            SET status = 'cancelled',
                updated_at = clock_timestamp()
            WHERE company_id = %s
              AND (%s::uuid IS NULL OR source_email_id = %s::uuid)
              AND assignee_user_id = %s
              AND status = 'pending'
              AND idempotency_key LIKE 'reply-cadence:%%'
            """,
            (company_id, source_email_id or None, source_email_id or None, sales_user_id),
        )
        return int(getattr(cur, "rowcount", 0) or 0)

    def _create_reply_follow_up_cadence(
        self,
        cur,
        *,
        company_id: str,
        sales_user_id: str,
        source_email_id: str,
        intent_level: str,
        next_action: str,
        occurred_at: datetime,
        parent_email_id: str | None = None,
    ) -> ReplyFollowUpCadencePlan:
        plan = build_reply_follow_up_cadence(
            intent_level=intent_level,
            next_action=next_action,
            source_email_id=source_email_id,
            occurred_at=occurred_at,
        )
        if plan.pause_existing or parent_email_id:
            self._cancel_reply_follow_up_cadence(
                cur,
                company_id=company_id,
                sales_user_id=sales_user_id,
                source_email_id=None if plan.pause_existing else parent_email_id,
            )
        if not plan.tasks or not sales_user_id:
            return plan

        for task in plan.tasks:
            cur.execute(
                """
                INSERT INTO ltc.follow_up_task (
                    company_id, lead_id, assignee_user_id, source_email_id, task_type, title,
                    description, due_at, status, priority, idempotency_key, created_by
                )
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO UPDATE SET
                    task_type = EXCLUDED.task_type,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    due_at = EXCLUDED.due_at,
                    status = EXCLUDED.status,
                    priority = EXCLUDED.priority,
                    updated_at = clock_timestamp()
                """,
                (
                    company_id,
                    sales_user_id,
                    source_email_id,
                    task.task_type,
                    task.title,
                    task.description,
                    task.due_at,
                    task.priority,
                    task.idempotency_key,
                    sales_user_id,
                ),
            )

        self._record_customer_activity(
            cur,
            company_id=company_id,
            direction="internal",
            subject=f"Reply cadence created for {intent_level}",
            body="; ".join(task.title for task in plan.tasks),
            source_external_key=f"reply-cadence:{source_email_id}",
            event_type="task_created",
            payload={
                "email_id": source_email_id,
                "parent_email_id": parent_email_id,
                "intent_level": intent_level,
                "task_count": len(plan.tasks),
                "task_types": [task.task_type for task in plan.tasks],
            },
            occurred_at=occurred_at,
        )
        return plan

    def _suppress_email_if_needed(
        self,
        cur,
        *,
        normalized_email: str,
        email_id: str,
        intent_level: str,
        occurred_at: datetime,
    ) -> None:
        if intent_level != "unsubscribe":
            return
        cur.execute(
            """
            INSERT INTO ltc.email_suppression (
                normalized_email,
                reason,
                source_email_id,
                status,
                suppressed_at,
                note
            )
            VALUES (%s, 'unsubscribe', %s, 'active', %s, 'Created from inbound reply intent.')
            ON CONFLICT (normalized_email) WHERE status = 'active'
            DO UPDATE SET source_email_id = EXCLUDED.source_email_id,
                          reason = EXCLUDED.reason,
                          suppressed_at = EXCLUDED.suppressed_at,
                          note = EXCLUDED.note
            """,
            (normalized_email, email_id, occurred_at),
        )

    @staticmethod
    def _lock_replied_contact(
        cur,
        *,
        company_id: str,
        contact_id: str,
        occurred_at: datetime,
    ) -> None:
        cur.execute(
            """
            UPDATE ltc.company_contact_roster
            SET engagement_locked=true, outreach_status='replied',
                last_engagement_at=%s, version=version+1,
                updated_at=clock_timestamp()
            WHERE company_id=%s AND contact_id=%s
            """,
            (occurred_at, company_id, contact_id),
        )

    @staticmethod
    def _mark_contact_email_verified(
        cur,
        *,
        company_id: str,
        contact_id: str,
        occurred_at: datetime,
    ) -> None:
        cur.execute(
            """
            UPDATE ltc.contact
            SET email_status = 'valid',
                last_verified_at = GREATEST(COALESCE(last_verified_at, %s), %s),
                updated_at = clock_timestamp(),
                version = version + 1
            WHERE company_id = %s
              AND contact_id = %s
              AND status = 'active'
            """,
            (occurred_at, occurred_at, company_id, contact_id),
        )

    def record_outbound_email(
        self,
        *,
        customer_name: str,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
        purpose: str = "first_touch",
        delivery: dict[str, Any],
        attachments: list[dict[str, Any]] | None = None,
        source: str = "customer-operation-email",
        user_id: str = "",
        company_id: str = "",
        contact_id: str = "",
    ) -> StoredMailContext:
        if not self.is_configured():
            raise RuntimeError("Database settings are not configured.")

        started_at = datetime.now(timezone.utc)
        delivery_attempt_id = str(uuid4())
        idempotency_key = str(delivery.get("messageId") or delivery_attempt_id)
        provider_message_id = str(delivery.get("messageId") or "") or None
        provider_code = str(delivery.get("provider") or "smtp")
        delivered_to = str(delivery.get("deliveredTo") or recipient_email)

        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                if company_id and contact_id:
                    customer_name, recipient_name, recipient_email = self._resolve_outbound_target(
                        cur,
                        company_id,
                        contact_id,
                        purpose=purpose,
                        enforce_guards=False,
                    )
                else:
                    company_id = self._ensure_company(cur, company_name=customer_name, recipient_email=recipient_email)
                    contact_id = self._ensure_contact(
                        cur,
                        company_id=company_id,
                        contact_name=recipient_name,
                        recipient_email=recipient_email,
                    )
                self._assign_operation_owner(cur, company_id=company_id, sales_user_id=user_id)
                from_lookup = self.settings.mail_from or self.settings.smtp_username
                if user_id:
                    from ltc.modules.customer_operation.infrastructure.user_email_resolver import resolve_user_email
                    email_cfg = resolve_user_email(user_id)
                    from_lookup = email_cfg.get("mail_from") or from_lookup
                cur.execute(
                    """
                    INSERT INTO ltc.email_message (
                        company_id,
                        contact_id,
                        sales_user_id,
                        direction,
                        purpose,
                        status,
                        from_address,
                        intended_to_address,
                        delivered_to_address,
                        subject,
                        body_text,
                        body_html,
                        provider_code,
                        provider_message_id,
                        message_id_header,
                        idempotency_key,
                        sent_at
                    )
                    VALUES (%s, %s, %s, 'outbound', %s, 'smtp_submitted', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING email_id
                    """,
                    (
                        company_id,
                        contact_id,
                        user_id or None,
                        purpose,
                        from_lookup,
                        recipient_email,
                        delivered_to,
                        subject,
                        body,
                        f"<div style=\"white-space:pre-wrap;\">{escape(body)}</div>",
                        provider_code,
                        provider_message_id,
                        provider_message_id,
                        idempotency_key,
                        started_at,
                    ),
                )
                email_row = cur.fetchone()
                email_id = str(email_row[0])
                cur.execute(
                    "UPDATE ltc.contact SET last_contacted_at=%s, updated_at=clock_timestamp(), "
                    "version=version+1 WHERE company_id=%s AND contact_id=%s",
                    (started_at, company_id, contact_id),
                )
                cur.execute(
                    """
                    UPDATE ltc.company_contact_roster
                    SET outreach_status='sent', last_engagement_at=%s,
                        version=version+1, updated_at=clock_timestamp()
                    WHERE company_id=%s AND contact_id=%s
                    """,
                    (started_at, company_id, contact_id),
                )
                self._record_customer_activity(
                    cur,
                    company_id=company_id,
                    direction="outbound",
                    subject=subject,
                    body=body,
                    source_external_key=provider_message_id or idempotency_key,
                    event_type="email_sent",
                    payload={"email_id": email_id, "purpose": purpose},
                    occurred_at=started_at,
                )

                cur.execute(
                    """
                    INSERT INTO ltc.email_delivery_attempt (
                        email_id,
                        attempt_no,
                        provider_code,
                        idempotency_key,
                        provider_request_id,
                        provider_message_id,
                        status,
                        request_payload,
                        response_payload,
                        accepted_at,
                        completed_at,
                        started_at
                    )
                    VALUES (%s, 1, %s, %s, %s, %s, 'accepted', %s, %s, %s, %s, %s)
                    """,
                    (
                        email_id,
                        provider_code,
                        idempotency_key,
                        str(delivery.get("raw", {}).get("requestId") or "") or None,
                        provider_message_id,
                        json.dumps(
                            {
                                "customer_name": customer_name,
                                "recipient_name": recipient_name,
                                "recipient_email": recipient_email,
                                "subject": subject,
                                "body": body,
                                "purpose": purpose,
                                "attachments": attachments or [],
                                "delivery": delivery,
                                "source": source,
                            }
                        ),
                        json.dumps(delivery),
                        started_at,
                        started_at,
                        started_at,
                    ),
                )

                attachment_inputs: list[EmailAttachmentInput] = []
                for item in attachments or []:
                    encoded = str(item.get("content") or "")
                    try:
                        raw_content = base64.b64decode(encoded)
                    except Exception:
                        raw_content = b""
                    attachment_inputs.append(
                        EmailAttachmentInput(
                            filename=str(item.get("filename") or "attachment.bin"),
                            content_type=str(item.get("contentType") or "application/octet-stream"),
                            content=raw_content,
                        )
                    )
                attachment_records = self._store_email_attachments(
                    cur,
                    company_id=company_id,
                    email_id=email_id,
                    attachments=attachment_inputs,
                    source=source,
                )
                attachment_text = "\n".join(
                    item["extracted_text"] for item in attachment_records if item["extracted_text"]
                )
                evidence = classify_progress_evidence(
                    "\n".join(part for part in [subject, body, attachment_text] if part)
                )
                if evidence is not None:
                    cur.execute(
                        """
                        UPDATE ltc.email_message
                        SET intent_level = %s,
                            intent_payload = %s,
                            next_action = %s
                        WHERE email_id = %s
                        """,
                        (
                            evidence.intent_level,
                            json.dumps(
                                {
                                    "intent_level": evidence.intent_level,
                                    "next_action": evidence.next_action,
                                    "source": source,
                                    "direction": "outbound",
                                    "evidence_sources": [
                                        {"type": "attachment", "attachment_id": item["attachment_id"]}
                                        for item in attachment_records
                                        if item["extracted_text"]
                                    ] or [{"type": "body"}],
                                }
                            ),
                            evidence.next_action,
                            email_id,
                        ),
                    )

                conn.commit()
            finally:
                cur.close()

        return StoredMailContext(
            company_id=company_id,
            contact_id=contact_id,
            email_id=email_id,
            delivery_attempt_id=delivery_attempt_id,
        )

    def record_failed_outbound_email(
        self,
        *,
        customer_name: str,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
        purpose: str,
        error_message: str,
        source: str,
        company_id: str = "",
        contact_id: str = "",
    ) -> StoredMailContext:
        if not self.is_configured():
            raise RuntimeError("Database is not configured.")
        now = datetime.now(timezone.utc)
        idempotency_key = f"{source}:failed:{sha256((recipient_email + subject + now.isoformat()).encode('utf-8')).hexdigest()}"
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            if company_id and contact_id:
                customer_name, recipient_name, recipient_email = self._resolve_outbound_target(
                    cur,
                    company_id,
                    contact_id,
                    purpose=purpose,
                    enforce_guards=False,
                )
            else:
                company_id = self._ensure_company(cur, company_name=customer_name, recipient_email=recipient_email)
                contact_id = self._ensure_contact(
                    cur,
                    company_id=company_id,
                    contact_name=recipient_name,
                    recipient_email=recipient_email,
                )
            cur.execute(
                """
                INSERT INTO ltc.email_message (
                    company_id,
                    contact_id,
                    direction,
                    purpose,
                    status,
                    from_address,
                    intended_to_address,
                    subject,
                    body_text,
                    provider_code,
                    idempotency_key,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, 'outbound', %s, 'failed', %s, %s, %s, %s, 'smtp', %s, %s, %s)
                RETURNING email_id
                """,
                (
                    company_id,
                    contact_id,
                    purpose,
                    self.settings.mail_from or self.settings.smtp_username,
                    recipient_email,
                    subject,
                    body,
                    idempotency_key,
                    now,
                    now,
                ),
            )
            email_id = str(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO ltc.email_delivery_attempt (
                    email_id,
                    attempt_no,
                    provider_code,
                    idempotency_key,
                    status,
                    request_payload,
                    response_payload,
                    error_code,
                    error_message,
                    started_at,
                    completed_at
                )
                VALUES (%s, 1, 'smtp', %s, 'failed', %s, %s, 'smtp_error', %s, %s, %s)
                RETURNING delivery_attempt_id
                """,
                (
                    email_id,
                    idempotency_key,
                    json.dumps({"to": recipient_email, "subject": subject}),
                    json.dumps({"provider": "smtp", "status": "failed"}),
                    error_message[:1000],
                    now,
                    now,
                ),
            )
            delivery_attempt_id = str(cur.fetchone()[0])
            conn.commit()
        return StoredMailContext(
            company_id=company_id,
            contact_id=contact_id,
            email_id=email_id,
            delivery_attempt_id=delivery_attempt_id,
        )

    @staticmethod
    def parse_delivery_notification(*, subject: str, body_text: str, attachments: list[Any] | None = None) -> dict[str, Any]:
        return _parse_delivery_notification(subject, body_text, attachments)

    def reconcile_delivery_notification(
        self,
        *,
        from_email: str,
        subject: str,
        body_text: str,
        in_reply_to: str | None = None,
        attachments: list[Any] | None = None,
    ) -> dict[str, str] | None:
        """Apply an IMAP delivery notification to its original outbound message."""
        if not self.is_configured():
            return None
        parsed = _parse_delivery_notification(subject, body_text, attachments)
        if not _looks_like_delivery_notification(subject, body_text, attachments):
            return None
        if parsed["status"] == "reconcile_required":
            return {"status": "reconcile_required", "bounce_type": ""}
        message_ids = list(dict.fromkeys([*parsed["message_ids"], str(in_reply_to or "").strip()]))
        recipients = parsed["recipients"]
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                row = None
                if message_ids:
                    placeholders = ",".join(["%s"] * len(message_ids))
                    cur.execute(
                        f"""SELECT email_id, company_id, contact_id, intended_to_address
                              FROM ltc.email_message
                             WHERE direction='outbound'
                               AND status IN ('smtp_submitted', 'sent', 'delivered', 'replied', 'bounced', 'reconcile_required')
                               AND (provider_message_id IN ({placeholders}) OR message_id_header IN ({placeholders}))
                             ORDER BY sent_at DESC NULLS LAST LIMIT 1""",
                        tuple(message_ids) + tuple(message_ids),
                    )
                    row = cur.fetchone()
                if row is None and parsed.get("original_subject") and recipients:
                    cur.execute(
                        """SELECT email_id, company_id, contact_id, intended_to_address
                             FROM ltc.email_message
                            WHERE direction='outbound'
                               AND status IN ('smtp_submitted', 'sent', 'delivered', 'replied', 'bounced', 'reconcile_required')
                              AND lower(intended_to_address) = ANY(%s)
                              AND lower(subject) = lower(%s)
                              AND COALESCE(sent_at, created_at) >= clock_timestamp() - INTERVAL '30 days'
                            ORDER BY sent_at DESC NULLS LAST, created_at DESC
                            LIMIT 2""",
                        ([value.lower() for value in recipients], parsed["original_subject"]),
                    )
                    subject_rows = cur.fetchall() or []
                    row = subject_rows[0] if len(subject_rows) == 1 else None
                if row is None and recipients:
                    cur.execute(
                        """SELECT email_id, company_id, contact_id, intended_to_address
                             FROM ltc.email_message
                            WHERE direction='outbound'
                               AND status IN ('smtp_submitted', 'sent', 'delivered', 'replied', 'bounced', 'reconcile_required')
                              AND lower(intended_to_address) = ANY(%s)
                              AND COALESCE(sent_at, created_at) >= clock_timestamp() - INTERVAL '7 days'
                            ORDER BY sent_at DESC NULLS LAST, created_at DESC""",
                        ([value.lower() for value in recipients],),
                    )
                    recipient_rows = cur.fetchall() or []
                    row = recipient_rows[0] if len(recipient_rows) == 1 else None
                    if len(recipient_rows) > 1:
                        return {"status": "reconcile_required", "bounce_type": parsed["bounce_type"] or ""}
                if not row:
                    return {"status": "reconcile_required", "bounce_type": parsed["bounce_type"] or ""}
                email_id, company_id, contact_id, recipient = (str(value or "") for value in row)
                is_hard = parsed["status"] == "hard_bounce"
                is_soft = parsed["status"] == "soft_bounce"
                email_status = "bounced" if (is_hard or is_soft) else "delivered"
                cur.execute(
                    "UPDATE ltc.email_message SET status=%s, updated_at=clock_timestamp() WHERE email_id=%s",
                    ("bounced" if (is_hard or is_soft) else "delivered", email_id),
                )
                cur.execute(
                    """UPDATE ltc.email_delivery_attempt
                          SET status=%s, bounce_type=%s, error_message=%s, completed_at=clock_timestamp(), response_payload=%s
                        WHERE email_id=%s AND status IN ('accepted', 'uncertain')""",
                    ("failed" if (is_hard or is_soft) else "delivered", parsed["bounce_type"], parsed.get("reason") or None, json.dumps({"source": "imap_dsn", "dsn": parsed}), email_id),
                )
                cur.execute(
                    """
                    UPDATE ltc.email_automation_run r
                    SET delivery_summary = COALESCE((
                        SELECT jsonb_build_object(
                            'replied', COUNT(DISTINCT em.email_id) FILTER (WHERE em.replied_at IS NOT NULL),
                            'hard_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '5xx'),
                            'soft_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '4xx'),
                            'delivered_confirmed', COUNT(*) FILTER (WHERE em.status = 'delivered' OR da.status = 'delivered')
                        )
                        FROM ltc.email_automation_touch t
                        LEFT JOIN ltc.email_message em ON em.provider_message_id = t.provider_message_id
                        LEFT JOIN LATERAL (
                            SELECT a.status, a.bounce_type
                            FROM ltc.email_delivery_attempt a
                            WHERE a.email_id = em.email_id
                            ORDER BY a.attempt_no DESC LIMIT 1
                        ) da ON TRUE
                        WHERE t.run_id = r.run_id
                    ), '{}'::jsonb)
                    WHERE EXISTS (
                        SELECT 1
                        FROM ltc.email_automation_touch t
                        JOIN ltc.email_message outbound_email
                          ON outbound_email.provider_message_id = t.provider_message_id
                        WHERE t.run_id = r.run_id AND outbound_email.email_id = %s
                    )
                    """,
                    (email_id,),
                )
                if is_hard:
                    cur.execute(
                        "UPDATE ltc.contact SET email_status='invalid', updated_at=clock_timestamp(), version=version+1 WHERE company_id=%s AND contact_id=%s",
                        (company_id, contact_id),
                    )
                    cur.execute(
                        """INSERT INTO ltc.email_suppression (normalized_email, reason, source_email_id, status, suppressed_at, note)
                             VALUES (%s, 'hard_bounce', %s, 'active', clock_timestamp(), 'Created from IMAP DSN.')
                             ON CONFLICT (normalized_email) WHERE status='active' DO UPDATE SET source_email_id=EXCLUDED.source_email_id, suppressed_at=EXCLUDED.suppressed_at, note=EXCLUDED.note""",
                        (_normalize_email(recipient), email_id),
                    )
                conn.commit()
                return {"emailId": email_id, "companyId": company_id, "contactId": contact_id, "status": parsed["status"], "bounceType": parsed["bounce_type"] or "", "recipient": recipient, "reason": parsed.get("reason") or ""}
            finally:
                cur.close()

    def record_inbound_email(
        self,
        *,
        from_email: str,
        to_email: str,
        subject: str,
        body_text: str,
        body_preview: str,
        message_id_header: str,
        in_reply_to: str | None = None,
        received_at: str | None = None,
        source: str = "imap",
        sales_user_id: str = "",
        attachments: list[EmailAttachmentInput] | None = None,
        related_email_id: str | None = None,
    ) -> StoredMailContext | None:
        if not self.is_configured():
            raise RuntimeError("Database settings are not configured.")

        received_ts = datetime.now(timezone.utc)
        if received_at:
            try:
                received_ts = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            except Exception:
                received_ts = datetime.now(timezone.utc)

        company_id: str | None = None
        contact_id: str | None = None
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                if message_id_header:
                    dedupe_key = f"{_normalize_email(to_email)}:{message_id_header}"
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (dedupe_key,),
                    )
                    existing = self._find_inbound_email_by_mailbox(
                        cur,
                        message_id_header=message_id_header,
                        mailbox_address=to_email,
                    )
                    if existing is not None:
                        email_id, company_id, contact_id = existing
                        inbound_category = classify_inbound_message(
                            subject=subject,
                            body_text=body_text,
                            from_email=from_email,
                            attachments=attachments,
                        )
                        if inbound_category == "delivery_notification" and related_email_id:
                            cur.execute(
                                """UPDATE ltc.email_message AS inbound
                                   SET parent_email_id=%s,
                                       company_id=parent.company_id,
                                       contact_id=parent.contact_id,
                                       thread_key=COALESCE(inbound.thread_key, parent.thread_key, parent.message_id_header),
                                       body_text=%s,
                                       message_category='delivery_notification',
                                       updated_at=clock_timestamp()
                                  FROM ltc.email_message AS parent
                                 WHERE inbound.email_id=%s AND parent.email_id=%s AND parent.direction='outbound'""",
                                (related_email_id, body_text, email_id, related_email_id),
                            )
                        conn.commit()
                        return StoredMailContext(
                            company_id=company_id,
                            contact_id=contact_id or "",
                            email_id=email_id,
                            delivery_attempt_id="",
                            created=False,
                        )
                inbound_category = classify_inbound_message(
                    subject=subject,
                    body_text=body_text,
                    from_email=from_email,
                    attachments=attachments,
                )
                safe_in_reply_to = in_reply_to if inbound_category in {"customer_reply", "automatic_reply"} else None
                inbound_context = None
                if inbound_category == "delivery_notification" and related_email_id:
                    cur.execute(
                        "SELECT email_id, company_id, contact_id FROM ltc.email_message WHERE email_id=%s AND direction='outbound'",
                        (related_email_id,),
                    )
                    related_row = cur.fetchone()
                    if related_row:
                        inbound_context = (str(related_row[0]), related_row[1], related_row[2])
                if inbound_context is None:
                    inbound_context = self._resolve_inbound_context(
                        cur, from_email=from_email, in_reply_to=safe_in_reply_to
                    )
                if inbound_context is None:
                    return None
                parent_email_id, company_id, contact_id = inbound_context
                # Parse "Display Name <addr>" once so both the contact name and the
                # derived company/domain use clean values (not the raw header).
                display_name, normalized_from = _split_sender(from_email)
                if company_id is None and not _is_personal_email_domain(normalized_from):
                    domain = normalized_from.split("@", 1)[1] if "@" in normalized_from else normalized_from
                    company_name = _normalize_company_name(domain) or "Inbound Contact"
                    company_id = self._ensure_company(cur, company_name=company_name, recipient_email=normalized_from)
                if contact_id is None and company_id is not None:
                    contact_id = self._ensure_contact(
                        cur,
                        company_id=company_id,
                        contact_name=display_name or normalized_from,
                        recipient_email=normalized_from,
                    )
                if company_id is not None:
                    self._assign_operation_owner(cur, company_id=company_id, sales_user_id=sales_user_id)

                thread_key = in_reply_to or message_id_header
                cur.execute(
                    """
                    INSERT INTO ltc.email_message (
                        company_id,
                        contact_id,
                        sales_user_id,
                        parent_email_id,
                        thread_key,
                        direction,
                        status,
                        message_category,
                        from_address,
                        intended_to_address,
                        delivered_to_address,
                        subject,
                        body_text,
                        body_html,
                        message_id_header,
                        in_reply_to,
                        received_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'inbound', 'received', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING email_id
                    """,
                    (
                        company_id,
                        contact_id,
                        sales_user_id or None,
                        parent_email_id,
                        thread_key,
                        inbound_category,
                        from_email,
                        to_email,
                        to_email,
                        subject,
                        body_text,
                        f"<div style=\"white-space:pre-wrap;\">{escape(body_text or body_preview)}</div>",
                        message_id_header,
                        in_reply_to,
                        received_ts,
                    ),
                )
                email_row = cur.fetchone()
                email_id = str(email_row[0])
                attachment_records = []
                if company_id is not None:
                    attachment_records = self._store_email_attachments(
                        cur,
                        company_id=company_id,
                        email_id=email_id,
                        attachments=list(attachments or []),
                        source=source,
                    )
                attachment_text = "\n".join(
                    item["extracted_text"] for item in attachment_records if item["extracted_text"]
                )
                classification_text = "\n".join(
                    part for part in [subject, body_text or body_preview, attachment_text] if part
                )
                inbound_analysis = analyze_inbound_email(
                    subject=subject,
                    body_text=classification_text,
                    from_email=from_email,
                    attachments=attachments,
                )
                intent = None
                if inbound_analysis.get("countsAsReply"):
                    intent = type("InboundEmailIntent", (), {
                        "intent_level": inbound_analysis.get("intentLevel"),
                        "next_action": inbound_analysis.get("nextAction"),
                        "confidence": inbound_analysis.get("confidence"),
                        "evidence_quote": inbound_analysis.get("evidenceQuote"),
                        "evidence_type": None,
                    })()
                intent_payload = {
                    "category": inbound_category,
                    "intent_level": intent.intent_level if intent else None,
                    "next_action": intent.next_action if intent else None,
                    "counts_as_reply": bool(inbound_analysis.get("countsAsReply")),
                    "delivery_status": inbound_analysis.get("deliveryStatus"),
                    "bounce_type": inbound_analysis.get("bounceType"),
                    "recipients": inbound_analysis.get("recipients") or [],
                    "original_subject": inbound_analysis.get("originalSubject") or "",
                    "reason": inbound_analysis.get("reason") or "",
                    "source": source,
                    "evidence_sources": [
                        {"type": "attachment", "attachment_id": item["attachment_id"]}
                        for item in attachment_records
                        if item["extracted_text"]
                    ] or [{"type": "body"}],
                }
                if intent and intent.confidence is not None:
                    intent_payload["confidence"] = intent.confidence
                if intent and intent.evidence_quote:
                    intent_payload["evidence_quote"] = intent.evidence_quote
                if intent and intent.evidence_type:
                    intent_payload["evidence_type"] = intent.evidence_type
                cur.execute(
                    """
                    UPDATE ltc.email_message
                    SET status = 'processed',
                        notification_created_at = CASE
                            WHEN %s IN ('customer_reply', 'automatic_reply') THEN COALESCE(notification_created_at, now())
                            ELSE notification_created_at
                        END,
                        intent_level = %s,
                        intent_payload = %s,
                        next_action = %s
                    WHERE email_id = %s
                    """,
                    (
                        inbound_category,
                        intent.intent_level if intent else None,
                        json.dumps(intent_payload),
                        intent.next_action if intent else None,
                        email_id,
                    ),
                )
                if parent_email_id and inbound_category in {"customer_reply", "automatic_reply"}:
                    cur.execute(
                        "UPDATE ltc.email_message SET replied_at=COALESCE(replied_at, %s), status=CASE WHEN status IN ('sent','delivered','opened','clicked') THEN 'replied' ELSE status END, updated_at=clock_timestamp() WHERE email_id=%s AND direction='outbound'",
                        (received_ts, parent_email_id),
                    )
                    cur.execute(
                        """
                        UPDATE ltc.email_automation_run r
                        SET delivery_summary = COALESCE((
                            SELECT jsonb_build_object(
                                'replied', COUNT(DISTINCT em.email_id) FILTER (WHERE em.replied_at IS NOT NULL),
                                'hard_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '5xx'),
                                'soft_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '4xx'),
                                'delivered_confirmed', COUNT(*) FILTER (WHERE em.status = 'delivered' OR da.status = 'delivered')
                            )
                            FROM ltc.email_automation_touch t
                            LEFT JOIN ltc.email_message em ON em.provider_message_id = t.provider_message_id
                            LEFT JOIN LATERAL (
                                SELECT a.status, a.bounce_type
                                FROM ltc.email_delivery_attempt a
                                WHERE a.email_id = em.email_id
                                ORDER BY a.attempt_no DESC LIMIT 1
                            ) da ON TRUE
                            WHERE t.run_id = r.run_id
                        ), '{}'::jsonb)
                        WHERE EXISTS (
                            SELECT 1
                            FROM ltc.email_automation_touch t
                            JOIN ltc.email_message outbound_email
                              ON outbound_email.provider_message_id = t.provider_message_id
                            WHERE t.run_id = r.run_id AND outbound_email.email_id = %s
                        )
                        """,
                        (parent_email_id,),
                    )
                if inbound_category == "customer_reply":
                    self._suppress_email_if_needed(
                        cur,
                        normalized_email=_normalize_email(from_email),
                        email_id=email_id,
                        intent_level=intent.intent_level,
                        occurred_at=received_ts,
                    )
                if inbound_category == "customer_reply" and company_id and contact_id:
                    self._lock_replied_contact(
                        cur,
                        company_id=company_id,
                        contact_id=contact_id,
                        occurred_at=received_ts,
                    )
                    self._mark_contact_email_verified(
                        cur,
                        company_id=company_id,
                        contact_id=contact_id,
                        occurred_at=received_ts,
                    )
                if company_id:
                    self._record_customer_activity(
                    cur,
                    company_id=company_id,
                    direction="inbound",
                    subject=subject,
                    body=body_text or body_preview,
                    source_external_key=message_id_header,
                    event_type="email_received",
                    payload={
                        "email_id": email_id,
                        "category": inbound_category,
                        "intent_level": intent.intent_level if intent else None,
                        "next_action": intent.next_action if intent else None,
                    },
                    occurred_at=received_ts,
                )
                if inbound_category == "customer_reply" and company_id:
                    self._create_reply_follow_up_cadence(
                        cur,
                        company_id=company_id,
                        sales_user_id=sales_user_id,
                        source_email_id=email_id,
                        parent_email_id=parent_email_id,
                        intent_level=intent.intent_level,
                        next_action=intent.next_action,
                        occurred_at=received_ts,
                    )
                conn.commit()
            finally:
                cur.close()

        return StoredMailContext(
            company_id=company_id,
            contact_id=contact_id,
            email_id=email_id,
            delivery_attempt_id="",
        )
