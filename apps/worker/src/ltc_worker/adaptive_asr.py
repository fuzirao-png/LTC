"""Bound provider concurrency across all media jobs in a worker process."""

from collections.abc import Callable
from threading import Condition
from time import monotonic

import httpx
from opentelemetry.metrics import get_meter
from opentelemetry.trace import StatusCode, Tracer


class AdaptiveAsr:
    def __init__(self, maximum: int, target_seconds: float, tracer: Tracer) -> None:
        self._condition = Condition()
        self._maximum = maximum
        self._limit = maximum
        self._in_flight = 0
        self._pending = 0
        self._target = target_seconds
        self._epoch = 0
        self._healthy = 0
        self._tracer = tracer
        meter = get_meter("ltc.media")
        self._limit_metric = meter.create_gauge("asr_concurrency_limit")
        self._in_flight_metric = meter.create_gauge("asr_in_flight")
        self._pending_metric = meter.create_gauge("asr_pending")
        self._duration = meter.create_histogram(
            "asr_request_duration", unit="s",
            explicit_bucket_boundaries_advisory=(0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 5, 6, 10, 30, 60, 120),
        )

    def request(self, send: Callable[[], httpx.Response]) -> httpx.Response:
        with self._condition:
            self._pending += 1
            self._observe()
            self._condition.wait_for(lambda: self._in_flight < self._limit)
            self._pending -= 1
            self._in_flight += 1
            epoch = self._epoch
            self._observe()

        slowed = False
        healthy = False
        start = monotonic()
        try:
            with self._tracer.start_as_current_span(
                "asr.request", record_exception=False, set_status_on_exception=False,
            ) as span:
                try:
                    response = send()
                except httpx.TransportError:
                    span.set_status(StatusCode.ERROR, "ASR_TRANSPORT_ERROR")
                    slowed = True
                    raise
                slowed = response.status_code == 429 or response.status_code >= 500
                healthy = response.is_success
                span.set_attribute("http.response.status_code", response.status_code)
                if response.is_error:
                    span.set_status(StatusCode.ERROR)
                return response
        finally:
            duration = monotonic() - start
            self._duration.record(duration)
            with self._condition:
                self._in_flight -= 1
                # A burst of completions admitted under one limit can trigger one cut.
                if epoch == self._epoch:
                    if slowed or duration > self._target:
                        self._limit = max(1, self._limit // 2)
                        self._epoch += 1
                        self._healthy = 0
                    elif healthy:
                        self._healthy += 1
                        if self._healthy >= max(4, self._limit):
                            self._limit = min(self._maximum, self._limit + 1)
                            self._healthy = 0
                self._observe()
                self._condition.notify_all()

    def _observe(self) -> None:
        self._limit_metric.set(self._limit)
        self._in_flight_metric.set(self._in_flight)
        self._pending_metric.set(self._pending)
