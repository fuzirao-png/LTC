from __future__ import annotations

import asyncio
import os
import uuid
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, UploadFile, status

from .schemas import AcceptedEnvelope, LeadSearchRunCreate, MAX_LEAD_SEARCH_RESULTS
from .promotion_schemas import CandidateSelectRequest
from ..application.service_factory import build_lead_search_pipeline
from ..application.import_service import LeadCandidateImportService
from ..application.promotion_service import CandidatePromotionService
from ..application.email_automation_service import EmailAutomationService
from ..infrastructure.email_automation_store import EmailAutomationStore
from ..infrastructure.promotion_adapter import PostgresPromotionAdapter
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.platform.first_page_cache import first_page


router = APIRouter(tags=["Lead Intelligence"])


def _services(request: Request):
    if not hasattr(request.app.state, "lead_intelligence"):
        request.app.state.lead_intelligence = build_lead_search_pipeline()
    return request.app.state.lead_intelligence


def _promotion_service(request: Request) -> CandidatePromotionService:
    if not hasattr(request.app.state, "lead_promotion_service"):
        adapter = PostgresPromotionAdapter(request.app.state.database)
        request.app.state.lead_promotion_service = CandidatePromotionService(adapter, adapter)
    return request.app.state.lead_promotion_service


def _require_strategic(context: AuthContext) -> None:
    if context.actor.account_type != "strategic":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_STRATEGIC_REQUIRED"})


def _execute_in_background(pipeline, *, job_id: str, payload: dict) -> None:
    """Run blocking provider adapters off FastAPI's event-loop thread."""
    asyncio.run(pipeline.execute(job_id=job_id, lock_token="api-background", payload=payload))


def _execute_inline_enabled() -> bool:
    """Keep API-side execution available for API-only development setups."""
    return os.getenv("LTC_LEAD_SEARCH_EXECUTION_MODE", "worker").strip().lower() == "inline"


async def _execute_async(pipeline, *, job_id: str, payload: dict) -> None:
    """Run the pipeline as a coroutine on the running event loop."""
    try:
        await pipeline.execute(job_id=job_id, lock_token="api-background", payload=payload)
    except Exception:
        # Logged inside pipeline.execute 鈥?don't let the coroutine crash silently
        pass


@router.post("/lead-search-runs", response_model=AcceptedEnvelope, status_code=status.HTTP_202_ACCEPTED)
def create_lead_search_run(
    body: LeadSearchRunCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
):
    _require_strategic(context)
    pipeline = _services(request)
    run_id, job_id = pipeline.repository.create_search_run(body)
    if _execute_inline_enabled():
        # API-only development mode. In Worker mode the queued job has one
        # owner, preventing duplicate provider calls and persistence writes.
        background_tasks.add_task(
            _execute_in_background,
            pipeline,
            job_id=job_id,
            payload={**body.model_dump(), "search_run_id": run_id},
        )
    return {"request_id": request.headers.get("x-request-id", "generated"), "data": {"resource_type": "lead_search_run", "resource_id": run_id, "job": {"job_id": job_id, "job_type": "lead.search_pipeline.v1", "status": "queued", "status_url": f"/api/v1/jobs/{job_id}"}}}


@router.get("/lead-search-runs/{search_run_id}")
def get_lead_search_run(
    search_run_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
):
    _require_strategic(context)
    result = _services(request).repository.get_search_run(str(search_run_id))
    if not result:
        raise HTTPException(status_code=404, detail="search run not found")
    return {"request_id": request.headers.get("x-request-id", "generated"), "data": result}


@router.get("/lead-search-runs/{search_run_id}/trace")
def get_lead_search_trace(
    search_run_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
):
    _require_strategic(context)
    result = _services(request).repository.get_run_trace(str(search_run_id))
    if not result:
        raise HTTPException(status_code=404, detail="search run not found")
    return {"request_id": request.headers.get("x-request-id", "generated"), "data": result}


@router.get("/lead-candidates")
def list_lead_candidates(
    request: Request,
    search_run_id: UUID | None = None,
    analysis_pool: bool = False,
    limit: int = Query(default=50, ge=1, le=MAX_LEAD_SEARCH_RESULTS),
    context: AuthContext = Depends(get_auth_context),
):
    query = {
        "search_run_id": str(search_run_id) if search_run_id else None,
        "limit": limit,
    }
    if analysis_pool:
        query["analysis_pool"] = True
    def load_page() -> dict[str, object]:
        repository = _services(request).repository
        return {
            "data": repository.list_candidates(**query),
            "page": {
                "limit": limit,
                "total": repository.count_candidates(search_run_id=query["search_run_id"], analysis_pool=analysis_pool),
                "next_cursor": None,
            },
        }

    key = ("lead-candidates", context.actor.user_id, context.actor.account_type, limit) if not search_run_id and not analysis_pool else None
    return {
        "request_id": request.headers.get("x-request-id", "generated"),
        **first_page(request, key, load_page),
    }


