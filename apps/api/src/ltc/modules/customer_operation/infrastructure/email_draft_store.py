from __future__ import annotations

import base64
from contextlib import closing
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pg8000 import dbapi

from ltc.modules.customer_operation.infrastructure.email_attachment_service import (
    EmailAttachmentInput,
    EmailAttachmentService,
)
from ltc.modules.customer_operation.infrastructure.mail_store import PostgresMailStore
from ltc.platform.config import get_settings


from ltc.modules.customer_operation.application.email_draft_errors import DraftVersionConflict


class EmailDraftStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.attachment_service = EmailAttachmentService()

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    @staticmethod
    def _valid_uuid(value: str) -> bool:
        try:
            UUID(str(value))
            return True
        except ValueError:
            return False

    def _attachments(self, cur, company_id: str, email_id: str) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT ea.email_attachment_id, ea.filename, ma.mime_type, ma.size_bytes,
                   ma.storage_key, ma.media_asset_id
            FROM ltc.email_attachment ea
            JOIN ltc.media_asset ma
              ON ma.media_asset_id = ea.media_asset_id
             AND ma.company_id = ea.company_id
            WHERE ea.company_id = %s
              AND ea.email_id = %s
              AND ma.status = 'ready'
            ORDER BY ea.created_at, ea.email_attachment_id
            """,
            (company_id, email_id),
        )
        return [
            {
                "attachment_id": str(row[0]),
                "filename": str(row[1] or "attachment.bin"),
                "content_type": str(row[2] or "application/octet-stream"),
                "size_bytes": int(row[3] or 0),
                "storage_key": str(row[4]),
                "media_asset_id": str(row[5]),
                "download_url": f"/api/v1/customers/{company_id}/emails/{email_id}/attachments/{row[0]}/download",
            }
            for row in cur.fetchall()
        ]

    def _draft_from_row(self, cur, row) -> dict[str, Any]:
        item = {
            "email_id": str(row[0]),
            "company_id": str(row[1]),
            "contact_id": str(row[2] or ""),
            "parent_email_id": str(row[3] or ""),
            "purpose": str(row[4] or "first_touch"),
            "status": str(row[5]),
            "from_address": str(row[6] or ""),
            "recipient_email": str(row[7] or ""),
            "subject": str(row[8] or ""),
            "body_text": str(row[9] or ""),
            "version": int(row[10] or 0),
            "created_at": row[11].isoformat() if row[11] else None,
            "updated_at": row[12].isoformat() if row[12] else None,
            "contact_name": str(row[13] or ""),
        }
        item["attachments"] = self._attachments(cur, item["company_id"], item["email_id"])
        return item

    def create(
        self,
        *,
        company_id: str,
        contact_id: str,
        sales_user_id: str,
        subject: str,
        body_text: str,
        purpose: str,
        parent_email_id: str = "",
        attachments: list[EmailAttachmentInput] | None = None,
    ) -> dict[str, Any]:
        if not all(self._valid_uuid(value) for value in (company_id, contact_id, sales_user_id)):
            raise ValueError("company_id, contact_id and sales_user_id must be UUIDs")
        if purpose not in {"first_touch", "reply_followup", "meeting_followup"}:
            raise ValueError("Unsupported email purpose")
        mail_store = PostgresMailStore()
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                customer_name, contact_name, recipient_email = mail_store._resolve_outbound_target(
                    cur, company_id, contact_id, purpose=purpose, enforce_guards=False
                )
                del customer_name
                email_id = str(uuid4())
                cur.execute(
                    "SELECT email_address FROM ltc.user_mailbox WHERE user_id=%s AND enabled=true",
                    (sales_user_id,),
                )
                mailbox = cur.fetchone()
                if not mailbox:
                    raise RuntimeError("No enabled mailbox is bound to the current sales user.")
                from_address = str(mailbox[0])
                if parent_email_id:
                    if not self._valid_uuid(parent_email_id):
                        raise ValueError("parent_email_id must be a UUID")
                    cur.execute(
                        "SELECT 1 FROM ltc.email_message WHERE email_id=%s AND company_id=%s",
                        (parent_email_id, company_id),
                    )
                    if not cur.fetchone():
                        raise ValueError("Parent email does not belong to the customer")
                cur.execute(
                    """
                    INSERT INTO ltc.email_message (
                        email_id, company_id, contact_id, parent_email_id, sales_user_id,
                        direction, purpose, status, from_address, intended_to_address,
                        subject, body_text, body_html
                    )
                    VALUES (%s, %s, %s, %s, %s, 'outbound', %s, 'draft', %s, %s, %s, %s, %s)
                    RETURNING email_id, company_id, contact_id, parent_email_id, purpose, status,
                              from_address, intended_to_address, subject, body_text, version,
                              created_at, updated_at
                    """,
                    (
                        email_id,
                        company_id,
                        contact_id,
                        parent_email_id or None,
                        sales_user_id,
                        purpose,
                        from_address,
                        recipient_email,
                        subject,
                        body_text,
                        body_text,
                    ),
                )
                row = (*cur.fetchone(), contact_name)
                mail_store._store_email_attachments(
                    cur,
                    company_id=company_id,
                    email_id=email_id,
                    attachments=list(attachments or []),
                    source="customer-operation-draft",
                )
                item = self._draft_from_row(cur, row)
                conn.commit()
                return item
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def get(self, *, email_id: str, sales_user_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.email_id, e.company_id, e.contact_id, e.parent_email_id, e.purpose,
                       e.status, e.from_address, e.intended_to_address, e.subject, e.body_text,
                       e.version, e.created_at, e.updated_at, c.full_name
                FROM ltc.email_message e
                LEFT JOIN ltc.contact c ON c.contact_id = e.contact_id AND c.company_id = e.company_id
                WHERE e.email_id = %s AND e.sales_user_id = %s AND e.direction = 'outbound'
                """,
                (email_id, sales_user_id),
            )
            row = cur.fetchone()
            return self._draft_from_row(cur, row) if row else None

    def list(self, *, company_id: str, sales_user_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.email_id, e.company_id, e.contact_id, e.parent_email_id, e.purpose,
                       e.status, e.from_address, e.intended_to_address, e.subject, e.body_text,
                       e.version, e.created_at, e.updated_at, c.full_name
                FROM ltc.email_message e
                LEFT JOIN ltc.contact c ON c.contact_id = e.contact_id AND c.company_id = e.company_id
                WHERE e.company_id = %s
                  AND e.sales_user_id = %s
                  AND e.direction = 'outbound'
                  AND e.status = 'draft'
                ORDER BY e.updated_at DESC, e.email_id DESC
                """,
                (company_id, sales_user_id),
            )
            rows = cur.fetchall()
            return [self._draft_from_row(cur, row) for row in rows]

    def update(
        self,
        *,
        email_id: str,
        sales_user_id: str,
        expected_version: int,
        contact_id: str,
        subject: str,
        body_text: str,
        purpose: str,
        attachments: list[EmailAttachmentInput] | None = None,
    ) -> dict[str, Any] | None:
        mail_store = PostgresMailStore()
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT company_id FROM ltc.email_message WHERE email_id=%s AND sales_user_id=%s AND status='draft'",
                    (email_id, sales_user_id),
                )
                found = cur.fetchone()
                if not found:
                    return None
                company_id = str(found[0])
                _, contact_name, recipient_email = mail_store._resolve_outbound_target(
                    cur, company_id, contact_id, purpose=purpose, enforce_guards=False
                )
                cur.execute(
                    """
                    UPDATE ltc.email_message
                    SET contact_id=%s, purpose=%s, intended_to_address=%s, subject=%s,
                        body_text=%s, body_html=%s, version=version+1, updated_at=now()
                    WHERE email_id=%s AND sales_user_id=%s AND status='draft' AND version=%s
                    RETURNING email_id, company_id, contact_id, parent_email_id, purpose, status,
                              from_address, intended_to_address, subject, body_text, version,
                              created_at, updated_at
                    """,
                    (
                        contact_id, purpose, recipient_email, subject, body_text, body_text,
                        email_id, sales_user_id, expected_version,
                    ),
                )
                updated = cur.fetchone()
                if not updated:
                    raise DraftVersionConflict("Draft version conflict")
                mail_store._store_email_attachments(
                    cur,
                    company_id=company_id,
                    email_id=email_id,
                    attachments=list(attachments or []),
                    source="customer-operation-draft",
                )
                item = self._draft_from_row(cur, (*updated, contact_name))
                conn.commit()
                return item
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def remove_attachment(
        self, *, email_id: str, attachment_id: str, sales_user_id: str, expected_version: int
    ) -> bool:
        storage_key = ""
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT ma.media_asset_id, ma.storage_key, e.version
                    FROM ltc.email_attachment ea
                    JOIN ltc.email_message e ON e.email_id=ea.email_id AND e.company_id=ea.company_id
                    JOIN ltc.media_asset ma ON ma.media_asset_id=ea.media_asset_id
                    WHERE ea.email_id=%s AND ea.email_attachment_id=%s
                      AND e.sales_user_id=%s AND e.status='draft'
                    """,
                    (email_id, attachment_id, sales_user_id),
                )
                row = cur.fetchone()
                if not row:
                    return False
                if int(row[2]) != expected_version:
                    raise DraftVersionConflict("Draft version conflict")
                media_asset_id, storage_key = str(row[0]), str(row[1])
                cur.execute("DELETE FROM ltc.email_attachment WHERE email_attachment_id=%s", (attachment_id,))
                cur.execute(
                    "UPDATE ltc.media_asset SET status='deleted', deleted_at=now() WHERE media_asset_id=%s",
                    (media_asset_id,),
                )
                cur.execute(
                    "UPDATE ltc.email_message SET version=version+1, updated_at=now() WHERE email_id=%s AND version=%s",
                    (email_id, expected_version),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
        path = self.attachment_service.resolve_path(storage_key)
        if path.is_file():
            path.unlink()
        return True

    def delete(self, *, email_id: str, sales_user_id: str, expected_version: int) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_message
                SET status='cancelled', version=version+1, updated_at=now()
                WHERE email_id=%s AND sales_user_id=%s AND status='draft' AND version=%s
                RETURNING email_id
                """,
                (email_id, sales_user_id, expected_version),
            )
            row = cur.fetchone()
            if row:
                conn.commit()
                return True
            cur.execute(
                "SELECT 1 FROM ltc.email_message WHERE email_id=%s AND sales_user_id=%s AND status='draft'",
                (email_id, sales_user_id),
            )
            if cur.fetchone():
                raise DraftVersionConflict("Draft version conflict")
            return False

    def attachment_payloads(self, *, email_id: str, sales_user_id: str) -> list[dict[str, Any]]:
        draft = self.get(email_id=email_id, sales_user_id=sales_user_id)
        if not draft:
            return []
        payloads = []
        for item in draft["attachments"]:
            path = self.attachment_service.resolve_path(item["storage_key"])
            if path.is_file():
                payloads.append({
                    "filename": item["filename"],
                    "contentType": item["content_type"],
                    "size": item["size_bytes"],
                    "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                })
        return payloads

    def mark_sent(self, *, email_id: str, sales_user_id: str, delivery: dict[str, Any]) -> bool:
        now = datetime.now(timezone.utc)
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_message
                SET status='smtp_submitted', delivered_to_address=%s, provider_code=%s,
                    provider_message_id=%s, message_id_header=%s, sent_at=%s,
                    version=version+1, updated_at=now()
                WHERE email_id=%s AND sales_user_id=%s AND status='draft'
                RETURNING email_id
                """,
                (
                    str(delivery.get("deliveredTo") or ""),
                    str(delivery.get("provider") or "smtp"),
                    str(delivery.get("messageId") or "") or None,
                    str(delivery.get("messageId") or "") or None,
                    now,
                    email_id,
                    sales_user_id,
                ),
            )
            row = cur.fetchone()
            if row:
                conn.commit()
                return True
            return False

    def mark_failed(self, *, email_id: str, sales_user_id: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE ltc.email_message SET status='failed', version=version+1, updated_at=now() WHERE email_id=%s AND sales_user_id=%s AND status='draft'",
                (email_id, sales_user_id),
            )
            conn.commit()
