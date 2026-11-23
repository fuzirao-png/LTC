"""FastAPI request and response DTOs for Customer Analysis."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CustomerProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_summary: str | None = None
    company_type: str | None = None
    business_model: str | None = None
    geography_note: str | None = None
    region_text: str | None = None
    employee_scale: str | None = None
    esim_scenario: str | None = None
    coverage: str | None = None
    estimated_usage: str | None = None
    integration: str | None = None
    compliance: str | None = None
    budget_text: str | None = None
    decision_maker_text: str | None = None
    decision_maker_contact_id: UUID | None = None
    decision_cycle_text: str | None = None

    def domain_changes(self) -> dict[str, Any]:
        values = self.model_dump(exclude_unset=True)
        if "company_summary" in values:
            values["company_type"] = values.pop("company_summary")
        if "geography_note" in values:
            values["region_text"] = values.pop("geography_note")
        return values


class SuggestionBatchReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: UUID
    suggestion_version: int = Field(ge=0)
    action: Literal["accept", "keep_original", "edit"]
    edited_value: Any | None = None
    review_note: str | None = None


class SuggestionBatchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_version: int = Field(ge=0)
    items: list[SuggestionBatchReviewItem] = Field(min_length=1)

class MeddpiccUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unknown", "partial", "confirmed", "rejected"]
    summary: str | None = None
    payload: dict[str, Any] | None = None


class AnalysisRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal["customer_analysis"] = "customer_analysis"
    force_refresh: bool = False
    trigger_type: Literal[
        "manual", "pool_entry", "assignment", "operation", "schedule", "migration"
    ] = "manual"


class RequestEnvelope(BaseModel):
    request_id: str
    data: Any


class PageMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool


class ReportListEnvelope(BaseModel):
    request_id: str
    data: list[dict[str, Any]]
    page: PageMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    request_id: str
    error: ErrorDetail

