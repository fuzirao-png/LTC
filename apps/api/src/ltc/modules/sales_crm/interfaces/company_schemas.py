"""Company and Contact CRUD schemas (PRD §4.9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Company ──────────────────────────────────────────────────────────

class CompanyResponse(BaseModel):
    company_id: UUID
    origin_candidate_id: UUID | None = None
    company_name: str
    normalized_company_name: str
    legal_name: str | None = None
    primary_domain: str | None = None
    website: str | None = None
    country_code: str | None = None
    region_code: str | None = None
    region_mapping_version: str | None = None
    city: str | None = None
    industry_code: str | None = None
    company_intro: str | None = None
    employee_count: int | None = None
    lifecycle_status: str
    version: int
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CompanyDetailResponse(BaseModel):
    request_id: UUID
    data: CompanyResponse


class PatchCompanyRequest(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=500)
    legal_name: str | None = Field(default=None, max_length=500)
    primary_domain: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=1000)
    country_code: str | None = Field(default=None, max_length=10)
    region_code: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=200)
    industry_code: str | None = Field(default=None, max_length=100)
    company_intro: str | None = Field(default=None, max_length=5000)
    employee_count: int | None = Field(default=None, ge=0)
    lifecycle_status: str | None = Field(default=None, pattern=r"^(prospect|active|customer|churned|archived)$")


# ── Contact ──────────────────────────────────────────────────────────

class ContactResponse(BaseModel):
    contact_id: UUID
    company_id: UUID
    source_candidate_contact_id: UUID | None = None
    full_name: str
    normalized_name: str
    title: str | None = None
    title_normalized: str | None = None
    department: str | None = None
    relationship_role: str | None = None
    priority: str | None = None
    primary_email: str | None = None
    normalized_email: str | None = None
    email_status: str
    email_type: str | None = None
    email_score: float | None = None
    email_pattern: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    source: str
    last_contacted_at: datetime | None = None
    employment_status: str = "unknown"
    legal_basis_status: str = "unknown"
    last_verified_at: datetime | None = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    request_id: UUID
    data: list[ContactResponse]


class ContactDetailResponse(BaseModel):
    request_id: UUID
    data: ContactResponse


class CreateContactRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    department: str | None = Field(default=None, max_length=200)
    relationship_role: str | None = Field(default=None, pattern=r"^(decision_maker|influencer|executor|general_employee)$")
    priority: str | None = Field(default=None, pattern=r"^(P1|P2|P3)$")
    primary_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    linkedin_url: str | None = Field(default=None, max_length=500)
    employment_status: str = Field(default="unknown", pattern=r"^(unknown|active|departed)$")
    legal_basis_status: str = Field(default="unknown", pattern=r"^(unknown|allowed|blocked)$")
    last_verified_at: datetime | None = None


class PatchContactRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    department: str | None = Field(default=None, max_length=200)
    relationship_role: str | None = Field(default=None, pattern=r"^(decision_maker|influencer|executor|general_employee)$")
    priority: str | None = Field(default=None, pattern=r"^(P1|P2|P3)$")
    primary_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    linkedin_url: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|archived)$")
    employment_status: str | None = Field(default=None, pattern=r"^(unknown|active|departed)$")
    legal_basis_status: str | None = Field(default=None, pattern=r"^(unknown|allowed|blocked)$")
    last_verified_at: datetime | None = None


class ContactRosterMutationRequest(BaseModel):
    action: Literal["activate", "backup", "pin", "unpin", "move"]
    position: int | None = Field(default=None, ge=1, le=5)
    replace_contact_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)


class ContactRosterResponse(BaseModel):
    request_id: UUID
    data: dict[str, Any]


# ── Timeline ─────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    event_id: UUID
    event_type: str  # stage_transition | email | meeting | task | activity | report
    occurred_at: datetime
    title: str
    description: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    request_id: UUID
    data: list[TimelineEvent]
    page: dict[str, object]
