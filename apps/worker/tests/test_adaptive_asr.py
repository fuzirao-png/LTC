import unittest
from unittest.mock import patch

import httpx
from opentelemetry.trace import NoOpTracer

from ltc_worker.adaptive_asr import AdaptiveAsr


class AdaptiveAsrTests(unittest.TestCase):
    def test_latency_and_overload_reduce_capacity_then_successes_restore_it(self):
        gate = AdaptiveAsr(4, 2.0, NoOpTracer())

        with patch("ltc_worker.adaptive_asr.monotonic", side_effect=[0.0, 3.0]):
            gate.request(lambda: httpx.Response(200))
        self.assertEqual(2, gate._limit)

        gate.request(lambda: httpx.Response(429))
        self.assertEqual(1, gate._limit)

        for _ in range(4):
            gate.request(lambda: httpx.Response(200))
        self.assertEqual(2, gate._limit)

    def test_transport_failure_releases_the_permit(self):
        gate = AdaptiveAsr(1, 2.0, NoOpTracer())

        def timeout():
            raise httpx.ReadTimeout("timed out")

        with self.assertRaises(httpx.ReadTimeout):
            gate.request(timeout)
        self.assertEqual(0, gate._in_flight)
        self.assertEqual(0, gate._pending)
        self.assertEqual(200, gate.request(lambda: httpx.Response(200)).status_code)
