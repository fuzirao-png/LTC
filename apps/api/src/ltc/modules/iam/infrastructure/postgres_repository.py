"""PostgreSQL implementations of IAM ports."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from typing import Iterator, cast
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from ltc.modules.iam.domain.models import (
    AccountStatus,
    AccountType,
    AuthSession,
    RegionCode,
    SalesTier,
    UserAccount,
)
from ltc.modules.iam.domain.ports import IamRepository
from ltc.platform.db import PostgresDatabase


USER_COLUMNS = """
    user_id, username, password_hash, display_name, email, account_type, sales_tier,
    region_code, capacity_limit, status, failed_login_attempts, locked_until,
    token_version, version
"""


def _user_from_row(row: dict[str, object]) -> UserAccount:
    return UserAccount(
        user_id=cast(UUID, row["user_id"]),
        username=cast(str, row["username"]),
        password_hash=cast(str, row["password_hash"]),
        display_name=cast(str, row["display_name"]),
        account_type=cast(AccountType, row["account_type"]),
        sales_tier=cast(SalesTier | None, row["sales_tier"]),
        region_code=cast(RegionCode | None, row["region_code"]),
        capacity_limit=cast(int | None, row["capacity_limit"]),
        status=cast(AccountStatus, row["status"]),
        failed_login_attempts=cast(int, row["failed_login_attempts"]),
        locked_until=cast(datetime | None, row["locked_until"]),
        token_version=cast(int, row["token_version"]),
        version=cast(int, row["version"]),
        email=cast(str | None, row.get("email")),
    )


def _session_from_row(row: dict[str, object]) -> AuthSession:
    return AuthSession(
        session_id=cast(UUID, row["session_id"]),
        user_id=cast(UUID, row["user_id"]),
        issued_token_version=cast(int, row["issued_token_version"]),
        refresh_token_hash=cast(str, row["refresh_token_hash"]),
        expires_at=cast(datetime, row["expires_at"]),
        revoked_at=cast(datetime | None, row["revoked_at"]),
    )


class PostgresIamRepository(IamRepository):
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    @property
    def connection(self) -> Connection:
        return self._connection

    def find_user_by_username_for_update(self, username: str) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"SELECT {USER_COLUMNS} FROM ltc.user_account "
                "WHERE lower(username) = lower(%s) FOR UPDATE",
                (username,),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def find_user_by_username(self, username: str) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"SELECT {USER_COLUMNS} FROM ltc.user_account WHERE lower(username) = lower(%s)",
                (username,),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def active_assignment_count(self, user_id: UUID) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*)::integer FROM ltc.lead_assignment WHERE assignee_user_id=%s AND status='active'",
                (user_id,),
            )
            return int(cursor.fetchone()[0])

    def find_user_by_id(self, user_id: UUID) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(f"SELECT {USER_COLUMNS} FROM ltc.user_account WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def find_user_by_id_for_update(self, user_id: UUID) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(f"SELECT {USER_COLUMNS} FROM ltc.user_account WHERE user_id = %s FOR UPDATE", (user_id,))
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def find_user_by_email(self, email: str) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(f"SELECT {USER_COLUMNS} FROM ltc.user_account WHERE email = %s", (email,))
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def list_user_summaries(
        self,
        account_type: str | None,
        region_code: str | None,
        sales_tier: str | None,
        status: str | None,
        query: str | None,
        cursor: tuple[str, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        predicates = ["1=1"]
        params: list[object] = []
        if account_type is not None:
            predicates.append("ua.account_type = %s")
            params.append(account_type)
        if region_code is not None:
            predicates.append("ua.region_code = %s")
            params.append(region_code)
        if sales_tier is not None:
            predicates.append("ua.sales_tier = %s")
            params.append(sales_tier)
        if status is not None:
            predicates.append("ua.status = %s")
            params.append(status)
        if query:
            predicates.append("(ua.display_name ILIKE %s OR ua.username ILIKE %s)")
            query_pattern = f"%{query.strip()}%"
            params.extend((query_pattern, query_pattern))
        if cursor is not None:
            predicates.append("(lower(ua.username), ua.user_id) > (%s, %s)")
            params.extend(cursor)
        params.append(limit)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT ua.user_id, ua.username, ua.display_name, ua.email,
                       ua.account_type, ua.status, ua.sales_tier, ua.region_code,
                       ua.capacity_limit, ua.version,
                       COUNT(la.assignment_id)::integer AS active_assignment_count
                FROM ltc.user_account ua
                LEFT JOIN ltc.lead_assignment la
                  ON la.assignee_user_id = ua.user_id AND la.status = 'active'
                WHERE {' AND '.join(predicates)}
                GROUP BY ua.user_id
                ORDER BY lower(ua.username), ua.user_id
                LIMIT %s
                """,
                params,
            )
            return list(cursor.fetchall())

    def create_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        email: str | None,
        account_type: str,
        sales_tier: str | None,
        region_code: str | None,
        capacity_limit: int | None,
    ) -> UserAccount:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                INSERT INTO ltc.user_account
                    (username, password_hash, display_name, email, account_type,
                     sales_tier, region_code, capacity_limit)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING {USER_COLUMNS}
                """,
                (username, password_hash, display_name, email, account_type,
                 sales_tier, region_code, capacity_limit),
            )
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("created user update returned no row")
        return _user_from_row(row)

    def update_user_profile(
        self,
        user_id: UUID,
        expected_version: int,
        display_name: str | None,
        email: str | None,
        email_present: bool,
    ) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.user_account
                SET display_name = COALESCE(%s, display_name),
                    email = CASE WHEN %s THEN %s ELSE email END,
                    version = version + 1, updated_at = clock_timestamp()
                WHERE user_id = %s AND version = %s
                RETURNING {USER_COLUMNS}
                """,
                (display_name, email_present, email, user_id, expected_version),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def set_user_status(self, user_id: UUID, expected_version: int, status: str) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.user_account
                SET status = %s, token_version = token_version + 1,
                    version = version + 1, updated_at = clock_timestamp()
                WHERE user_id = %s AND version = %s
                RETURNING {USER_COLUMNS}
                """,
                (status, user_id, expected_version),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def unlock_user(self, user_id: UUID, expected_version: int) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.user_account
                SET failed_login_attempts = 0, locked_until = NULL,
                    version = version + 1, updated_at = clock_timestamp()
                WHERE user_id = %s AND version = %s
                RETURNING {USER_COLUMNS}
                """,
                (user_id, expected_version),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def reset_user_password(self, user_id: UUID, expected_version: int, password_hash: str) -> UserAccount | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.user_account
                SET password_hash = %s, failed_login_attempts = 0, locked_until = NULL,
                    token_version = token_version + 1, version = version + 1,
                    updated_at = clock_timestamp()
                WHERE user_id = %s AND version = %s
                RETURNING {USER_COLUMNS}
                """,
                (password_hash, user_id, expected_version),
            )
            row = cursor.fetchone()
        return _user_from_row(row) if row else None

    def mark_user_departed(self, user_id: UUID, departed_by: UUID, reason_text: str, departed_at: datetime) -> UserAccount:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""UPDATE ltc.user_account SET status='departed', departed_at=%s, departed_by=%s,
                departure_reason=%s, token_version=token_version + 1, version=version + 1,
                updated_at=clock_timestamp() WHERE user_id=%s RETURNING {USER_COLUMNS}""",
                (departed_at, departed_by, reason_text, user_id),
            )
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("departed user update returned no row")
        return _user_from_row(row)

    def revoke_all_sessions(self, user_id: UUID, reason: str, revoked_at: datetime) -> None:
        self._connection.execute(
            "UPDATE ltc.auth_session SET revoked_at=%s, revoke_reason=%s WHERE user_id=%s AND revoked_at IS NULL",
            (revoked_at, reason, user_id),
        )

    def find_idempotency_record(self, scope: str, principal_id: str, idempotency_key: str) -> dict[str, object] | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT request_hash, state, response_body FROM ltc.idempotency_record
                WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s
                FOR UPDATE""",
                (scope, principal_id, idempotency_key),
            )
            return cursor.fetchone()

    def create_idempotency_record(self, scope: str, principal_id: str, actor_user_id: UUID, idempotency_key: str, request_hash: str, expires_at: datetime) -> None:
        self._connection.execute(
            """INSERT INTO ltc.idempotency_record
            (scope, principal_type, principal_id, actor_user_id, idempotency_key, request_hash, state, expires_at)
            VALUES (%s,'user',%s,%s,%s,%s,'in_progress',%s)""",
            (scope, principal_id, actor_user_id, idempotency_key, request_hash, expires_at),
        )

    def complete_idempotency_record(self, scope: str, principal_id: str, idempotency_key: str, response_body: dict[str, object], response_status: int) -> None:
        self._connection.execute(
            """UPDATE ltc.idempotency_record SET state='completed', response_status=%s,
            response_body=%s::jsonb, updated_at=clock_timestamp()
            WHERE scope=%s AND principal_type='user' AND principal_id=%s AND idempotency_key=%s""",
            (response_status, json.dumps(response_body), scope, principal_id, idempotency_key),
        )

    def append_user_departed_audit_and_outbox(self, user: UserAccount, actor_user_id: UUID, reason_text: str, release: object, request_id: str, occurred_at: datetime) -> None:
        released_count = int(release.released_lead_count)
        handover_count = int(getattr(release, "handover_lead_count", released_count))
        pools = list(release.returned_pools)
        self._connection.execute(
            """INSERT INTO ltc.audit_log (actor_user_id, action, resource_type, resource_id, request_id, before_data, after_data, metadata)
            VALUES (%s, 'depart', 'user_account', %s, %s, jsonb_build_object('status','active'),
                    jsonb_build_object('status','departed'), jsonb_build_object('reason',%s::text,'handover_lead_count',%s::integer))""",
            (actor_user_id, user.user_id, request_id, reason_text, handover_count),
        )
        self._connection.execute(
            """INSERT INTO ltc.outbox_event (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
            VALUES ('iam.sales_departed.v1', 'iam', 'user_account', %s, %s,
                    jsonb_build_object('user_id',%s,'departed_by',%s,'released_lead_count',%s,'handover_lead_count',%s,'returned_pools',%s::jsonb,'departed_at',%s), %s)""",
            (user.user_id, user.version, user.user_id, actor_user_id, released_count, handover_count, json.dumps(pools), occurred_at, UUID(request_id)),
        )

    def append_audit(
        self,
        actor_user_id: UUID,
        action: str,
        resource_id: UUID,
        request_id: str,
        before_data: dict[str, object] | None,
        after_data: dict[str, object] | None,
        metadata: dict[str, object],
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO ltc.audit_log
                (actor_user_id, action, resource_type, resource_id, request_id,
                 before_data, after_data, metadata)
            VALUES (%s,%s,'user_account',%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
            """,
            (actor_user_id, action, resource_id, request_id,
             json.dumps(before_data) if before_data is not None else None,
             json.dumps(after_data) if after_data is not None else None,
             json.dumps(metadata)),
        )

    def append_outbox(
        self,
        event_type: str,
        producer: str,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        payload: dict[str, object],
        correlation_id: UUID,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO ltc.outbox_event
                (event_type, producer, aggregate_type, aggregate_id,
                 aggregate_version, payload, correlation_id)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
            """,
            (event_type, producer, aggregate_type, aggregate_id,
             aggregate_version, json.dumps(payload), correlation_id),
        )

    def record_login_failure(self, user_id: UUID, attempts: int, locked_until: datetime | None) -> None:
        self._connection.execute(
            """
            UPDATE ltc.user_account
            SET failed_login_attempts = %s,
                locked_until = %s,
                version = version + 1,
                updated_at = clock_timestamp()
            WHERE user_id = %s
            """,
            (attempts, locked_until, user_id),
        )

    def append_login_lock_audit_and_outbox(
        self,
        user: UserAccount,
        attempts: int,
        locked_until: datetime,
        request_id: str,
        occurred_at: datetime,
    ) -> None:
        correlation_id = UUID(request_id)
        payload = {
            "user_id": str(user.user_id),
            "username": user.username,
            "notify_user_id": str(user.user_id),
            "notification_kind": "login_locked",
            "failed_login_attempts": attempts,
            "locked_until": locked_until.isoformat(),
            "occurred_at": occurred_at.isoformat(),
        }
        self._connection.execute(
            """
            INSERT INTO ltc.audit_log
                (action, resource_type, resource_id, request_id, before_data, after_data, metadata)
            VALUES ('login_locked', 'user_account', %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            """,
            (
                user.user_id,
                request_id,
                json.dumps({"failed_login_attempts": user.failed_login_attempts, "locked_until": None}),
                json.dumps({"failed_login_attempts": attempts, "locked_until": locked_until.isoformat()}),
                json.dumps({"notification_kind": "login_locked"}),
            ),
        )
        self._connection.execute(
            """
            INSERT INTO ltc.outbox_event
                (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
            VALUES ('notification.user_login_locked.v1', 'iam', 'user_account', %s, %s, %s::jsonb, %s)
            """,
            (user.user_id, user.version + 1, json.dumps(payload), correlation_id),
        )

    def reset_login_failures(self, user_id: UUID, logged_in_at: datetime) -> None:
        self._connection.execute(
            """
            UPDATE ltc.user_account
            SET failed_login_attempts = 0,
                locked_until = NULL,
                last_login_at = %s,
                version = version + 1,
                updated_at = clock_timestamp()
            WHERE user_id = %s
            """,
            (logged_in_at, user_id),
        )

    def create_session(
        self,
        user_id: UUID,
        issued_token_version: int,
        refresh_token_hash: str,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO ltc.auth_session (
                    user_id, issued_token_version, refresh_token_hash, expires_at, ip_address, user_agent, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, %s, clock_timestamp())
                RETURNING session_id, user_id, issued_token_version, refresh_token_hash, expires_at, revoked_at
                """,
                (user_id, issued_token_version, refresh_token_hash, expires_at, ip_address, user_agent),
            )
            row = cursor.fetchone()
        return _session_from_row(row)

    def find_session_by_id(self, session_id: UUID) -> AuthSession | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT session_id, user_id, issued_token_version, refresh_token_hash, expires_at, revoked_at
                FROM ltc.auth_session WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cursor.fetchone()
        return _session_from_row(row) if row else None

    def find_session_by_refresh_hash_for_update(self, refresh_token_hash: str) -> AuthSession | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT session_id, user_id, issued_token_version, refresh_token_hash, expires_at, revoked_at
                FROM ltc.auth_session WHERE refresh_token_hash = %s FOR UPDATE
                """,
                (refresh_token_hash,),
            )
            row = cursor.fetchone()
        return _session_from_row(row) if row else None

    def rotate_session(
        self,
        session_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        seen_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            UPDATE ltc.auth_session
            SET refresh_token_hash = %s, expires_at = %s, last_seen_at = %s
            WHERE session_id = %s AND revoked_at IS NULL
            """,
            (refresh_token_hash, expires_at, seen_at, session_id),
        )

    def revoke_session(self, session_id: UUID, reason: str, revoked_at: datetime) -> None:
        self._connection.execute(
            """
            UPDATE ltc.auth_session
            SET revoked_at = %s, revoke_reason = %s
            WHERE session_id = %s AND revoked_at IS NULL
            """,
            (revoked_at, reason, session_id),
        )


class PostgresIamUnitOfWork:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    @contextmanager
    def transaction(self) -> Iterator[PostgresIamRepository]:
        with self._database.transaction() as connection:
            yield PostgresIamRepository(connection)
