"""Schemas for candidate promotion (select → Sales Lead)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SelectItem(BaseModel):
    candidate_id: UUID
    expected_version: int = Field(ge=0)
    override: bool = False
    override_reason: str | None = None

    @model_validator(mode="after")
    def _check_override_reason(self) -> "SelectItem":
        if self.override and not self.override_reason:
            raise ValueError("override_reason is required when override=true")
        return self


class CandidateSelectRequest(BaseModel):
    items: list[SelectItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _check_no_duplicates(self) -> "CandidateSelectRequest":
        ids = [str(item.candidate_id) for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate_id in batch")
        return self


class SelectSucceededItem(BaseModel):
    candidate_id: UUID
    company_id: UUID
    lead_id: UUID
    selected_icp_assessment_id: UUID
    selected_scale_assessment_id: UUID
    promotion_result: str  # "created_lead" | "reused_open_lead" | "created_completion_lead"
    allocation_status: str


class SelectFailedItem(BaseModel):
    candidate_id: UUID
    code: str
    message: str


class CandidateSelectResponse(BaseModel):
    succeeded: list[dict[str, Any]]
    failed: list[dict[str, Any]]
