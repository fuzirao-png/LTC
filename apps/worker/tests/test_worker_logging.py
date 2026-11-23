"""Tests for worker logging configuration (main.configure_worker_logging)."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import patch


class WorkerMainTests(unittest.TestCase):
    def setUp(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()

    def tearDown(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()

    def test_configure_worker_logging_defaults_to_info_json(self) -> None:
        from ltc_worker.main import configure_worker_logging
        configure_worker_logging()
        root = logging.getLogger()
        self.assertEqual(logging.INFO, root.level)
        self.assertEqual(1, len(root.handlers))
        root.handlers.clear()

    def test_configure_worker_logging_respects_log_level_env(self) -> None:
        from ltc_worker.main import configure_worker_logging
        with patch.dict("os.environ", {"LTC_LOG_LEVEL": "DEBUG"}, clear=True):
            configure_worker_logging()
            root = logging.getLogger()
            self.assertEqual(logging.DEBUG, root.level)
        root.handlers.clear()

    def test_runtime_queue_names_default_to_wired_queues(self) -> None:
        from ltc_worker.main import queue_names_from_environment

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(queue_names_from_environment(), ["crm", "analysis", "media"])

    def test_runtime_queue_names_can_be_explicitly_overridden(self) -> None:
        from ltc_worker.main import queue_names_from_environment

        with patch.dict(
            "os.environ",
            {"LTC_WORKER_QUEUE_NAMES": "crm, lead-search,crm"},
            clear=True,
        ):
            self.assertEqual(queue_names_from_environment(), ["crm", "lead-search"])


if __name__ == "__main__":
    unittest.main()
