"""Login and session application services."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace as dataclass_replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.domain.ports import IamUnitOfWork, PasswordVerifier, SalesDeparturePort


MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_DURATION = timedelta(minutes=30)


class AuthenticationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LoginCommand:
    username: str
    password: str
    refresh_token_hash: str
    refresh_expires_at: datetime
    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True)
class RefreshCommand:
    refresh_token_hash: str
    new_refresh_token_hash: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    actor: CurrentActor
    session_id: UUID


@dataclass(frozen=True)
class DepartSalesResult:
    user_id: UUID
    status: str
    released_lead_count: int
    returned_pools: tuple[dict[str, object], ...]
    departed_at: datetime
    handover_lead_count: int = 0

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["user_id"] = str(self.user_id)
        result["departed_at"] = self.departed_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DepartSalesResult":
        return cls(
            user_id=UUID(str(value["user_id"])),
            status=str(value["status"]),
            released_lead_count=int(value["released_lead_count"]),
            returned_pools=tuple(value["returned_pools"]),
            departed_at=datetime.fromisoformat(str(value["departed_at"])),
            handover_lead_count=int(value.get("handover_lead_count", value.get("released_lead_count", 0))),
        )


@dataclass(frozen=True)
class DepartSalesCommand:
    target_user_id: UUID
    actor_user_id: UUID
    reason_text: str
    expected_version: int
    request_id: str
    idempotency_key: str


class AuthenticationService:
    def __init__(self, unit_of_work: IamUnitOfWork, password_verifier: PasswordVerifier) -> None:
        self._unit_of_work = unit_of_work
        self._password_verifier = password_verifier

    @staticmethod
    def _assignment_count(repository: object, user_id: UUID) -> int:
        # Keep lightweight unit-test repositories compatible with the production port.
        counter = getattr(repository, "active_assignment_count", None)
        return int(counter(user_id)) if counter is not None else 0

    def depart_sales(
        self,
        command: DepartSalesCommand,
        sales_departure_port: SalesDeparturePort,
        now: datetime | None = None,
    ) -> "DepartSalesResult":
        occurred_at = now or datetime.now(timezone.utc)
        request_hash = sha256(
            json.dumps(
                {
                    "target_user_id": str(command.target_user_id),
                    "reason_text": command.reason_text,
                    "expected_version": command.expected_version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self._unit_of_work.transaction() as repository:
            actor = repository.find_user_by_id(command.actor_user_id)
            if actor is None or actor.status != "active" or actor.account_type != "strategic":
                raise AuthenticationError("FORBIDDEN_STRATEGIC_REQUIRED")
            principal_id = str(actor.user_id)
            existing = repository.find_idempotency_record("depart_sales", principal_id, command.idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if existing.get("state") == "completed" and isinstance(existing.get("response_body"), dict):
                    return DepartSalesResult.from_dict(existing["response_body"])
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record(
                scope="depart_sales",
                principal_id=principal_id,
                actor_user_id=actor.user_id,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                expires_at=occurred_at + timedelta(days=1),
            )
            target = repository.find_user_by_id_for_update(command.target_user_id)
            if target is None:
                raise AuthenticationError("USER_NOT_FOUND")
            if target.account_type != "sales":
                raise AuthenticationError("TARGET_NOT_SALES")
            if target.status == "departed":
                raise AuthenticationError("USER_ALREADY_DEPARTED")
            if target.status not in ("active", "disabled"):
                raise AuthenticationError("INVALID_USER_STATUS")
            if target.version != command.expected_version:
                raise AuthenticationError("USER_VERSION_CONFLICT")

            departed = repository.mark_user_departed(
                target.user_id,
                actor.user_id,
                command.reason_text,
                occurred_at,
            )
            repository.revoke_all_sessions(target.user_id, "departed", occurred_at)
            release = sales_departure_port.release_departed_sales(
                connection=repository.connection,
                departed_user_id=target.user_id,
                departed_by=actor.user_id,
                reason_text=command.reason_text,
                request_id=command.request_id,
                occurred_at=occurred_at,
            )
            repository.append_user_departed_audit_and_outbox(
                user=departed,
                actor_user_id=actor.user_id,
                reason_text=command.reason_text,
                release=release,
                request_id=command.request_id,
                occurred_at=occurred_at,
            )
            result = DepartSalesResult(
                user_id=departed.user_id,
                status="departed",
                released_lead_count=release.released_lead_count,
                returned_pools=release.returned_pools,
                departed_at=occurred_at,
                handover_lead_count=release.handover_lead_count,
            )
            repository.complete_idempotency_record(
                scope="depart_sales",
                principal_id=principal_id,
                idempotency_key=command.idempotency_key,
                response_body=result.to_dict(),
                response_status=200,
            )
            return result

    def login(self, command: LoginCommand, now: datetime | None = None) -> AuthenticatedSession:
        occurred_at = now or datetime.now(timezone.utc)
        username = command.username.strip()
        with self._unit_of_work.transaction() as repository:
            user = repository.find_user_by_username_for_update(username)
            if user is None:
                raise AuthenticationError("AUTH_INVALID_CREDENTIALS")
            if user.status == "disabled":
                raise AuthenticationError("USER_DISABLED")
            if user.status == "departed":
                raise AuthenticationError("USER_DEPARTED")
            if user.is_locked(occurred_at):
                raise AuthenticationError("USER_LOCKED")
            if not self._password_verifier.verify(command.password, user.password_hash):
                attempts = user.failed_login_attempts + 1
                locked_until = occurred_at + LOGIN_LOCK_DURATION if attempts >= MAX_LOGIN_FAILURES else None
                repository.record_login_failure(user.user_id, attempts, locked_until)
                if locked_until is not None:
                    repository.append_login_lock_audit_and_outbox(
                        user=user,
                        attempts=attempts,
                        locked_until=locked_until,
                        request_id=str(uuid4()),
                        occurred_at=occurred_at,
                    )
                    raise AuthenticationError("USER_LOCKED")
                raise AuthenticationError("AUTH_INVALID_CREDENTIALS")

            repository.reset_login_failures(user.user_id, occurred_at)
            session = repository.create_session(
                user_id=user.user_id,
                issued_token_version=user.token_version,
                refresh_token_hash=command.refresh_token_hash,
                expires_at=command.refresh_expires_at,
                ip_address=command.ip_address,
                user_agent=command.user_agent,
            )
            actor = dataclass_replace(CurrentActor.from_user(user), active_assignment_count=self._assignment_count(repository, user.user_id))
            return AuthenticatedSession(actor=actor, session_id=session.session_id)

    def refresh(self, command: RefreshCommand, now: datetime | None = None) -> AuthenticatedSession:
        occurred_at = now or datetime.now(timezone.utc)
        with self._unit_of_work.transaction() as repository:
            session = repository.find_session_by_refresh_hash_for_update(command.refresh_token_hash)
            if session is None or not session.is_active(occurred_at):
                raise AuthenticationError("AUTH_INVALID_SESSION")
            user = repository.find_user_by_id(session.user_id)
            if user is None or user.status != "active" or user.token_version != session.issued_token_version:
                raise AuthenticationError("AUTH_INVALID_SESSION")
            repository.rotate_session(
                session.session_id,
                command.new_refresh_token_hash,
                command.refresh_expires_at,
                occurred_at,
            )
            actor = dataclass_replace(CurrentActor.from_user(user), active_assignment_count=self._assignment_count(repository, user.user_id))
            return AuthenticatedSession(actor=actor, session_id=session.session_id)

    def get_current_actor(
        self,
        session_id: UUID,
        user_id: UUID,
        issued_token_version: int,
        now: datetime | None = None,
    ) -> CurrentActor:
        occurred_at = now or datetime.now(timezone.utc)
        with self._unit_of_work.transaction() as repository:
            session = repository.find_session_by_id(session_id)
            if session is None or not session.is_active(occurred_at):
                raise AuthenticationError("AUTH_INVALID_SESSION")
            if session.user_id != user_id or session.issued_token_version != issued_token_version:
                raise AuthenticationError("AUTH_INVALID_SESSION")
            user = repository.find_user_by_id(user_id)
            if user is None or user.status != "active" or user.token_version != issued_token_version:
                raise AuthenticationError("AUTH_INVALID_SESSION")
            return dataclass_replace(CurrentActor.from_user(user), active_assignment_count=self._assignment_count(repository, user.user_id))

    def logout(self, session_id: UUID, now: datetime | None = None) -> None:
        occurred_at = now or datetime.now(timezone.utc)
        with self._unit_of_work.transaction() as repository:
            repository.revoke_session(session_id, "logout", occurred_at)
