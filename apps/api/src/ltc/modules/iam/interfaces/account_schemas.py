"""IAM account-management DTOs."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class UserSummary(BaseModel):
    user_id: UUID
    username: str
    display_name: str
    email: str | None = None
    account_type: Literal["sales", "strategic"]
    status: Literal["active", "disabled", "departed"]
    sales_tier: Literal["MA", "SA", "A"] | None = None
    region_code: Literal["NA", "EA", "SEA", "EU", "ME", "OTHER"] | None = None
    capacity_limit: int | None = None
    active_assignment_count: int = 0
    version: int = 0


class PageMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class UserListResponse(BaseModel):
    request_id: UUID
    data: list[UserSummary]
    page: PageMeta


class UserEnvelope(BaseModel):
    request_id: UUID
    data: UserSummary


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    account_type: Literal["sales", "strategic"]
    sales_tier: Literal["MA", "SA", "A"] | None = None
    region_code: Literal["NA", "EA", "SEA", "EU", "ME", "OTHER"] | None = None
    capacity_limit: int | None = Field(default=None, ge=1)


class UserPatchRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None

    @model_validator(mode="after")
    def require_value(self) -> "UserPatchRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class UserCommandData(BaseModel):
    user_id: UUID
    status: Literal["active", "disabled", "departed"]
    version: int
    active_assignment_count: int = 0


class UserCommandResponse(BaseModel):
    request_id: UUID
    data: UserCommandData


class PasswordResetData(BaseModel):
    user_id: UUID
    temporary_password: str


class PasswordResetResponse(BaseModel):
    request_id: UUID
    data: PasswordResetData
