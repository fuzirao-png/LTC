"""SSE progress event stream (PRD §3.3, §6.2).

GET /api/v1/jobs/{job_id}/events
Accept: text/event-stream
Last-Event-ID: <int>

Event types: progress, step_started, step_completed, candidate_upserted,
candidate_scored, warning, error, completed.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from psycopg.rows import dict_row
from starlette.responses import StreamingResponse

from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

router = APIRouter(tags=["Jobs"])


@router.get("/jobs/{job_id}/events")
async def job_events_stream(
    job_id: UUID,
    request: Request,
    last_event_id: int = Header(default=0, alias="Last-Event-ID", ge=0),
    context: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    """SSE stream of job progress events (PRD §3.3).

    Reads from ltc.job_progress_event ordered by sequence_no.
    Client reconnects with Last-Event-ID to resume where it left off.
    """
    job_id_str = str(job_id)
    db = request.app.state.database

    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT status FROM ltc.job WHERE job_id = %s",
                (job_id_str,),
            )
            job = cur.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"})

    job_status = job["status"]

    async def event_generator():
        emitted_seq: set[int] = set()
        last_sent_seq = last_event_id

        # If job is already terminal, emit completed immediately
        if job_status in ("succeeded", "failed", "cancelled"):
            yield _sse_event(
                sequence_no=last_sent_seq + 1,
                event_type="completed",
                data={"job_status": job_status},
            )
            return

        while True:
            with db.transaction() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """SELECT pe.sequence_no, pe.event_type, pe.step_code,
                                  pe.progress_percent, pe.message, pe.payload,
                                  pe.created_at, j.status AS current_job_status
                           FROM ltc.job_progress_event pe
                           JOIN ltc.job j ON j.job_id = pe.job_id
                           WHERE pe.job_id = %s AND pe.sequence_no > %s
                           ORDER BY pe.sequence_no ASC
                           LIMIT 50""",
                        (job_id_str, last_sent_seq),
                    )
                    new_events = cur.fetchall()

                current_job_status = None
                for evt in new_events:
                    seq = int(evt["sequence_no"])
                    if seq not in emitted_seq:
                        emitted_seq.add(seq)
                        last_sent_seq = seq
                        yield _sse_event(
                            sequence_no=seq,
                            event_type=evt["event_type"],
                            data={
                                "step_code": evt.get("step_code"),
                                "progress_percent": float(evt["progress_percent"]) if evt.get("progress_percent") is not None else None,
                                "message": evt.get("message"),
                                "payload": evt.get("payload") if evt.get("payload") else None,
                                "occurred_at": evt["created_at"].isoformat() if evt.get("created_at") else None,
                            },
                        )
                    current_job_status = evt.get("current_job_status")

                # If we got events and the job is now terminal, emit completed
                if current_job_status in ("succeeded", "failed", "cancelled"):
                    yield _sse_event(
                        sequence_no=last_sent_seq + 1,
                        event_type="completed",
                        data={"job_status": current_job_status},
                    )
                    return

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(*, sequence_no: int, event_type: str, data: dict | None = None) -> str:
    """Format a dict as an SSE event with id, event, and data fields."""
    parts: list[str] = []
    parts.append(f"id: {sequence_no}")
    if event_type:
        parts.append(f"event: {event_type}")
    parts.append(f"data: {json.dumps(data or {}, ensure_ascii=False)}")
    parts.append("")
    return "\n".join(parts) + "\n"
