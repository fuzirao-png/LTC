"""FastAPI middleware: request trace-id injection and structured access logging.

Registers as a pure-ASGI middleware so it wraps every request.  Callers must
add it to the app inside ``create_app()``:

.. code-block:: python

    from ltc.platform.observability.interfaces.logging_middleware import ObservabilityMiddleware
    app.add_middleware(ObservabilityMiddleware)
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any, Awaitable, Callable

from opentelemetry.trace import get_current_span
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..domain.trace_context import get_trace_id, set_trace_id, set_request_path
from ..infrastructure.json_logger import get_logger

_logger = get_logger("ltc.api.http")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Per-request: resolve trace-id, log start/end, and attach the response header.

    Trace-id resolution order:
    1. ``X-Trace-Id`` request header (pass-through from upstream)
    2. ``X-Request-Id`` request header (common CDN/proxy convention)
    3. OpenTelemetry trace ID, when instrumentation is enabled
    4. Auto-generated UUID
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
        span = get_current_span().get_span_context()
        trace_id = incoming or (f"{span.trace_id:032x}" if span.is_valid else get_trace_id())
        set_trace_id(trace_id)
        set_request_path(request.url.path)

        _logger.debug(
            "request.started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": _client_ip(request),
            },
        )

        started_at = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            _logger.error(
                "request.failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(elapsed_ms, 3),
                    "status_code": HTTPStatus.INTERNAL_SERVER_ERROR,
                },
                exc_info=True,
            )
            raise

        elapsed_ms = (time.monotonic() - started_at) * 1000
        response.headers["X-Trace-Id"] = trace_id
        _logger.info(
            "request.completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(elapsed_ms, 3),
            },
        )
        return response


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client is not None:
        return getattr(client, "host", None)
    return None
