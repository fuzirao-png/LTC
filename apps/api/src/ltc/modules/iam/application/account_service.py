"""Strategic account-management use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from secrets import token_urlsafe
from uuid import UUID

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.domain.models import CurrentActor, UserAccount
from ltc.modules.iam.domain.ports import IamRepository, IamUnitOfWork, PasswordVerifier


@dataclass(frozen=True)
class CreateUserCommand:
    username: str
    password: str
    display_name: str
    email: str | None
    account_type: str
    sales_tier: str | None
    region_code: str | None
    capacity_limit: int | None
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class UpdateUserCommand:
    user_id: UUID
    expected_version: int
    display_name: str | None
    email: str | None
    email_present: bool
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class UserCommandResult:
    user_id: UUID
    status: str
    version: int
    active_assignment_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "user_id": str(self.user_id),
            "status": self.status,
            "version": self.version,
            "active_assignment_count": self.active_assignment_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "UserCommandResult":
        return cls(
            UUID(str(value["user_id"])),
            str(value["status"]),
            int(value["version"]),
            int(value.get("active_assignment_count", 0)),
        )


@dataclass(frozen=True)
class PasswordResetResult:
    user_id: UUID
    temporary_password: str

    def to_dict(self) -> dict[str, object]:
        return {"user_id": str(self.user_id), "temporary_password": self.temporary_password}

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PasswordResetResult":
        return cls(UUID(str(value["user_id"])), str(value["temporary_password"]))


def user_summary(row: dict[str, object]) -> dict[str, object]:
    return {
        "user_id": str(row["user_id"]),
        "username": row["username"],
        "display_name": row["display_name"],
        "email": row.get("email"),
        "account_type": row["account_type"],
        "status": row["status"],
        "sales_tier": row.get("sales_tier"),
        "region_code": row.get("region_code"),
        "capacity_limit": row.get("capacity_limit"),
        "active_assignment_count": int(row.get("active_assignment_count", 0)),
        "version": int(row.get("version", 0)),
    }


def account_summary(user: UserAccount, active_assignment_count: int = 0) -> dict[str, object]:
    return user_summary({
        "user_id": str(user.user_id),
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "account_type": user.account_type,
        "status": user.status,
        "sales_tier": user.sales_tier,
        "region_code": user.region_code,
        "capacity_limit": user.capacity_limit,
        "active_assignment_count": active_assignment_count,
        "version": user.version,
    })


class AccountManagementService:
    def __init__(self, unit_of_work: IamUnitOfWork, password_hasher: PasswordVerifier) -> None:
        self._unit_of_work = unit_of_work
        self._password_hasher = password_hasher

    def _require_strategic(self, actor: CurrentActor) -> None:
        if actor.account_type != "strategic" or not actor.capabilities or actor.username == "":
            raise AuthenticationError("FORBIDDEN_STRATEGIC_REQUIRED")

    @staticmethod
    def _assignment_count(repository: object, user_id: UUID) -> int:
        counter = getattr(repository, "active_assignment_count", None)
        return int(counter(user_id)) if counter is not None else 0

    @staticmethod
    def _hash(payload: object) -> str:
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    def list_users(
        self,
        actor: CurrentActor,
        account_type: str | None,
        region_code: str | None,
        sales_tier: str | None,
        status: str | None,
        query: str | None,
        cursor: tuple[str, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self._require_strategic(actor)
        with self._unit_of_work.transaction() as repository:
            return [user_summary(row) for row in repository.list_user_summaries(account_type, region_code, sales_tier, status, query, cursor, limit)]

    def create_user(self, actor: CurrentActor, command: CreateUserCommand) -> dict[str, object]:
        self._require_strategic(actor)
        username = command.username.strip()
        email = command.email.strip().lower() if command.email else None
        if command.account_type not in {"sales", "strategic"}:
            raise AuthenticationError("INVALID_ACCOUNT_TYPE")
        if command.account_type == "sales":
            if not command.sales_tier or not command.region_code or command.capacity_limit is None:
                raise AuthenticationError("SALES_ACCOUNT_ATTRIBUTES_REQUIRED")
        elif any(value is not None for value in (command.sales_tier, command.region_code, command.capacity_limit)):
            raise AuthenticationError("STRATEGIC_ACCOUNT_ATTRIBUTES_FORBIDDEN")
        payload = {
            "username": username, "password": command.password, "display_name": command.display_name,
            "email": email, "account_type": command.account_type, "sales_tier": command.sales_tier,
            "region_code": command.region_code, "capacity_limit": command.capacity_limit,
        }
        request_hash = self._hash(payload)
        with self._unit_of_work.transaction() as repository:
            existing = repository.find_idempotency_record("create_user", str(actor.user_id), command.idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if isinstance(existing.get("response_body"), dict):
                    return existing["response_body"]
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record("create_user", str(actor.user_id), actor.user_id, command.idempotency_key, request_hash, datetime.now(timezone.utc) + timedelta(days=1))
            if repository.find_user_by_username(username) is not None:
                raise AuthenticationError("USERNAME_ALREADY_EXISTS")
            if email and repository.find_user_by_email(email) is not None:
                raise AuthenticationError("EMAIL_ALREADY_EXISTS")
            user = repository.create_user(
                username, self._password_hasher.hash(command.password), command.display_name.strip(), email,
                command.account_type, command.sales_tier, command.region_code, command.capacity_limit,
            )
            result = account_summary(user, self._assignment_count(repository, user.user_id))
            repository.append_audit(actor.user_id, "create", user.user_id, command.request_id, None, result, {})
            repository.complete_idempotency_record("create_user", str(actor.user_id), command.idempotency_key, result, 201)
            return result

    def update_user(self, actor: CurrentActor, command: UpdateUserCommand) -> dict[str, object]:
        self._require_strategic(actor)
        email = command.email.strip().lower() if command.email else None
        request_hash = self._hash({
            "user_id": command.user_id,
            "expected_version": command.expected_version,
            "display_name": command.display_name,
            "email": email,
            "email_present": command.email_present,
        })
        with self._unit_of_work.transaction() as repository:
            existing = repository.find_idempotency_record("update_user", str(actor.user_id), command.idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if isinstance(existing.get("response_body"), dict):
                    return existing["response_body"]
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record("update_user", str(actor.user_id), actor.user_id, command.idempotency_key, request_hash, datetime.now(timezone.utc) + timedelta(days=1))
            target = repository.find_user_by_id_for_update(command.user_id)
            if target is None:
                raise AuthenticationError("USER_NOT_FOUND")
            if target.version != command.expected_version:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            if command.email_present and email and repository.find_user_by_email(email) not in (None, target):
                raise AuthenticationError("EMAIL_ALREADY_EXISTS")
            updated = repository.update_user_profile(
                command.user_id, command.expected_version, command.display_name.strip() if command.display_name else None,
                email if command.email_present else None,
                command.email_present,
            )
            if updated is None:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            result = account_summary(updated, self._assignment_count(repository, updated.user_id))
            repository.append_audit(
                actor.user_id,
                "update",
                updated.user_id,
                command.request_id,
                account_summary(target, self._assignment_count(repository, target.user_id)),
                result,
                {},
            )
            repository.complete_idempotency_record("update_user", str(actor.user_id), command.idempotency_key, result, 200)
            return result

    def _status_command(
        self,
        actor: CurrentActor,
        user_id: UUID,
        expected_version: int,
        target_status: str,
        action: str,
        idempotency_key: str,
        request_id: str,
    ) -> UserCommandResult:
        self._require_strategic(actor)
        request_hash = self._hash({"user_id": user_id, "expected_version": expected_version, "status": target_status})
        with self._unit_of_work.transaction() as repository:
            existing = repository.find_idempotency_record(action, str(actor.user_id), idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if isinstance(existing.get("response_body"), dict):
                    return UserCommandResult.from_dict(existing["response_body"])
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record(action, str(actor.user_id), actor.user_id, idempotency_key, request_hash, datetime.now(timezone.utc) + timedelta(days=1))
            target = repository.find_user_by_id_for_update(user_id)
            if target is None:
                raise AuthenticationError("USER_NOT_FOUND")
            if target.status == "departed":
                raise AuthenticationError("USER_ALREADY_DEPARTED")
            if action == "disable_user" and target.status != "active":
                raise AuthenticationError("INVALID_USER_STATUS")
            if action == "enable_user" and target.status != "disabled":
                raise AuthenticationError("INVALID_USER_STATUS")
            if target.version != expected_version:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            updated = repository.set_user_status(user_id, expected_version, target_status)
            if updated is None:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            if action == "disable_user":
                repository.revoke_all_sessions(user_id, "disabled", datetime.now(timezone.utc))
                repository.append_outbox("iam.user_disabled.v1", "iam", "user_account", user_id, updated.version, {"user_id": str(user_id), "token_version": updated.token_version, "disabled_at": datetime.now(timezone.utc).isoformat()}, UUID(request_id))
            result = UserCommandResult(
                updated.user_id,
                updated.status,
                updated.version,
                self._assignment_count(repository, updated.user_id),
            )
            repository.append_audit(actor.user_id, action, updated.user_id, request_id, {"status": target.status}, {"status": updated.status}, {})
            repository.complete_idempotency_record(action, str(actor.user_id), idempotency_key, result.to_dict(), 200)
            return result

    def disable_user(
        self,
        actor: CurrentActor,
        user_id: UUID,
        expected_version: int,
        idempotency_key: str,
        request_id: str,
    ) -> UserCommandResult:
        return self._status_command(
            actor, user_id, expected_version, "disabled", "disable_user", idempotency_key, request_id
        )

    def enable_user(
        self,
        actor: CurrentActor,
        user_id: UUID,
        expected_version: int,
        idempotency_key: str,
        request_id: str,
    ) -> UserCommandResult:
        return self._status_command(
            actor, user_id, expected_version, "active", "enable_user", idempotency_key, request_id
        )

    def unlock_user(self, actor: CurrentActor, user_id: UUID, expected_version: int, idempotency_key: str, request_id: str) -> UserCommandResult:
        self._require_strategic(actor)
        request_hash = self._hash({"user_id": user_id, "expected_version": expected_version})
        with self._unit_of_work.transaction() as repository:
            existing = repository.find_idempotency_record("unlock_user", str(actor.user_id), idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if isinstance(existing.get("response_body"), dict):
                    return UserCommandResult.from_dict(existing["response_body"])
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record("unlock_user", str(actor.user_id), actor.user_id, idempotency_key, request_hash, datetime.now(timezone.utc) + timedelta(days=1))
            target = repository.find_user_by_id_for_update(user_id)
            if target is None:
                raise AuthenticationError("USER_NOT_FOUND")
            if target.status == "departed":
                raise AuthenticationError("USER_ALREADY_DEPARTED")
            if target.version != expected_version:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            updated = repository.unlock_user(user_id, expected_version)
            if updated is None:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            result = UserCommandResult(
                updated.user_id,
                updated.status,
                updated.version,
                self._assignment_count(repository, updated.user_id),
            )
            repository.append_audit(actor.user_id, "unlock_user", updated.user_id, request_id, {"locked": True}, {"locked": False}, {})
            repository.complete_idempotency_record("unlock_user", str(actor.user_id), idempotency_key, result.to_dict(), 200)
            return result

    def reset_password(self, actor: CurrentActor, user_id: UUID, expected_version: int, idempotency_key: str, request_id: str) -> PasswordResetResult:
        self._require_strategic(actor)
        temporary_password = token_urlsafe(12)
        request_hash = self._hash({"user_id": user_id, "expected_version": expected_version})
        with self._unit_of_work.transaction() as repository:
            existing = repository.find_idempotency_record("reset_password", str(actor.user_id), idempotency_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise AuthenticationError("IDEMPOTENCY_KEY_REUSED")
                if isinstance(existing.get("response_body"), dict):
                    return PasswordResetResult.from_dict(existing["response_body"])
                raise AuthenticationError("IDEMPOTENCY_IN_PROGRESS")
            repository.create_idempotency_record("reset_password", str(actor.user_id), actor.user_id, idempotency_key, request_hash, datetime.now(timezone.utc) + timedelta(days=1))
            target = repository.find_user_by_id_for_update(user_id)
            if target is None:
                raise AuthenticationError("USER_NOT_FOUND")
            if target.status == "departed":
                raise AuthenticationError("USER_ALREADY_DEPARTED")
            if target.version != expected_version:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            updated = repository.reset_user_password(user_id, expected_version, self._password_hasher.hash(temporary_password))
            if updated is None:
                raise AuthenticationError("USER_VERSION_CONFLICT")
            repository.revoke_all_sessions(user_id, "security", datetime.now(timezone.utc))
            result = PasswordResetResult(user_id, temporary_password)
            repository.append_audit(actor.user_id, "reset_password", user_id, request_id, None, None, {"token_version": updated.token_version})
            repository.complete_idempotency_record("reset_password", str(actor.user_id), idempotency_key, result.to_dict(), 200)
            return result
