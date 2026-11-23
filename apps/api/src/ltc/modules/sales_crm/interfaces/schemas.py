"""Sales CRM HTTP response DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PoolLead(BaseModel):
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
    required_sales_tier: Literal["MA", "SA", "A"]
    pool_region_code: Literal["NA", "EA", "SEA", "EU", "ME", "OTHER"]
    allocation_status: Literal["claimable"]
    pipeline_stage: Literal["new", "contacted", "engaged", "meeting", "proposal", "won", "lost", "dormant"]
    sla_due_at: datetime | None
    current_owner_user_id: UUID | None
    version: int


class PoolLeadResponse(BaseModel):
    request_id: UUID
    data: list[PoolLead]
    page: dict[str, object]
