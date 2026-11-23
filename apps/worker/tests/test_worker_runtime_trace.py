"""Tests for worker runtime trace-id propagation."""

from __future__ import annotations

import unittest

from ltc_worker.application import JobAttemptHandle
from ltc_worker.lease import JobLease
from ltc_worker.observability._formatter import get_worker_trace_id
from ltc_worker.registry import build_current_phase_registry
from ltc_worker.runtime import WorkerRuntime


class RuntimeTraceIdTests(unittest.IsolatedAsyncioTestCase):

    async def test_runtime_sets_trace_id_from_payload(self) -> None:
        captured: list[str] = []

        class FakeUseCase:
            def __init__(self, c): self.c = c
            async def execute(self, *, job_id, lock_token, payload): self.c.append(get_worker_trace_id())

        class FakeRepo:
            def __init__(self, j): self._j = j
            async def claim(self, w, qn, ls): v, self._j = self._j, None; return v
            async def start_attempt(self, j, w): return JobAttemptHandle("a1", j.job_id)
            async def finish_attempt(self, a, s, m=None): pass
            async def complete_job(self, a, rs=None): pass
            async def retry_job(self, j, a, ec, em, d): pass
            async def fail_job(self, j, a, ec, em): pass
            async def renew_lease(self, *a): return True
            async def cancel_job(self, *a): return True

        uc = FakeUseCase(captured)
        job = JobLease("j1", "lead.search_pipeline.v1", "lt", "lead",
                       {"_trace_id": "http-abc", "q": "tmc"})

        class App:
            jobs = FakeRepo(job)
            lead_search_pipeline = uc; refresh_candidate = uc
            generate_analysis_report = uc; generate_email_draft = uc
            send_email = uc; reconcile_email = uc; process_meeting = uc
            dispatch_outbox = uc; process_external_event = uc
            auto_release_overdue = uc; send_notification = uc
            extract_manual_note = uc; complete_scale_data = uc; complete_region_data = uc

        rt = WorkerRuntime(worker_id="w1", registry=build_current_phase_registry())
        handled = await rt.run_once(App(), ["lead"])
        self.assertTrue(handled)
        self.assertEqual(["http-abc"], captured)
        self.assertEqual("", get_worker_trace_id())

    async def test_runtime_fallback_when_no_trace_id(self) -> None:
        captured: list[str] = []

        class FakeUseCase:
            def __init__(self, c): self.c = c
            async def execute(self, *, job_id, lock_token, payload): self.c.append(get_worker_trace_id())

        class FakeRepo:
            def __init__(self, j): self._j = j
            async def claim(self, w, qn, ls): v, self._j = self._j, None; return v
            async def start_attempt(self, j, w): return JobAttemptHandle("a2", j.job_id)
            async def finish_attempt(self, a, s, m=None): pass
            async def complete_job(self, a, rs=None): pass
            async def retry_job(self, j, a, ec, em, d): pass
            async def fail_job(self, j, a, ec, em): pass
            async def renew_lease(self, *a): return True
            async def cancel_job(self, *a): return True

        uc = FakeUseCase(captured)
        job = JobLease("j2", "lead.search_pipeline.v1", "lt", "lead", {"q": "tmc"})

        class App:
            jobs = FakeRepo(job)
            lead_search_pipeline = uc; refresh_candidate = uc
            generate_analysis_report = uc; generate_email_draft = uc
            send_email = uc; reconcile_email = uc; process_meeting = uc
            dispatch_outbox = uc; process_external_event = uc
            auto_release_overdue = uc; send_notification = uc
            extract_manual_note = uc; complete_scale_data = uc; complete_region_data = uc

        rt = WorkerRuntime(worker_id="w2", registry=build_current_phase_registry())
        await rt.run_once(App(), ["lead"])
        self.assertEqual(1, len(captured))
        self.assertTrue(captured[0].startswith("wrk-j2"))
        self.assertEqual("", get_worker_trace_id())
