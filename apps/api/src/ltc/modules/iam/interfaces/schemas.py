"""IAM HTTP request and response DTOs."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    user_id: UUID
    username: str
    display_name: str
    account_type: Literal["sales", "strategic"]
    sales_tier: Literal["MA", "SA", "A"] | None
    region_code: Literal["NA", "EA", "SEA", "EU", "ME", "OTHER"] | None
    capacity_limit: int | None
    status: Literal["active", "disabled", "departed"]
    active_assignment_count: int


class AuthData(BaseModel):
    user: UserResponse
    capabilities: tuple[str, ...]


class AuthResponse(BaseModel):
    request_id: UUID
    data: AuthData


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    request_id: UUID
    error: ErrorBody