@router.get("/lead-candidates/{candidate_id}")
def get_lead_candidate(
    candidate_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
):
    result = _services(request).repository.get_candidate(str(candidate_id))
    if not result:
        raise HTTPException(status_code=404, detail="candidate not found")
    return {"request_id": request.headers.get("x-request-id", "generated"), "data": result}


@router.post("/lead-candidates:import")
async def import_lead_candidates(
    request: Request,
    file: UploadFile = File(...),
    context: AuthContext = Depends(get_auth_context),
):
    _require_strategic(context)
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only UTF-8 CSV files are supported.")
    content = await file.read(1_000_001)
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 1 MB limit.")
    try:
        result = LeadCandidateImportService(_services(request).repository).import_csv(
            content=content, filename=filename
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"request_id": request.headers.get("x-request-id", "generated"), "data": result}


# 鈹€鈹€ Candidate Commands (v3.6 PRD 搂3.7-3.9) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@router.post("/lead-candidates:select", status_code=status.HTTP_200_OK)
def select_candidates(
    body: CandidateSelectRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> dict:
    """Batch-promote candidates 鈫?Sales Leads (Strategic only, PRD 搂3.9)."""
    _require_strategic(context)
    service = _promotion_service(request)
    request_id = str(request.headers.get("x-request-id", str(uuid.uuid4())))
    items = [
        {
            "candidate_id": str(item.candidate_id),
            "expected_version": item.expected_version,
            "override": item.override,
            "override_reason": item.override_reason,
        }
        for item in body.items
    ]
    result = service.promote_batch(items, str(context.actor.user_id), request_id)
    return {"request_id": request_id, "data": result}


@router.post("/lead-candidates/{candidate_id}:reject", status_code=status.HTTP_200_OK)
def reject_candidate(
    candidate_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Strategic rejects a candidate (PRD 搂3.7)."""
    _require_strategic(context)
    adapter = PostgresPromotionAdapter(request.app.state.database)
    candidate = adapter.fetch_candidate_for_promotion(str(candidate_id))
    if not candidate:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
    expected_version = int(if_match.strip().strip('"'))
    if int(candidate.get("version", -1)) != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    status_text = str(candidate.get("processing_status") or "")
    if status_text in ("promoted", "merged", "archived", "rejected"):
        raise HTTPException(status_code=409, detail={"code": "CANDIDATE_CANNOT_REJECT", "message": f"Candidate is {status_text}"})
    with adapter._db.transaction() as conn:
        conn.execute(
            "UPDATE ltc.lead_candidate SET processing_status='rejected', reject_reason='strategic_reject', version=version+1 WHERE candidate_id=%s",
            (str(candidate_id),),
        )
    return {"request_id": str(request.headers.get("x-request-id", "generated")), "data": {"candidate_id": str(candidate_id), "processing_status": "rejected"}}


@router.post("/lead-candidates/{candidate_id}:reopen", status_code=status.HTTP_200_OK)
def reopen_candidate(
    candidate_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Strategic reopens a rejected candidate (PRD 搂3.7)."""
    _require_strategic(context)
    adapter = PostgresPromotionAdapter(request.app.state.database)
    candidate = adapter.fetch_candidate_for_promotion(str(candidate_id))
    if not candidate:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
    expected_version = int(if_match.strip().strip('"'))
    if int(candidate.get("version", -1)) != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    if candidate.get("processing_status") != "rejected":
        raise HTTPException(status_code=409, detail={"code": "CANDIDATE_NOT_REJECTED"})
    with adapter._db.transaction() as conn:
        conn.execute(
            "UPDATE ltc.lead_candidate SET processing_status='enriched', assessments_stale=true, reject_reason=NULL, version=version+1 WHERE candidate_id=%s",
            (str(candidate_id),),
        )
    return {"request_id": str(request.headers.get("x-request-id", "generated")), "data": {"candidate_id": str(candidate_id), "processing_status": "enriched", "assessments_stale": True}}


@router.post("/lead-candidates/{candidate_id}:refresh-enrichment", status_code=status.HTTP_202_ACCEPTED)
def refresh_enrichment(
    candidate_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Refresh enrichment for a candidate (PRD 搂3.7)."""
    _require_strategic(context)
    adapter = PostgresPromotionAdapter(request.app.state.database)
    candidate = adapter.fetch_candidate_for_promotion(str(candidate_id))
    if not candidate:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
    expected_version = int(if_match.strip().strip('"'))
    if int(candidate.get("version", -1)) != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    status_text = str(candidate.get("processing_status") or "")
    if status_text in ("merged", "archived"):
        raise HTTPException(status_code=409, detail={"code": "CANDIDATE_CANNOT_REFRESH", "message": f"Candidate is {status_text}"})
    # Mark assessments stale and create enrichment run via the adapter,
    # keeping SQL out of the interface layer.
    refresh = adapter.prepare_refresh_enrichment(str(candidate_id))
    job_id = refresh["job_id"]
    enrichment_run_id = refresh["enrichment_run_id"]
    # Trigger async pipeline re-run
    pipeline = _services(request)
    background_tasks.add_task(
        _execute_in_background,
        pipeline,
        job_id=job_id,
        payload=refresh["pipeline_payload"],
    )
    return {
        "request_id": str(request.headers.get("x-request-id", "generated")),
        "data": {
            "candidate_id": str(candidate_id),
            "assessments_stale": True,
            "enrichment_run_id": enrichment_run_id,
            "job": {"job_id": job_id, "job_type": "lead.enrichment_pipeline.v1", "status": "queued"},
        },
    }


@router.post("/lead-candidates/{source_id}:merge", status_code=status.HTTP_202_ACCEPTED)
def merge_candidate(
    source_id: UUID,
    body: dict,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Merge source candidate into target (PRD 搂3.8)."""
    _require_strategic(context)
    target_id = str(body.get("target_candidate_id", ""))
    if not target_id:
        raise HTTPException(status_code=400, detail={"code": "INVALID_COMMAND", "message": "target_candidate_id is required"})
    adapter = PostgresPromotionAdapter(request.app.state.database)
    source = adapter.fetch_candidate_for_promotion(str(source_id))
    target = adapter.fetch_candidate_for_promotion(target_id)
    if not source:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND", "message": "Source candidate not found"})
    if not target:
        raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND", "message": "Target candidate not found"})
    expected_version = int(if_match.strip().strip('"'))
    if int(source.get("version", -1)) != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    target_expected = int(body.get("target_expected_version", -1))
    if int(target.get("version", -1)) != target_expected:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT", "message": "Target version mismatch"})
    src_status = str(source.get("processing_status") or "")
    tgt_status = str(target.get("processing_status") or "")
    if src_status == "promoted":
        raise HTTPException(status_code=409, detail={"code": "CANDIDATE_ALREADY_PROMOTED"})
    if src_status in ("merged", "archived"):
        raise HTTPException(status_code=409, detail={"code": "CANDIDATE_ALREADY_MERGED"})
    if tgt_status in ("merged", "archived"):
        raise HTTPException(status_code=409, detail={"code": "MERGE_TARGET_NOT_CANONICAL"})
    # Sort IDs to avoid deadlocks
    ids = sorted([str(source_id), target_id])
    first_id, second_id = ids[0], ids[1]
    import uuid as _uuid
    job_id = str(_uuid.uuid4())
    enrichment_run_id = str(_uuid.uuid4())
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    with adapter._db.transaction() as conn:
        # Lock both in order
        conn.execute("SELECT 1 FROM ltc.lead_candidate WHERE candidate_id=%s FOR UPDATE", (first_id,))
        conn.execute("SELECT 1 FROM ltc.lead_candidate WHERE candidate_id=%s FOR UPDATE", (second_id,))
        # Mark source as merged
        conn.execute(
            """UPDATE ltc.lead_candidate
               SET processing_status='merged', merged_into_candidate_id=%s, merged_at=%s, version=version+1
               WHERE candidate_id=%s""",
            (target_id, now, str(source_id)),
        )
        # Mark target stale + create enrichment run
        conn.execute(
            "UPDATE ltc.lead_candidate SET assessments_stale=true, version=version+1 WHERE candidate_id=%s",
            (target_id,),
        )
        conn.execute(
            """INSERT INTO ltc.lead_enrichment_run
               (enrichment_run_id, candidate_id, version_no, status, scene_code, rule_version,
                prompt_version, config_checksum, current_job_id, is_current, created_at, version)
               VALUES (%s,%s,1,'queued','S1','v3.6.0','v1','0000000000000000000000000000000000000000000000000000000000000000',
                       %s,true,%s,0)""",
            (enrichment_run_id, target_id, job_id, now),
        )
        conn.execute(
            """INSERT INTO ltc.job (job_id, job_type, queue_name, status, priority, payload,
                                    progress_percent, attempt_count, max_attempts, run_after,
                                    created_at, updated_at, version)
               VALUES (%s,'lead.enrichment_pipeline.v1','lead-search','queued',0,'{}'::jsonb,
                       0,0,3,%s,%s,%s,0)""",
            (job_id, now, now, now),
        )
    return {
        "request_id": str(request.headers.get("x-request-id", "generated")),
        "data": {
            "source_candidate_id": str(source_id),
            "canonical_candidate_id": target_id,
            "source_status": "merged",
            "canonical_assessments_stale": True,
            "enrichment_run_id": enrichment_run_id,
            "current_job_id": job_id,
        },
    }


# 鈹€鈹€ Search Run Commands (v3.6 PRD 搂3.4) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@router.post("/lead-search-runs/{search_run_id}:cancel", status_code=status.HTTP_200_OK)
def cancel_search_run(
    search_run_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Cancel a queued/running search run (PRD 搂3.4)."""
    pipeline = _services(request)
    run = pipeline.repository.get_search_run(str(search_run_id))
    if not run:
        raise HTTPException(status_code=404, detail="search run not found")
    if run.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=409, detail={"code": "RESOURCE_NOT_CANCELLABLE"})
    pipeline.repository.finish_search_run(
        str(search_run_id), run.get("current_job_id"),
        status="cancelled", counts={
            "candidate_count": int(run.get("candidate_count") or 0),
            "enriched_count": int(run.get("enriched_count") or 0),
            "scored_count": int(run.get("scored_count") or 0),
        }, error="Cancelled by user",
    )
    return {"request_id": str(request.headers.get("x-request-id", "generated")), "data": {"search_run_id": str(search_run_id), "status": "cancelled"}}


@router.post("/lead-search-runs/{search_run_id}:retry", status_code=status.HTTP_202_ACCEPTED)
def retry_search_run(
    search_run_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Retry a failed/partial search run with a new Job (PRD 搂3.4)."""
    _require_strategic(context)
    pipeline = _services(request)
    run = pipeline.repository.get_search_run(str(search_run_id))
    if not run:
        raise HTTPException(status_code=404, detail="search run not found")
    if run.get("status") not in ("failed", "partial", "completed"):
        raise HTTPException(status_code=409, detail={"code": "RESOURCE_NOT_RETRYABLE"})
    import uuid as _uuid
    new_job_id = str(_uuid.uuid4())
    with pipeline.repository._connect() as conn:
        conn.execute(
            "UPDATE ltc.lead_search_run SET status='queued', current_job_id=%s WHERE search_run_id=%s",
            (new_job_id, str(search_run_id)),
        )
    background_tasks.add_task(
        _execute_in_background, pipeline,
        job_id=new_job_id,
        payload={"search_run_id": str(search_run_id), "query_text": run.get("query_text"), "search_mode": run.get("search_mode"), "target_count": run.get("target_count", 10), "scene_code": run.get("scene_code", "S1"), "retry": True},
    )
    return {
        "request_id": str(request.headers.get("x-request-id", "generated")),
        "data": {
            "resource_type": "lead_search_run",
            "resource_id": str(search_run_id),
            "previous_job_id": run.get("current_job_id"),
            "current_job_id": new_job_id,
            "status": "queued",
            "job": {"job_id": new_job_id, "job_type": "lead.search_pipeline.v1", "status": "queued"},
        },
    }


@router.get("/email-automation/preview")
def preview_email_automation(context: AuthContext = Depends(get_auth_context)) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().preview()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/email-automation/config")
def get_email_automation_config(context: AuthContext = Depends(get_auth_context)) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().get_config()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/email-automation/config")
def update_email_automation_config(
    payload: dict,
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().update_config(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/email-automation/agent/run")
async def run_email_automation(
    background_tasks: BackgroundTasks,
    payload: dict | None = None,
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        run_payload = dict(payload or {})
        run_payload.setdefault("senderUserId", str(context.actor.user_id))
        service = EmailAutomationService()
        queued = service.enqueue(run_payload)
        if queued.get("status") != "queued":
            return queued
        background_tasks.add_task(service.process_run, queued["runId"], run_payload)
        return queued
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/email-automation/runs/{run_id}")
def get_email_automation_run(
    run_id: str,
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        run = EmailAutomationStore().get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Email automation run not found")
        return run
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.get("/email-automation/runs/{run_id}/replies")
def list_email_automation_replies(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().list_replies(run_id, page, page_size)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Email automation run not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.get("/email-automation/runs/{run_id}/failures")
def list_email_automation_failures(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    code: str | None = Query(default=None),
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().list_failures(run_id, page, page_size, code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Email automation run not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/email-automation/runs")
def list_email_automation_runs(
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    _require_strategic(context)
    try:
        return EmailAutomationService().list_runs(limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
