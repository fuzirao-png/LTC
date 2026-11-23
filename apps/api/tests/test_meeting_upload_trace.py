import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ltc.modules.iam.interfaces.router import get_auth_context
from ltc.modules.meeting_analysis.interfaces.router import router
from ltc.platform.observability import ObservabilityMiddleware


class MeetingUploadTracingTests(unittest.TestCase):
    def test_upload_passes_server_span_to_persisted_job_metadata(self):
        app = FastAPI()
        app.include_router(router)
        app.add_middleware(ObservabilityMiddleware)
        app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(actor=SimpleNamespace(user_id=uuid4()))
        app.state.meeting_uow = SimpleNamespace(transaction=lambda: nullcontext(object()))
        meeting_id = uuid4()
        service = app.state.meeting_service = Mock()
        service.create_meeting.return_value = SimpleNamespace(meeting_id=meeting_id, processing_status="uploaded")

        provider = TracerProvider()
        self.addCleanup(provider.shutdown)
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, exclude_spans=["send", "receive"])

        with TestClient(app) as client:
            response = client.post(
                "/meetings/upload", data={"company_id": str(uuid4())}, files={"file": ("meeting.wav", b"wav")},
                headers={"Idempotency-Key": "test-upload"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(str(meeting_id), response.json()["data"]["meeting_id"])
        span, = exporter.get_finished_spans()
        trace_id = f"{span.context.trace_id:032x}"
        span_id = f"{span.context.span_id:016x}"
        self.assertEqual(trace_id, response.headers["X-Trace-Id"])
        self.assertEqual(
            f"00-{trace_id}-{span_id}-01", service.create_meeting.call_args.kwargs["trace_metadata"]["traceparent"],
        )
