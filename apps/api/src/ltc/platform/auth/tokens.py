"""Opaque refresh token and signed access token helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt

from ltc.platform.config import AppSettings


class AccessTokenError(ValueError):
    pass


@dataclass(frozen=True)
class AccessTokenClaims:
    session_id: UUID
    user_id: UUID
    token_version: int


def new_refresh_token() -> str:
    return token_urlsafe(48)


def refresh_token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class AccessTokenCodec:
    def __init__(self, settings: AppSettings) -> None:
        self._secret = settings.jwt_secret_key
        self._ttl = timedelta(minutes=settings.jwt_access_token_ttl_minutes)

    def issue(self, session_id: UUID, user_id: UUID, token_version: int) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sid": str(session_id),
                "sub": str(user_id),
                "tv": token_version,
                "iat": now,
                "exp": now + self._ttl,
            },
            self._secret,
            algorithm="HS256",
        )

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"], options={"require": ["sid", "sub", "tv", "iat", "exp"]})
            return AccessTokenClaims(
                session_id=UUID(payload["sid"]),
                user_id=UUID(payload["sub"]),
                token_version=int(payload["tv"]),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AccessTokenError("invalid access token") from exc
