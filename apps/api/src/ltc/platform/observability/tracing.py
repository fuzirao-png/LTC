"""OpenTelemetry wiring shared by the API and the job worker."""

import os
from socket import gethostname

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

trace_context = TraceContextTextMapPropagator()


def _resource(service_name: str) -> Resource:
    return Resource.create({"service.name": service_name, "service.instance.id": f"{gethostname()}-{os.getpid()}"})


def create_trace_provider(service_name: str) -> TracerProvider | None:
    if not (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")):
        return None
    provider = TracerProvider(
        resource=_resource(service_name),
        sampler=ALWAYS_ON,
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def create_meter_provider(service_name: str) -> MeterProvider | None:
    if not (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")):
        return None
    return MeterProvider(
        resource=_resource(service_name),
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
