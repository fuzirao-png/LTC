"""Structured log formatters for the Worker Runtime.

Mirrors the API observability formatters but shares nothing via import.
The worker is a separate deployment unit so it bundles its own copy.

Trace-ID propagation
--------------------
The ``worker_trace_id`` contextvar is set by ``WorkerRuntime`` from
``job.payload["_trace_id"]`` before each handler invocation.  Every log
record emitted during the job execution automatically inherits the
trace-id — no explicit ``extra=`` passing needed in handler code.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

worker_trace_id: ContextVar[str] = ContextVar("worker_trace_id", default="")

_LOG_RECORD_DEFAULT_KEYS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
    }
)


def get_worker_trace_id() -> str:
    """Return the current trace-id for the executing job, or ``""``."""
    return worker_trace_id.get()


def set_worker_trace_id(tid: str) -> None:
    """Set or clear the per-job trace-id."""
    worker_trace_id.set(tid)


def _default_json_serializer(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return repr(obj)


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line with automatic trace-id."""

    def __init__(self, *args: object, service_name: str = "ltc-worker", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        tid = worker_trace_id.get()
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "trace_id": tid,
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info is not None and record.exc_info is not True:
            info = record.exc_info
            if isinstance(info, tuple) and len(info) >= 2 and info[1] is not None:
                payload["exception"] = str(info[1])
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _LOG_RECORD_DEFAULT_KEYS and value is not None
        }
        if extras:
            payload["extra"] = extras
        return json.dumps(payload, default=_default_json_serializer)


class HumanFormatter(logging.Formatter):
    """Coloured human-readable output for local development."""

    _COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def __init__(self, *args: object, service_name: str = "ltc-worker", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLORS.get(record.levelname, "")
        tid = worker_trace_id.get()
        tid_short = tid[:8] if tid else "--------"
        msg = super().format(record)
        return f"{colour}{record.levelname:<8}{self._RESET} [{self.service_name}][{tid_short}] {record.name}: {msg}"
