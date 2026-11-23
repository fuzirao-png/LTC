"""Request trace identity via contextvars — framework-free, importable from any layer."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("observability_trace_id", default="")
_request_path: ContextVar[str] = ContextVar("observability_request_path", default="")


def get_trace_id() -> str:
    """Return the current request trace-id, generating one if absent."""
    value = _trace_id.get()
    if not value:
        value = str(uuid.uuid4())
        _trace_id.set(value)
    return value


def set_trace_id(trace_id: str) -> None:
    """Set an explicit trace-id (e.g. from an incoming request header)."""
    _trace_id.set(trace_id)


def get_request_path() -> str:
    return _request_path.get()


def set_request_path(path: str) -> None:
    _request_path.set(path)


class TraceContext:
    """Namespaced holder for trace context variables.

    Exists so tests can reset state without reaching into module internals.
    """

    @staticmethod
    def current_trace_id() -> str:
        return get_trace_id()

    @staticmethod
    def reset() -> None:
        _trace_id.set("")
        _request_path.set("")
