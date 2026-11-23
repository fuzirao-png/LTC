"""Structured JSON logging powered by Python stdlib logging.

Design:
- Each log record is a single JSON line with mandatory ``timestamp``,
  ``service``, ``trace_id``, ``logger``, ``level``, and ``message`` fields.
- The trace_id is auto-resolved from the observability contextvar at emit time.
- In local dev the formatter can be swapped to human-readable output
  by setting ``LTC_LOG_FORMAT=console``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


LOG_RECORD_DEFAULT_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }
)


def _default_json_serializer(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return repr(obj)


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line with standard fields."""

    def __init__(
        self,
        *args: object,
        service_name: str = "ltc-api",
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        from ..domain.trace_context import get_trace_id

        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "trace_id": get_trace_id(),
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
            if key not in LOG_RECORD_DEFAULT_KEYS
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

    def format(self, record: logging.LogRecord) -> str:
        from ..domain.trace_context import get_trace_id

        colour = self._COLORS.get(record.levelname, "")
        trace_id = get_trace_id()[:8]
        msg = super().format(record)
        return f"{colour}{record.levelname:<8}{self._RESET} [{trace_id}] {record.name}: {msg}"


def configure_logging(
    service_name: str = "ltc-api",
    log_level: str | None = None,
) -> None:
    """Wire up the root logger with structured output.

    Call once at application startup (main.py).
    """
    level_name = log_level or os.getenv("LTC_LOG_LEVEL", "INFO")
    format_mode = os.getenv("LTC_LOG_FORMAT", "json")

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level_name.upper(), logging.INFO))

    if format_mode == "console":
        handler.setFormatter(HumanFormatter("%(message)s"))
    else:
        handler.setFormatter(JSONFormatter(service_name=service_name))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(handler.level)
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "uvicorn.error", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name.

    Usage::

        logger = get_logger(__name__)
        logger.info("lead.assigned", extra={"lead_id": str(lead_id)})
    """
    return logging.getLogger(name)
