"""Ports used by IAM application services."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ltc.modules.iam.domain.models import AuthSession, UserAccount


@dataclass(frozen=True)
class DepartureReleaseResult:
    released_lead_count: int
    returned_pools: tuple[dict[str, object], ...]
    handover_lead_count: int = 0


class SalesDeparturePort(Protocol):
    def release_departed_sales(
        self,
        connection: object,
        departed_user_id: UUID,
        departed_by: UUID,
        reason_text: str,
        request_id: str,
        occurred_at: datetime,
    ) -> "DepartureReleaseResult": ...


class PasswordVerifier(Protocol):
    def verify(self, password: str, password_hash: str) -> bool: ...

    def hash(self, password: str) -> str: ...


class IamRepository(Protocol):
    @property
    def connection(self) -> object: ...
    def find_user_by_username_for_update(self, username: str) -> UserAccount | None: ...

    def find_user_by_id(self, user_id: UUID) -> UserAccount | None: ...

    def find_user_by_id_for_update(self, user_id: UUID) -> UserAccount | None: ...

    def find_user_by_email(self, email: str) -> UserAccount | None: ...

    def find_user_by_username(self, username: str) -> UserAccount | None: ...

    def active_assignment_count(self, user_id: UUID) -> int: ...

    def list_user_summaries(
        self,
        account_type: str | None,
        region_code: str | None,
        sales_tier: str | None,
        status: str | None,
        query: str | None,
        cursor: tuple[str, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]: ...

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
    ) -> UserAccount: ...

    def update_user_profile(
        self,
        user_id: UUID,
        expected_version: int,
        display_name: str | None,
        email: str | None,
        email_present: bool,
    ) -> UserAccount | None: ...

    def set_user_status(
        self,
        user_id: UUID,
        expected_version: int,
        status: str,
    ) -> UserAccount | None: ...

    def unlock_user(self, user_id: UUID, expected_version: int) -> UserAccount | None: ...

    def reset_user_password(
        self,
        user_id: UUID,
        expected_version: int,
        password_hash: str,
    ) -> UserAccount | None: ...

    def append_audit(
        self,
        actor_user_id: UUID,
        action: str,
        resource_id: UUID,
        request_id: str,
        before_data: dict[str, object] | None,
        after_data: dict[str, object] | None,
        metadata: dict[str, object],
    ) -> None: ...

    def append_outbox(
        self,
        event_type: str,
        producer: str,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        payload: dict[str, object],
        correlation_id: UUID,
    ) -> None: ...

    def mark_user_departed(self, user_id: UUID, departed_by: UUID, reason_text: str, departed_at: datetime) -> UserAccount: ...

    def revoke_all_sessions(self, user_id: UUID, reason: str, revoked_at: datetime) -> None: ...

    def find_idempotency_record(self, scope: str, principal_id: str, idempotency_key: str) -> dict[str, object] | None: ...

    def create_idempotency_record(
        self,
        scope: str,
        principal_id: str,
        actor_user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        expires_at: datetime,
    ) -> None: ...

    def complete_idempotency_record(
        self,
        scope: str,
        principal_id: str,
        idempotency_key: str,
        response_body: dict[str, object],
        response_status: int,
    ) -> None: ...

    def append_user_departed_audit_and_outbox(self, user: UserAccount, actor_user_id: UUID, reason_text: str, release: DepartureReleaseResult, request_id: str, occurred_at: datetime) -> None: ...

    def record_login_failure(self, user_id: UUID, attempts: int, locked_until: datetime | None) -> None: ...

    def append_login_lock_audit_and_outbox(
        self,
        user: UserAccount,
        attempts: int,
        locked_until: datetime,
        request_id: str,
        occurred_at: datetime,
    ) -> None: ...

    def reset_login_failures(self, user_id: UUID, logged_in_at: datetime) -> None: ...

    def create_session(
        self,
        user_id: UUID,
        issued_token_version: int,
        refresh_token_hash: str,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession: ...

    def find_session_by_id(self, session_id: UUID) -> AuthSession | None: ...

    def find_session_by_refresh_hash_for_update(self, refresh_token_hash: str) -> AuthSession | None: ...

    def rotate_session(
        self,
        session_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        seen_at: datetime,
    ) -> None: ...

    def revoke_session(self, session_id: UUID, reason: str, revoked_at: datetime) -> None: ...


class IamUnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[IamRepository]: ...
