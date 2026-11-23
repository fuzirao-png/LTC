from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings


class PostgresManualNoteStore:
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

    def create_note(self, *, company_id: str, sales_id: str, raw_text: str) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Database is not configured.")
        if not sales_id or not raw_text:
            raise ValueError("salesId and rawText are required.")
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ltc.manual_note (
                    company_id, sales_id, raw_text, extracted_fields_json,
                    confirm_status, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'pending', %s, %s)
                RETURNING note_id, confirm_status
                """,
                (company_id, sales_id, raw_text, json.dumps([]), now, now),
            )
            note_id, confirm_status = cur.fetchone()
            conn.commit()
        return {
            "noteId": str(note_id),
            "companyId": company_id,
            "salesId": sales_id,
            "rawText": raw_text,
            "confirmStatus": str(confirm_status),
        }

    def create_confirmed_note(
        self, *, company_id: str, sales_id: str, raw_text: str, extracted_fields: list
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Database is not configured.")
        if not sales_id or not raw_text:
            raise ValueError("salesId and rawText are required.")
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ltc.manual_note (
                    company_id, sales_id, raw_text, extracted_fields_json, confirm_status
                )
                VALUES (%s, %s, %s, %s, 'confirmed')
                RETURNING note_id, company_id, sales_id, raw_text, confirm_status
                """,
                (company_id, sales_id, raw_text, json.dumps(extracted_fields, ensure_ascii=False)),
            )
            row = cur.fetchone()
            self._record_confirmation(cur, row, extracted_fields)
            conn.commit()
        return {
            "noteId": str(row[0]),
            "companyId": str(row[1]),
            "salesId": str(row[2]),
            "rawText": str(row[3]),
            "confirmStatus": str(row[4]),
            "extractedFields": extracted_fields,
        }

    def update_note_status(
        self, *, note_id: str, confirm_status: str, extracted_fields: list | None = None, sales_id: str | None = None
    ) -> dict[str, Any] | None:
        if confirm_status not in {"pending", "confirmed", "discarded"}:
            raise ValueError("confirmStatus must be one of: pending, confirmed, discarded")
        if not self.is_configured():
            raise RuntimeError("Database is not configured.")
        with self._connect() as conn:
            cur = conn.cursor()
            owner_filter = "AND sales_id = %s" if sales_id else ""
            if extracted_fields is not None:
                cur.execute(
                    """
                    UPDATE ltc.manual_note
                    SET confirm_status = %s,
                        extracted_fields_json = %s,
                        updated_at = clock_timestamp()
                    WHERE note_id = %s
                      {owner_filter}
                    RETURNING note_id, company_id, sales_id, raw_text, confirm_status
                    """.format(owner_filter=owner_filter),
                    (confirm_status, json.dumps(extracted_fields, ensure_ascii=False), note_id, sales_id) if sales_id else (confirm_status, json.dumps(extracted_fields, ensure_ascii=False), note_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE ltc.manual_note
                    SET confirm_status = %s,
                        updated_at = clock_timestamp()
                    WHERE note_id = %s
                      {owner_filter}
                    RETURNING note_id, company_id, sales_id, raw_text, confirm_status
                    """.format(owner_filter=owner_filter),
                    (confirm_status, note_id, sales_id) if sales_id else (confirm_status, note_id),
                )
            row = cur.fetchone()
            if row is not None and confirm_status == "confirmed":
                self._record_confirmation(cur, row, extracted_fields or [])
            elif row is not None and confirm_status == "discarded":
                self._record_audit(cur, row, "manual_note.discarded", extracted_fields or [])
            conn.commit()
        if row is None:
            return None
        return {
            "noteId": str(row[0]),
            "companyId": str(row[1]),
            "salesId": str(row[2]),
            "rawText": str(row[3]),
            "confirmStatus": str(row[4]),
            "extractedFields": extracted_fields or [],
        }

    @staticmethod
    def _record_confirmation(cur, row: tuple, extracted_fields: list) -> None:
        note_id, company_id, sales_id, raw_text, _ = row
        payload = {
            "event_type": "manual_note",
            "note_id": str(note_id),
            "extracted_fields": extracted_fields,
        }
        cur.execute(
            """
            INSERT INTO ltc.customer_activity (
                company_id, activity_type, direction, subject, body,
                actor_user_id, source_type, source_external_key, payload, occurred_at
            )
            VALUES (%s, 'note', 'internal', 'Manual note', %s,
                    %s, 'manual', %s, %s, clock_timestamp())
            ON CONFLICT (source_type, company_id, source_external_key)
            WHERE source_external_key IS NOT NULL
            DO UPDATE SET body = EXCLUDED.body, payload = EXCLUDED.payload
            """,
            (company_id, raw_text, sales_id, f"manual_note:{note_id}", json.dumps(payload, ensure_ascii=False)),
        )
        PostgresManualNoteStore._record_audit(
            cur, row, "manual_note.confirmed", extracted_fields
        )

    @staticmethod
    def _record_audit(cur, row: tuple, action: str, extracted_fields: list) -> None:
        note_id, company_id, sales_id, raw_text, confirm_status = row
        cur.execute(
            """
            INSERT INTO ltc.audit_log (
                actor_user_id, action, resource_type, resource_id, after_data, metadata
            )
            VALUES (%s, %s, 'manual_note', %s, %s, %s)
            """,
            (
                sales_id,
                action,
                note_id,
                json.dumps(
                    {
                        "companyId": str(company_id),
                        "rawText": str(raw_text),
                        "confirmStatus": str(confirm_status),
                        "extractedFields": extracted_fields,
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"source": "customer_operation"}),
            ),
        )

