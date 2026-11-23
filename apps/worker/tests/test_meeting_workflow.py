import os
import unittest
import wave
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import asyncpg
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer

from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.meeting_analysis.application.meeting_service import MeetingService
from ltc.modules.meeting_analysis.domain.errors import AsrTranscriptionError
from ltc.modules.meeting_analysis.infrastructure import PostgresMeetingRepository, SummaryAdapter
from ltc.platform.observability.tracing import trace_context
from ltc_worker.crm_services import CrmWorkerDatabase
from ltc_worker.errors import LeaseLost
from ltc_worker.infrastructure.job_repository import PostgreSQLJobRepository
from ltc_worker.media_job import MEDIA_LEASE_SECONDS, MediaJobRunner
from ltc_worker.meeting_workflow import MeetingWorkflow


class MediaTracingTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_attempt_continues_request_trace_and_retry_links_to_it(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        self.addCleanup(provider.shutdown)
        tracer = provider.get_tracer("test")
        job_repo = Mock(spec=PostgreSQLJobRepository)
        workflow = Mock(spec=MeetingWorkflow)
        runner = MediaJobRunner(job_repo, workflow, tracer)
        carrier = {"enqueued_at": datetime.now(timezone.utc).isoformat()}
        with tracer.start_as_current_span("upload") as request:
            trace_context.inject(carrier)
        job = SimpleNamespace(job_id=str(uuid4()), payload=carrier, attempt_count=1)
        await runner.handle(job)
        job.attempt_count = 2
        workflow.run.side_effect = AsrTranscriptionError("provider failed")
        await runner.handle(job)

        _, first, retry = exporter.get_finished_spans()
        context = request.get_span_context()
        self.assertEqual((context.trace_id, context.span_id), (first.parent.trace_id, first.parent.span_id))
        self.assertTrue(first.parent.is_remote)
        self.assertNotEqual(first.context.trace_id, retry.context.trace_id)
        self.assertEqual(request.get_span_context().trace_id, retry.links[0].context.trace_id)
        self.assertEqual("ERROR", retry.status.status_code.name)


@unittest.skipUnless(os.getenv("LTC_MEDIA_TEST_DSN"), "requires a migrated, disposable PostgreSQL database")
class MeetingWorkflowDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_recovers_expired_lease_and_reuses_committed_segment(self):
        dsn = os.environ["LTC_MEDIA_TEST_DSN"]
        database = CrmWorkerDatabase(dsn)
        database.open()
        self.addCleanup(database.close)
        jobs = PostgreSQLJobRepository(lambda: asyncpg.connect(dsn=dsn))

        with TemporaryDirectory() as folder:
            recording = Path(folder) / "recording.wav"
            with wave.open(str(recording), "wb") as audio_file:
                audio_file.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
                audio_file.writeframes(b"\x00\x00" * 40_000)

            with database.transaction() as conn, recording.open("rb") as upload, patch(
                "ltc.modules.meeting_analysis.application.meeting_service._TEMP_ROOT", folder,
            ):
                company_id = conn.execute("SELECT company_id FROM ltc.company LIMIT 1").fetchone()[0]
                user_id = conn.execute("SELECT user_id FROM ltc.user_account WHERE status='active' LIMIT 1").fetchone()[0]
                actor = CurrentActor(user_id, "tester", "Test", "strategic", None, None, None, 0, ())
                meeting = MeetingService(audio_processor=Mock(), asr_service=Mock(), summary_service=Mock()).create_meeting(
                    PostgresMeetingRepository(conn), upload_file=SimpleNamespace(filename=recording.name, file=upload),
                    company_id=company_id, owner_user_id=user_id, title="resumption check", actor=actor,
                )

            first_job = await jobs.claim("test-first-worker", ["media"], MEDIA_LEASE_SECONDS)
            self.assertEqual(str(meeting.current_job_id), first_job.job_id)
            first_attempt = await jobs.start_attempt(first_job, "test-first-worker")
            first_asr = Mock()
            first_asr.transcribe_segment.side_effect = ["first", AsrTranscriptionError("worker interrupted")]
            summary = SummaryAdapter(api_key="", base_url="")
            workflow = MeetingWorkflow(database, first_asr, summary, NoOpTracer(), model="test", chunk_seconds=1, parallel=1)
            with self.assertRaises(AsrTranscriptionError):
                workflow.run(first_job)
            with database.transaction() as conn:
                conn.execute("UPDATE ltc.job SET locked_until=now()-interval '1 second' WHERE job_id=%s", (first_job.job_id,))

            self.assertEqual(1, await jobs.recover_media_jobs())
            second_job = await jobs.claim("test-restarted-worker", ["media"], MEDIA_LEASE_SECONDS)
            self.assertNotEqual(first_job.lock_token, second_job.lock_token)
            with self.assertRaises(LeaseLost):
                workflow.run(first_job)

            second_asr = Mock()
            second_asr.transcribe_segment.side_effect = ["second", "third"]
            resumed = MeetingWorkflow(database, second_asr, summary, NoOpTracer(), model="test", chunk_seconds=1, parallel=1)
            await MediaJobRunner(jobs, resumed, NoOpTracer()).handle(second_job)

            self.assertEqual(2, second_asr.transcribe_segment.call_count)
            self.assertEqual(first_asr.transcribe_segment.call_args.args[1], second_asr.transcribe_segment.call_args_list[0].args[1])
            with database.transaction() as conn:
                repo = PostgresMeetingRepository(conn)
                saved = repo.find_meeting_by_id(meeting.meeting_id)
                self.assertEqual("completed", saved.processing_status)
                self.assertEqual("first\nsecond\nthird", saved.transcript_text)
                segments = repo.list_segments(meeting.meeting_id)
                self.assertEqual([(0, 1), (1, 2), (2, 2.5)], [(s.start_seconds, s.end_seconds) for s in segments])
                self.assertEqual("succeeded", conn.execute("SELECT status FROM ltc.job WHERE job_id=%s", (second_job.job_id,)).fetchone()[0])
                self.assertEqual("lease_lost", conn.execute("SELECT status FROM ltc.job_attempt WHERE attempt_id=%s", (first_attempt.attempt_id,)).fetchone()[0])
