"""Observability platform — structured logging, tracing, and audit infrastructure.

Exports:
    get_logger: factory for module-scoped structured loggers.
    AuditEvent: domain value object for business audit records.
    TraceContext: contextvars-based request tracing.
    AuditWriter: protocol for audit log persistence.
    InMemoryAuditWriter: collects events in memory for tests.
    ObservabilityMiddleware: FastAPI request logging and trace-id injection.
"""

from __future__ import annotations

from .domain.audit_event import AuditEvent
from .domain.trace_context import TraceContext, get_trace_id, set_trace_id
from .infrastructure.audit_writer import AuditWriter, InMemoryAuditWriter
from .infrastructure.json_logger import configure_logging, get_logger
from .interfaces.logging_middleware import ObservabilityMiddleware

__all__ = [
    "AuditEvent",
    "AuditWriter",
    "InMemoryAuditWriter",
    "configure_logging",
    "get_logger",
    "get_trace_id",
    "ObservabilityMiddleware",
    "set_trace_id",
    "TraceContext",
]
