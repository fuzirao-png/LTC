"""Tests for ObservabilityMiddleware request logging and trace-id injection."""

from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from ltc.main import create_app
from ltc.platform.config import AppSettings
from ltc.platform.observability.domain.trace_context import TraceContext


def _test_app():
    settings = AppSettings(
        app_name="ltc-test",
        app_version="0.0.0",
        environment="test",
    )
    return create_app(settings)


class MiddlewareIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        TraceContext.reset()
        self.client = TestClient(_test_app())

    def tearDown(self) -> None:
        TraceContext.reset()
        root = logging.getLogger()
        root.handlers.clear()

    def test_health_endpoint_returns_trace_id_header(self) -> None:
        response = self.client.get("/health/live")
        self.assertEqual(200, response.status_code)
        self.assertIn("X-Trace-Id", response.headers)
        tid = response.headers["X-Trace-Id"]
        self.assertTrue(len(tid) >= 32, f"Expected UUID-length trace-id, got {tid!r}")

    def test_trace_id_header_passed_through(self) -> None:
        response = self.client.get(
            "/health/live",
            headers={"X-Trace-Id": "my-incoming-trace"},
        )
        self.assertEqual("my-incoming-trace", response.headers["X-Trace-Id"])

    def test_x_request_id_used_as_fallback(self) -> None:
        """When X-Trace-Id is absent, X-Request-Id is treated as trace-id."""
        response = self.client.get(
            "/health/live",
            headers={"X-Request-Id": "cdn-request-id"},
        )
        self.assertEqual("cdn-request-id", response.headers["X-Trace-Id"])

    def test_different_requests_get_unique_trace_ids(self) -> None:
        """FastAPI TestClient reuses context between requests by design.
        We test that trace-id is unique when explicitly reset between requests."""
        tids = set()
        for _ in range(5):
            TraceContext.reset()
            resp = self.client.get("/health/live")
            tids.add(resp.headers["X-Trace-Id"])
        self.assertEqual(5, len(tids), "Each request should get a unique trace-id")

    def test_404_path_logged_correctly(self) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(404, response.status_code)
        self.assertIn("X-Trace-Id", response.headers)

    def test_middleware_does_not_leak_trace_id_between_requests(self) -> None:
        resp1 = self.client.get("/health/live")
        resp2 = self.client.get("/health/live")
        self.assertNotEqual(resp1.headers["X-Trace-Id"], resp2.headers["X-Trace-Id"])

    @patch("ltc.platform.observability.interfaces.logging_middleware._logger")
    def test_started_and_completed_events_emitted(self, mock_logger: MagicMock) -> None:
        self.client.get("/health/live")
        self.assertTrue(mock_logger.debug.called)
        self.assertTrue(mock_logger.info.called)
        debug_call = mock_logger.debug.call_args_list[0]
        self.assertEqual("request.started", debug_call[0][0])
        info_call = mock_logger.info.call_args_list[-1]
        self.assertEqual("request.completed", info_call[0][0])

    @patch("ltc.platform.observability.interfaces.logging_middleware._logger")
    def test_failed_event_emitted_on_exception(self, mock_logger: MagicMock) -> None:
        """Middleware catches unhandled exceptions and logs them as errors.

        BaseHTTPMiddleware only sees exceptions that aren't caught by FastAPI's
        default exception handlers. We use a raw ASGI app so the exception propagates
        all the way to the middleware layer.
        """
        from starlette.types import ASGIApp, Scope, Receive, Send

        ObservabilityMiddleware = __import__(
            "ltc.platform.observability.interfaces.logging_middleware",
            fromlist=["ObservabilityMiddleware"],
        ).ObservabilityMiddleware

        async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                raise RuntimeError("simulated crash")
            await send({"type": "lifespan.shutdown.complete"})

        wrapped: ASGIApp = ObservabilityMiddleware(failing_app)

        async def run():
            from starlette.testclient import TestClient as AsyncTestClient
            # Use httpx directly to trigger the ASGI exception path
            import httpx
            transport = httpx.ASGITransport(app=wrapped, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                try:
                    await client.get("/boom")
                except Exception:
                    pass

        import asyncio
        asyncio.run(run())
        self.assertTrue(mock_logger.error.called)
        if mock_logger.error.called:
            error_call = mock_logger.error.call_args_list[0]
            self.assertEqual("request.failed", error_call[0][0])
