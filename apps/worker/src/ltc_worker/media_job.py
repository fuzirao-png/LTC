"""Meeting job leases, retries, and trace propagation."""

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

from opentelemetry.context import Context
from opentelemetry.trace import Link, SpanKind, StatusCode, Tracer, get_current_span

from ltc.modules.meeting_analysis.infrastructure import AudioProcessingError, MediaExtractionError
from ltc.platform.observability.tracing import trace_context

from .application import compute_retry_delay
from .errors import LeaseLost
from .infrastructure.job_repository import PostgreSQLJobRepository
from .lease import JobLease
from .meeting_workflow import MeetingWorkflow
from .observability._formatter import worker_trace_id

MEDIA_LEASE_SECONDS = 30
_logger = logging.getLogger(__name__)


class MediaJobRunner:
    def __init__(self, jobs: PostgreSQLJobRepository, workflow: MeetingWorkflow, tracer: Tracer) -> None:
        self._jobs = jobs
        self._workflow = workflow
        self._tracer = tracer

    async def handle(self, job: JobLease) -> None:
        attempt = await self._jobs.start_attempt(job, "ltc-media-worker")
        heartbeat = asyncio.create_task(self._keep_lease(job))
        carrier = {key: job.payload[key] for key in ("traceparent", "tracestate") if isinstance(job.payload.get(key), str)}
        parent = trace_context.extract(carrier)
        upstream = get_current_span(parent).get_span_context()
        links = []
        if job.attempt_count > 1 or _queue_age(job) > 60:
            # A fresh attempt remains eligible for tail sampling after the HTTP trace is decided.
            links = [Link(upstream)] if upstream.is_valid else []
            parent = Context()
        log_token = None
        try:
            with self._tracer.start_as_current_span(
                "meeting.process", context=parent, kind=SpanKind.CONSUMER, links=links, record_exception=False,
            ) as span:
                if span.get_span_context().is_valid:
                    log_token = worker_trace_id.set(f"{span.get_span_context().trace_id:032x}")
                span.set_attribute("ltc.job.id", job.job_id)
                span.set_attribute("ltc.job.attempt", job.attempt_count)
                error = None
                delay = None
                try:
                    await asyncio.to_thread(self._workflow.run, job)
                except LeaseLost:
                    span.set_status(StatusCode.ERROR, "LEASE_LOST")
                    # Close immediately if still owned, e.g. the meeting was deleted.
                    await self._jobs.finish_media_attempt(job, attempt, None, None)
                    return
                except Exception as exc:
                    error = type(exc).__name__
                    span.set_status(StatusCode.ERROR, error)
                    if not isinstance(exc, (AudioProcessingError, MediaExtractionError, FileNotFoundError, ValueError)):
                        delay = compute_retry_delay(job.attempt_count)
                    _logger.warning("meeting.processing_failed", extra={"job_id": job.job_id, "error_code": error})
                await self._jobs.finish_media_attempt(job, attempt, error, delay)
        finally:
            if log_token is not None:
                worker_trace_id.reset(log_token)
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _keep_lease(self, job: JobLease) -> None:
        while True:
            await asyncio.sleep(MEDIA_LEASE_SECONDS / 3)
            try:
                if not await self._jobs.renew_lease(job.job_id, job.lock_token, MEDIA_LEASE_SECONDS):
                    return
            except Exception:
                _logger.warning("meeting.lease_renewal_failed", extra={"job_id": job.job_id}, exc_info=True)

    def close(self) -> None:
        self._workflow.close()


def _queue_age(job: JobLease) -> float:
    try:
        queued = datetime.fromisoformat(job.payload["enqueued_at"])
        return (datetime.now(timezone.utc) - queued).total_seconds()
    except (KeyError, TypeError, ValueError):
        return float("inf")
