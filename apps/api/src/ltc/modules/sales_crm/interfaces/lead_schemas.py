"""Sales CRM command DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AssignLeadRequest(BaseModel):
    assignee_user_id: UUID
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)


class ReasonRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)


class TransferLeadRequest(BaseModel):
    to_assignee_user_id: UUID
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)


class HandoverAssignRequest(BaseModel):
    to_assignee_user_id: UUID
    reason_text: str | None = Field(default=None, max_length=500)


class BatchTransferItem(BaseModel):
    lead_id: UUID
    expected_version: int = Field(ge=0)
    to_assignee_user_id: UUID
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)


class BatchTransferRequest(BaseModel):
    items: list[BatchTransferItem] = Field(min_length=1, max_length=100)


class BatchTransferResponse(BaseModel):
    request_id: UUID
    data: dict[str, list[dict[str, object]]]


class HandoverReturnRequest(BaseModel):
    departed_user_id: UUID


class HandoverLead(BaseModel):
    lead_id: UUID
    company_id: UUID
    company_name: str
    departed_user_id: UUID
    departed_user_name: str
    sales_tier: str
    region_code: str | None
    required_sales_tier: str
    customer_grade: str | None
    customer_region_code: str | None
    country_code: str | None
    country_name: str | None
    pipeline_stage: str
    allocation_status: Literal["claimed"]
    version: int


class HandoverResponse(BaseModel):
    request_id: UUID
    data: list[HandoverLead]


class HandoverReturnResponse(BaseModel):
    request_id: UUID
    data: dict[str, object]


class FirstTouchRequest(BaseModel):
    contact_id: UUID
    channel: str = Field(min_length=1, max_length=50)
    occurred_at: datetime
    note: str | None = Field(default=None, max_length=2000)


class ChangeStageRequest(BaseModel):
    target_stage: Literal["new", "contacted", "engaged", "meeting", "proposal", "dormant"]
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)


class TerminalStageRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str | None = Field(default=None, max_length=500)
    closed_at: datetime | None = None


class LeadCommandData(BaseModel):
    lead_id: UUID
    assignment_id: UUID | None = None
    previous_assignment_id: UUID | None = None
    allocation_status: Literal["claimable", "claimed"]
    owner_user_id: UUID | None = None
    from_owner_user_id: UUID | None = None
    assigned_at: datetime | None = None
    sla_due_at: datetime | None = None
    pipeline_stage: str
    version: int


class LeadCommandResponse(BaseModel):
    request_id: UUID
    data: LeadCommandData


class PipelineChangeData(BaseModel):
    lead_id: UUID
    transition_id: UUID
    contact_id: UUID | None = None
    first_touch_at: datetime | None = None
    pipeline_stage: str | None = None
    from_stage: str | None = None
    to_stage: str | None = None
    occurred_at: datetime | None = None
    version: int


class PipelineChangeResponse(BaseModel):
    request_id: UUID
    data: PipelineChangeData
