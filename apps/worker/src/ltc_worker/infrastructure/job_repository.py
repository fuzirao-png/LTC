"""PostgreSQL-backed ``JobRepository`` implementation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from ..application import JobAttemptHandle, JobLease

_logger = logging.getLogger("ltc.worker.repo")

_FAIL_MEETING = """UPDATE ltc.meeting SET processing_status='failed',
    transcript_status=CASE WHEN transcript_status='done' THEN 'done' ELSE 'failed' END,
    error_code=$2, error_message='Meeting processing failed', updated_at=clock_timestamp(), version=version+1
    WHERE meeting_id=$1 AND deleted_at IS NULL
      AND processing_status IN ('uploaded','queued','extracting','transcribing','summarizing')"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_metrics(metrics: dict[str, Any] | None) -> str:
    import json

    if metrics is None:
        metrics = {
            "schema_version": 1,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "cost_amount": None,
            "currency": None,
            "cost_status": "unknown",
        }
    return json.dumps(metrics, default=str)


def _decode_payload(value: Any) -> dict[str, Any]:
    """Normalize asyncpg JSONB values into the worker payload contract."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


class PostgreSQLJobRepository:
    """Persists job lifecycle events to ``ltc.job`` / ``ltc.job_attempt``.

    *connection_factory* is an async callable that returns a fresh
    ``asyncpg.Connection``.  Each public method acquires its own
    short-lived connection so that long-running handlers never tie up
    a pool connection.
    """

    def __init__(self, connection_factory: Any) -> None:
        self._cf = connection_factory

    # ── claim ───────────────────────────────────────────────────────

    async def claim(
        self, worker_id: str, queue_names: list[str], lease_seconds: int = 300
    ) -> JobLease | None:
        conn = await self._cf()
        try:
            token = uuid.uuid4()
            row = await conn.fetchrow(
                """\
                WITH picked AS (
                    SELECT job_id
                    FROM ltc.job
                    WHERE queue_name = ANY($1::text[])
                      AND status IN ('queued', 'retry_wait')
                      AND run_after <= clock_timestamp()
                    ORDER BY priority, created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE ltc.job j
                SET status       = 'running',
                    locked_by    = $2,
                    lock_token   = $3,
                    locked_until = clock_timestamp() + ($4 || ' seconds')::interval,
                    started_at   = COALESCE(started_at, clock_timestamp()),
                    attempt_count = attempt_count + 1,
                    version      = version + 1
                FROM picked
                WHERE j.job_id = picked.job_id
                RETURNING j.job_id::text, j.job_type, j.lock_token::text,
                          j.queue_name, j.payload, j.attempt_count,
                          j.concurrency_key
                """,
                queue_names, worker_id, str(token), str(lease_seconds),
            )
            if row is None:
                return None
            payload = _decode_payload(row[4])
            return JobLease(
                job_id=row[0], job_type=row[1], lock_token=row[2],
                queue_name=row[3],
                payload=payload,
                attempt_count=row[5], concurrency_key=row[6],
            )
        finally:
            await conn.close()

    # ── start attempt ───────────────────────────────────────────────

    async def start_attempt(self, job: JobLease, worker_id: str) -> JobAttemptHandle:
        aid = str(uuid.uuid4())
        conn = await self._cf()
        try:
            await conn.execute(
                """\
                INSERT INTO ltc.job_attempt (attempt_id, job_id, attempt_no,
                  worker_id, lock_token, status, metrics, started_at)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, 'started', $6::jsonb, $7)
                """,
                aid, job.job_id, job.attempt_count, worker_id,
                job.lock_token, _serialize_metrics(None), _now(),
            )
            return JobAttemptHandle(attempt_id=aid, job_id=job.job_id)
        finally:
            await conn.close()

    # ── finish attempt ──────────────────────────────────────────────

    async def finish_attempt(
        self, attempt: JobAttemptHandle, status: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        conn = await self._cf()
        try:
            await conn.execute(
                """\
                UPDATE ltc.job_attempt
                SET status = $1, metrics = COALESCE($2::jsonb, metrics),
                    completed_at = clock_timestamp()
                WHERE attempt_id = $3::uuid
                """,
                status, _serialize_metrics(metrics), attempt.attempt_id,
            )
        finally:
            await conn.close()

    # ── complete job ────────────────────────────────────────────────

    async def complete_job(
        self, attempt: JobAttemptHandle,
        result_summary: dict[str, Any] | None = None,
    ) -> None:
        conn = await self._cf()
        try:
            await conn.execute(
                """\
                UPDATE ltc.job
                SET status = 'succeeded', progress_percent = 100,
                    result_summary = COALESCE($1::jsonb, result_summary),
                    completed_at = clock_timestamp(),
                    locked_by = NULL, lock_token = NULL, locked_until = NULL,
                    version = version + 1
                WHERE job_id = $2::uuid
                """,
                _serialize_metrics(result_summary) if result_summary else None,
                attempt.job_id,
            )
        finally:
            await conn.close()

    # ── retry ───────────────────────────────────────────────────────

    async def retry_job(
        self, job: JobLease, attempt: JobAttemptHandle,
        error_code: str, error_message: str, retry_delay_seconds: int,
    ) -> None:
        conn = await self._cf()
        try:
            async with conn.transaction():
                await conn.execute(
                    """\
                    UPDATE ltc.job_attempt
                    SET status = 'failed', error_code = $1,
                        error_message = $2, completed_at = clock_timestamp()
                    WHERE attempt_id = $3::uuid
                    """, error_code, error_message, attempt.attempt_id,
                )
                await conn.execute(
                    """\
                    UPDATE ltc.job
                    SET status = 'retry_wait',
                        run_after = clock_timestamp() + ($1 || ' seconds')::interval,
                        last_error_code = $2, last_error_message = $3,
                        version = version + 1
                    WHERE job_id = $4::uuid
                    """,
                    str(retry_delay_seconds), error_code, error_message, attempt.job_id,
                )
        finally:
            await conn.close()

    # ── fail (terminal) ─────────────────────────────────────────────

    async def fail_job(
        self, job: JobLease, attempt: JobAttemptHandle,
        error_code: str, error_message: str,
    ) -> None:
        conn = await self._cf()
        try:
            async with conn.transaction():
                await conn.execute(
                    """\
                    UPDATE ltc.job_attempt
                    SET status = 'failed', error_code = $1,
                        error_message = $2, completed_at = clock_timestamp()
                    WHERE attempt_id = $3::uuid
                    """, error_code, error_message, attempt.attempt_id,
                )
                await conn.execute(
                    """\
                    UPDATE ltc.job
                    SET status = 'failed_final',
                        last_error_code = $1, last_error_message = $2,
                        completed_at = clock_timestamp(),
                        locked_by = NULL, lock_token = NULL, locked_until = NULL,
                        version = version + 1
                    WHERE job_id = $3::uuid
                    """,
                    error_code, error_message, attempt.job_id,
                )
        finally:
            await conn.close()

    # ── lease / cancel ──────────────────────────────────────────────

    async def finish_media_attempt(
        self, job: JobLease, attempt: JobAttemptHandle, error_code: str | None,
        retry_delay: int | None,
    ) -> None:
        conn = await self._cf()
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT attempt_count, max_attempts, aggregate_id FROM ltc.job
                       WHERE job_id=$1::uuid AND lock_token=$2::uuid AND status='running'
                         AND locked_until > clock_timestamp() FOR UPDATE""", job.job_id, job.lock_token,
                )
                if row is None:
                    return  # Expired leases and their attempts are closed by recovery.
                status = "succeeded"
                if error_code:
                    status = "retry_wait" if retry_delay is not None and row[0] < row[1] else "failed_final"
                await conn.execute(
                    """UPDATE ltc.job SET status=$2, last_error_code=$3,
                           progress_percent=CASE WHEN $2='succeeded' THEN 100 ELSE progress_percent END,
                           completed_at=CASE WHEN $2<>'retry_wait' THEN clock_timestamp() END,
                           run_after=clock_timestamp() + make_interval(secs => $4::integer),
                           locked_by=NULL, lock_token=NULL, locked_until=NULL,
                           updated_at=clock_timestamp(), version=version+1
                       WHERE job_id=$1::uuid""", job.job_id, status, error_code, retry_delay or 0,
                )
                await conn.execute(
                    """UPDATE ltc.job_attempt SET status=$2, error_code=$3, completed_at=clock_timestamp()
                       WHERE attempt_id=$1::uuid AND status='started'""",
                    attempt.attempt_id, "failed" if error_code else "succeeded", error_code,
                )
                if status == "failed_final" and row[2]:
                    await conn.execute(_FAIL_MEETING, row[2], error_code)
        finally:
            await conn.close()

    async def recover_media_jobs(self) -> int:
        conn = await self._cf()
        try:
            async with conn.transaction():
                await conn.execute(
                    """WITH expired AS (
                           SELECT job.job_id, job.lock_token,
                               CASE WHEN meeting.processing_status='completed' THEN 'succeeded'
                                    WHEN job.attempt_count >= job.max_attempts THEN 'failed_final'
                                    ELSE 'retry_wait' END AS outcome
                           FROM ltc.job job LEFT JOIN ltc.meeting meeting ON meeting.meeting_id=job.aggregate_id
                           WHERE job.job_type='engagement.process_meeting.v1' AND job.queue_name='media'
                             AND job.status='running' AND job.locked_until <= clock_timestamp()
                           ORDER BY job.locked_until LIMIT 100 FOR UPDATE OF job SKIP LOCKED
                       ), recovered AS (
                           UPDATE ltc.job job SET status=expired.outcome,
                               completed_at=CASE WHEN expired.outcome<>'retry_wait' THEN clock_timestamp() END,
                               progress_percent=CASE WHEN expired.outcome='succeeded' THEN 100 ELSE progress_percent END,
                               locked_by=NULL, lock_token=NULL, locked_until=NULL,
                               last_error_code=CASE WHEN expired.outcome<>'succeeded' THEN 'LEASE_EXPIRED' END,
                               run_after=clock_timestamp(), updated_at=clock_timestamp(), version=job.version+1
                           FROM expired WHERE job.job_id=expired.job_id
                           RETURNING job.job_id, job.aggregate_id, expired.lock_token, job.status
                       ), attempts AS (
                           UPDATE ltc.job_attempt attempt SET status='lease_lost', completed_at=clock_timestamp()
                           FROM recovered WHERE attempt.job_id=recovered.job_id
                             AND attempt.lock_token=recovered.lock_token AND attempt.status='started'
                       )
                       UPDATE ltc.meeting meeting SET processing_status='failed',
                           transcript_status=CASE WHEN transcript_status='done' THEN 'done' ELSE 'failed' END,
                           error_code='LEASE_EXPIRED', error_message='Meeting processing worker lease expired',
                           updated_at=clock_timestamp(), version=meeting.version+1
                       FROM recovered WHERE recovered.aggregate_id=meeting.meeting_id
                         AND recovered.status='failed_final' AND meeting.deleted_at IS NULL
                         AND meeting.processing_status IN ('uploaded','queued','extracting','transcribing','summarizing')""",
                )
                return await conn.fetchval(
                    "SELECT count(*) FROM ltc.job WHERE queue_name='media' AND status IN ('queued','retry_wait')",
                )
        finally:
            await conn.close()

    async def renew_lease(self, job_id: str, lock_token: str, lease_seconds: int) -> bool:
        conn = await self._cf()
        try:
            result = await conn.execute(
                """\
                UPDATE ltc.job
                SET locked_until = clock_timestamp() + ($1 || ' seconds')::interval,
                    version = version + 1
                WHERE job_id = $2::uuid AND status = 'running'
                  AND lock_token = $3::uuid
                """, str(lease_seconds), job_id, lock_token,
            )
            return result != "UPDATE 0"
        finally:
            await conn.close()

    async def cancel_job(self, job_id: str, lock_token: str) -> bool:
        conn = await self._cf()
        try:
            async with conn.transaction():
                result = await conn.execute(
                    """\
                    UPDATE ltc.job
                    SET status = 'cancelled', completed_at = clock_timestamp(),
                        locked_by = NULL, lock_token = NULL, locked_until = NULL,
                        version = version + 1
                    WHERE job_id = $1::uuid AND status = 'running'
                  AND lock_token = $2::uuid AND locked_until > clock_timestamp()
                    """, job_id, lock_token,
                )
                return result != "UPDATE 0"
        finally:
            await conn.close()
