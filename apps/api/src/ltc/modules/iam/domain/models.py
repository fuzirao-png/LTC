"""Framework-free IAM domain values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


AccountType = Literal["sales", "strategic"]
AccountStatus = Literal["active", "disabled", "departed"]
SalesTier = Literal["MA", "SA", "A"]
RegionCode = Literal["NA", "EA", "SEA", "EU", "ME", "OTHER"]


@dataclass(frozen=True)
class UserAccount:
    user_id: UUID
    username: str
    password_hash: str
    display_name: str
    account_type: AccountType
    sales_tier: SalesTier | None
    region_code: RegionCode | None
    capacity_limit: int | None
    status: AccountStatus
    failed_login_attempts: int
    locked_until: datetime | None
    token_version: int
    version: int
    email: str | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now

    @property
    def capabilities(self) -> tuple[str, ...]:
        if self.account_type == "strategic":
            return (
                "user.view",
                "user.manage",
                "sales_lead.view_all",
                "sales_lead.assign",
                "sales_lead.release",
                "sales.depart",
            )
        return (
            "sales_lead.view_pool",
            "sales_lead.claim",
            "sales_lead.release_own",
            "sales_lead.transfer_own",
        )


@dataclass(frozen=True)
class AuthSession:
    session_id: UUID
    user_id: UUID
    issued_token_version: int
    refresh_token_hash: str
    expires_at: datetime
    revoked_at: datetime | None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


@dataclass(frozen=True)
class CurrentActor:
    user_id: UUID
    username: str
    display_name: str
    account_type: AccountType
    sales_tier: SalesTier | None
    region_code: RegionCode | None
    capacity_limit: int | None
    token_version: int
    capabilities: tuple[str, ...]
    status: AccountStatus = "active"
    active_assignment_count: int = 0
    version: int = 0

    @classmethod
    def from_user(cls, user: UserAccount) -> "CurrentActor":
        return cls(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            account_type=user.account_type,
            sales_tier=user.sales_tier,
            region_code=user.region_code,
            capacity_limit=user.capacity_limit,
            token_version=user.token_version,
            capabilities=user.capabilities,
            status=user.status,
            version=user.version,
        )
