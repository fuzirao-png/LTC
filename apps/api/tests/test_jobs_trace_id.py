"""Tests for platform/jobs trace-id injection helper."""

from __future__ import annotations

import unittest

from ltc.platform.observability.domain.trace_context import TraceContext


class InjectTraceIdTests(unittest.TestCase):
    def setUp(self) -> None:
        TraceContext.reset()

    def tearDown(self) -> None:
        TraceContext.reset()

    def test_injects_current_trace_id(self) -> None:
        from ltc.platform.observability import set_trace_id
        from ltc.platform.jobs import inject_trace_id

        set_trace_id("req-deadbeef")
        payload = inject_trace_id({"query_text": "hello"})

        self.assertEqual("req-deadbeef", payload["_trace_id"])
        self.assertEqual("hello", payload["query_text"])

    def test_does_not_overwrite_existing_trace_id(self) -> None:
        from ltc.platform.jobs import inject_trace_id

        payload = inject_trace_id({"_trace_id": "custom-caller-id"})
        self.assertEqual("custom-caller-id", payload["_trace_id"])

    def test_generates_fallback_when_no_current_trace_id(self) -> None:
        from ltc.platform.jobs import inject_trace_id

        payload = inject_trace_id({"scene_code": "S1"})
        self.assertIn("_trace_id", payload)
        self.assertTrue(len(payload["_trace_id"]) >= 32)

    def test_original_payload_is_not_mutated(self) -> None:
        from ltc.platform.jobs import inject_trace_id

        original = {"x": 1}
        enriched = inject_trace_id(original)

        self.assertNotIn("_trace_id", original)
        self.assertIn("_trace_id", enriched)
        self.assertEqual(1, original["x"])
        self.assertEqual(1, enriched["x"])
