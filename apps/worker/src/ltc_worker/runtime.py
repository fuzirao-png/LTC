"""``WorkerRuntime`` — the claim → dispatch → handle loop core."""

from __future__ import annotations

import logging
import time

from .application import ApplicationServices
from .errors import UnsupportedJobTypeError
from .lease import JobLease
from .observability._formatter import set_worker_trace_id
from .registry import HandlerRegistry

_logger = logging.getLogger("ltc.worker")

_TRACE_ID_PAYLOAD_KEY = "_trace_id"


class WorkerRuntime:
    """Stateless orchestrator: claim a job, dispatch to a handler, log results.

    The runtime does **not** own a ``JobRepository`` directly — it reads
    ``queue_names`` + ``lease_seconds`` from the caller so the
    composition root controls lease policy and queue scoping.
    """

    def __init__(self, *, worker_id: str, registry: HandlerRegistry) -> None:
        self._worker_id = worker_id
        self._registry = registry

    async def run_once(
        self,
        app: ApplicationServices,
        queue_names: list[str],
        lease_seconds: int = 300,
    ) -> bool:
        """Claim one job and execute it.  Returns ``True`` if a job was handled."""
        job = await app.jobs.claim(self._worker_id, queue_names, lease_seconds)
        if job is None:
            return False

        handler = self._registry.resolve(job.job_type)
        if handler is None:
            _logger.error(
                "unsupported_job_type",
                extra={"worker_id": self._worker_id, "job_type": job.job_type, "job_id": job.job_id},
            )
            raise UnsupportedJobTypeError(f"unsupported job type: {job.job_type}")

        trace_id = _extract_trace_id(job)
        set_worker_trace_id(trace_id)

        started_at = time.monotonic()
        _logger.info(
            "job.started",
            extra={
                "worker_id": self._worker_id, "job_id": job.job_id,
                "job_type": job.job_type, "queue_name": job.queue_name,
                "attempt_count": job.attempt_count,
            },
        )

        try:
            await handler.handle(job, app)
        except Exception:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            _logger.error(
                "job.failed",
                extra={
                    "worker_id": self._worker_id, "job_id": job.job_id,
                    "job_type": job.job_type,
                    "duration_ms": round(elapsed_ms, 3),
                },
                exc_info=True,
            )
            raise
        finally:
            set_worker_trace_id("")

        elapsed_ms = (time.monotonic() - started_at) * 1000
        _logger.info(
            "job.completed",
            extra={
                "worker_id": self._worker_id, "job_id": job.job_id,
                "job_type": job.job_type,
                "duration_ms": round(elapsed_ms, 3),
            },
        )
        return True


def _extract_trace_id(job: JobLease) -> str:
    if isinstance(job.payload, dict):
        tid = job.payload.get(_TRACE_ID_PAYLOAD_KEY)
        if isinstance(tid, str) and tid:
            return tid
    return f"wrk-{job.job_id}"
