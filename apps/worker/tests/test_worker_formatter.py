"""Tests for worker log formatters: JSON, human-readable, and trace-id contextvar."""

from __future__ import annotations

import json
import logging
import unittest

from ltc_worker.observability._formatter import (
    JSONFormatter,
    HumanFormatter,
    get_worker_trace_id,
    set_worker_trace_id,
)


class WorkerTraceContextTests(unittest.TestCase):
    def setUp(self) -> None:
        set_worker_trace_id("")

    def tearDown(self) -> None:
        set_worker_trace_id("")

    def test_default_trace_id_is_empty_string(self) -> None:
        self.assertEqual("", get_worker_trace_id())

    def test_set_and_get_roundtrip(self) -> None:
        set_worker_trace_id("trace-from-api-123")
        self.assertEqual("trace-from-api-123", get_worker_trace_id())

    def test_reset_to_empty(self) -> None:
        set_worker_trace_id("trace-from-api-123")
        set_worker_trace_id("")
        self.assertEqual("", get_worker_trace_id())


class WorkerJSONFormatterTraceIdTests(unittest.TestCase):
    def setUp(self) -> None:
        set_worker_trace_id("")

    def tearDown(self) -> None:
        set_worker_trace_id("")

    def test_formatter_reads_trace_id_from_contextvar(self) -> None:
        set_worker_trace_id("api-trace-abc")
        formatter = JSONFormatter(service_name="ltc-worker")
        record = logging.LogRecord(
            name="ltc.worker", level=logging.INFO, pathname=__file__,
            lineno=1, msg="job.started", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        self.assertEqual("api-trace-abc", parsed["trace_id"])

    def test_empty_trace_id_when_not_set(self) -> None:
        formatter = JSONFormatter(service_name="ltc-worker")
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
        parsed = json.loads(formatter.format(record))
        self.assertEqual("", parsed["trace_id"])


class WorkerJSONFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        set_worker_trace_id("")

    def tearDown(self) -> None:
        set_worker_trace_id("")

    def test_emits_json_with_required_fields(self) -> None:
        formatter = JSONFormatter(service_name="ltc-test-worker")
        record = logging.LogRecord(
            "ltc.worker", logging.INFO, __file__, 1, "job.started", (), None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual("ltc-test-worker", parsed["service"])
        self.assertEqual("ltc.worker", parsed["logger"])
        self.assertEqual("INFO", parsed["level"])
        self.assertEqual("job.started", parsed["message"])

    def test_extra_fields_preserved(self) -> None:
        formatter = JSONFormatter(service_name="ltc-test-worker")
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
        record.__dict__["job_id"] = "job-1"
        record.__dict__["queue_name"] = "lead-search"
        parsed = json.loads(formatter.format(record))
        self.assertEqual(
            {"job_id": "job-1", "queue_name": "lead-search"}, parsed["extra"],
        )

    def test_includes_exception_on_error(self) -> None:
        formatter = JSONFormatter(service_name="ltc-test-worker")
        try:
            raise ValueError("worker crash")
        except ValueError:
            import sys
            exc_info_tuple = sys.exc_info()
            record = logging.LogRecord(
                "x", logging.ERROR, __file__, 1, "failed", (), exc_info_tuple,
            )
        parsed = json.loads(formatter.format(record))
        self.assertIn("exception", parsed)
        self.assertIn("worker crash", parsed["exception"])


class WorkerHumanFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        set_worker_trace_id("")

    def tearDown(self) -> None:
        set_worker_trace_id("")

    def test_produces_coloured_output_with_trace_id(self) -> None:
        set_worker_trace_id("deadbeef-cafe-dead-beef-deadbeefdead")
        formatter = HumanFormatter(service_name="ltc-dev-worker")
        formatter._style = logging.PercentStyle("%(message)s")
        record = logging.LogRecord(
            "ltc.worker", logging.WARNING, __file__, 1,
            "lease about to expire", (), None,
        )
        output = formatter.format(record)
        self.assertIn("WARNING", output)
        self.assertIn("ltc-dev-worker", output)
        self.assertIn("deadbeef", output)
        self.assertIn("lease about to expire", output)
