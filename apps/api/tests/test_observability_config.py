"""Tests for observability logging configuration and trace context."""

from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import patch

from ltc.platform.observability.domain.trace_context import (
    TraceContext,
    get_trace_id,
    set_trace_id,
    set_request_path,
    get_request_path,
)
from ltc.platform.observability.infrastructure.json_logger import (
    JSONFormatter,
    configure_logging,
    get_logger,
)
from ltc.platform.observability.domain.trace_context import set_trace_id, TraceContext


class TraceContextTests(unittest.TestCase):
    def setUp(self) -> None:
        TraceContext.reset()

    def tearDown(self) -> None:
        TraceContext.reset()

    def test_get_trace_id_generates_non_empty_uuid(self) -> None:
        tid = get_trace_id()
        self.assertIsInstance(tid, str)
        self.assertTrue(len(tid) >= 32, f"Expected UUID-length string, got {tid!r}")

    def test_get_trace_id_is_stable_within_a_context(self) -> None:
        first = get_trace_id()
        second = get_trace_id()
        self.assertEqual(first, second)

    def test_set_trace_id_overrides_auto_generated(self) -> None:
        set_trace_id("my-custom-trace-id")
        self.assertEqual("my-custom-trace-id", get_trace_id())

    def test_set_trace_id_then_reset_allows_new_id(self) -> None:
        set_trace_id("explicit-id")
        TraceContext.reset()
        tid = get_trace_id()
        self.assertNotEqual("explicit-id", tid)

    def test_request_path_roundtrip(self) -> None:
        set_request_path("/api/v1/leads/search")
        self.assertEqual("/api/v1/leads/search", get_request_path())

    def test_reset_clears_request_path(self) -> None:
        set_request_path("/some/path")
        TraceContext.reset()
        self.assertEqual("", get_request_path())


class JSONFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        TraceContext.reset()

    def tearDown(self) -> None:
        TraceContext.reset()

    def test_emits_json_with_required_fields(self) -> None:
        set_trace_id("deadbeef-dead-beef-dead-beefdeadbeef")
        formatter = JSONFormatter(service_name="ltc-test")
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Something happened",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual("ltc-test", parsed["service"])
        self.assertEqual("deadbeef-dead-beef-dead-beefdeadbeef", parsed["trace_id"])
        self.assertEqual("test.module", parsed["logger"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("Something happened", parsed["message"])
        self.assertIn("timestamp", parsed)

    def test_includes_exception_on_error(self) -> None:
        set_trace_id("tid")
        formatter = JSONFormatter(service_name="ltc-test")
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info_tuple = sys.exc_info()
            record = logging.LogRecord(
                name="x",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=exc_info_tuple,
            )
        parsed = json.loads(formatter.format(record))
        self.assertIn("exception", parsed)
        self.assertIn("boom", parsed["exception"])

    def test_extra_fields_preserved(self) -> None:
        set_trace_id("tid")
        formatter = JSONFormatter(service_name="ltc-test")
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event",
            args=(),
            exc_info=None,
        )
        record.__dict__["lead_id"] = "lead-1"
        record.__dict__["company_name"] = "Acme"
        parsed = json.loads(formatter.format(record))
        self.assertEqual({"lead_id": "lead-1", "company_name": "Acme"}, parsed["extra"])


class LoggerFactoryTests(unittest.TestCase):
    def test_get_logger_returns_stdlib_logger(self) -> None:
        lg = get_logger("ltc.iam")
        self.assertIsInstance(lg, logging.Logger)
        self.assertEqual("ltc.iam", lg.name)

    def test_configure_logging_sets_level_from_env(self) -> None:
        with patch.dict("os.environ", {"LTC_LOG_LEVEL": "DEBUG"}, clear=True):
            configure_logging(service_name="ltc-test", log_level="DEBUG")
            root = logging.getLogger()
            self.assertEqual(logging.DEBUG, root.level)
        root.handlers.clear()

    def test_configure_logging_defaults_to_info(self) -> None:
        configure_logging(service_name="ltc-test")
        root = logging.getLogger()
        self.assertEqual(logging.INFO, root.level)
        root.handlers.clear()
