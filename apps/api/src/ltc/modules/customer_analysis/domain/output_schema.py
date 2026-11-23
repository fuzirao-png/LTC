"""Strict provider output contract for customer analysis generation."""

from __future__ import annotations

from typing import Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9 .+/_-]{0,23}$")


def _is_chinese_copy(value: str | None, *, allow_identifier: bool = False) -> bool:
    if value is None or not value.strip():
        return True
    text = value.strip()
    if _CJK_PATTERN.search(text):
        return True
    return bool(allow_identifier and _IDENTIFIER_PATTERN.fullmatch(text))


def _bounded_readable_copy(value: str | None) -> str | None:
    if value is None or not value.strip():
        return value
    text = value.strip()
    # Identifiers, URLs and evidence IDs are not narrative fields.
    if _IDENTIFIER_PATTERN.fullmatch(text) or text.startswith(("http://", "https://", "exa:", "weknora:")):
        return value
    length = len(text)
    if length < 20 or length > 300:
        raise ValueError("readable customer-analysis fields must contain 20-300 characters")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldCandidate(StrictModel):
    value: str | None
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    quote: str | None
    reason: str
    missing_reason: str | None
    source_kind: Literal[
        "sales_confirmed",
        "internal",
        "weknora",
        "exa",
        "web",
        "internal_and_web",
        "unknown",
    ]
    review_status: Literal["auto_applied", "pending_review", "conflict", "unknown"] = "unknown"
    evidence_state: Literal["customer_confirmed", "sales_confirmed", "knowledge_supported", "external_supported", "inferred", "missing"] = "missing"
    customer_fact_status: Literal["confirmed", "unconfirmed", "rejected"] = "unconfirmed"
    field_catalog_version: Literal["core-field-catalog-v1"] = "core-field-catalog-v1"

class MeddpiccCandidate(StrictModel):
    status: Literal["unknown", "partial", "confirmed"]
    summary: str | None
    detail: str | None
    metric: str | None
    actors: list[str]
    process_steps: list[str]
    next_question: str | None
    risk: str | None
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    missing_reason: str | None
    evidence_state: Literal["customer_confirmed", "sales_confirmed", "knowledge_supported", "external_supported", "inferred", "missing"] = "missing"
    customer_fact_status: Literal["confirmed", "unconfirmed", "rejected"] = "unconfirmed"

    def persistence_value(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "payload": {
                "detail": self.detail,
                "metric": self.metric,
                "actors": self.actors,
                "process_steps": self.process_steps,
                "next_question": self.next_question,
                "risk": self.risk,
            },
        }


class ProfileCandidateSet(StrictModel):
    company_type: FieldCandidate
    business_model: FieldCandidate
    employee_scale: FieldCandidate
    region_text: FieldCandidate
    esim_scenario: FieldCandidate
    coverage: FieldCandidate
    estimated_usage: FieldCandidate
    integration: FieldCandidate
    compliance: FieldCandidate
    budget_text: FieldCandidate
    decision_maker_text: FieldCandidate
    decision_maker_contact_id: FieldCandidate
    decision_cycle_text: FieldCandidate


class CoreMeddpiccCandidateSet(StrictModel):
    metrics: MeddpiccCandidate
    economic_buyer: MeddpiccCandidate
    decision_process: MeddpiccCandidate
    identify_pain: MeddpiccCandidate


class EvidenceClaim(StrictModel):
    """A customer-facing statement with explicit evidence provenance."""

    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_state: Literal["customer_confirmed", "sales_confirmed", "knowledge_supported", "external_supported", "inferred", "missing"] = "missing"
    customer_fact_status: Literal["confirmed", "unconfirmed", "rejected"] = "unconfirmed"


