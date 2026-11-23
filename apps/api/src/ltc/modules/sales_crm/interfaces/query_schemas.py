"""Sales CRM query DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LeadListItem(BaseModel):
    lead_id: UUID
    company_id: UUID
    company_name: str
    website: str | None = None
    company_intro: str | None = None
    industry_code: str | None = None
    country_code: str | None = None
    city: str | None = None
    icp_score: float | None = None
    icp_grade: str | None = None
    required_sales_tier: str
    pool_region_code: str | None
    allocation_status: str
    pipeline_stage: str
    sla_due_at: datetime | None
    current_owner_user_id: UUID | None
    owner_name: str | None = None
    owner_username: str | None = None
    icp_score: float | None = None
    icp_grade: str | None = None
    customer_size_grade: str | None = None
    last_activity_at: datetime | None = None
    version: int


class LeadListResponse(BaseModel):
    request_id: UUID
    data: list[LeadListItem]
    page: dict[str, object]


class LeadDetail(BaseModel):
    lead_id: UUID
    company_id: UUID
    company_name: str
    required_sales_tier: str
    pool_region_code: str | None
    allocation_status: str
    pipeline_stage: str
    sla_due_at: datetime | None
    last_activity_at: datetime | None
    current_owner_user_id: UUID | None
    current_assignment_started_at: datetime | None
    first_touch_at: datetime | None
    version: int
    assignment_id: UUID | None = None
    assignee_user_id: UUID | None = None
    assigned_at: datetime | None = None
    assignment_type: str | None = None
    assignment_status: str | None = None


class LeadDetailResponse(BaseModel):
    request_id: UUID
    data: LeadDetail


class AssessmentResponse(BaseModel):
    request_id: UUID
    data: dict[str, object]
