"""Application use cases for the Customer Analysis module."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import time
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from ltc.modules.customer_analysis.domain.errors import (
    InvalidStateError,
    ResourceNotFoundError,
    VersionConflictError,
)
from ltc.modules.customer_analysis.domain.enrichment import (
    confirmed_manual_note_updates,
    internal_evidence_refs,
)
from ltc.modules.customer_analysis.domain.field_catalog import (
    FIELD_COLLECTION_GUIDANCE,
    catalog_entries,
    field_catalog_payload,
)
from ltc.modules.customer_analysis.domain.models import (
    MEDDPICC_DIMENSIONS,
    AnalysisContext,
    AnalysisReport,
    AnalysisRun,
    AnalysisSuggestion,
    CustomerProfile,
    MeddpiccDimension,
    evidence_summary,
    public_evidence_ref,
)
from ltc.modules.customer_analysis.domain.ports import (
    AnalysisContextPort,
    AnalysisJobPort,
    CustomerAnalysisRepository,
    EngagementEvidenceReadPort,
    ReportGeneratorPort,
    SearchPort,
)
from ltc.modules.customer_analysis.domain.reporting import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    build_analysis_suggestions,
    canonical_input_hash,
    health_grade,
    intention_level,
    meddpicc_revision,
)
from ltc.modules.customer_analysis.domain.quality import evaluate_report_quality


class CustomerAnalysisService:
    """Coordinates Profile, MEDDPICC, reports, and suggestions through Ports."""

    _ANALYSIS_DEBOUNCE_SECONDS = 300

    def __init__(
        self,
        *,
        repository: CustomerAnalysisRepository,
        context_port: AnalysisContextPort,
        report_generator: ReportGeneratorPort,
        job_port: AnalysisJobPort,
        search_port: SearchPort | None = None,
        engagement_evidence_port: EngagementEvidenceReadPort | None = None,
    ) -> None:
        self.repository = repository
        self.context_port = context_port
        self.report_generator = report_generator
        self.job_port = job_port
        self.search_port = search_port
        self.engagement_evidence_port = engagement_evidence_port
        self.compat_events: list[dict[str, Any]] = []
        self.compat_icp_history: dict[str, list[dict[str, Any]]] = {}

    def get_profile(self, company_id: UUID) -> CustomerProfile:
        profile = self.repository.get_profile(company_id)
        if profile is not None:
            return profile
        context = self._source_context(company_id)
        source = {**context.company, **context.profile}
        profile = CustomerProfile(
            company_id=company_id,
            company_type=_optional_text(source.get("company_type") or source.get("industry")),
            region_text=_optional_text(source.get("region_text") or source.get("region")),
            employee_scale=_optional_text(source.get("employee_scale")),
            business_model=_optional_text(source.get("business_model")),
            esim_scenario=_optional_text(source.get("esim_scenario")),
            coverage=_optional_text(source.get("coverage")),
            estimated_usage=_optional_text(source.get("estimated_usage")),
            integration=_optional_text(source.get("integration")),
            compliance=_optional_text(source.get("compliance")),
            budget_text=_optional_text(source.get("budget_text") or source.get("budget")),
            decision_maker_text=_optional_text(
                source.get("decision_maker_text") or source.get("decision_maker")
            ),
            decision_maker_contact_id=_optional_uuid(source.get("decision_maker_contact_id")),
            decision_cycle_text=_optional_text(
                source.get("decision_cycle_text") or source.get("decision_cycle")
            ),
            source_summary="Initialized from company and sales context",
        ).finalized()
        self.repository.save_profile(profile)
        return profile

    def update_profile(
        self,
        company_id: UUID,
        changes: dict[str, Any],
        *,
        expected_version: int,
        updated_by: UUID | None = None,
    ) -> CustomerProfile:
        profile = self.get_profile(company_id)
        updated = profile.patch(
            changes,
            expected_version=expected_version,
            updated_by=updated_by,
            source="manual",
        )
        self.repository.save_profile(updated)
        return updated

    def get_meddpicc(self, company_id: UUID) -> list[MeddpiccDimension]:
        self._source_context(company_id)
        existing = {
            item.dimension_code: item
            for item in self.repository.list_meddpicc(company_id)
        }
        source = self._source_context(company_id)
        source_dimensions = source.meddpicc
        for code in MEDDPICC_DIMENSIONS:
            if code not in existing:
                raw = source_dimensions.get(code, {}) if isinstance(source_dimensions, dict) else {}
                raw = raw if isinstance(raw, dict) else {}
                status = str(raw.get("status", "unknown"))
                if status not in {"unknown", "partial", "confirmed", "rejected"}:
                    status = "partial" if status not in {"warn", "strong"} else "partial"
                dimension = MeddpiccDimension(
                    company_id=company_id,
                    dimension_code=code,
                    level=raw.get("level"),
                    status=status,
                    summary=raw.get("summary") or raw.get("desc"),
                    payload={key: value for key, value in raw.items() if key not in {"level", "status", "summary", "desc"}},
                )
                existing[code] = dimension
                self.repository.save_meddpicc_dimension(dimension)
        return [existing[code] for code in MEDDPICC_DIMENSIONS]

    def update_meddpicc(
        self,
        company_id: UUID,
        dimension_code: str,
        *,
        expected_version: int,
        status: str,
        summary: str | None,
        payload: dict[str, Any] | None,
        level: str | None = None,
        updated_by: UUID | None = None,
    ) -> MeddpiccDimension:
        dimensions = {item.dimension_code: item for item in self.get_meddpicc(company_id)}
        current = dimensions.get(dimension_code)
        if current is None:
            raise ResourceNotFoundError(f"MEDDPICC dimension {dimension_code} not found")
        updated = current.patch(
            expected_version=expected_version,
            status=status,
            summary=summary,
            payload=payload,
            level=level,
            updated_by=updated_by,
        )
        self.repository.save_meddpicc_dimension(updated)
        return updated

    def request_incremental_refresh(
        self,
        company_id: UUID,
        *,
        trigger_type: str = "operation",
        trigger_context: dict[str, Any] | None = None,
    ) -> AnalysisRun:
        context = {"refresh_mode": "incremental"}
        if trigger_context:
            context.update(trigger_context)
        return self.request_analysis(
            company_id,
            trigger_type=trigger_type,
            force_refresh=False,
            trigger_context=context,
        )

    def request_full_calibration(
        self,
        company_id: UUID,
        *,
        trigger_context: dict[str, Any] | None = None,
    ) -> AnalysisRun:
        context = {"refresh_mode": "full", "calibration_mode": "nightly"}
        if trigger_context:
            context.update(trigger_context)
        return self.request_analysis(
            company_id,
            trigger_type="schedule",
            force_refresh=True,
            trigger_context=context,
        )

    def request_external_recovery(self, company_id: UUID) -> AnalysisRun:
        """Create an audited, internal-only recovery run with fresh research."""
        return self.request_analysis(
            company_id,
            force_refresh=True,
            trigger_type="operation",
            trigger_context={
                "recovery_external_research": True,
                "recovery_reason": "internal_operational_replay",
            },
        )

    def request_analysis(
        self,
        company_id: UUID,
        *,
        report_type: str = "customer_analysis",
        force_refresh: bool = False,
        trigger_type: str = "manual",
        trigger_context: dict[str, Any] | None = None,
    ) -> AnalysisRun:
        context, profile, dimensions = self._analysis_context(company_id)
        engagement_cutoff_at = datetime.now(timezone.utc)
        context = self._with_engagement_evidence(context, engagement_cutoff_at)
        context = self._with_prior_external_evidence(context)
        profile, dimensions, conflict_queue = self._apply_confirmed_manual_note_updates(
            context, profile, dimensions
        )
        if conflict_queue:
            engagement = dict(context.engagement)
            engagement["conflict_queue"] = conflict_queue
            context = replace(context, engagement=engagement)
        context = replace(
            context,
            profile=profile.to_dict(),
            meddpicc={item.dimension_code: item.to_dict() for item in dimensions},
        )

        run_id = uuid4()
        generation_parameters: dict[str, Any] = {
            "temperature": 0.4,
            "report_type": report_type,
            "field_catalog_version": "core-field-catalog-v1",
        }
        research_mode = _research_mode_for_trigger(trigger_type, trigger_context)
        external_research_allowed = research_mode == "initial_external"
        if self.search_port is not None and external_research_allowed:
            generation_parameters["search_freshness"] = datetime.now(
                timezone.utc
            ).date().isoformat()
        generation_parameters["research_mode"] = research_mode
        if force_refresh:
            generation_parameters["force_refresh_id"] = str(run_id)
        trigger_context_payload = {
            "trigger_type": trigger_type,
            "trigger_source": (
                "first_lead_claim" if trigger_type == "assignment" else "customer_operation"
                if trigger_type == "operation" else trigger_type
            ),
            "research_mode": research_mode,
            "external_research_allowed": external_research_allowed,
            "weknora_snapshot_id": None,
            "exa_snapshot_id": None,
            "requested_at": engagement_cutoff_at.isoformat(),
            "debounce_window_seconds": self._ANALYSIS_DEBOUNCE_SECONDS,
            "refresh_mode": "full" if force_refresh else "incremental",
        }
        if trigger_type == "schedule":
            trigger_context_payload["calibration_mode"] = "nightly"
        if trigger_context:
            # Caller metadata is retained for audit, but cannot weaken the
            # trigger policy selected above (especially operation -> external).
            trigger_context_payload.update(
                {
                    key: value
                    for key, value in trigger_context.items()
                    if key not in {"research_mode", "external_research_allowed", "trigger_source"}
                }
            )
        if conflict_queue:
            trigger_context_payload["conflict_queue"] = conflict_queue
            trigger_context_payload["conflict_count"] = len(conflict_queue)
        input_hash = canonical_input_hash(
            context,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            model_name=self.report_generator.model_name,
            generation_parameters=generation_parameters,
        )
        if not force_refresh:
            recent = self.repository.find_recent_run(
                company_id,
                report_type,
                since_at=engagement_cutoff_at - timedelta(
                    seconds=self._ANALYSIS_DEBOUNCE_SECONDS
                ),
            )
            if (
                recent is not None
                and recent.status in {"queued", "running", "completed"}
                and recent.input_hash == input_hash
            ):
                return recent
            existing = self.repository.find_run_by_input(
                company_id, report_type, input_hash
            )
            if existing is not None and existing.status in {"queued", "running", "completed"}:
                return existing

        job_id = uuid4()
        run = AnalysisRun(
            run_id=run_id,
            company_id=company_id,
            current_job_id=job_id,
            report_type=report_type,
            trigger_type=trigger_type if trigger_type in {"manual", "pool_entry", "assignment", "operation", "schedule", "migration"} else "manual",
            status="queued",
            input_hash=input_hash,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            model_name=self.report_generator.model_name,
            profile_version=profile.version,
            meddpicc_revision=meddpicc_revision(dimensions),
            input_snapshot=context.snapshot(),
            engagement_cutoff_at=engagement_cutoff_at,
            triggered_at=engagement_cutoff_at,
            trigger_context=trigger_context_payload,
        )
        _submit_analysis_job(
            self.job_port,
            run_id,
            job_id,
            {
                "company_id": str(company_id),
                "run_id": str(run_id),
                "research_mode": research_mode,
                "external_research_allowed": external_research_allowed,
                "snapshot_ref": f"analysis_run:{run_id}:input_snapshot",
            },
        )
        self.repository.save_run(run)
        run = self.repository.get_run(run_id) or run
        self.job_port.dispatch(run_id)
        return run

    def execute_analysis(self, run_id: UUID) -> AnalysisRun:
        run = self.get_run(run_id)
        if run.status != "queued":
            raise InvalidStateError(f"analysis run {run_id} is {run.status}")
        running = run.transition("running")
        self.repository.save_run(running)
        context = _context_from_snapshot(running.company_id, running.input_snapshot)
        try:
            context = replace(
                context,
                evidence_refs=_dedupe_evidence(
                    _ensure_evidence_ids(context.evidence_refs)
                    + internal_evidence_refs(context)
                ),
            )
            if self.search_port is not None and running.external_research_allowed:
                sources = self._verified_search_sources(context)
                if sources:
                    context = replace(
                        context,
                        evidence_refs=_dedupe_evidence(
                            context.evidence_refs + tuple(sources)
                        ),
                    )
            content, generation_attempts = self._generate_report_with_retry(context)
            # Research evidence and report generation are separate stages. Do
            # not label a template fallback as a research-worker report just
            # because the Worker successfully collected evidence.
            if (
                running.trigger_context.get("research_job_id")
                and content.content_source != "template"
            ):
                content = replace(content, content_source="research_worker")
            # Fill token_usage from AI events (best-effort)
            _token_usage: dict[str, int] = {}
            if hasattr(self.report_generator, "model_name"):
                _token_usage["model"] = self.report_generator.model_name
            _token_usage["attempts"] = generation_attempts
            profile = self.get_profile(running.company_id)
            dimensions = self.get_meddpicc(running.company_id)
            profile, dimensions = self._apply_trusted_knowledge_candidates(
                content,
                profile,
                dimensions,
                conflicts=list(running.trigger_context.get("research_conflicts") or []),
            )
            report_id = uuid4()
            score = float(context.adopted_icp.get("total_score") or 0)
            section_confidence = dict(content.section_confidence)
            report_payload = dict(content.report_payload)
            report_meta = dict(report_payload.get("_meta", {}))
            report_meta.update(content.generation_metadata)
            report_meta["generation_attempts"] = generation_attempts
            report_meta["research_mode"] = running.research_mode
            report_meta["external_research_allowed"] = running.external_research_allowed
            report_meta["research_worker_used"] = bool(
                running.trigger_context.get("research_job_id")
            )
            report_meta["weknora_snapshot_id"] = running.trigger_context.get(
                "weknora_snapshot_id"
            )
            report_meta["exa_snapshot_id"] = running.trigger_context.get(
                "exa_snapshot_id"
            )
            for key in (
                "weknora_status",
                "exa_status",
                "gpt_researcher_status",
                "research_scope",
            ):
                if key in running.trigger_context:
                    report_meta[key] = running.trigger_context.get(key)
            report_meta["weknora_used"] = any(
                str(item.get("source_type") or "").startswith("weknora")
                for item in content.evidence_refs
            )
            report_meta["exa_used"] = any(
                str(item.get("source_type") or "") in {"exa", "web", "external_web"}
                for item in content.evidence_refs
            )
            report_meta.update(
                evaluate_report_quality(report_payload, content.evidence_refs)
            )
            report_payload["_meta"] = report_meta
            report = AnalysisReport(
                report_id=report_id,
                company_id=running.company_id,
                analysis_run_id=running.run_id,
                report_type=running.report_type,
                version_no=self.repository.next_report_version(
                    running.company_id, running.report_type
                ),
                schema_version=running.schema_version,
                summary=content.summary,
                health_grade=health_grade(score),
                intention_level=intention_level(score, context.engagement),
                confidence=content.confidence,
                section_confidence=section_confidence,
                low_confidence_sections=tuple(
                    name
                    for name, confidence in section_confidence.items()
                    if float(confidence) < 0.5
                ),
                data_sources=tuple(_evidence_urls(content.evidence_refs)),
                evidence_refs=content.evidence_refs,
                profile_snapshot=profile.to_dict(),
                meddpicc_snapshot={
                    item.dimension_code: item.to_dict() for item in dimensions
                },
                icp_snapshot=dict(context.adopted_icp),
                scale_snapshot=dict(context.adopted_scale),
                report_payload=report_payload,
                sales_guide_payload=dict(content.sales_guide_payload),
                generated_by="agent",
                model_name=content.model_name,
                content_source=content.content_source,
                input_hash=running.input_hash,
            )
            suggestions = list(build_analysis_suggestions(
                company_id=running.company_id,
                report_id=report_id,
                content=content,
                profile=profile,
                dimensions=dimensions,
            ))
            pending_by_target = {
                (item.target_type, item.dimension_code or item.target_path): item
                for item in self.list_suggestions(running.company_id)
            }
            refreshed_suggestions = []
            superseded_suggestions = []
            for suggestion in suggestions:
                target = (
                    suggestion.target_type,
                    suggestion.dimension_code or suggestion.target_path,
                )
                previous = pending_by_target.get(target)
                if previous is None:
                    refreshed_suggestions.append(suggestion)
                    continue
                if previous.proposed_value == suggestion.proposed_value:
                    continue
                superseded_suggestions.append(previous.review(
                    "rejected",
                    expected_version=previous.version,
                    reviewed_by=None,
                    review_note="已由更新的分析报告候选值替换",
                ))
                refreshed_suggestions.append(suggestion)
            suggestions = refreshed_suggestions
            completed = running.transition("completed", report_id=report_id)
            with self.repository.transaction() as conn:
                self.repository.save_report(report, _conn=conn)
                for suggestion in superseded_suggestions:
                    self.repository.save_suggestion(suggestion, _conn=conn)
                for suggestion in suggestions:
                    self.repository.save_suggestion(suggestion, _conn=conn)
                self.repository.save_run(completed, _conn=conn)
            self.compat_events.append({
                "topic": "report.generated",
                "company_id": str(running.company_id),
                "report_id": str(report_id),
                "llm_model": content.model_name or "template",
                "token_usage": _token_usage,
                "created_at": _now_iso(),
            })
            return completed
        except Exception as exc:  # the worker records the domain failure before surfacing it
            failed = running.transition(
                "failed",
                error_code="ANALYSIS_GENERATION_FAILED",
                error_message=str(exc),
            )
            self.repository.save_run(failed)
            return failed

    def _generate_report_with_retry(
        self, context: AnalysisContext
    ) -> tuple[Any, int]:
        """Retry report generation with bounded exponential backoff.

        Provider adapters may manage their own transport retries; adapters that do
        not expose ``handles_retries`` are retried here so the application port
        remains usable with deterministic test or on-premise generators.
        """
        max_retries = 1
        delays = (1.0, 2.0)
        attempts = 0
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            attempts = attempt + 1
            try:
                return self.report_generator.generate(context), attempts
            except Exception as exc:
                last_error = exc
                if getattr(self.report_generator, "handles_retries", False) or attempt >= max_retries:
                    break
                time.sleep(delays[attempt])
        assert last_error is not None
        raise last_error

    def _apply_trusted_knowledge_candidates(
        self,
        content: Any,
        profile: CustomerProfile,
        dimensions: list[MeddpiccDimension],
        conflicts: list[dict[str, Any]] | None = None,
    ) -> tuple[CustomerProfile, list[MeddpiccDimension]]:
        """Auto-apply only high-confidence, non-conflicting WeKnora values.

        Public web/Exa values always remain suggestions.  Knowledge-base values
        may fill an empty field only when the field catalog allows public or
        internal collection and every cited item resolves to WeKnora evidence.
        """
        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in content.evidence_refs
            if item.get("evidence_id")
        }
        conflicted_evidence_ids = {
            str(evidence_id)
            for conflict in conflicts or []
            if isinstance(conflict, dict)
            for evidence_id in conflict.get("evidence_ids") or []
        }
        changes: dict[str, Any] = {}
        provenance: dict[str, Any] = {}
        for field_id, candidate in dict(content.profile_candidates).items():
            if not isinstance(candidate, dict):
                continue
            guidance = FIELD_COLLECTION_GUIDANCE.get(field_id)
            if guidance is None or guidance[0] != "public_or_internal":
                continue
            if getattr(profile, field_id, None) not in (None, "", "待确认"):
                continue
            value = candidate.get("value")
            if value in (None, "", "待确认"):
                continue
            try:
                confidence = float(candidate.get("confidence") or 0)
            except (TypeError, ValueError):
                continue
            evidence_ids = [str(value) for value in candidate.get("evidence_ids") or []]
            if conflicted_evidence_ids.intersection(evidence_ids):
                continue
            evidence = [evidence_by_id.get(value) for value in evidence_ids]
            knowledge_only = bool(evidence) and all(
                item is not None and item.get("source_type") == "weknora"
                for item in evidence
            )
            if candidate.get("source_kind") != "weknora" and not knowledge_only:
                continue
            if candidate.get("review_status") == "conflict":
                continue
            if confidence < 0.85 or not knowledge_only:
                continue
            changes[field_id] = _normalize_profile_value(field_id, value)
            provenance[field_id] = {
                "confidence": confidence,
                "evidence_refs": evidence_ids,
                "evidence_state": "knowledge_supported",
                "customer_fact_status": "unconfirmed",
            }

        if not changes:
            return profile, dimensions
        updated = profile.patch(
            changes,
            expected_version=profile.version,
            updated_by=None,
            source="weknora_auto_applied",
            provenance_by_field=provenance,
        )
        self.repository.save_profile(updated)
        return updated, dimensions

    def get_run(self, run_id: UUID) -> AnalysisRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ResourceNotFoundError(f"analysis run {run_id} not found")
        return run

    def get_run_by_job_id(self, job_id: UUID) -> AnalysisRun:
        run = self.repository.get_run_by_job_id(job_id)
        if run is None:
            raise ResourceNotFoundError(f"analysis job {job_id} not found")
        return run

    def retry_run(self, run_id: UUID, *, expected_version: int) -> AnalysisRun:
        run = self.get_run(run_id)
        if run.version != expected_version:
            raise VersionConflictError(
                f"analysis run version {run.version} does not match {expected_version}"
            )
        job_id = uuid4()
        queued = run.transition("queued", job_id=job_id)
        self.repository.save_run(queued)
        _submit_analysis_job(
            self.job_port,
            run_id,
            job_id,
            {
                "company_id": str(run.company_id),
                "run_id": str(run.run_id),
                "research_mode": run.research_mode,
                "external_research_allowed": run.external_research_allowed,
                "snapshot_ref": f"analysis_run:{run.run_id}:input_snapshot",
            },
        )
        return self.repository.get_run(run_id) or queued

    def cancel_run(self, run_id: UUID, *, expected_version: int) -> AnalysisRun:
        run = self.get_run(run_id)
        if run.version != expected_version:
            raise VersionConflictError(
                f"analysis run version {run.version} does not match {expected_version}"
            )
        cancelled = run.transition("cancelled")
        self.repository.save_run(cancelled)
        return cancelled

    def get_current_report(self, company_id: UUID) -> AnalysisReport:
        report = self.repository.get_current_report(company_id)
        if report is None:
            raise ResourceNotFoundError(f"current report for company {company_id} not found")
        return report

    def get_report(self, report_id: UUID) -> AnalysisReport:
        report = self.repository.get_report(report_id)
        if report is None:
            raise ResourceNotFoundError(f"report {report_id} not found")
        return report

    def list_reports(
        self, company_id: UUID, *, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[AnalysisReport], str | None]:
        return self.repository.list_reports(company_id, limit=limit, cursor=cursor)

    def list_suggestions(self, company_id: UUID) -> list[AnalysisSuggestion]:
        return self.repository.list_suggestions(company_id, status="pending")

    def field_catalog(self) -> dict[str, Any]:
        return field_catalog_payload()

    def core_fields(self, company_id: UUID) -> dict[str, Any]:
        profile = self.get_profile(company_id)
        current_report = self.repository.get_current_report(company_id)
        dimensions = {
            item.dimension_code: item for item in self.get_meddpicc(company_id)
        }
        suggestions = {
            (item.target_type, item.dimension_code or item.target_path): item
            for item in self.list_suggestions(company_id)
        }
        fields: list[dict[str, Any]] = []
        covered = 0
        for entry in catalog_entries():
            field_id = entry["field_id"]
            if entry["target_type"] == "profile":
                value = getattr(profile, field_id)
                suggestion = suggestions.get(("profile", field_id))
                status = "confirmed" if value not in (None, "", "待确认") else "missing"
                provenance = dict(profile.field_provenance.get(field_id) or {})
            else:
                dimension = dimensions[field_id]
                value = dimension.summary or (dimension.payload if dimension.payload else None)
                suggestion = suggestions.get(("meddpicc", field_id))
                status = dimension.status
                provenance = {
                    "evidence_refs": [dict(item) for item in dimension.evidence_refs]
                }
            if value not in (None, "", "待确认", {}, []) or suggestion is not None:
                covered += 1
            fields.append(
                {
                    **entry,
                    "value": str(value) if isinstance(value, UUID) else value,
                    "status": status,
                    "candidate": suggestion.to_dict() if suggestion else None,
                    "provenance": provenance,
                }
            )
        return {
            "catalog_version": "core-field-catalog-v1",
            "company_id": str(company_id),
            "confirmed_profile_completeness": profile.completeness_score,
            "candidate_coverage": round(covered / len(fields), 4),
            "source_counts": evidence_summary(
                current_report.evidence_refs if current_report else ()
            ),
            "fields": fields,
        }

    def review_suggestions_batch(
        self,
        company_id: UUID,
        *,
        profile_version: int,
        items: list[dict[str, Any]],
        reviewed_by: UUID | None = None,
    ) -> dict[str, Any]:
        if not items:
            raise ValueError("batch review requires at least one item")
        profile = self.get_profile(company_id)
        if profile.version != profile_version:
            raise VersionConflictError(
                f"profile version {profile.version} does not match {profile_version}"
            )
        dimensions = {
            item.dimension_code: item for item in self.get_meddpicc(company_id)
        }
        reviewed_items: list[AnalysisSuggestion] = []
        profile_changes: dict[str, Any] = {}
        profile_provenance: dict[str, Any] = {}
        dimension_updates: list[MeddpiccDimension] = []
        reviewed_targets: set[tuple[str, str]] = set()

        for request_item in items:
            suggestion = self.repository.get_suggestion(request_item["suggestion_id"])
            if suggestion is None or suggestion.company_id != company_id:
                raise ResourceNotFoundError("analysis suggestion not found for company")
            action = request_item["action"]
            accepted = action in {"accept", "edit"}
            target_key = (
                suggestion.target_type,
                suggestion.dimension_code or suggestion.target_path,
            )
            if target_key in reviewed_targets:
                raise ValueError("batch review contains duplicate target fields")
            reviewed_targets.add(target_key)
            reviewed = suggestion.review(
                "accepted" if accepted else "rejected",
                expected_version=request_item["suggestion_version"],
                reviewed_by=reviewed_by,
                review_note=request_item.get("review_note"),
            )
            value = (
                request_item.get("edited_value")
                if action == "edit"
                else suggestion.proposed_value
            )
            if action == "edit" and value is None:
                raise ValueError("edited_value is required when action is edit")

            if accepted and suggestion.target_type == "profile":
                if suggestion.target_version_at_creation != profile_version:
                    raise VersionConflictError(
                        f"suggestion target version for {suggestion.target_path} is stale"
                    )
                profile_changes[suggestion.target_path] = _normalize_profile_value(
                    suggestion.target_path, value
                )
                profile_provenance[suggestion.target_path] = {
                    "confidence": suggestion.confidence,
                    "evidence_refs": [
                        item.get("evidence_id")
                        for item in suggestion.evidence_refs
                        if item.get("evidence_id")
                    ],
                }
            elif accepted:
                code = suggestion.dimension_code or ""
                dimension = dimensions.get(code)
                if dimension is None:
                    raise ResourceNotFoundError("suggestion target dimension not found")
                if not isinstance(value, dict):
                    raise ValueError("MEDDPICC suggestion value must be an object")
                proposed = value
                dimension_updates.append(
                    dimension.patch(
                        expected_version=suggestion.target_version_at_creation,
                        status=str(proposed.get("status") or "partial"),
                        summary=_optional_text(proposed.get("summary")),
                        payload={
                            **(proposed.get("payload") if isinstance(proposed.get("payload"), dict) else {}),
                            "evidence_state": "customer_confirmed",
                            "customer_fact_status": "confirmed",
                        },
                        evidence_refs=suggestion.evidence_refs,
                        evidence_state="customer_confirmed",
                        customer_fact_status="confirmed",
                        updated_by=reviewed_by,
                    )
                )
            reviewed_items.append(reviewed)

        updated_profile = profile
        if profile_changes:
            updated_profile = profile.patch(
                profile_changes,
                expected_version=profile_version,
                updated_by=reviewed_by,
                source="accepted_analysis_suggestion",
                provenance_by_field=profile_provenance,
            )
        with self.repository.transaction() as conn:
            if profile_changes:
                self.repository.save_profile(updated_profile, _conn=conn)
            for dimension in dimension_updates:
                self.repository.save_meddpicc_dimension(dimension, _conn=conn)
            for suggestion in reviewed_items:
                self.repository.save_suggestion(suggestion, _conn=conn)
        return {
            "profile": updated_profile.to_dict(),
            "suggestions": [item.to_dict() for item in reviewed_items],
        }

    def review_suggestion(
        self,
        suggestion_id: UUID,
        *,
        accept: bool,
        expected_version: int,
        reviewed_by: UUID | None = None,
        review_note: str | None = None,
    ) -> AnalysisSuggestion:
        suggestion = self.repository.get_suggestion(suggestion_id)
        if suggestion is None:
            raise ResourceNotFoundError(f"suggestion {suggestion_id} not found")
        # Validate the suggestion version before mutating its target.
        reviewed = suggestion.review(
            "accepted" if accept else "rejected",
            expected_version=expected_version,
            reviewed_by=reviewed_by,
            review_note=review_note,
        )
        if accept:
            if suggestion.target_type == "profile":
                profile = self.get_profile(suggestion.company_id)
                updated = profile.patch(
                    {
                        suggestion.target_path: _normalize_profile_value(
                            suggestion.target_path, suggestion.proposed_value
                        )
                    },
                    expected_version=suggestion.target_version_at_creation,
                    updated_by=reviewed_by,
                    source="accepted_analysis_suggestion",
                    provenance_by_field={
                        suggestion.target_path: {
                            "confidence": suggestion.confidence,
                            "evidence_refs": [
                                item.get("evidence_id")
                                for item in suggestion.evidence_refs
                                if item.get("evidence_id")
                            ],
                        }
                    },
                )
                with self.repository.transaction() as conn:
                    self.repository.save_profile(updated, _conn=conn)
                    self.repository.save_suggestion(reviewed, _conn=conn)
            else:
                dimension = self.repository.get_meddpicc_dimension(
                    suggestion.company_id, suggestion.dimension_code or ""
                )
                if dimension is None:
                    raise ResourceNotFoundError("suggestion target dimension not found")
                proposed = (
                    suggestion.proposed_value
                    if isinstance(suggestion.proposed_value, dict)
                    else {}
                )
                updated_dimension = dimension.patch(
                    expected_version=suggestion.target_version_at_creation,
                    status=str(proposed.get("status") or "partial"),
                    summary=_optional_text(proposed.get("summary")),
                    payload=proposed.get("payload") if isinstance(proposed.get("payload"), dict) else {},
                    evidence_refs=suggestion.evidence_refs,
                    updated_by=reviewed_by,
                )
                with self.repository.transaction() as conn:
                    self.repository.save_meddpicc_dimension(updated_dimension, _conn=conn)
                    self.repository.save_suggestion(reviewed, _conn=conn)
        else:
            self.repository.save_suggestion(reviewed)

        return reviewed

    def list_contexts(self, *, owner_user_id: str | None = None) -> list[AnalysisContext]:
        loader = getattr(self.context_port, "list_contexts", None)
        if loader is None:
            return []
        return list(loader(owner_user_id=owner_user_id))

    def find_context_id(self, client_id: str) -> UUID | None:
        for context in self.list_contexts():
            aliases = {
                str(context.company_id),
                str(context.company.get("company_id", "")),
                str(context.company.get("client_id", "")),
                str(context.company.get("company_name", "")),
            }
            if client_id in aliases:
                return context.company_id
        return None

    def upsert_context(self, company_id: UUID, payload: dict[str, Any], *, reason: str) -> AnalysisContext:
        """Apply CRM/event updates through the module's context port."""
        current = self.context_port.load_context(company_id)
        if current is None:
            current = AnalysisContext(
                company_id=company_id,
                company={"company_id": str(company_id), "company_name": payload.get("name") or f"Demo Client {str(company_id)[:6]}"},
                sales_lead={}, adopted_icp={}, adopted_scale={},
            )
        company = dict(current.company)
        sales_lead = dict(current.sales_lead)
        profile = dict(current.profile)
        meddpicc = dict(current.meddpicc)
        engagement = dict(current.engagement)
        company.update({key: value for key, value in payload.items() if key in {"company_id", "company_name", "name", "industry", "city", "country", "website", "owner", "ownerName"} and value not in (None, "")})
        if "name" in company:
            company.setdefault("company_name", company["name"])
        company.setdefault("client_id", str(payload.get("client_id") or payload.get("company_id") or company_id))
        lead_keys = {"stage", "status", "signals", "source", "owner", "ownerId", "ownerName"}
        sales_lead.update({key: value for key, value in payload.items() if key in lead_keys and value not in (None, "")})
        profile_map = {
            "industry": "company_type", "company_type": "company_type", "region": "region_text", "region_text": "region_text",
            "employee_scale": "employee_scale", "business_model": "business_model", "esim_scenario": "esim_scenario",
            "coverage": "coverage", "estimated_usage": "estimated_usage", "integration": "integration",
            "compliance": "compliance", "budget": "budget_text", "budget_text": "budget_text",
            "decision_maker": "decision_maker_text", "decision_maker_text": "decision_maker_text",
            "decision_cycle": "decision_cycle_text", "decision_cycle_text": "decision_cycle_text",
        }
        for source, target in profile_map.items():
            if payload.get(source) not in (None, ""):
                profile[target] = payload[source]
        contacts = current.contacts
        if isinstance(payload.get("contacts"), list):
            contacts = tuple(item for item in payload["contacts"] if isinstance(item, dict))
        if isinstance(payload.get("meddpicc"), dict):
            meddpicc.update(payload["meddpicc"])
        if isinstance(payload.get("communication"), dict):
            communication = payload["communication"]
            engagement["latest_summary"] = communication.get("summary") or communication.get("content") or engagement.get("latest_summary")
            engagement["intent_level"] = communication.get("intent_level") or engagement.get("intent_level")
            communications = list(engagement.get("communications", []))
            communications.append(dict(communication))
            engagement["communications"] = communications
        updated = replace(current, company=company, sales_lead=sales_lead, contacts=contacts, profile=profile, meddpicc=meddpicc, engagement=engagement)
        put_context = getattr(self.context_port, "put_context", None)
        if put_context is None:
            raise InvalidStateError("context port is read-only; cannot apply event")
        put_context(updated)
        self.compat_events.append({"topic": reason, "company_id": str(company_id), "created_at": _now_iso(), **payload})
        return updated

    def score_company(self, company_id: UUID, *, change_reason: str = "manual") -> dict[str, Any]:
        context = self._source_context(company_id)
        adopted = dict(context.adopted_icp)
        total = max(0.0, min(100.0, float(adopted.get("total_score") or 0)))
        raw_dimensions = adopted.get("dimension_scores")
        dimensions = {
            code: float((raw_dimensions or {}).get(code) or adopted.get(f"{code.lower()}_score") or 0)
            for code in ("D1", "D2", "D3", "D4")
        }
        grade = str(adopted.get("grade") or "").upper()
        if grade not in {"A", "B", "C", "D"}:
            grade = "A" if total >= 80 else "B" if total >= 60 else "C" if total >= 40 else "D"
        item = {
            "client_id": str(context.company.get("company_id", company_id)),
            "name": context.company.get("company_name", str(company_id)),
            "total_score": total,
            "grade": grade,
            "dimension_scores": dimensions,
            "rank": 0,
            "scored_at": _now_iso(),
        }
        self.compat_icp_history.setdefault(str(company_id), []).append({"total_score": total, "dimension_scores": dimensions, "change_reason": change_reason, "created_at": item["scored_at"]})
        contexts = []
        for other in self.list_contexts():
            if other.company_id == company_id:
                contexts.append(item)
            else:
                contexts.append({"client_id": str(other.company.get("company_id", other.company_id)), "name": other.company.get("company_name"), "total_score": float(other.adopted_icp.get("total_score") or 0)})
        contexts.sort(key=lambda row: row["total_score"], reverse=True)
        for rank, row in enumerate(contexts, 1):
            if row.get("client_id") == item["client_id"]: item["rank"] = rank
        return item

    def score_all(self, client_ids: list[UUID] | None = None, *, change_reason: str = "batch_refresh") -> list[dict[str, Any]]:
        targets = client_ids or [context.company_id for context in self.list_contexts()]
        return [self.score_company(company_id, change_reason=change_reason) for company_id in targets]

    def _source_context(self, company_id: UUID) -> AnalysisContext:
        context = self.context_port.load_context(company_id)
        if context is None:
            raise ResourceNotFoundError(f"company {company_id} not found")
        return context

    def _analysis_context(
        self, company_id: UUID
    ) -> tuple[AnalysisContext, CustomerProfile, list[MeddpiccDimension]]:
        source = self._source_context(company_id)
        profile = self.get_profile(company_id)
        dimensions = self.get_meddpicc(company_id)
        context = replace(
            source,
            profile=profile.to_dict(),
            meddpicc={item.dimension_code: item.to_dict() for item in dimensions},
        )
        return context, profile, dimensions

    def _with_engagement_evidence(
        self, context: AnalysisContext, cutoff_at: datetime
    ) -> AnalysisContext:
        evidence = context.evidence_refs
        if self.engagement_evidence_port is not None:
            email_evidence = self.engagement_evidence_port.list_email_evidence(
                context.company_id, cutoff_at=cutoff_at, limit=50
            )
            manual_evidence = (
                self.engagement_evidence_port.list_confirmed_manual_note_evidence(
                    context.company_id, cutoff_at=cutoff_at, limit=100
                )
            )
            meeting_reader = getattr(self.engagement_evidence_port, "list_meeting_evidence", None)
            meeting_evidence = (
                meeting_reader(context.company_id, cutoff_at=cutoff_at, limit=20)
                if meeting_reader is not None else ()
            )
            evidence = _dedupe_evidence(
                evidence
                + tuple(item.to_dict() for item in email_evidence)
                + tuple(item.to_dict() for item in manual_evidence)
                + tuple(item.to_dict() for item in meeting_evidence)
            )

        communications = [
            item
            for item in evidence
            if item.get("source_type") in {"internal_email", "internal_meeting"}
        ]
        engagement = dict(context.engagement)
        if communications:
            latest = max(
                communications, key=lambda item: str(item.get("occurred_at") or "")
            )
            metadata = dict(latest.get("metadata") or {})
            engagement["latest_summary"] = latest.get("excerpt") or latest.get("title")
            if metadata.get("intent_level"):
                engagement["intent_level"] = metadata["intent_level"]
            engagement["communications"] = [
                {
                    "evidence_id": item.get("evidence_id"),
                    "summary": item.get("excerpt") or item.get("title"),
                    "direction": dict(item.get("metadata") or {}).get("direction"),
                    "occurred_at": item.get("occurred_at"),
                }
                for item in communications[-10:]
            ]
        engagement["source_counts"] = evidence_summary(evidence)
        return replace(
            context,
            engagement=engagement,
            evidence_refs=evidence,
            engagement_cutoff_at=cutoff_at,
        )

    def _with_prior_external_evidence(self, context: AnalysisContext) -> AnalysisContext:
        """Carry forward valid research citations without carrying forward claims.

        Meeting/internal evidence remains authoritative for customer facts. The
        inherited Exa/WeKnora rows are only supporting sources and therefore do
        not update profile or MEDDPICC confirmation state by themselves.
        """
        external_types = {"exa", "web", "external_web", "weknora"}
        # The current report may itself be an internal-only refresh. Search
        # report history so a later meeting refresh does not permanently lose
        # the last successful external research snapshot.
        reports, _ = self.repository.list_reports(
            context.company_id, limit=50, cursor=None
        )
        inherited: tuple[dict[str, Any], ...] = ()
        for report in reports:
            candidate = tuple(
                {
                    **dict(item),
                    "metadata": {
                        **dict(item.get("metadata") or {}),
                        "inherited_from_report_id": str(report.report_id),
                        "customer_fact_status": "knowledge_supported",
                    },
                }
                for item in report.evidence_refs
                if str(item.get("source_type") or "") in external_types
            )
            if candidate:
                inherited = candidate
                break
        if not inherited:
            return context
        return replace(
            context,
            evidence_refs=_dedupe_evidence(context.evidence_refs + inherited),
        )

    def _apply_confirmed_manual_note_updates(
        self,
        context: AnalysisContext,
        profile: CustomerProfile,
        dimensions: list[MeddpiccDimension],
    ) -> tuple[CustomerProfile, list[MeddpiccDimension], list[dict[str, Any]]]:
        profile_candidates, meddpicc_candidates, conflict_queue = confirmed_manual_note_updates(context)
        profile_changes: dict[str, Any] = {}
        profile_provenance: dict[str, Any] = {}
        for field_id, candidate in profile_candidates.items():
            # Legacy extraction payloads have no target version. They remain
            # report candidates and must be reviewed instead of bypassing the
            # optimistic-concurrency boundary for formal profile data.
            if candidate.get("target_version") != profile.version:
                continue
            value = _normalize_profile_value(field_id, candidate.get("value"))
            current = getattr(profile, field_id)
            if current not in (None, "", "待确认") and str(current) != str(value):
                continue
            evidence = dict(candidate["evidence"])
            evidence_id = str(evidence.get("evidence_id") or "")
            current_refs = list(
                dict(profile.field_provenance.get(field_id) or {}).get("evidence_refs")
                or []
            )
            if str(current) == str(value) and evidence_id in current_refs:
                continue
            profile_changes[field_id] = value
            profile_provenance[field_id] = {
                "confidence": candidate.get("confidence"),
                "evidence_refs": [evidence_id],
            }

        updated_profile = profile
        if profile_changes:
            updated_profile = profile.patch(
                profile_changes,
                expected_version=profile.version,
                updated_by=None,
                source="confirmed_manual_note",
                provenance_by_field=profile_provenance,
            )

        by_code = {item.dimension_code: item for item in dimensions}
        updated_dimensions: dict[str, MeddpiccDimension] = {}
        for code, candidate in meddpicc_candidates.items():
            dimension = by_code.get(code)
            if dimension is None:
                continue
            target_version = candidate.get("target_version")
            legacy_initial_competition = (
                code == "competition"
                and target_version is None
                and dimension.version == 0
                and dimension.status == "unknown"
                and dimension.summary in (None, "", "待确认")
            )
            if target_version != dimension.version and not legacy_initial_competition:
                continue
            value = str(candidate.get("value") or "").strip()
            if dimension.summary not in (None, "", "待确认") and dimension.summary != value:
                continue
            evidence = public_evidence_ref(dict(candidate["evidence"]))
            evidence_id = str(evidence.get("evidence_id") or "")
            existing_ids = {
                str(item.get("evidence_id") or "") for item in dimension.evidence_refs
            }
            if dimension.summary == value and evidence_id in existing_ids:
                continue
            refs = tuple(
                list(dimension.evidence_refs)
                + ([evidence] if evidence_id not in existing_ids else [])
            )
            updated_dimensions[code] = dimension.patch(
                expected_version=dimension.version,
                status="confirmed",
                summary=value,
                payload={**dimension.payload, "source": "confirmed_manual_note"},
                evidence_refs=refs,
                updated_by=None,
            )

        if profile_changes or updated_dimensions:
            with self.repository.transaction() as conn:
                if profile_changes:
                    self.repository.save_profile(updated_profile, _conn=conn)
                for dimension in updated_dimensions.values():
                    self.repository.save_meddpicc_dimension(dimension, _conn=conn)

        merged_dimensions = [
            updated_dimensions.get(item.dimension_code, item) for item in dimensions
        ]
        return updated_profile, merged_dimensions, conflict_queue

    def _safe_search_sources(
        self, company_name: str
    ) -> list[dict[str, Any]]:
        """Call the search port and never let it break the analysis pipeline."""
        if not company_name.strip():
            return []
        try:
            assert self.search_port is not None
            return self.search_port.search_company_sources(company_name)
        except Exception:
            # Search enrichment is best-effort; do not block analysis.
            return []

    def _verified_search_sources(self, context: AnalysisContext) -> list[dict[str, Any]]:
        company_name = str(
            context.company.get("company_name")
            or context.company.get("name", "")
        ).strip()
        website = str(context.company.get("website") or "").strip()
        official_domain = _website_domain(website)
        if official_domain and _is_reserved_domain(official_domain):
            return []
        verified = _filter_company_sources(
            company_name,
            official_domain,
            self._safe_search_sources(company_name),
        )
        return [_normalize_external_evidence(source) for source in verified]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _research_mode_for_trigger(
    trigger_type: str,
    trigger_context: dict[str, Any] | None,
) -> str:
    """Resolve the immutable research policy for a newly-created Run.

    External research is normally limited to the first assignment/claim. An
    operational recovery marker is created only by request_external_recovery;
    public routes cannot supply it.
    """
    if trigger_type == "assignment":
        return "initial_external"
    if (
        trigger_type == "operation"
        and isinstance(trigger_context, dict)
        and trigger_context.get("recovery_external_research") is True
    ):
        return "initial_external"
    return "internal_only"


