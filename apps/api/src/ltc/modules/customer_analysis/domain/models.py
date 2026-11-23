"""Framework-free domain models for Customer Analysis."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Final
from uuid import UUID

from ltc.modules.customer_analysis.domain.errors import (
    InvalidDimensionError,
    InvalidStateError,
    VersionConflictError,
)


JsonObject = dict[str, Any]

PROFILE_FIELD_NAMES: Final[tuple[str, ...]] = (
    "company_type",
    "region_text",
    "employee_scale",
    "business_model",
    "esim_scenario",
    "coverage",
    "estimated_usage",
    "integration",
    "compliance",
    "budget_text",
    "decision_maker_text",
    "decision_maker_contact_id",
    "decision_cycle_text",
)

CUSTOMER_VIEW_FIELD_NAMES: Final[tuple[str, ...]] = (
    "concerns",
    "partners",
    "impression_of_us",
)

MEDDPICC_DIMENSIONS: Final[tuple[str, ...]] = (
    "metrics",
    "economic_buyer",
    "decision_criteria",
    "decision_process",
    "paper_process",
    "identify_pain",
    "champion",
    "competition",
)

MEDDPICC_STATUSES: Final[tuple[str, ...]] = (
    "unknown",
    "partial",
    "confirmed",
    "rejected",
)

# Research policy is persisted in ``analysis_run.trigger_context`` so the API,
# worker and audit readers all evaluate the same immutable decision.
RESEARCH_MODES: Final[tuple[str, ...]] = ("initial_external", "internal_only")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _has_value(value: Any) -> bool:
    return value not in (None, "", "待确认", [], {})


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def public_evidence_ref(value: JsonObject) -> JsonObject:
    """Return evidence metadata safe for Customer Analysis API responses."""
    metadata = dict(value.get("metadata") or {})
    public_metadata = {
        key: metadata[key]
        for key in (
            "direction",
            "contact_id",
            "intent_level",
            "next_action",
            "note_version",
            "knowledge_base_id",
            "document_id",
            "document_updated_at",
            "research_snapshot_id",
            "field_hints",
            "score",
            "permission_filtered",
            "inherited_from_report_id",
            "customer_fact_status",
        )
        if metadata.get(key) not in (None, "")
    }
    public_metadata["evidence_grade"] = _evidence_grade(
        str(value.get("source_type") or ""),
        metadata,
    )
    return {
        key: item
        for key, item in {
            "evidence_id": value.get("evidence_id"),
            "source_type": value.get("source_type"),
            "source_priority": value.get("source_priority"),
            "source_resource_id": value.get("source_resource_id"),
            "occurred_at": value.get("occurred_at"),
            "retrieved_at": value.get("retrieved_at"),
            "title": value.get("title"),
            "url": value.get("url"),
            "excerpt": value.get("excerpt") or str(value.get("text") or "")[:240],
            "highlights": value.get("highlights"),
            "content_hash": value.get("content_hash"),
            "metadata": public_metadata or None,
        }.items()
        if item not in (None, "", {})
    }


def evidence_summary(values: tuple[JsonObject, ...]) -> JsonObject:
    source_types = [str(item.get("source_type") or "") for item in values]
    email_values = [
        item for item in values if item.get("source_type") == "internal_email"
    ]
    return {
        "total_count": len(values),
        "email_count": len(email_values),
        "inbound_email_count": sum(
            1
            for item in email_values
            if dict(item.get("metadata") or {}).get("direction") == "inbound"
        ),
        "outbound_email_count": sum(
            1
            for item in email_values
            if dict(item.get("metadata") or {}).get("direction") == "outbound"
        ),
        "manual_note_count": source_types.count("internal_manual_note"),
        "meeting_count": source_types.count("internal_meeting"),
        "knowledge_count": source_types.count("weknora"),
        "exa_count": sum(1 for item in source_types if item in {"exa", "web", "external_web"}),
        "web_count": sum(
            1
            for item in values
            if item.get("url")
            and not str(item.get("source_type") or "").startswith("internal_")
        ),
        "grade_counts": _evidence_grade_counts(values),
    }


def _evidence_grade_counts(values: tuple[JsonObject, ...]) -> JsonObject:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for item in values:
        grade = _evidence_grade(
            str(item.get("source_type") or ""),
            dict(item.get("metadata") or {}),
        )
        counts[grade] = counts.get(grade, 0) + 1
    return counts


def _evidence_grade(source_type: str, metadata: JsonObject | None = None) -> str:
    metadata = dict(metadata or {})
    direction = str(metadata.get("direction") or "")
    if source_type == "internal_manual_note":
        return "A"
    if source_type == "internal_email" and direction == "inbound":
        return "B"
    if source_type == "internal_email" and direction == "outbound":
        return "C"
    if source_type.startswith("internal_"):
        return "B"
    if source_type in {"exa", "web", "external_web"}:
        return "D"
    if source_type == "weknora":
        return "C"
    return "C"


@dataclass(frozen=True)
class EngagementEvidence:
    evidence_id: str
    source_type: str
    source_resource_id: str
    company_id: UUID
    occurred_at: datetime
    title: str
    text: str
    content_hash: str
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_resource_id": self.source_resource_id,
            "company_id": str(self.company_id),
            "occurred_at": self.occurred_at.isoformat(),
            "title": self.title,
            "text": self.text,
            "excerpt": self.text[:240],
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
            "url": None,
        }


@dataclass(frozen=True)
class CustomerProfile:
    company_id: UUID
    company_type: str | None = None
    region_text: str | None = None
    employee_scale: str | None = None
    business_model: str | None = None
    esim_scenario: str | None = None
    coverage: str | None = None
    estimated_usage: str | None = None
    integration: str | None = None
    compliance: str | None = None
    budget_text: str | None = None
    decision_maker_text: str | None = None
    decision_maker_contact_id: UUID | None = None
    decision_cycle_text: str | None = None
    completeness_score: float = 0.0
    missing_fields: tuple[str, ...] = PROFILE_FIELD_NAMES
    extra_payload: JsonObject = field(default_factory=dict)
    field_provenance: JsonObject = field(default_factory=dict)
    source_summary: str | None = None
    last_enriched_at: datetime | None = None
    version: int = 0
    updated_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)

    def finalized(self) -> "CustomerProfile":
        missing = tuple(
            name for name in PROFILE_FIELD_NAMES if not _has_value(getattr(self, name))
        )
        completeness = round((len(PROFILE_FIELD_NAMES) - len(missing)) / len(PROFILE_FIELD_NAMES), 4)
        return replace(self, completeness_score=completeness, missing_fields=missing)

    def patch(
        self,
        changes: JsonObject,
        *,
        expected_version: int,
        updated_by: UUID | None,
        source: str = "manual",
        provenance_by_field: JsonObject | None = None,
    ) -> "CustomerProfile":
        if expected_version != self.version:
            raise VersionConflictError(
                f"profile version {self.version} does not match {expected_version}"
            )
        supported_fields = set(PROFILE_FIELD_NAMES) | set(CUSTOMER_VIEW_FIELD_NAMES)
        unknown = set(changes) - supported_fields
        if unknown:
            raise ValueError(f"unsupported profile fields: {', '.join(sorted(unknown))}")
        changed_at = utc_now()
        provenance = dict(self.field_provenance)
        for name in changes:
            details = dict((provenance_by_field or {}).get(name) or {})
            provenance[name] = {
                "source": source,
                "confidence": details.get(
                    "confidence", 1.0 if source == "manual" else None
                ),
                "evidence_refs": list(details.get("evidence_refs") or []),
                "updated_at": changed_at.isoformat(),
            }
        profile_changes = {
            name: value for name, value in changes.items() if name in PROFILE_FIELD_NAMES
        }
        extra_payload = dict(self.extra_payload)
        extra_payload.update({
            name: value
            for name, value in changes.items()
            if name in CUSTOMER_VIEW_FIELD_NAMES
        })
        return replace(
            self,
            **profile_changes,
            extra_payload=extra_payload,
            field_provenance=provenance,
            version=self.version + 1,
            updated_by=updated_by,
            updated_at=changed_at,
        ).finalized()

    def to_dict(self) -> JsonObject:
        return {
            "company_id": str(self.company_id),
            **{name: _json_value(getattr(self, name)) for name in PROFILE_FIELD_NAMES},
            "completeness_score": self.completeness_score,
            "missing_fields": list(self.missing_fields),
            "extra_payload": dict(self.extra_payload),
            "field_provenance": dict(self.field_provenance),
            "source_summary": self.source_summary,
            "last_enriched_at": _json_value(self.last_enriched_at),
            "profile_version": self.version,
            "updated_by": _json_value(self.updated_by),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class MeddpiccDimension:
    company_id: UUID
    dimension_code: str
    level: str | None = None
    status: str = "unknown"
    summary: str | None = None
    payload: JsonObject = field(default_factory=dict)
    evidence_refs: tuple[JsonObject, ...] = ()
    evidence_state: str = "missing"
    customer_fact_status: str = "unconfirmed"
    version: int = 0
    updated_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.dimension_code not in MEDDPICC_DIMENSIONS:
            raise InvalidDimensionError(self.dimension_code)
        if self.status not in MEDDPICC_STATUSES:
            raise ValueError(f"invalid MEDDPICC status: {self.status}")

    def patch(
        self,
        *,
        expected_version: int,
        status: str,
        summary: str | None,
        payload: JsonObject | None,
        level: str | None = None,
        evidence_refs: tuple[JsonObject, ...] | None = None,
        evidence_state: str | None = None,
        customer_fact_status: str | None = None,
        updated_by: UUID | None = None,
    ) -> "MeddpiccDimension":
        if expected_version != self.version:
            raise VersionConflictError(
                f"MEDDPICC version {self.version} does not match {expected_version}"
            )
        return replace(
            self,
            status=status,
            summary=summary,
            payload=dict(payload or {}),
            level=level if level is not None else self.level,
            evidence_refs=evidence_refs if evidence_refs is not None else self.evidence_refs,
            evidence_state=evidence_state if evidence_state is not None else self.evidence_state,
            customer_fact_status=customer_fact_status if customer_fact_status is not None else self.customer_fact_status,
            version=self.version + 1,
            updated_by=updated_by,
            updated_at=utc_now(),
        )

    def to_dict(self) -> JsonObject:
        return {
            "company_id": str(self.company_id),
            "dimension_code": self.dimension_code,
            "level": self.level,
            "status": self.status,
            "summary": self.summary,
            "payload": dict(self.payload),
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "evidence_state": self.evidence_state,
            "customer_fact_status": self.customer_fact_status,
            "version": self.version,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class AnalysisContext:
    company_id: UUID
    company: JsonObject
    sales_lead: JsonObject
    adopted_icp: JsonObject
    adopted_scale: JsonObject
    contacts: tuple[JsonObject, ...] = ()
    engagement: JsonObject = field(default_factory=dict)
    profile: JsonObject = field(default_factory=dict)
    meddpicc: JsonObject = field(default_factory=dict)
    evidence_refs: tuple[JsonObject, ...] = ()
    engagement_cutoff_at: datetime | None = None

    def snapshot(self) -> JsonObject:
        return {
            "company": dict(self.company),
            "sales_lead": dict(self.sales_lead),
            "adopted_icp": dict(self.adopted_icp),
            "adopted_scale": dict(self.adopted_scale),
            "contacts": [dict(item) for item in self.contacts],
            "engagement": dict(self.engagement),
            "profile": dict(self.profile),
            "meddpicc": dict(self.meddpicc),
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "engagement_cutoff_at": _json_value(self.engagement_cutoff_at),
        }


@dataclass(frozen=True)
class AnalysisRun:
    run_id: UUID
    company_id: UUID
    current_job_id: UUID
    report_type: str
    trigger_type: str
    status: str
    input_hash: str
    prompt_version: str
    schema_version: str
    model_name: str | None
    profile_version: int
    meddpicc_revision: str
    input_snapshot: JsonObject
    engagement_cutoff_at: datetime | None = None
    report_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    triggered_at: datetime = field(default_factory=utc_now)
    trigger_context: JsonObject = field(default_factory=dict)
    superseded_by_run_id: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    version: int = 0

    @property
    def research_mode(self) -> str:
        value = str(self.trigger_context.get("research_mode") or "internal_only")
        return value if value in RESEARCH_MODES else "internal_only"

    @property
    def external_research_allowed(self) -> bool:
        return bool(self.trigger_context.get("external_research_allowed")) and self.research_mode == "initial_external"

    def transition(
        self,
        status: str,
        *,
        report_id: UUID | None = None,
        job_id: UUID | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> "AnalysisRun":
        allowed = {
            "queued": {"running", "cancelled"},
            "running": {"completed", "failed", "cancelled"},
            "failed": {"queued"},
            "completed": set(),
            "cancelled": set(),
        }
        if status not in allowed.get(self.status, set()):
            raise InvalidStateError(f"cannot transition analysis run {self.status} -> {status}")
        now = utc_now()
        return replace(
            self,
            status=status,
            report_id=report_id if report_id is not None else self.report_id,
            current_job_id=job_id if job_id is not None else self.current_job_id,
            error_code=error_code,
            error_message=error_message,
            started_at=now if status == "running" else self.started_at,
            completed_at=now if status in {"completed", "failed", "cancelled"} else None,
            version=self.version + 1,
        )

    def to_dict(self) -> JsonObject:
        return {
            "run_id": str(self.run_id),
            "company_id": str(self.company_id),
            "status": self.status,
            "report_type": self.report_type,
            "trigger_type": self.trigger_type,
            "research_mode": self.research_mode,
            "external_research_allowed": self.external_research_allowed,
            "current_job_id": str(self.current_job_id),
            "report_id": _json_value(self.report_id),
            "triggered_at": _json_value(self.triggered_at),
            "trigger_context": dict(self.trigger_context),
            "superseded_by_run_id": _json_value(self.superseded_by_run_id),
            "engagement_cutoff_at": _json_value(self.engagement_cutoff_at),
            "version": self.version,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class GeneratedReportContent:
    summary: str
    report_payload: JsonObject
    sales_guide_payload: JsonObject
    content_source: str
    model_name: str | None = None
    confidence: float | None = None
    section_confidence: JsonObject = field(default_factory=dict)
    evidence_refs: tuple[JsonObject, ...] = ()
    profile_candidates: JsonObject = field(default_factory=dict)
    meddpicc_candidates: JsonObject = field(default_factory=dict)
    generation_metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisReport:
    report_id: UUID
    company_id: UUID
    analysis_run_id: UUID
    report_type: str
    version_no: int
    schema_version: str
    summary: str
    health_grade: str | None
    intention_level: str | None
    confidence: float | None
    section_confidence: JsonObject
    low_confidence_sections: tuple[str, ...]
    data_sources: tuple[str, ...]
    evidence_refs: tuple[JsonObject, ...]
    profile_snapshot: JsonObject
    meddpicc_snapshot: JsonObject
    icp_snapshot: JsonObject
    scale_snapshot: JsonObject
    report_payload: JsonObject
    sales_guide_payload: JsonObject
    generated_by: str
    model_name: str | None
    content_source: str
    input_hash: str
    generated_at: datetime = field(default_factory=utc_now)
    superseded_at: datetime | None = None

    def to_dict(self) -> JsonObject:
        return {
            "report_id": str(self.report_id),
            "company_id": str(self.company_id),
            "analysis_run_id": str(self.analysis_run_id),
            "report_type": self.report_type,
            "version_no": self.version_no,
            "schema_version": self.schema_version,
            "prompt_version": self.report_payload.get("_meta", {}).get("prompt_version"),
            "generation_attempts": self.report_payload.get("_meta", {}).get("generation_attempts", 1),
            "research_meta": dict(self.report_payload.get("_meta", {})),
            "header": self.report_payload.get("header", {}),
            "customer_view": self.report_payload.get("customer_view", {}),
            "summary": self.summary,
            "health_grade": self.health_grade,
            "intention_level": self.intention_level,
            "confidence": self.confidence,
            "section_confidence": dict(self.section_confidence),
            "low_confidence_sections": list(self.low_confidence_sections),
            "data_sources": list(self.data_sources),
            "evidence_refs": [public_evidence_ref(item) for item in self.evidence_refs],
            "evidence_summary": evidence_summary(self.evidence_refs),
            "profile_snapshot": dict(self.profile_snapshot),
            "meddpicc_snapshot": dict(self.meddpicc_snapshot),
            "icp_snapshot": dict(self.icp_snapshot),
            "scale_snapshot": dict(self.scale_snapshot),
            **{
                name: self.report_payload.get(name, {})
                for name in ("market", "company", "competitor", "pain", "product")
            },
            "modules": [
                {"module_name": name, "sections": list(self.report_payload.get(name, {}).get("sections", []))}
                for name in ("market", "company", "competitor", "pain", "product")
            ],
            "sales_guide": dict(self.sales_guide_payload),
            "generated_by": self.generated_by,
            "model_name": self.model_name,
            "content_source": self.content_source,
            "generated_at": self.generated_at.isoformat(),
            "superseded_at": _json_value(self.superseded_at),
        }


@dataclass(frozen=True)
class AnalysisSuggestion:
    suggestion_id: UUID
    company_id: UUID
    report_id: UUID
    target_type: str
    dimension_code: str | None
    target_path: str
    target_version_at_creation: int
    current_value_snapshot: Any
    proposed_value: Any
    evidence_refs: tuple[JsonObject, ...] = ()
    confidence: float | None = None
    status: str = "pending"
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    version: int = 0

    def review(
        self,
        status: str,
        *,
        expected_version: int,
        reviewed_by: UUID | None,
        review_note: str | None = None,
    ) -> "AnalysisSuggestion":
        if expected_version != self.version:
            raise VersionConflictError(
                f"suggestion version {self.version} does not match {expected_version}"
            )
        if self.status != "pending" or status not in {"accepted", "rejected"}:
            raise InvalidStateError(f"cannot review suggestion in state {self.status}")
        return replace(
            self,
            status=status,
            reviewed_by=reviewed_by,
            reviewed_at=utc_now(),
            review_note=review_note,
            version=self.version + 1,
        )

    def to_dict(self) -> JsonObject:
        return {
            "suggestion_id": str(self.suggestion_id),
            "company_id": str(self.company_id),
            "report_id": str(self.report_id),
            "target_type": self.target_type,
            "dimension_code": self.dimension_code,
            "target_path": self.target_path,
            "target_version_at_creation": self.target_version_at_creation,
            "current_value_snapshot": self.current_value_snapshot,
            "proposed_value": self.proposed_value,
            "evidence_refs": [public_evidence_ref(item) for item in self.evidence_refs],
            "confidence": self.confidence,
            "status": self.status,
            "summary": f"建议更新 {self.target_path}",
            "version": self.version,
            "created_at": self.created_at.isoformat(),
        }
