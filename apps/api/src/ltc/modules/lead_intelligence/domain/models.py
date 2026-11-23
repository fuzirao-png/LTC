"""Framework-free lead intelligence value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchRequest:
    query_text: str
    search_mode: str
    target_count: int
    scene_code: str
    dialogue_session_id: str | None = None

    def __post_init__(self) -> None:
        value = self.query_text.strip()
        if value.count("?") >= 3 and value.count("?") >= len(value) // 3:
            raise ValueError("query_text appears to be encoding-corrupted; send UTF-8 text")
        self.query_text = value


@dataclass(slots=True)
class CompanyCandidate:
    candidate_id: str
    company_name: str
    legal_name: str | None = None
    website: str | None = None
    company_intro: str | None = None
    industry_code: str | None = None
    employee_count: int | None = None
    region_code: str | None = None
    country_code: str | None = None
    city: str | None = None
    linkedin_company_url: str | None = None
    contacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    raw_ai_output: dict[str, Any] = field(default_factory=dict)
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DimensionScore:
    dimension_code: str
    score: float
    explanation: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provider_status: str = "succeeded"
    error_message: str | None = None


@dataclass(slots=True)
class ScoringResult:
    icp_dimensions: list[DimensionScore]
    scale_dimensions: list[DimensionScore]


PIPELINE_STEPS = (
    "memory_read",
    "exa_candidate_search",
    "leads_finder_company_lookup",
    "exa_missing_fields_once",
    "linkedin_contact_lookup",
    "company_summary_persist",
    "parallel_7_agent_scoring",
)
