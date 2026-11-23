from __future__ import annotations

import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from ltc.modules.iam.application.auth_service import (
    AuthenticationError,
    AuthenticationService,
    LoginCommand,
)
from ltc.modules.iam.domain.models import AuthSession, UserAccount


class FakePasswordVerifier:
    def verify(self, password: str, password_hash: str) -> bool:
        return password == "correct" and password_hash == "hash"


class FakeRepository:
    def __init__(self, user: UserAccount) -> None:
        self.user = user
        self.sessions: dict[UUID, AuthSession] = {}
        self.failure_updates: list[tuple[int, datetime | None]] = []
        self.login_lock_audits: list[dict[str, object]] = []
        self.reset_count = 0

    def find_user_by_username_for_update(self, username: str) -> UserAccount | None:
        return self.user if self.user.username == username else None

    def find_user_by_id(self, user_id: UUID) -> UserAccount | None:
        return self.user if self.user.user_id == user_id else None

    def record_login_failure(self, user_id: UUID, attempts: int, locked_until: datetime | None) -> None:
        self.failure_updates.append((attempts, locked_until))
        self.user = replace(self.user, failed_login_attempts=attempts, locked_until=locked_until)

    def append_login_lock_audit_and_outbox(self, user: UserAccount, attempts: int, locked_until: datetime, request_id: str, occurred_at: datetime) -> None:
        self.login_lock_audits.append({
            "user_id": user.user_id,
            "attempts": attempts,
            "locked_until": locked_until,
            "request_id": request_id,
            "occurred_at": occurred_at,
        })

    def reset_login_failures(self, user_id: UUID, logged_in_at: datetime) -> None:
        self.reset_count += 1

    def create_session(self, user_id: UUID, issued_token_version: int, refresh_token_hash: str, expires_at: datetime, ip_address: str | None, user_agent: str | None) -> AuthSession:
        session = AuthSession(uuid4(), user_id, issued_token_version, refresh_token_hash, expires_at, None)
        self.sessions[session.session_id] = session
        return session

    def find_session_by_id(self, session_id: UUID) -> AuthSession | None:
        return self.sessions.get(session_id)

    def find_session_by_refresh_hash_for_update(self, refresh_token_hash: str) -> AuthSession | None:
        return next((session for session in self.sessions.values() if session.refresh_token_hash == refresh_token_hash), None)

    def rotate_session(self, session_id: UUID, refresh_token_hash: str, expires_at: datetime, seen_at: datetime) -> None:
        session = self.sessions[session_id]
        self.sessions[session_id] = AuthSession(session.session_id, session.user_id, session.issued_token_version, refresh_token_hash, expires_at, session.revoked_at)

    def revoke_session(self, session_id: UUID, reason: str, revoked_at: datetime) -> None:
        session = self.sessions[session_id]
        self.sessions[session_id] = AuthSession(session.session_id, session.user_id, session.issued_token_version, session.refresh_token_hash, session.expires_at, revoked_at)


class FakeUnitOfWork:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository

    @contextmanager
    def transaction(self):
        yield self.repository


def make_user(**overrides: object) -> UserAccount:
    values: dict[str, object] = {
        "user_id": uuid4(),
        "username": "ma.east",
        "password_hash": "hash",
        "display_name": "Lin Wei",
        "account_type": "sales",
        "sales_tier": "MA",
        "region_code": "EA",
        "capacity_limit": 15,
        "status": "active",
        "failed_login_attempts": 0,
        "locked_until": None,
        "token_version": 1,
        "version": 0,
    }
    values.update(overrides)
    return UserAccount(**values)


class IamApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 20, tzinfo=timezone.utc)

    def test_sales_login_returns_region_tier_capacity_and_capabilities(self) -> None:
        repository = FakeRepository(make_user())
        service = AuthenticationService(FakeUnitOfWork(repository), FakePasswordVerifier())

        result = service.login(
            LoginCommand("ma.east", "correct", "refresh-hash", self.now + timedelta(days=7), None, None),
            now=self.now,
        )

        self.assertEqual(result.actor.region_code, "EA")
        self.assertEqual(result.actor.sales_tier, "MA")
        self.assertEqual(result.actor.capacity_limit, 15)
        self.assertIn("sales_lead.view_pool", result.actor.capabilities)

    def test_fifth_wrong_password_locks_the_user(self) -> None:
        repository = FakeRepository(make_user())
        service = AuthenticationService(FakeUnitOfWork(repository), FakePasswordVerifier())

        for _ in range(4):
            with self.assertRaisesRegex(AuthenticationError, "AUTH_INVALID_CREDENTIALS"):
                service.login(LoginCommand("ma.east", "wrong", "hash", self.now + timedelta(days=7), None, None), self.now)
        with self.assertRaisesRegex(AuthenticationError, "USER_LOCKED"):
            service.login(LoginCommand("ma.east", "wrong", "hash", self.now + timedelta(days=7), None, None), self.now)

        self.assertEqual(repository.failure_updates[-1][0], 5)
        self.assertIsNotNone(repository.failure_updates[-1][1])
        self.assertEqual(len(repository.login_lock_audits), 1)
        self.assertEqual(repository.login_lock_audits[0]["attempts"], 5)

    def test_disabled_and_departed_accounts_cannot_login(self) -> None:
        for account_status, code in (("disabled", "USER_DISABLED"), ("departed", "USER_DEPARTED")):
            repository = FakeRepository(make_user(status=account_status))
            service = AuthenticationService(FakeUnitOfWork(repository), FakePasswordVerifier())
            with self.assertRaisesRegex(AuthenticationError, code):
                service.login(LoginCommand("ma.east", "correct", "hash", self.now + timedelta(days=7), None, None), self.now)


if __name__ == "__main__":
    unittest.main()
