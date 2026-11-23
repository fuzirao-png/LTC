"""Worker application layer — stable contracts for the job lifecycle.

All types in this module are framework-level abstractions.  Concrete
implementations live in ``infrastructure/`` (PostgreSQL-backed) or in
business modules (UseCase implementations).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


# ── Lease ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class JobLease:
    """A claimed job ready for execution."""

    job_id: str
    job_type: str
    lock_token: str
    queue_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 0
    concurrency_key: str | None = None


# ── Attempt handle ─────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class JobAttemptHandle:
    """Opaque handle returned by ``start_attempt()``."""

    attempt_id: str
    job_id: str


# ── Job repository (framework Port) ─────────────────────────────────


class JobRepository(Protocol):
    """Persistence Port for the job queue.

    Implemented by ``PostgreSQLJobRepository`` in production and by
    in-memory doubles in tests.
    """

    async def claim(self, worker_id: str, queue_names: list[str], lease_seconds: int) -> JobLease | None:
        """Atomically claim the next runnable job or return None."""
        ...

    async def start_attempt(self, job: JobLease, worker_id: str) -> JobAttemptHandle:
        """Record a ``job_attempt`` row in ``started`` state."""
        ...

    async def finish_attempt(
        self, attempt: JobAttemptHandle, status: str, metrics: dict[str, Any] | None = None
    ) -> None:
        """Mark attempt as ``succeeded``, ``failed``, or ``lease_lost``."""
        ...

    async def complete_job(self, attempt: JobAttemptHandle, result_summary: dict[str, Any] | None = None) -> None:
        """Mark the parent job as ``succeeded``."""
        ...

    async def retry_job(
        self,
        job: JobLease,
        attempt: JobAttemptHandle,
        error_code: str,
        error_message: str,
        retry_delay_seconds: int,
    ) -> None:
        """Mark attempt as ``failed`` and transition job to ``retry_wait``."""
        ...

    async def fail_job(
        self,
        job: JobLease,
        attempt: JobAttemptHandle,
        error_code: str,
        error_message: str,
    ) -> None:
        """Mark attempt as ``failed`` and job as ``failed_final``."""
        ...

    async def renew_lease(self, job_id: str, lock_token: str, lease_seconds: int) -> bool:
        """Extend ``locked_until``.  Returns ``False`` if the lease was lost."""
        ...

    async def cancel_job(self, job_id: str, lock_token: str) -> bool:
        """Atomically cancel a running job (only if the lock token matches)."""
        ...


# ── Use-case port (business module entry point) ─────────────────────


class JobExecutionUseCase(Protocol):
    """A single handler's business logic entry point.

    Every handler delegates to exactly one UseCase.  The UseCase is
    responsible for:
    - Validating the job payload against its domain schema
    - Calling external providers *outside* any database transaction
    - Writing domain results through the module's own Port / UoW
    """

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        ...


# ── Application services bag ────────────────────────────────────────


class ApplicationServices(Protocol):
    """Typed bag of shared services and per-job-type use cases.

    Concrete wiring is done by the composition root (``main.py``).
    """

    jobs: JobRepository
    lead_search_pipeline: JobExecutionUseCase
    refresh_candidate: JobExecutionUseCase
    generate_analysis_report: JobExecutionUseCase
    research_customer: JobExecutionUseCase
    generate_email_draft: JobExecutionUseCase
    send_email: JobExecutionUseCase
    reconcile_email: JobExecutionUseCase
    process_meeting: JobExecutionUseCase
    dispatch_outbox: JobExecutionUseCase
    process_external_event: JobExecutionUseCase
    crm_pipeline_consumer: JobExecutionUseCase
    auto_release_overdue: JobExecutionUseCase
    send_notification: JobExecutionUseCase
    extract_manual_note: JobExecutionUseCase
    complete_scale_data: JobExecutionUseCase
    complete_region_data: JobExecutionUseCase


# ── Default empty metrics (helper) ──────────────────────────────────


def empty_metrics() -> dict[str, Any]:
    return {
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


# ── Backoff helper ──────────────────────────────────────────────────


def compute_retry_delay(attempt_count: int, base_seconds: int = 5, max_seconds: int = 600) -> int:
    """Exponential backoff with jitter: 5s, 10s, 20s, ... capping at 600s."""
    delay = min(base_seconds * (2 ** (attempt_count - 1)), max_seconds)
    # deterministic pseudo-jitter based on attempt number (avoid random for testability)
    jitter = (attempt_count * 173) % (max(delay // 4, 1))
    return delay + jitter
