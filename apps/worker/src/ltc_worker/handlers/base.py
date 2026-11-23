"""Base handler that delegates every job type to a ``JobExecutionUseCase``.

Each concrete handler declares:
- ``job_type`` — the versioned job type string.
- ``use_case_attr`` — the attribute name on ``ApplicationServices``
  that holds the matching ``JobExecutionUseCase``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..application import ApplicationServices, compute_retry_delay, empty_metrics
from ..errors import LeaseLost, PayloadValidationError, RetryableError
from ..lease import JobLease

_logger = logging.getLogger("ltc.worker.handler")


class UseCaseBackedHandler:
    job_type: str
    use_case_attr: str

    async def handle(self, job: JobLease, app: ApplicationServices) -> None:
        repo = app.jobs
        attempt = await repo.start_attempt(job, "ltc-worker")
        started_at = time.monotonic()

        try:
            payload = self.validate_payload(job.payload)
            use_case = getattr(app, self.use_case_attr)
            await use_case.execute(job_id=job.job_id, lock_token=job.lock_token, payload=payload)

            await repo.finish_attempt(attempt, "succeeded", empty_metrics())
            await repo.complete_job(attempt)
            _logger.info(
                "attempt.succeeded",
                extra={
                    "job_id": job.job_id, "job_type": job.job_type,
                    "attempt_id": attempt.attempt_id,
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 3),
                },
            )
        except LeaseLost:
            await repo.finish_attempt(attempt, "lease_lost")
            _logger.warning("attempt.lease_lost", extra={
                "job_id": job.job_id, "job_type": job.job_type,
                "attempt_id": attempt.attempt_id,
            })
        except RetryableError as exc:
            err_code = _error_code(exc)
            delay = compute_retry_delay(job.attempt_count)
            await repo.retry_job(job, attempt, err_code, str(exc), delay)
            _logger.warning("attempt.retrying", extra={
                "job_id": job.job_id, "job_type": job.job_type,
                "attempt_id": attempt.attempt_id, "error": str(exc),
                "retry_delay_seconds": delay,
                "duration_ms": round((time.monotonic() - started_at) * 1000, 3),
            })
        except Exception as exc:
            err_code = _error_code(exc)
            await repo.fail_job(job, attempt, err_code, str(exc))
            _logger.error("attempt.failed", extra={
                "job_id": job.job_id, "job_type": job.job_type,
                "attempt_id": attempt.attempt_id, "error": str(exc),
                "duration_ms": round((time.monotonic() - started_at) * 1000, 3),
            }, exc_info=True)

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PayloadValidationError("job payload must be a JSON object")
        return payload


def _error_code(exc: Exception) -> str:
    """Derive a stable error code from the exception type name."""
    name = type(exc).__name__
    # Convert CamelCase → UPPER_SNAKE
    code = []
    for ch in name:
        if ch.isupper() and code:
            code.append("_")
        code.append(ch.upper())
    return "".join(code).replace("_ERROR", "")
