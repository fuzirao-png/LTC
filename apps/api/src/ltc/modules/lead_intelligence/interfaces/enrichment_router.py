"""Enrichment Run command endpoints (PRD §3.7).

POST /api/v1/lead-enrichment-runs/{run_id}:retry   — new Job, old Job stays terminal
POST /api/v1/lead-enrichment-runs/{run_id}:cancel  — Run + current Job cancelled in one tx
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from psycopg.rows import dict_row

from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

router = APIRouter(tags=["Lead Enrichment"])


def _require_strategic(context: AuthContext) -> None:
    if context.actor.account_type != "strategic":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_STRATEGIC_REQUIRED"})


def _parse_if_match(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error


@router.post("/lead-enrichment-runs/{run_id}:retry", status_code=status.HTTP_202_ACCEPTED)
def retry_enrichment_run(
    run_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Retry a failed/completed enrichment run with a new Job (PRD §3.7)."""
    _require_strategic(context)
    expected_version = _parse_if_match(if_match)
    db = request.app.state.database

    # Read outside transaction first to validate
    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM ltc.lead_enrichment_run WHERE enrichment_run_id = %s",
                (str(run_id),),
            )
            run_row = cur.fetchone()
    if not run_row:
        raise HTTPException(status_code=404, detail={"code": "ENRICHMENT_RUN_NOT_FOUND"})
    run = dict(run_row)
    if run["version"] != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    if run["status"] not in ("failed", "completed", "partial", "cancelled"):
        raise HTTPException(status_code=409, detail={"code": "RESOURCE_NOT_RETRYABLE"})

    # Write in transaction
    now = datetime.now(timezone.utc)
    new_job_id = str(uuid4())
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO ltc.job (job_id, job_type, queue_name, status, priority, payload,
                                    progress_percent, attempt_count, max_attempts, run_after,
                                    created_at, updated_at, version)
               VALUES (%s,'lead.enrichment_pipeline.v1','lead-search','queued',0,'{}'::jsonb,
                       0,0,3,%s,%s,%s,0)""",
            (new_job_id, now, now, now),
        )
        conn.execute(
            """UPDATE ltc.lead_enrichment_run
               SET status = 'queued',
                   current_job_id = %s,
                   version_no = version_no + 1,
                   version = version + 1,
                   superseded_at = NULL,
                   is_current = false,
                   error_code = NULL,
                   error_message = NULL
               WHERE enrichment_run_id = %s""",
            (new_job_id, str(run_id)),
        )

        # Mark all other runs for this candidate as non-current
        conn.execute(
            """UPDATE ltc.lead_enrichment_run
               SET is_current = false
               WHERE candidate_id = %s AND enrichment_run_id != %s""",
            (str(run.get("candidate_id", "")), str(run_id)),
        )

    return {
        "request_id": str(request.headers.get("x-request-id", "generated")),
        "data": {
            "enrichment_run_id": str(run_id),
            "previous_job_id": str(run["current_job_id"]) if run.get("current_job_id") else None,
            "current_job_id": new_job_id,
            "status": "queued",
            "job": {"job_id": new_job_id, "job_type": "lead.enrichment_pipeline.v1", "status": "queued"},
        },
    }


@router.post("/lead-enrichment-runs/{run_id}:cancel", status_code=status.HTTP_200_OK)
def cancel_enrichment_run(
    run_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> dict:
    """Cancel enrichment run and current Job in one transaction (PRD §3.7)."""
    _require_strategic(context)
    expected_version = _parse_if_match(if_match)
    db = request.app.state.database

    # Read outside transaction first
    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM ltc.lead_enrichment_run WHERE enrichment_run_id = %s",
                (str(run_id),),
            )
            run_row = cur.fetchone()
    if not run_row:
        raise HTTPException(status_code=404, detail={"code": "ENRICHMENT_RUN_NOT_FOUND"})
    run = dict(run_row)
    if run["version"] != expected_version:
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})
    if run["status"] not in ("queued", "running"):
        raise HTTPException(status_code=409, detail={"code": "RESOURCE_NOT_CANCELLABLE"})

    # Write in transaction
    now = datetime.now(timezone.utc)
    current_job_id = run.get("current_job_id")
    with db.transaction() as conn:
        conn.execute(
            """UPDATE ltc.lead_enrichment_run
               SET status = 'cancelled', error_code = 'cancelled_by_user',
                   version = version + 1
               WHERE enrichment_run_id = %s""",
            (str(run_id),),
        )
        if current_job_id:
            conn.execute(
                """UPDATE ltc.job
                   SET status = 'cancelled', completed_at = %s, updated_at = %s, version = version + 1
                   WHERE job_id = %s AND status IN ('queued', 'running', 'retrying')""",
                (now, now, str(current_job_id)),
            )

    return {
        "request_id": str(request.headers.get("x-request-id", "generated")),
        "data": {
            "enrichment_run_id": str(run_id),
            "status": "cancelled",
            "cancelled_job_id": str(current_job_id) if current_job_id else None,
        },
    }