def _submit_analysis_job(
    job_port: AnalysisJobPort,
    run_id: UUID,
    job_id: UUID,
    payload: dict[str, Any],
) -> None:
    """Pass the versioned Worker payload while retaining old test doubles."""
    try:
        job_port.submit(run_id, job_id, payload)
    except TypeError as exc:
        # Older composition roots implement the two-argument port.  They can
        # still execute the run; production adapters receive the policy payload.
        if "positional" not in str(exc) and "argument" not in str(exc):
            raise
        job_port.submit(run_id, job_id)


def _website_domain(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _is_reserved_domain(domain: str) -> bool:
    return any(
        domain == suffix or domain.endswith(f".{suffix}")
        for suffix in ("example.com", "example.org", "example.net", "test", "invalid", "localhost")
    )


def _normalize_identity(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _filter_company_sources(
    company_name: str,
    official_domain: str,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_name = _normalize_identity(company_name)
    verified: list[dict[str, Any]] = []
    for source in sources:
        source_domain = _website_domain(str(source.get("url") or ""))
        normalized_title = _normalize_identity(
            " ".join(
                str(source.get(key) or "")
                for key in ("title", "text", "highlights")
            )
        )
        domain_matches = bool(
            official_domain
            and (source_domain == official_domain or source_domain.endswith(f".{official_domain}"))
        )
        name_matches = bool(normalized_name and normalized_name in normalized_title)
        if domain_matches or name_matches:
            verified.append(source)
    return verified


def _normalize_external_evidence(source: dict[str, Any]) -> dict[str, Any]:
    """Convert platform search rows into the shared evidence contract."""
    value = dict(source)
    original_source_type = str(value.get("source_type") or "")
    source_type = (
        original_source_type
        if original_source_type in {"exa", "web", "external_web"}
        else "exa" if value.get("provider") == "exa" else "web"
    )
    text = str(
        value.get("text")
        or value.get("content")
        or value.get("snippet")
        or value.get("excerpt")
        or ""
    ).strip()
    highlights = value.get("highlights") or []
    if isinstance(highlights, str):
        highlights = [highlights]
    url = str(value.get("url") or "") or None
    raw_id = str(value.get("evidence_id") or value.get("id") or url or "external")
    prefix = "exa" if source_type == "exa" else "web"
    value.update(
        {
            "evidence_id": raw_id if raw_id.startswith(("exa:", "web:")) else f"{prefix}:{raw_id}",
            "source_type": source_type,
            "source_priority": 1,
            "text": text,
            "excerpt": text[:240],
            "highlights": [str(item) for item in highlights if str(item).strip()],
            "retrieved_at": value.get("retrieved_at") or _now_iso(),
            "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "metadata": {
                **dict(value.get("metadata") or {}),
                "research_snapshot_id": value.get("research_snapshot_id"),
                "provider_source_type": original_source_type or None,
            },
            "url": url,
        }
    )
    return value


def _context_from_snapshot(company_id: UUID, snapshot: dict[str, Any]) -> AnalysisContext:
    cutoff = snapshot.get("engagement_cutoff_at")
    cutoff_at = None
    if cutoff:
        try:
            cutoff_at = datetime.fromisoformat(str(cutoff))
        except ValueError:
            cutoff_at = None
    return AnalysisContext(
        company_id=company_id,
        company=dict(snapshot.get("company", {})),
        sales_lead=dict(snapshot.get("sales_lead", {})),
        adopted_icp=dict(snapshot.get("adopted_icp", {})),
        adopted_scale=dict(snapshot.get("adopted_scale", {})),
        contacts=tuple(snapshot.get("contacts", [])),
        engagement=dict(snapshot.get("engagement", {})),
        profile=dict(snapshot.get("profile", {})),
        meddpicc=dict(snapshot.get("meddpicc", {})),
        evidence_refs=tuple(snapshot.get("evidence_refs", [])),
        engagement_cutoff_at=cutoff_at,
    )


def _optional_text(value: Any) -> str | None:
    if value in (None, "", "pending_confirmation"):
        return None
    return str(value)


def _optional_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _normalize_profile_value(field_id: str, value: Any) -> Any:
    if field_id == "decision_maker_contact_id":
        parsed = _optional_uuid(value)
        if value not in (None, "") and parsed is None:
            raise ValueError("decision_maker_contact_id must be a UUID")
        return parsed
    return value


def _evidence_urls(evidence_refs: tuple[dict[str, Any], ...]) -> list[str]:
    return [str(item["url"]) for item in evidence_refs if item.get("url")]


def _ensure_evidence_ids(
    evidence_refs: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for item in evidence_refs:
        value = dict(item)
        if not value.get("evidence_id"):
            seed = "|".join(
                str(value.get(key) or "") for key in ("url", "title", "source_type")
            )
            value["evidence_id"] = "context:" + hashlib.sha256(
                seed.encode("utf-8")
            ).hexdigest()[:20]
        normalized.append(value)
    return tuple(normalized)


def _dedupe_evidence(
    evidence_refs: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence_refs:
        key = str(item.get("evidence_id") or item.get("url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)
