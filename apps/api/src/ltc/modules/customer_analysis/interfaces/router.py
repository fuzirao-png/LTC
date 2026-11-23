"""FastAPI Router for the v3.6 Customer Analysis contract."""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
import os
from typing import Any
from uuid import UUID, uuid4, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.errors import (
    CustomerAnalysisError,
    InvalidDimensionError,
    InvalidStateError,
    ResourceNotFoundError,
    VersionConflictError,
)
from ltc.modules.customer_analysis.domain.models import MEDDPICC_DIMENSIONS, evidence_summary
from ltc.modules.customer_analysis.domain.field_catalog import (
    CORE_MEDDPICC_FIELDS,
    CORE_PROFILE_FIELDS,
)
from ltc.modules.customer_analysis.interfaces.schemas import (
    AnalysisRunCreateRequest,
    CustomerProfilePatchRequest,
    MeddpiccUpdateRequest,
    SuggestionBatchReviewRequest,
)
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


_legacy_report_service: CustomerAnalysisService | None = None


def build_customer_analysis_router(service: CustomerAnalysisService) -> APIRouter:
    global _legacy_report_service
    _legacy_report_service = service
    router = APIRouter(tags=["Analysis"])

    def optional_auth_context(request: Request) -> AuthContext | None:
        """Apply sales ownership when the compatibility UI has a session."""
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        credentials = (
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            if scheme.lower() == "bearer" and token
            else None
        )
        try:
            return get_auth_context(
                request,
                credentials=credentials,
                access_cookie=request.cookies.get("ltc_access_token"),
            )
        except HTTPException:
            return None

    def visible_contexts(context: AuthContext | None) -> list:
        if context is None or context.actor.account_type != "sales":
            return service.list_contexts()
        return service.list_contexts(owner_user_id=str(context.actor.user_id))

    @router.get("/customer-analysis/field-catalog")
    def get_customer_analysis_field_catalog() -> dict[str, Any]:
        return _envelope(service.field_catalog())

    @router.get("/companies/{company_id}/profile")
    def get_company_profile(company_id: UUID, response: Response) -> dict[str, Any]:
        try:
            profile = service.get_profile(company_id)
            response.headers["ETag"] = _etag(profile.version)
            return _envelope(_profile_payload(profile.to_dict()))
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.patch("/companies/{company_id}/profile")
    def update_company_profile(
        company_id: UUID,
        payload: CustomerProfilePatchRequest,
        response: Response,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            profile = service.update_profile(
                company_id,
                payload.domain_changes(),
                expected_version=_parse_etag(if_match),
                updated_by=None,
            )
            response.headers["ETag"] = _etag(profile.version)
            return _envelope(_profile_payload(profile.to_dict()))
        except (CustomerAnalysisError, ValueError) as exc:
            _raise_http(exc)

    @router.get("/companies/{company_id}/meddpicc")
    def get_company_meddpicc(company_id: UUID) -> dict[str, Any]:
        try:
            dimensions = service.get_meddpicc(company_id)
            return _envelope({
                "company_id": str(company_id),
                "dimensions": [item.to_dict() for item in dimensions],
            })
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.patch("/companies/{company_id}/meddpicc/{dimension_code}")
    def update_company_meddpicc_dimension(
        company_id: UUID,
        dimension_code: str,
        payload: MeddpiccUpdateRequest,
        response: Response,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        if dimension_code not in MEDDPICC_DIMENSIONS:
            _raise_http(InvalidDimensionError(dimension_code))
        try:
            updated = service.update_meddpicc(
                company_id,
                dimension_code,
                expected_version=_parse_etag(if_match),
                status=payload.status,
                summary=payload.summary,
                payload=payload.payload,
                updated_by=None,
            )
            response.headers["ETag"] = _etag(updated.version)
            return _envelope({
                "company_id": str(company_id),
                "dimensions": [item.to_dict() for item in service.get_meddpicc(company_id)],
            })
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post(
        "/companies/{company_id}/analysis-runs",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_analysis_run(
        company_id: UUID,
        payload: AnalysisRunCreateRequest,
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        if payload.trigger_type == "assignment":
            raise HTTPException(
                status_code=403,
                detail="assignment analysis can only be triggered by the lead-claim workflow",
            )
        try:
            run = service.request_analysis(
                company_id,
                report_type=payload.report_type,
                force_refresh=payload.force_refresh,
                trigger_type=payload.trigger_type,
            )
            return _async_envelope(run.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.get("/analysis-runs/{run_id}")
    def get_analysis_run(run_id: UUID, response: Response) -> dict[str, Any]:
        try:
            run = service.get_run(run_id)
            response.headers["ETag"] = _etag(run.version)
            return _envelope(run.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post(
        "/internal/analysis-runs/{run_id}:execute",
        include_in_schema=False,
    )
    def execute_researched_analysis_run(
        run_id: UUID,
        worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    ) -> dict[str, Any]:
        expected = os.getenv("LTC_INTERNAL_WORKER_TOKEN", "")
        if (
            not expected
            or not worker_token
            or not hmac.compare_digest(expected, worker_token)
        ):
            raise HTTPException(status_code=403, detail="worker authorization failed")
        try:
            current = service.get_run(run_id)
            run = service.execute_analysis(run_id) if current.status == "queued" else current
            return _envelope(run.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post(
        "/internal/companies/{company_id}:replay-external-analysis",
        status_code=status.HTTP_202_ACCEPTED,
        include_in_schema=False,
    )
    def replay_external_analysis(
        company_id: UUID,
        worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    ) -> dict[str, Any]:
        """Operational recovery only; never exposed through the sales UI."""
        expected = os.getenv("LTC_INTERNAL_WORKER_TOKEN", "")
        if (
            not expected
            or not worker_token
            or not hmac.compare_digest(expected, worker_token)
        ):
            raise HTTPException(status_code=403, detail="worker authorization failed")
        try:
            return _async_envelope(service.request_external_recovery(company_id).to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post(
        "/analysis-runs/{run_id}:retry",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def retry_analysis_run(
        run_id: UUID,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            run = service.retry_run(run_id, expected_version=_parse_etag(if_match))
            return _async_envelope(run.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post(
        "/analysis-runs/{run_id}:cancel",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def cancel_analysis_run(
        run_id: UUID,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            run = service.cancel_run(run_id, expected_version=_parse_etag(if_match))
            return _async_envelope(run.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.get("/companies/{company_id}/analysis-reports/current")
    def get_current_analysis_report(company_id: UUID) -> dict[str, Any]:
        try:
            return _envelope(service.get_current_report(company_id).to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.get("/companies/{company_id}/analysis-reports")
    def list_analysis_reports(
        company_id: UUID,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            reports, next_cursor = service.list_reports(
                company_id, limit=limit, cursor=cursor
            )
            return {
                "request_id": _request_id(),
                "data": [item.to_dict() for item in reports],
                "page": {"next_cursor": next_cursor, "has_more": next_cursor is not None},
            }
        except (CustomerAnalysisError, ValueError) as exc:
            _raise_http(exc)

    @router.get("/analysis-reports/{report_id}")
    def get_analysis_report(report_id: UUID) -> dict[str, Any]:
        try:
            return _envelope(service.get_report(report_id).to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.get("/companies/{company_id}/analysis-suggestions")
    def list_analysis_suggestions(company_id: UUID) -> dict[str, Any]:
        return _envelope([
            item.to_dict() for item in service.list_suggestions(company_id)
        ])

    @router.get("/companies/{company_id}/core-fields")
    def get_company_core_fields(company_id: UUID) -> dict[str, Any]:
        try:
            return _envelope(service.core_fields(company_id))
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post("/companies/{company_id}/analysis-suggestions:review-batch")
    def review_analysis_suggestions_batch(
        company_id: UUID,
        payload: SuggestionBatchReviewRequest,
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            return _envelope(
                service.review_suggestions_batch(
                    company_id,
                    profile_version=payload.profile_version,
                    items=[item.model_dump() for item in payload.items],
                    reviewed_by=None,
                )
            )
        except (CustomerAnalysisError, ValueError) as exc:
            _raise_http(exc)

    @router.post("/analysis-suggestions/{suggestion_id}:accept")
    def accept_analysis_suggestion(
        suggestion_id: UUID,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            suggestion = service.review_suggestion(
                suggestion_id,
                accept=True,
                expected_version=_parse_etag(if_match),
                reviewed_by=None,
            )
            return _envelope(suggestion.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.post("/analysis-suggestions/{suggestion_id}:reject")
    def reject_analysis_suggestion(
        suggestion_id: UUID,
        if_match: str = Header(alias="If-Match"),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        del idempotency_key
        try:
            suggestion = service.review_suggestion(
                suggestion_id,
                accept=False,
                expected_version=_parse_etag(if_match),
                reviewed_by=None,
            )
            return _envelope(suggestion.to_dict())
        except CustomerAnalysisError as exc:
            _raise_http(exc)

    @router.get("/health", include_in_schema=False)
    def legacy_health() -> dict[str, Any]:
        return {"code": 0, "message": "success", "data": {"status": "ok"}, "request_id": _request_id()}

    @router.get("/api/analysis/profile/{client_id}", include_in_schema=False)
    def legacy_profile(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        profile = service.get_profile(company_id).to_dict()
        context = service._source_context(company_id)
        overview = {
            "completeness": f"{round(profile['completeness_score'] * 100):g}%",
            "budget": profile.get("budget_text") or "\u5f85\u786e\u8ba4",
            "decision_maker": profile.get("decision_maker_text") or "\u5f85\u786e\u8ba4",
            "cycle": profile.get("decision_cycle_text") or "\u5f85\u786e\u8ba4",
        }
        return _legacy_envelope({
            "client_id": client_id,
            "name": context.company.get("company_name", client_id),
            "overview": overview,
            "profile": _legacy_profile_payload(service, company_id),
            "missing_fields": profile.get("missing_fields", []),
            "updated_at": profile.get("updated_at"),
        })

    @router.put("/api/analysis/profile/{client_id}", include_in_schema=False)
    def legacy_profile_update(client_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        changes = dict(payload)
        if "budget" in changes: changes["budget_text"] = changes.pop("budget")
        if "decision_maker" in changes: changes["decision_maker_text"] = changes.pop("decision_maker")
        if "decision_cycle" in changes: changes["decision_cycle_text"] = changes.pop("decision_cycle")
        changes.pop("source", None)
        current = service.get_profile(company_id)
        updated = service.update_profile(company_id, changes, expected_version=current.version)
        return _legacy_envelope(updated.to_dict())

    @router.post("/api/analysis/report/generate", include_in_schema=False)
    def legacy_generate(payload: dict[str, Any]) -> dict[str, Any]:
        company_id = _resolve_context_id(service, str(payload.get("client_id", "")))
        run = service.request_analysis(company_id, force_refresh=bool(payload.get("force_refresh", False)), trigger_type=str(payload.get("trigger_type", "manual")))
        return _legacy_envelope({"job_id": str(run.current_job_id), "status": run.status}, message="accepted")

    @router.get("/api/analysis/report/{client_id}/history", include_in_schema=False)
    def legacy_history(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        reports, _ = service.list_reports(company_id, limit=200, cursor=None)
        return _legacy_envelope({"items": [{"version": item.version_no, "generated_at": item.generated_at.isoformat(), "health_grade": item.health_grade, "summary": item.summary} for item in reports]})

    @router.get("/api/analysis/report/{client_id}", include_in_schema=False)
    def legacy_report(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        report = service.get_current_report(company_id).to_dict()
        return _legacy_envelope(_legacy_report_payload(client_id, report))

    @router.get("/api/analysis/guide/{client_id}", include_in_schema=False)
    def legacy_guide(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        report = service.get_current_report(company_id).to_dict()
        return _legacy_envelope({"client_id": client_id, **report["sales_guide"], "updated_at": report["generated_at"]})

    @router.get("/api/analysis/list", include_in_schema=False)
    def legacy_analysis_list(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        sort_by: str = "score",
        order: str = "desc",
        context: AuthContext | None = Depends(optional_auth_context),
    ) -> dict[str, Any]:
        contexts = visible_contexts(context)
        rows = []
        for context in contexts:
            company_id = context.company_id
            profile = service.get_profile(company_id).to_dict()
            current = service.repository.get_current_report(company_id)
            score = float(context.adopted_icp.get("total_score") or 0)
            rows.append({
                "client_id": context.company.get("company_id", str(company_id)),
                "name": context.company.get("company_name", str(company_id)),
                "location": context.company.get("city", "\u5f85\u786e\u8ba4"),
                "country": context.company.get("country_code") or context.company.get("country") or "",
                "region_code": context.company.get("region_code") or context.company.get("region") or "",
                "time_zone": context.company.get("time_zone") or "",
                "company_type": context.company.get("industry", "\u5f85\u786e\u8ba4"),
                "health_grade": current.health_grade if current else _preview_health(score),
                "intention_level": current.intention_level if current else _preview_intention(score, context.engagement),
                "budget": profile.get("budget_text") or "\u5f85\u786e\u8ba4",
                "summary": current.summary if current else _preview_summary(context.company.get("company_name", "\u5f85\u786e\u8ba4"), score),
                "quick_metrics": {"market_opportunity": "\u5f3a" if score >= 70 else "\u4e2d", "demand_confirmation": context.meddpicc.get("identify_pain", {}).get("status", "\u5f85\u786e\u8ba4"), "competition_status": context.meddpicc.get("competition", {}).get("status", "\u5f85\u786e\u8ba4"), "compliance_requirement": profile.get("compliance") or "\u5f85\u786e\u8ba4"},
                "icp_score": score,
                "rank": 0,
                "report_generated": current is not None,
                # E1: additional fields for frontend KPI alignment
                "decision_maker_text": profile.get("decision_maker_text") or "\u5f85\u786e\u8ba4",
                "decision_cycle_text": profile.get("decision_cycle_text") or "\u5f85\u786e\u8ba4",
                "employee_scale": profile.get("employee_scale") or context.company.get("employee_scale") or "\u5f85\u786e\u8ba4",
                "region_text": profile.get("region_text") or context.company.get("region_code") or context.company.get("city") or "\u5f85\u786e\u8ba4",
                "profile_completeness": profile.get("completeness_score"),
                "report_coverage": _list_report_coverage(
                    service, company_id, profile, context.meddpicc
                ),
                "decision_team_label": profile.get("decision_maker_team_label") or "\u5f85\u786e\u8ba4",
                # E3: profile_structure for inline card display
                "profile_structure": _build_profile_structure(
                    profile,
                    context,
                    current.report_payload if current else None,
                ),
            })
        rows.sort(key=lambda item: item["icp_score"], reverse=order != "asc")
        for rank, item in enumerate(sorted(rows, key=lambda item: item["icp_score"], reverse=True), 1): item["rank"] = rank
        start, end = (page - 1) * page_size, page * page_size
        return _legacy_envelope({"items": rows[start:end], "total": len(rows)})

    @router.get("/api/analysis/jobs/{job_id}", include_in_schema=False)
    def legacy_job(job_id: str) -> dict[str, Any]:
        try:
            run = service.get_run_by_job_id(UUID(job_id))
            report = service.repository.get_report(run.report_id) if run.report_id else None
        except (CustomerAnalysisError, ValueError) as exc:
            _raise_http(exc)
        return _legacy_envelope({
            "job_id": job_id,
            "client_id": str(run.company_id),
            "status": run.status,
            "result_payload": {
                "client_id": str(run.company_id),
                "report_id": str(run.report_id) if run.report_id else None,
                "report_version": report.version_no if report else None,
            },
            "error_message": run.error_message,
        })

    @router.get("/api/customers/analysis/list", include_in_schema=False)
    def legacy_front_list(
        page: int = Query(1, ge=1),
        pageSize: int = Query(20, ge=1, le=100),
        context: AuthContext | None = Depends(optional_auth_context),
    ) -> dict[str, Any]:
        result = legacy_analysis_list(page=page, page_size=pageSize, context=context)
        items = result["data"]["items"]
        adapted = [{"customerId": item["client_id"], "client_id": item["client_id"], "customerName": item["name"], "companyName": item["name"], "industry": item["company_type"], "country": item.get("country") or "", "city": item.get("location") or "", "region": item.get("region_code") or "", "timeZone": item.get("time_zone") or "", "opportunityScore": item["icp_score"], "icpScore": item["icp_score"], "riskLevel": "low" if item["icp_score"] >= 85 else "medium" if item["icp_score"] >= 70 else "high", "profileCompleteness": item.get("profile_completeness"), "reportCoverage": item.get("report_coverage"), "budget": item["budget"], "analysisSummary": item["summary"], "reportGenerated": item["report_generated"], "reportId": None, "decisionMakerText": item.get("decision_maker_text") or "待确认", "decisionCycleText": item.get("decision_cycle_text") or "待确认", "employeeScale": item.get("employee_scale") or "待确认", "regionText": item.get("region_text") or "待确认", "decisionTeamLabel": item.get("decision_team_label") or "待确认", "completenessScore": item.get("profile_completeness") or 0, "profileStructure": item.get("profile_structure")} for item in items]
        average_report_coverage = (
            round(sum(float(item.get("reportCoverage") or 0) for item in adapted) / len(adapted), 4)
            if adapted else 0
        )
        return {"success": True, "list": adapted, "items": adapted, "page": page, "pageSize": pageSize, "total": result["data"]["total"], "summary": {"analyzedCount": result["data"]["total"], "averageProfileCompleteness": round(sum(float(item.get("profileCompleteness") or 0) for item in adapted) / len(adapted), 4) if adapted else 0, "averageReportCoverage": average_report_coverage}}

    @router.get("/api/customers/analysis/detail", include_in_schema=False)
    def legacy_front_detail(id: str = Query(..., alias="id")) -> dict[str, Any]:
        company_id = _resolve_context_id(service, id)
        context = service._source_context(company_id)
        profile = service.get_profile(company_id).to_dict()
        return {"success": True, "data": {"customerId": id, "client_id": id, "customerName": context.company.get("company_name", id), "companyName": context.company.get("company_name", id), "industry": context.company.get("industry"), "customerPerspective": {"concerns": context.meddpicc.get("identify_pain", {}).get("summary")}, "latestNews": [{"title": "Recent customer activity", "summary": context.engagement.get("latest_summary")}], "decisionTeam": {"count": len(context.contacts), "label": f"{len(context.contacts)} people"}, "budget": profile.get("budget_text"), "decisionMaker": profile.get("decision_maker_text"), "decisionCycle": profile.get("decision_cycle_text"), "icpScore": float(context.adopted_icp.get("total_score") or 0), "opportunityScore": float(context.adopted_icp.get("total_score") or 0)}}

    @router.get("/api/customers/analysis/contacts", include_in_schema=False)
    def legacy_front_contacts(id: str = Query(..., alias="id")) -> dict[str, Any]:
        company_id = _resolve_context_id(service, id)
        context = service._source_context(company_id)
        contacts = [{"contactId": item.get("contact_id"), "name": item.get("name"), "title": item.get("title", ""), "email": item.get("email", "")} for item in context.contacts]
        relations = [{"from": contacts[0]["contactId"], "to": contacts[1]["contactId"], "relationType": "collaborative decision"}] if len(contacts) > 1 else []
        return {"success": True, "customerId": id, "client_id": id, "contacts": contacts, "relations": relations}

    @router.get("/api/customers/analysis/report", include_in_schema=False)
    def legacy_front_report(id: str = Query(..., alias="id")) -> dict[str, Any]:
        return {"success": True, "data": _legacy_report_payload(id, service.get_current_report(_resolve_context_id(service, id)).to_dict())}

    @router.get("/api/customers/{client_id}/report", include_in_schema=False)
    def legacy_customer_report(client_id: str) -> dict[str, Any]:
        return {"success": True, "data": _legacy_report_payload(client_id, service.get_current_report(_resolve_context_id(service, client_id)).to_dict())}

    @router.get("/api/customers/{client_id}/360", include_in_schema=False)
    def legacy_customer_360(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        profile = service.get_profile(company_id).to_dict()
        try:
            report = service.get_current_report(company_id).to_dict()
        except ResourceNotFoundError:
            # No persisted AnalysisReport — build from _analysis_context on demand
            ctx, domain_profile, dimensions = service._analysis_context(company_id)
            from ltc.modules.customer_analysis.domain.reporting import build_template_report
            content = build_template_report(ctx)
            report = {
                "report_id": str(uuid4()),
                "company_id": str(company_id),
                "analysis_run_id": str(uuid4()),
                "report_type": "customer_analysis",
                "version_no": 0,
                "schema_version": "0.1",
                "prompt_version": None,
                "generation_attempts": 1,
                "header": content.report_payload.get("header", {}),
                "customer_view": content.report_payload.get("customer_view", {}),
                "summary": content.summary,
                "health_grade": None,
                "intention_level": None,
                "confidence": content.confidence,
                "section_confidence": content.section_confidence,
                "low_confidence_sections": [],
                "data_sources": [],
                "evidence_refs": [],
                "profile_snapshot": domain_profile.to_dict(),
                "meddpicc_snapshot": {dim.dimension_code: {"level": dim.level, "status": dim.status, "desc": dim.summary} for dim in dimensions},
                "icp_snapshot": dict(ctx.adopted_icp) if ctx.adopted_icp else {},
                "scale_snapshot": {},
                **{
                    name: content.report_payload.get(name, {})
                    for name in ("market", "company", "competitor", "pain", "product")
                },
                "modules": [
                    {"module_name": name, "sections": list(content.report_payload.get(name, {}).get("sections", []))}
                    for name in ("market", "company", "competitor", "pain", "product")
                ],
                "sales_guide": content.sales_guide_payload,
                "generated_by": "legacy_on_demand",
                "model_name": None,
                "content_source": "template",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "superseded_at": None,
            }
        analysis = _legacy_report_payload(client_id, report)["analysis_report"]
        # E2: profile_structure — reuse shared helper
        context = service._source_context(company_id)
        profile_structure = _build_profile_structure(
            profile,
            context,
            report,
        )
        return {"success": True, "data": {"company_id": client_id, "customer_profile": _legacy_profile_payload(service, company_id), "meddpicc": _legacy_meddpicc_payload(service, company_id), "analysis_report": analysis, "analysis_modules": analysis, "profile_structure": profile_structure, "communications": list(context.engagement.get("communications", [])), "latest_report": {"report_id": report["report_id"], "summary": report["summary"], "content_source": report["content_source"]}}}

    @router.post("/api/analysis/icp/score/{client_id}", include_in_schema=False)
    def legacy_icp_score(client_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        item = service.score_company(company_id, change_reason="manual")
        return _legacy_envelope({"job_id": str(uuid4()), "status": "completed", "score": item}, message="accepted")

    @router.post("/api/analysis/icp/batch", include_in_schema=False)
    def legacy_icp_batch(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        requested = (payload or {}).get("client_ids") or []
        ids = [_resolve_context_id(service, str(item)) for item in requested] if requested else None
        items = service.score_all(ids, change_reason="batch_refresh")
        return _legacy_envelope({"count": len(items), "items": items}, message="accepted")

    @router.get("/api/analysis/meddpicc/{client_id}", include_in_schema=False)
    def legacy_meddpicc(client_id: str) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        dimensions = service.get_meddpicc(company_id)
        return _legacy_envelope({"client_id": client_id, **{item.dimension_code: {"level": item.level, "status": item.status, "desc": item.summary, **item.payload} for item in dimensions}, "updated_at": _now_iso()})

    @router.put("/api/analysis/meddpicc/{client_id}", include_in_schema=False)
    def legacy_meddpicc_update(client_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        company_id = _resolve_context_id(service, client_id)
        for code, value in payload.items():
            if code not in MEDDPICC_DIMENSIONS or not isinstance(value, dict): continue
            current = next(item for item in service.get_meddpicc(company_id) if item.dimension_code == code)
            service.update_meddpicc(company_id, code, expected_version=current.version, status=str(value.get("status", "partial")), summary=value.get("desc") or value.get("summary"), payload={key: val for key, val in value.items() if key not in {"status", "desc", "summary", "level"}}, level=value.get("level"))
        return legacy_meddpicc(client_id)

    @router.get("/api/sales/dashboard", include_in_schema=False)
    def legacy_sales_dashboard(request: Request) -> dict[str, Any]:
        auth_context = optional_auth_context(request)
        items = []
        for context in visible_contexts(auth_context):
            report = service.repository.get_current_report(context.company_id)
            score = float(context.adopted_icp.get("total_score") or 0)
            items.append({"company_id": context.company.get("company_id", str(context.company_id)), "company_name": context.company.get("company_name"), "stage": "proposal" if report else "acquired", "stage_dates": {"report_generated_at": report.generated_at.isoformat() if report else None}, "strategy": {"next_action": "\u8865\u9f50\u51b3\u7b56\u94fe\u8bc1\u636e", "channel": "meeting"}, "deal_amount": 0.0, "last_follow_up_at": None, "report_generated": report is not None, "report_id": str(report.report_id) if report else None, "health_grade": report.health_grade if report else _preview_health(score), "icp_score": score, "customer_scale": service.get_profile(context.company_id).employee_scale, "data_source": "demo_derived", "is_estimated": True})
        converted = sum(1 for item in items if item["stage"] == "won")
        rank_metrics: dict[str, Any] = {
            "team_quota": None,
            "team_target": None,
            "personal_rank": None,
            "team_size": 0,
            "company_rank": None,
            "company_size": 0,
            "average_deal_amount": None,
            "data_source": "database_derived",
            "is_estimated": False,
        }
        if auth_context is not None and auth_context.actor.account_type == "sales":
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            with service.repository._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.user_id, u.region_code,
                               COUNT(sl.lead_id) FILTER (
                                   WHERE sl.pipeline_stage = 'won'
                                     AND sl.closed_at >= %s
                               )::integer AS won_count
                        FROM ltc.user_account u
                        LEFT JOIN ltc.sales_lead sl
                          ON sl.current_owner_user_id = u.user_id
                        WHERE u.account_type = 'sales' AND u.status = 'active'
                        GROUP BY u.user_id, u.region_code
                        """,
                        (month_start,),
                    )
                    sales_rows = cursor.fetchall()
            current_id = str(auth_context.actor.user_id)
            current_row = next((row for row in sales_rows if str(row[0]) == current_id), None)
            if current_row is not None:
                personal_won = int(current_row[2] or 0)
                team_rows = [row for row in sales_rows if row[1] == current_row[1]]
                rank_metrics.update({
                    "personal_rank": 1 + sum(int(row[2] or 0) > personal_won for row in team_rows),
                    "team_size": len(team_rows),
                    "company_rank": 1 + sum(int(row[2] or 0) > personal_won for row in sales_rows),
                    "company_size": len(sales_rows),
                })
        return {"success": True, "data": {"overview": {"total_leads": len(items), "converted_leads": converted, "conversion_rate": round(converted / len(items), 4) if items else 0, "total_contract_amount_year": 0.0, "personal_target_completion": 0, "latest_follow_up_at": None, "data_source": "demo_derived", "is_estimated": True}, "team_metrics": rank_metrics, "customers": items}}

    @router.get("/api/boss/dashboard", include_in_schema=False)
    def legacy_boss_dashboard() -> dict[str, Any]:
        contexts = service.list_contexts(); reports = [service.repository.get_current_report(item.company_id) for item in contexts]
        run_counts = service.repository.count_runs_by_status()
        failed = run_counts.get("failed", 0)
        jobs = sum(run_counts.values())
        teams = [{"team": context.company.get("owner", "\u672a\u5206\u914d\u56e2\u961f"), "country": [context.company.get("country", "\u5f85\u786e\u8ba4")], "sales_count": 1, "regional_contract_amount": 0.0, "health_status": _health_status(float(context.adopted_icp.get("total_score") or 0)), "customer_scale": [service.get_profile(context.company_id).employee_scale], "customer_count": 1, "data_source": "demo_derived", "is_estimated": True} for context in contexts]
        return {"success": True, "data": {"ceo_metrics": {"profit": 0, "total_contract_amount": 0.0, "report_generated_count": sum(1 for item in reports if item), "data_source": "demo_derived", "is_estimated": True}, "regional_teams": teams, "agent_monitoring": {"system_trust": round(1 - failed / jobs, 4) if jobs else 1.0, "error_rate": round(failed / jobs, 4) if jobs else 0.0, "total_jobs": jobs, "failed_jobs": failed, "event_count": len(service.compat_events), "data_source": "demo_derived", "is_estimated": True}, "team_assignment": []}}

    @router.post("/internal/events/lead-created", include_in_schema=False)
    def legacy_lead_created(payload: dict[str, Any]) -> dict[str, Any]:
        return _process_legacy_event(service, payload, "new_lead")

    @router.post("/internal/events/customer-assigned", include_in_schema=False)
    def legacy_customer_assigned(payload: dict[str, Any]) -> dict[str, Any]:
        client_id = payload.get("client_id") or payload.get("company_id") or payload.get("customerId")
        if not client_id: raise HTTPException(status_code=422, detail="client_id/company_id/customerId is required")
        normalized = dict(payload.get("payload") or {})
        normalized.update({key: payload[key] for key in ("customerName", "ownerId", "ownerName", "source") if payload.get(key) is not None})
        normalized["name"] = payload.get("customerName") or normalized.get("name")
        return _process_legacy_event(service, {"client_id": client_id, "payload": normalized}, "customer_assigned")

    @router.post("/internal/events/communication-updated", include_in_schema=False)
    def legacy_communication_updated(payload: dict[str, Any]) -> dict[str, Any]:
        client_id = str(payload.get("client_id", "")); company_id = _resolve_context_id(service, client_id)
        service.upsert_context(company_id, {"communication": payload.get("payload") or {}}, reason="communication_update")
        return _legacy_envelope({"client_id": client_id, "status": "processed"})

    @router.post("/internal/events/crawl-finished", include_in_schema=False)
    def legacy_crawl_finished(payload: dict[str, Any]) -> dict[str, Any]:
        client_id = str(payload.get("client_id", "")); company_id = _resolve_context_id(service, client_id)
        service.upsert_context(company_id, dict(payload.get("payload") or {}), reason="crawl_refresh")
        return _legacy_envelope({"client_id": client_id, "status": "processed"})

    @router.get("/api/analysis/icp/ranking", include_in_schema=False)
    def legacy_ranking(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        items = []
        for context in service.list_contexts():
            items.append({"client_id": context.company.get("company_id", str(context.company_id)), "name": context.company.get("company_name"), "total_score": float(context.adopted_icp.get("total_score") or 0)})
        items.sort(key=lambda item: item["total_score"], reverse=True)
        for rank, item in enumerate(items, 1): item["rank"] = rank
        start, end = (page - 1) * page_size, page * page_size
        return _legacy_envelope({"items": items[start:end], "total": len(items)})

    @router.get("/", include_in_schema=False)
    def legacy_root() -> dict[str, Any]:
        return {"message": "Customer Analysis Agent Demo is running.", "docs": "/api/v1/docs"}

    return router


def _process_legacy_event(service: CustomerAnalysisService, payload: dict[str, Any], reason: str) -> dict[str, Any]:
    client_id = str(payload.get("client_id", "")); context_id = service.find_context_id(client_id)
    if context_id is None:
        try:
            context_id = UUID(client_id)
        except ValueError:
            context_id = uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), client_id)
    event_payload = dict(payload.get("payload") or {})
    event_payload.setdefault("company_id", str(context_id))
    event_payload.setdefault("client_id", client_id)
    service.upsert_context(context_id, event_payload, reason=reason)
    score = service.score_company(context_id, change_reason=reason)
    return _legacy_envelope({"client_id": client_id, "status": "processed", "icp_score": score["total_score"]})


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _health_status(score: float) -> str:
    return "\u826f\u597d" if score >= 85 else "\u8b66\u544a" if score >= 70 else "\u5f02\u5e38"


def _resolve_context_id(service: CustomerAnalysisService, client_id: str) -> UUID:
    for context in service.list_contexts():
        if client_id in {str(context.company_id), str(context.company.get("company_id", "")), str(context.company.get("client_id", "")), str(context.company.get("company_name", ""))}:
            return context.company_id
    raise ResourceNotFoundError(f"client_id {client_id} not found")


def _legacy_envelope(data: Any, *, message: str = "success") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data, "request_id": _request_id()}


def _build_profile_structure(
    profile: dict[str, Any],
    context: Any,
    report_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build profile_structure payload from context and profile data."""
    extra = profile.get("extra_payload") or {}
    report_view = (report_payload or {}).get("customer_view") or {}
    return {
        "customer_view": {
            "concerns": extra.get("concerns") or report_view.get("concerns") or context.meddpicc.get("identify_pain", {}).get("summary") or "待分析",
            "partners": extra.get("partners") or report_view.get("partners") or "待确认",
            "impression_of_us": extra.get("impression_of_us") or report_view.get("impression_of_us") or context.engagement.get("latest_summary") or "待评估",
        },
        "latest_news": [
            summary_item
            for summary_item in [
                {"title": "经营概况", "summary": context.company.get("website", "") or None},
                {"title": "近期动态", "summary": context.engagement.get("latest_summary", "") or None},
            ]
            if summary_item["summary"]
        ] or [{"title": "暂无资讯", "summary": "暂无客户资讯数据"}],
    }


def _legacy_profile_payload(service: CustomerAnalysisService, company_id: UUID) -> dict[str, Any]:
    profile = service.get_profile(company_id).to_dict()
    return {
        **profile,
        "client_id": str(company_id),
        "region": profile.get("region_text") or "\u5f85\u786e\u8ba4",
        "budget": profile.get("budget_text") or "\u5f85\u786e\u8ba4",
        "decision_maker": profile.get("decision_maker_text") or "\u5f85\u786e\u8ba4",
        "decision_cycle": profile.get("decision_cycle_text") or "\u5f85\u786e\u8ba4",
        "completeness_score": round(float(profile.get("completeness_score") or 0) * 100),
        "overview": {
            "completeness": f"{round(float(profile.get('completeness_score') or 0) * 100):g}%",
            "budget": profile.get("budget_text") or "\u5f85\u786e\u8ba4",
            "decision_maker": profile.get("decision_maker_text") or "\u5f85\u786e\u8ba4",
            "cycle": profile.get("decision_cycle_text") or "\u5f85\u786e\u8ba4",
        },
    }


def _legacy_meddpicc_payload(service: CustomerAnalysisService, company_id: UUID) -> dict[str, Any]:
    result: dict[str, Any] = {}
    profile = service.get_profile(company_id).to_dict()
    for item in service.get_meddpicc(company_id):
        payload = dict(item.payload)
        payload.update({"level": item.level, "status": item.status, "desc": item.summary})
        if item.dimension_code == "economic_buyer":
            payload.setdefault("name", profile.get("decision_maker_text") or "\u5f85\u786e\u8ba4")
        if item.dimension_code == "identify_pain":
            payload.setdefault("identified", item.status in {"partial", "confirmed"})
        result[item.dimension_code] = payload
    return result


def _flatten_report_sections(report: dict[str, Any]) -> dict[str, Any]:
    """Convert structured report modules into PRD-compliant 5-section flat text.

    Each section is assembled from its sub-fields with clear headings.
    The original structured fields remain in ``_raw`` for consumers that need them.
    """

    def _str(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "；".join(filter(None, (_str(item) for item in v)))
        if isinstance(v, dict):
            lines: list[str] = []
            for key, val in v.items():
                s = _str(val)
                if s:
                    lines.append(f"{key}: {s}" if not s.startswith(key) else s)
            return "；".join(lines)
        return str(v)

    def _evidence_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            title = _str(value.get("title"))
            excerpt = _str(value.get("excerpt"))
            source_type = _str(value.get("source_type"))
            if title:
                return title
            if excerpt:
                return excerpt
            if source_type == "internal_manual_note":
                return "销售手工记录"
            if source_type == "internal_email":
                return "邮件证据"
            return ""
        text = _str(value)
        if text.startswith("internal-manual-note:"):
            return "销售手工记录"
        if text.startswith("internal-email:"):
            return "邮件证据"
        if text.startswith("context:"):
            return "客户上下文"
        return text

    market = report.get("market", {})
    market_structure = market.get("structure", {})
    market_lines = []
    if market_structure.get("tam"):
        market_lines.append(f"【总市场规模(TAM)】{market_structure['tam']}")
    if market_structure.get("sam"):
        market_lines.append(f"【可服务市场(SAM)】{market_structure['sam']}")
    if market_structure.get("som"):
        market_lines.append(f"【可获取市场(SOM)】{market_structure['som']}")
    if market_structure.get("competitor_landscape"):
        cl = market_structure["competitor_landscape"]
        if isinstance(cl, list):
            market_lines.append(f"【竞争格局】{_str(cl)}")
    if market_structure.get("coverage_judgement"):
        market_lines.append(f"【覆盖判断】{_str(market_structure['coverage_judgement'])}")
    if market.get("trend"):
        market_lines.append(f"【市场趋势】{_str(market['trend'])}")
    for item in market.get("scenario_demand", []):
        if isinstance(item, dict):
            parts = []
            if item.get("scenario"): parts.append(f"场景: {item['scenario']}")
            if item.get("demand"): parts.append(f"需求: {item['demand']}")
            evidence_text = _evidence_text(item.get("evidence"))
            if evidence_text:
                parts.append(f"证据: {evidence_text}")
            market_lines.append(f"【场景需求】{'；'.join(parts)}")
    for item in market.get("scenario_opportunity", []):
        if isinstance(item, dict):
            parts = []
            if item.get("scenario"): parts.append(f"场景: {item['scenario']}")
            if item.get("opportunity"): parts.append(f"机会: {item['opportunity']}")
            if item.get("size"): parts.append(f"规模: {item['size']}")
            if item.get("our_fit"): parts.append(f"我方匹配: {item['our_fit']}")
            market_lines.append(f"【场景机会】{'；'.join(parts)}")
    market_analysis = "\n\n".join(market_lines) if market_lines else "暂无市场分析数据"

    company = report.get("company", {})
    company_lines = []
    if company.get("operation"):
        company_lines.append(f"【经营分析】{_str(company['operation'])}")
    biz = company.get("business", {})
    if biz:
        biz_parts = []
        if biz.get("main_business"): biz_parts.append(f"主营业务: {biz['main_business']}")
        if biz.get("revenue_model"): biz_parts.append(f"营收模型: {biz['revenue_model']}")
        if biz.get("geography"): biz_parts.append(f"覆盖区域: {biz['geography']}")
        if biz.get("employee_scale"): biz_parts.append(f"员工规模: {biz['employee_scale']}")
        if biz_parts:
            company_lines.append(f"【业务分析】{'；'.join(biz_parts)}")
    prod = company.get("product", {})
    if prod:
        prod_parts = []
        if prod.get("esim_scenario"): prod_parts.append(f"eSIM场景: {prod['esim_scenario']}")
        if prod.get("integration"): prod_parts.append(f"集成方式: {prod['integration']}")
        if prod.get("estimated_usage"): prod_parts.append(f"预估用量: {prod['estimated_usage']}")
        if prod_parts:
            company_lines.append(f"【产品分析】{'；'.join(prod_parts)}")
    dc = company.get("decision_chain", {})
    if dc:
        dc_parts = []
        for code, val in dc.items():
            if isinstance(val, dict):
                status = val.get("level") or val.get("status") or ""
                desc = val.get("desc") or val.get("summary") or _str(val)
            else:
                status = ""
                desc = _str(val)
            if desc:
                dc_parts.append(f"{code}({status}):{desc}" if status else f"{code}:{desc}")
        if dc_parts:
            company_lines.append(f"【决策链分析】{'；'.join(dc_parts)}")
    if company.get("target_market"):
        company_lines.append(f"【目标市场】{_str(company['target_market'])}")
    company_analysis = "\n\n".join(company_lines) if company_lines else "暂无公司分析数据"

    competitor = report.get("competitor", {})
    competitor_lines = []
    products = competitor.get("products", [])
    if products:
        names = [p["name"] if isinstance(p, dict) and p.get("name") else _str(p) for p in products]
        competitor_lines.append(f"【竞品产品】{'、'.join(filter(None, names))}")
    services = competitor.get("services", [])
    if services:
        names = [s["name"] if isinstance(s, dict) and s.get("name") else _str(s) for s in services]
        competitor_lines.append(f"【竞品服务】{'、'.join(filter(None, names))}")
    pricing = competitor.get("pricing", [])
    if pricing:
        names = []
        for p in pricing:
            if isinstance(p, dict):
                nm = p.get("name", "")
                pr = p.get("price_range", "")
                names.append(f"{nm}({pr})" if pr else nm)
            else:
                names.append(_str(p))
        competitor_lines.append(f"【竞品定价】{'、'.join(filter(None, names))}")
    advantages = competitor.get("advantages", [])
    if advantages:
        competitor_lines.append(f"【竞品优势】{_str(advantages)}")
    weaknesses = competitor.get("weaknesses", [])
    if weaknesses:
        competitor_lines.append(f"【竞品劣势】{_str(weaknesses)}")
    competitor_analysis = "\n\n".join(competitor_lines) if competitor_lines else "暂无竞争分析数据"

    product = report.get("product", {})
    product_lines = []
    if product.get("requirement"):
        product_lines.append(f"【需求分析】{_str(product['requirement'])}")
    recommended = product.get("recommended", [])
    if recommended:
        items = []
        for r in recommended:
            if isinstance(r, dict):
                nm = r.get("name", "")
                price = r.get("price", "")
                rationale = r.get("rationale", "")
                diff = r.get("our_diff", "")
                parts = [nm]
                if price: parts.append(f"参考价: {price}")
                if rationale: parts.append(f"推荐理由: {rationale}")
                if diff: parts.append(f"我方差异: {diff}")
                items.append("；".join(parts))
            else:
                items.append(_str(r))
        product_lines.append(f"【推荐产品】{'；'.join(items)}")
    rp = product.get("recommended_price", {})
    if rp:
        rp_parts = []
        if rp.get("range"): rp_parts.append(f"价格区间: {rp['range']}")
        if rp.get("rationale"): rp_parts.append(f"定价理由: {rp['rationale']}")
        if rp.get("payment_terms"): rp_parts.append(f"付款条件: {rp['payment_terms']}")
        if rp_parts:
            product_lines.append(f"【推荐定价】{'；'.join(rp_parts)}")
    actions = product.get("actions", [])
    if actions:
        product_lines.append(f"【行动建议】{'；'.join(filter(None, (_str(a) for a in actions)))}")
    product_suggestion = "\n\n".join(product_lines) if product_lines else "暂无产品建议数据"

    sales_guide = report.get("_meta", {}).get("sales_guide", report.get("sales_guide", {}))
    guide_text = _str(sales_guide) if sales_guide else "暂无销售指引数据"

    return {
        "market_analysis": market_analysis,
        "company_analysis": company_analysis,
        "competitor_analysis": competitor_analysis,
        "product_suggestion": product_suggestion,
        "sales_guidance": guide_text,
        # Preserve report provenance through the legacy /360 compatibility
        # route. The frontend uses this to distinguish real output from the
        # deterministic template fallback.
        "content_source": report.get("content_source") or "missing",
        "generated_by": report.get("generated_by"),
        "model_name": report.get("model_name"),
        "generated_at": report.get("generated_at"),
        "report_id": report.get("report_id"),
        "research_meta": dict(report.get("research_meta") or {}),
        "_raw": {
            "market": market,
            "company": company,
            "competitor": competitor,
            "pain": report.get("pain", {}),
            "product": product,
        },
    }


def _legacy_report_payload(client_id: str, report: dict[str, Any]) -> dict[str, Any]:
    company_id = UUID(report["company_id"])
    payload = {"report_id": report["report_id"], "company_id": client_id, "client_id": client_id, **report}
    payload["customer_profile"] = _legacy_profile_payload(_legacy_report_service, company_id) if _legacy_report_service is not None else payload.get("profile_snapshot", {})
    payload["meddpicc"] = _legacy_meddpicc_payload(_legacy_report_service, company_id) if _legacy_report_service is not None else payload.get("meddpicc_snapshot", {})
    payload["modules"] = [{"module_name": name, "sections": report.get(name, {}).get("sections", [])} for name in ("market", "company", "competitor", "pain", "product")]
    payload["analysis_report"] = _flatten_report_sections(report)
    payload["analysis_report"]["evidence_refs"] = list(report.get("evidence_refs") or [])
    payload["analysis_report"]["evidence_summary"] = evidence_summary(
        tuple(report.get("evidence_refs") or [])
    )
    payload["analysis_report"]["research_meta"] = dict(report.get("research_meta") or {})
    return payload


def _list_report_coverage(
    service: CustomerAnalysisService,
    company_id: UUID,
    profile: dict[str, Any],
    meddpicc: dict[str, Any],
) -> float:
    """Calculate the list KPI from already-loaded context plus pending candidates."""
    covered = {
        field_id
        for field_id in CORE_PROFILE_FIELDS
        if profile.get(field_id) not in (None, "", "待确认", {}, [])
    }
    for code in CORE_MEDDPICC_FIELDS:
        dimension = meddpicc.get(code) or {}
        if not isinstance(dimension, dict):
            continue
        if (
            dimension.get("status") in {"partial", "confirmed"}
            or dimension.get("summary") not in (None, "", "待确认")
            or dimension.get("desc") not in (None, "", "待确认")
            or dimension.get("payload") not in (None, {}, [])
        ):
            covered.add(code)
    valid_fields = set(CORE_PROFILE_FIELDS + CORE_MEDDPICC_FIELDS)
    for suggestion in service.list_suggestions(company_id):
        target = suggestion.dimension_code or suggestion.target_path
        if target in valid_fields:
            covered.add(target)
    return round(len(covered) / len(valid_fields), 4)


def _preview_health(score: float) -> str:
    return "A-" if score >= 85 else "B+" if score >= 72 else "C+"


def _preview_intention(score: float, engagement: dict[str, Any]) -> str:
    if str(engagement.get("intent_level")) in {"interested", "pricing"}:
        return "\u5f3a\u610f\u5411"
    if score >= 85 or str(engagement.get("intent_level")) == "product_question":
        return "\u4e2d\u9ad8"
    if score >= 60:
        return "\u4e2d\u7b49"
    return "\u5f85\u786e\u8ba4"


def _preview_summary(name: str, score: float) -> str:
    if score >= 85:
        return f"{name} \u5f53\u524d\u5c5e\u4e8e\u9ad8\u6f5c\u5ba2\u6237\uff0c\u9884\u7b97\u4e0e\u8bd5\u70b9\u8bc9\u6c42\u76f8\u5bf9\u660e\u786e\uff0c\u9002\u5408\u4f18\u5148\u63a8\u8fdb\u3002"
    if score >= 72:
        return f"{name} \u5f53\u524d\u5df2\u6709\u660e\u786e\u5174\u8da3\u548c\u90e8\u5206\u51b3\u7b56\u4fe1\u53f7\uff0c\u5efa\u8bae\u5148\u8865\u9f50\u9884\u7b97\u548c\u5ba1\u6279\u8def\u5f84\u3002"
    return f"{name} \u5f53\u524d\u4fe1\u606f\u4ecd\u5f85\u8865\u9f50\uff0c\u5efa\u8bae\u5148\u786e\u8ba4\u771f\u5b9e\u573a\u666f\u3001\u9884\u7b97\u548c\u5173\u952e\u51b3\u7b56\u4eba\u3002"


def _profile_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        **profile,
        "company_summary": profile.get("source_summary") or profile.get("company_type"),
        "geography_note": profile.get("region_text"),
    }


def _async_envelope(run: dict[str, Any]) -> dict[str, Any]:
    job_id = run["current_job_id"]
    return _envelope({
        "resource_type": "analysis_run",
        "resource_id": run["run_id"],
        "job": {
            "job_id": job_id,
            "status": run["status"],
            "status_url": f"/api/v1/analysis-runs/{run['run_id']}",
            "events_url": f"/api/v1/jobs/{job_id}/events",
        },
    })


def _envelope(data: Any) -> dict[str, Any]:
    return {"request_id": _request_id(), "data": data}


def _request_id() -> str:
    return f"req_{uuid4().hex[:16]}"


def _etag(version: int) -> str:
    return f'"{version}"'


def _parse_etag(value: str) -> int:
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    try:
        return int(normalized)
    except ValueError as exc:
        raise VersionConflictError(f"invalid If-Match value: {value}") from exc


def _raise_http(exc: Exception) -> None:
    request_id = _request_id()
    if isinstance(exc, ResourceNotFoundError):
        status_code, code = 404, "RESOURCE_NOT_FOUND"
    elif isinstance(exc, (VersionConflictError, InvalidStateError)):
        status_code, code = 409, "VERSION_CONFLICT"
    elif isinstance(exc, InvalidDimensionError):
        status_code, code = 422, "INVALID_COMMAND"
    elif isinstance(exc, ValueError):
        status_code, code = 422, "INVALID_COMMAND"
    else:
        status_code, code = 400, "INVALID_COMMAND"
    raise HTTPException(
        status_code=status_code,
        detail={
            "request_id": request_id,
            "error": {"code": code, "message": str(exc), "details": None},
        },
    )
