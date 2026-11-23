from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from ltc_worker.application import JobAttemptHandle, compute_retry_delay
from ltc_worker.errors import LeaseLost, RetryableError, UnsupportedJobTypeError
from ltc_worker.lease import JobLease
from ltc_worker.registry import build_current_phase_registry
from ltc_worker.runtime import WorkerRuntime


@dataclass
class FakeJobRepo:
    events: list[tuple[str, str]] = field(default_factory=list)
    _next_lease: JobLease | None = None

    def set_next(self, job: JobLease | None) -> None:
        self._next_lease = job

    async def claim(self, worker_id: str, queue_names: list[str], lease_seconds: int) -> JobLease | None:
        j, self._next_lease = self._next_lease, None
        return j

    async def start_attempt(self, job: JobLease, worker_id: str) -> JobAttemptHandle:
        self.events.append(("start", job.job_id))
        return JobAttemptHandle(attempt_id="att-1", job_id=job.job_id)

    async def finish_attempt(self, att, status, metrics=None):
        self.events.append(("finish", status))

    async def complete_job(self, att, result_summary=None):
        self.events.append(("complete", att.job_id))

    async def retry_job(self, job, att, err_code, err_msg, delay):
        self.events.append(("retry", err_code))

    async def fail_job(self, job, att, err_code, err_msg):
        self.events.append(("fail", err_code))

    async def renew_lease(self, job_id, lock_token, lease_seconds):
        return True

    async def cancel_job(self, job_id, lock_token):
        return True


class FakeUseCase:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.calls: list[tuple[str, str, dict]] = []

    async def execute(self, *, job_id: str, lock_token: str, payload: dict) -> None:
        self.calls.append((job_id, lock_token, payload))
        if self.exc is not None:
            raise self.exc


@dataclass
class FakeApp:
    repo: FakeJobRepo = field(default_factory=FakeJobRepo)
    uc: FakeUseCase = field(default_factory=FakeUseCase)

    @property
    def jobs(self): return self.repo
    @property
    def lead_search_pipeline(self): return self.uc
    @property
    def refresh_candidate(self): return self.uc
    @property
    def generate_analysis_report(self): return self.uc
    @property
    def generate_email_draft(self): return self.uc
    @property
    def send_email(self): return self.uc
    @property
    def reconcile_email(self): return self.uc
    @property
    def process_meeting(self): return self.uc
    @property
    def dispatch_outbox(self): return self.uc
    @property
    def process_external_event(self): return self.uc
    @property
    def auto_release_overdue(self): return self.uc
    @property
    def send_notification(self): return self.uc
    @property
    def extract_manual_note(self): return self.uc
    @property
    def complete_scale_data(self): return self.uc
    @property
    def complete_region_data(self): return self.uc


class WorkerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_and_completes(self) -> None:
        app = FakeApp()
        job = JobLease("j1", "lead.search_pipeline.v1", "lt-1", "lead", {"q": "tmc"})
        app.repo.set_next(job)
        rt = WorkerRuntime(worker_id="w1", registry=build_current_phase_registry())

        handled = await rt.run_once(app, ["lead"])
        self.assertTrue(handled)
        self.assertEqual([("j1", "lt-1", {"q": "tmc"})], app.uc.calls)
        self.assertEqual(
            [("start", "j1"), ("finish", "succeeded"), ("complete", "j1")],
            app.repo.events,
        )

    async def test_retryable_triggers_retry(self) -> None:
        app = FakeApp(uc=FakeUseCase(exc=RetryableError("boom")))
        job = JobLease("j2", "lead.search_pipeline.v1", "lt-2", "lead", {}, attempt_count=2)
        app.repo.set_next(job)
        rt = WorkerRuntime(worker_id="w2", registry=build_current_phase_registry())

        await rt.run_once(app, ["lead"])
        # base handler calls finish_attempt('failed') then retry_job
        self.assertIn(("start", "j2"), app.repo.events)
        self.assertIn(("retry", "RETRYABLE"), app.repo.events)

    async def test_lease_lost_triggers_lease_lost_finish(self) -> None:
        app = FakeApp(uc=FakeUseCase(exc=LeaseLost("gone")))
        job = JobLease("j3", "lead.search_pipeline.v1", "lt-3", "lead", {})
        app.repo.set_next(job)
        rt = WorkerRuntime(worker_id="w3", registry=build_current_phase_registry())

        await rt.run_once(app, ["lead"])
        self.assertEqual(
            [("start", "j3"), ("finish", "lease_lost")],
            app.repo.events,
        )

    async def test_unknown_job_type_raises(self) -> None:
        app = FakeApp()
        job = JobLease("j4", "legacy.cleanup.v99", "lt-4", "lead", {})
        app.repo.set_next(job)
        rt = WorkerRuntime(worker_id="w4", registry=build_current_phase_registry())

        with self.assertRaises(UnsupportedJobTypeError):
            await rt.run_once(app, ["lead"])

    async def test_no_job_available_returns_false(self) -> None:
        app = FakeApp()
        app.repo.set_next(None)
        rt = WorkerRuntime(worker_id="w5", registry=build_current_phase_registry())

        handled = await rt.run_once(app, ["lead"])
        self.assertFalse(handled)
        self.assertEqual([], app.repo.events)


class BackoffTests(unittest.TestCase):
    def test_first_attempt_small_delay(self) -> None:
        d = compute_retry_delay(1)
        self.assertGreaterEqual(d, 5)
        self.assertLess(d, 25)  # base=5 + jitter < ~7

    def test_high_attempt_capped(self) -> None:
        d = compute_retry_delay(20)
        self.assertLessEqual(d, 700)  # 600 cap + jitter

    def test_monotonic(self) -> None:
        d1 = compute_retry_delay(1)
        d2 = compute_retry_delay(3)
        self.assertLess(d1, d2)
