"""Company and contact operations owned by the Sales CRM module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import UUID

from psycopg.rows import dict_row

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.domain.models import CurrentActor
from ltc.platform.db import PostgresDatabase


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


class CompanyContactService:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get_company(self, actor: CurrentActor, company_id: UUID) -> dict[str, object]:
        with self._database.transaction() as connection:
            return self._authorized_company(connection, actor, company_id)

    def update_company(
        self,
        actor: CurrentActor,
        company_id: UUID,
        expected_version: int,
        values: dict[str, object],
        idempotency_key: str,
        request_id: UUID,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        request_hash = _hash({"company_id": company_id, "expected_version": expected_version, "values": values})
        with self._database.transaction() as connection:
            existing = self._existing_command(connection, actor, "update_company", idempotency_key, request_hash)
            if existing:
                return existing
            self._begin_command(connection, actor, "update_company", idempotency_key, request_hash, now)
            company = self._authorized_company(connection, actor, company_id, lock=True, require_owner=True)
            if int(company["version"]) != expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            fields = {key: value for key, value in values.items() if value is not None}
            if "company_name" in fields:
                fields["normalized_company_name"] = str(fields["company_name"]).strip().lower()
            if not fields:
                raise AuthenticationError("COMPANY_UPDATE_EMPTY")
            assignments = ", ".join(f"{key}=%s" for key in fields)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"UPDATE ltc.company SET {assignments}, version=version+1, updated_at=%s "
                    "WHERE company_id=%s RETURNING *",
                    (*fields.values(), now, company_id),
                )
                updated = cursor.fetchone()
            self._audit(connection, actor, "update", "company", company_id, request_id, company, updated)
            self._complete_command(connection, actor, "update_company", idempotency_key, updated, 200)
            return updated

    def list_contacts(self, actor: CurrentActor, company_id: UUID) -> list[dict[str, object]]:
        with self._database.transaction() as connection:
            self._authorized_company(connection, actor, company_id)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM ltc.contact WHERE company_id=%s AND status='active' ORDER BY full_name",
                    (company_id,),
                )
                return list(cursor.fetchall())

    def create_contact(
        self,
        actor: CurrentActor,
        company_id: UUID,
        values: dict[str, object],
        idempotency_key: str,
        request_id: UUID,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        request_hash = _hash({"company_id": company_id, "values": values})
        with self._database.transaction() as connection:
            existing = self._existing_command(connection, actor, "create_contact", idempotency_key, request_hash)
            if existing:
                return existing
            self._begin_command(connection, actor, "create_contact", idempotency_key, request_hash, now)
            self._authorized_company(connection, actor, company_id, lock=True, require_owner=True)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """INSERT INTO ltc.contact
                        (company_id, full_name, normalized_name, title, department,
                         relationship_role, priority, primary_email, normalized_email,
                         email_status, phone, linkedin_url, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,'unknown'),%s,%s,'manual')
                    RETURNING *""",
                    (
                        company_id,
                        values["full_name"],
                        str(values["full_name"]).strip().lower(),
                        values.get("title"),
                        values.get("department"),
                        values.get("relationship_role"),
                        values.get("priority"),
                        values.get("primary_email"),
                        values.get("normalized_email"),
                        values.get("email_status"),
                        values.get("phone"),
                        values.get("linkedin_url"),
                    ),
                )
                contact = cursor.fetchone()
            self._audit(connection, actor, "create", "contact", contact["contact_id"], request_id, None, contact)
            self._complete_command(connection, actor, "create_contact", idempotency_key, contact, 201)
            return contact

    def update_contact(
        self,
        actor: CurrentActor,
        contact_id: UUID,
        expected_version: int,
        values: dict[str, object],
        idempotency_key: str,
        request_id: UUID,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        request_hash = _hash({"contact_id": contact_id, "expected_version": expected_version, "values": values})
        with self._database.transaction() as connection:
            existing = self._existing_command(connection, actor, "update_contact", idempotency_key, request_hash)
            if existing:
                return existing
            self._begin_command(connection, actor, "update_contact", idempotency_key, request_hash, now)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM ltc.contact WHERE contact_id=%s FOR UPDATE", (contact_id,))
                contact = cursor.fetchone()
            if not contact:
                raise AuthenticationError("CONTACT_NOT_FOUND")
            self._authorized_company(connection, actor, contact["company_id"], lock=True, require_owner=True)
            if int(contact["version"]) != expected_version:
                raise AuthenticationError("VERSION_CONFLICT")
            fields = {key: value for key, value in values.items() if value is not None}
            if "full_name" in fields:
                fields["normalized_name"] = str(fields["full_name"]).strip().lower()
            if not fields:
                raise AuthenticationError("CONTACT_UPDATE_EMPTY")
            assignments = ", ".join(f"{key}=%s" for key in fields)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"UPDATE ltc.contact SET {assignments}, version=version+1, updated_at=%s "
                    "WHERE contact_id=%s RETURNING *",
                    (*fields.values(), now, contact_id),
                )
                updated = cursor.fetchone()
            self._audit(connection, actor, "update", "contact", contact_id, request_id, contact, updated)
            self._complete_command(connection, actor, "update_contact", idempotency_key, updated, 200)
            return updated

    def _authorized_company(
        self,
        connection: object,
        actor: CurrentActor,
        company_id: UUID,
        lock: bool = False,
        require_owner: bool = False,
    ) -> dict[str, object]:
        suffix = " FOR UPDATE OF c" if lock else ""
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT c.*, sl.lead_id, sl.current_owner_user_id, sl.allocation_status,
                          sl.pipeline_stage, sl.pool_region_code, sl.required_sales_tier
                   FROM ltc.company c
                   LEFT JOIN ltc.sales_lead sl ON sl.company_id=c.company_id
                     AND sl.allocation_status <> 'archived' AND sl.pipeline_stage NOT IN ('won','lost')
                   WHERE c.company_id=%s""" + suffix,
                (company_id,),
            )
            company = cursor.fetchone()
        if not company:
            raise AuthenticationError("COMPANY_NOT_FOUND")
        if actor.account_type == "sales":
            is_owner = company["current_owner_user_id"] == actor.user_id
            is_visible_pool = (
                company["allocation_status"] == "claimable"
                and company["pool_region_code"] == actor.region_code
                and company["required_sales_tier"] == actor.sales_tier
            )
            if not is_owner and not is_visible_pool:
                raise AuthenticationError("FORBIDDEN_COMPANY_ACCESS")
            if require_owner and not is_owner:
                raise AuthenticationError("FORBIDDEN_COMPANY_WRITE")
        return company

    @staticmethod
    def _existing_command(connection: object, actor: CurrentActor, scope: str, key: str, request_hash: str) -> dict[str, object] | None:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT request_hash, state, response_body FROM ltc.idempotency_record "
                "WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s FOR UPDATE",
                (scope, str(actor.user_id), key),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if row["request_hash"] != request_hash:
            raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
        if row["state"] == "completed" and isinstance(row["response_body"], dict):
            return dict(row["response_body"])
        raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")

    @staticmethod
    def _begin_command(connection: object, actor: CurrentActor, scope: str, key: str, request_hash: str, now: datetime) -> None:
        connection.execute(
            "INSERT INTO ltc.idempotency_record "
            "(scope, principal_type, principal_id, actor_user_id, idempotency_key, request_hash, state, expires_at) "
            "VALUES (%s,'user',%s,%s,%s,%s,'in_progress',%s)",
            (scope, str(actor.user_id), actor.user_id, key, request_hash, now + timedelta(days=1)),
        )

    @staticmethod
    def _complete_command(connection: object, actor: CurrentActor, scope: str, key: str, result: dict[str, object], status_code: int) -> None:
        connection.execute(
            "UPDATE ltc.idempotency_record SET state='completed', response_status=%s, response_body=%s::jsonb, "
            "updated_at=clock_timestamp() WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s",
            (status_code, json.dumps(result, default=str), scope, str(actor.user_id), key),
        )

    @staticmethod
    def _audit(connection: object, actor: CurrentActor, action: str, resource_type: str, resource_id: UUID, request_id: UUID, before: dict[str, object] | None, after: dict[str, object] | None) -> None:
        connection.execute(
            "INSERT INTO ltc.audit_log (actor_user_id, action, resource_type, resource_id, request_id, before_data, after_data) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
            (actor.user_id, action, resource_type, resource_id, str(request_id), json.dumps(before, default=str) if before else None, json.dumps(after, default=str) if after else None),
        )