class UnknownItem(StrictModel):
    model_config = ConfigDict(extra="ignore")
    item: str
    reason: str

    @model_validator(mode="before")
    @classmethod
    def normalize_unknown(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        text = normalized.get("item") or normalized.get("text")
        normalized["item"] = text
        normalized["reason"] = normalized.get("reason") or text or "当前证据不足"
        return normalized


class SalesRecommendation(StrictModel):
    model_config = ConfigDict(extra="ignore")
    action: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_recommendation(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        text = normalized.get("action") or normalized.get("text")
        normalized["action"] = text
        normalized["reason"] = normalized.get("reason") or text or "基于现有证据推进验证"
        return normalized


class ReportModuleOutput(StrictModel):
    model_config = ConfigDict(extra="ignore")
    summary: str
    findings: list[str]
    confidence: float = Field(ge=0, le=1)
    facts: list[EvidenceClaim] = Field(default_factory=list)
    inferences: list[EvidenceClaim] = Field(default_factory=list)
    unknowns: list[UnknownItem] = Field(default_factory=list)
    sales_recommendations: list[SalesRecommendation] = Field(default_factory=list)
    competitor_relations: list[dict[str, object]] = Field(default_factory=list)

    @field_validator("findings", mode="before")
    @classmethod
    def normalize_findings(cls, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            if isinstance(value, dict):
                value = value.get("text") or value.get("item") or value.get("content")
            if value not in (None, ""):
                normalized.append(str(value))
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary_length(cls, value: str) -> str:
        return str(_bounded_readable_copy(value))

    @field_validator("findings")
    @classmethod
    def validate_finding_lengths(cls, values: list[str]) -> list[str]:
        return [str(_bounded_readable_copy(value)) for value in values]


class StructuredReportOutput(StrictModel):
    market: ReportModuleOutput
    company: ReportModuleOutput
    competitor: ReportModuleOutput
    pain: ReportModuleOutput
    product: ReportModuleOutput


class CustomerViewOutput(StrictModel):
    concerns: str | None
    partners: str | None
    impression_of_us: str | None


class SectionConfidenceOutput(StrictModel):
    market: float = Field(ge=0, le=1)
    company: float = Field(ge=0, le=1)
    competitor: float = Field(ge=0, le=1)
    pain: float = Field(ge=0, le=1)
    product: float = Field(ge=0, le=1)


class EmailDraftOutput(StrictModel):
    subject: str
    body: str


class SalesGuideModuleOutput(StrictModel):
    questions: list[str]
    actions: list[str]
    talk_track: list[str]
    email_draft: EmailDraftOutput


class SalesGuideOutput(StrictModel):
    customer_need: SalesGuideModuleOutput
    decision_chain: SalesGuideModuleOutput
    competitive_edge: SalesGuideModuleOutput


class CustomerAnalysisLLMOutput(StrictModel):
    schema_version: Literal["customer-analysis-schema-v1"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    section_confidence: SectionConfidenceOutput
    profile_candidates: ProfileCandidateSet | None = None
    meddpicc_candidates: CoreMeddpiccCandidateSet | None = None
    report: StructuredReportOutput
    customer_view: CustomerViewOutput
    sales_guide: SalesGuideOutput | None = None

    @model_validator(mode="after")
    def require_simplified_chinese_copy(self) -> "CustomerAnalysisLLMOutput":
        """Reject English narrative output before it reaches the customer-facing report."""
        violations: list[str] = []

        def check(path: str, value: str | None, *, allow_identifier: bool = False) -> None:
            if not _is_chinese_copy(value, allow_identifier=allow_identifier):
                violations.append(path)

        check("summary", self.summary)
        for module_name, module in self.report:
            check(f"report.{module_name}.summary", module.summary)
            for index, finding in enumerate(module.findings):
                check(f"report.{module_name}.findings.{index}", finding)
            for index, claim in enumerate(module.facts):
                check(f"report.{module_name}.facts.{index}", claim.text)
            for index, claim in enumerate(module.inferences):
                check(f"report.{module_name}.inferences.{index}", claim.text)
            for index, item in enumerate(module.unknowns):
                check(f"report.{module_name}.unknowns.{index}.item", item.item)
                check(f"report.{module_name}.unknowns.{index}.reason", item.reason)
            for index, recommendation in enumerate(module.sales_recommendations):
                check(f"report.{module_name}.sales_recommendations.{index}.action", recommendation.action)
                check(f"report.{module_name}.sales_recommendations.{index}.reason", recommendation.reason)

        for field_name, value in self.customer_view:
            check(f"customer_view.{field_name}", value, allow_identifier=True)

        if self.profile_candidates is not None:
            for field_name, candidate in self.profile_candidates:
                check(
                    f"profile_candidates.{field_name}.value",
                    candidate.value,
                    allow_identifier=True,
                )
                check(f"profile_candidates.{field_name}.reason", candidate.reason)
                check(
                    f"profile_candidates.{field_name}.missing_reason",
                    candidate.missing_reason,
                )

        if self.meddpicc_candidates is not None:
            for code, candidate in self.meddpicc_candidates:
                for name in ("summary", "detail", "metric", "next_question", "risk", "missing_reason"):
                    check(f"meddpicc_candidates.{code}.{name}", getattr(candidate, name))
                for index, step in enumerate(candidate.process_steps):
                    check(f"meddpicc_candidates.{code}.process_steps.{index}", step)

        if self.sales_guide is not None:
            for module_name, guide in self.sales_guide:
                for collection_name in ("questions", "actions", "talk_track"):
                    for index, item in enumerate(getattr(guide, collection_name)):
                        check(f"sales_guide.{module_name}.{collection_name}.{index}", item)
                check(f"sales_guide.{module_name}.email_draft.subject", guide.email_draft.subject)
                check(f"sales_guide.{module_name}.email_draft.body", guide.email_draft.body)

        if violations:
            raise ValueError(
                "面向用户的内容必须使用简体中文，以下字段未通过语言检查："
                + ", ".join(violations[:12])
            )
        return self


def missing_field_candidate(reason: str = "现有资料无法支持判断") -> dict[str, object]:
    return {
        "value": None,
        "confidence": 0.0,
        "evidence_ids": [],
        "quote": None,
        "reason": reason,
        "missing_reason": reason,
        "source_kind": "unknown",
    }


def missing_meddpicc_candidate(reason: str = "现有资料无法支持判断") -> dict[str, object]:
    return {
        "status": "unknown",
        "summary": None,
        "detail": None,
        "metric": None,
        "actors": [],
        "process_steps": [],
        "next_question": None,
        "risk": None,
        "confidence": 0.0,
        "evidence_ids": [],
        "missing_reason": reason,
    }
