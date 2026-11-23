from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyResponse(BaseModel):
    request_id: UUID
    data: dict[str, Any]


class CompanyPatchRequest(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=300)
    legal_name: str | None = Field(default=None, max_length=300)
    website: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=200)
    industry_code: Literal["TMC", "TRAVEL_OTA", "FINTECH", "OTHER"] | None = None
    company_intro: str | None = Field(default=None, max_length=5000)
    employee_count: int | None = Field(default=None, ge=0)


class ContactListResponse(BaseModel):
    request_id: UUID
    data: list[dict[str, Any]]


class ContactWriteRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    relationship_role: Literal["decision_maker", "influencer", "executor", "general_employee"] | None = None
    priority: Literal["P1", "P2", "P3"] | None = None
    primary_email: str | None = None
    normalized_email: str | None = None
    email_status: Literal["unknown", "valid", "invalid", "risky", "opted_out", "bounced"] | None = None
    phone: str | None = None
    linkedin_url: str | None = None


class ContactResponse(BaseModel):
    request_id: UUID
    data: dict[str, Any]
