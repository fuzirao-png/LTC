"""Event emitter — convenience API for recording telemetry events.

Usage (from any adapter / service)::

    emitter = EventEmitter(writer)
    emitter.ai_call(
        agent_name="CustomerAnalysisAgent",
        model="gpt-5.6-terra",
        input_token=1500,
        output_token=800,
        response_time_ms=3200,
        cost=0.015,
        company_id=company_id,
    )
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..domain.telemetry_events import AiEvent, LifecycleEvent, ToolEvent
from ..infrastructure.telemetry_writer import TelemetryWriter


class EventEmitter:
    """Thin facade over TelemetryWriter with ergonomic keyword-argument helpers."""

    __slots__ = ("_writer",)

    def __init__(self, writer: TelemetryWriter) -> None:
        self._writer = writer

    # -- AI events ----------------------------------------------------------

    def ai_call(
        self,
        *,
        agent_name: str,
        model: str,
        input_token: int = 0,
        output_token: int = 0,
        response_time_ms: int = 0,
        retry_count: int = 0,
        cost: float = 0.0,
        success: bool = True,
        triggered_by: str = "system",
        prompt_version: str | None = None,
        confidence: float | None = None,
        input_hash: str | None = None,
        output_hash: str | None = None,
        company_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._writer.write_ai_event(
                AiEvent(
                    agent_name=agent_name,
                    model=model,
                    input_token=input_token,
                    output_token=output_token,
                    response_time_ms=response_time_ms,
                    retry_count=retry_count,
                    cost=cost,
                    success=success,
                    triggered_by=triggered_by,
                    prompt_version=prompt_version,
                    confidence=confidence,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    company_id=company_id,
                    lead_id=lead_id,
                    job_id=job_id,
                    event_metadata=metadata or {},
                )
            )
        except Exception:
            pass  # telemetry is best-effort; never fail the caller

    # -- Tool events --------------------------------------------------------

    def tool_call(
        self,
        *,
        tool_name: str,
        provider: str,
        duration_ms: int = 0,
        retry: int = 0,
        cost: float = 0.0,
        cache_hit: bool = False,
        api: str | None = None,
        request_id: str | None = None,
        response_code: int | None = None,
        company_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._writer.write_tool_event(
                ToolEvent(
                    tool_name=tool_name,
                    provider=provider,
                    duration_ms=duration_ms,
                    retry=retry,
                    cost=cost,
                    cache_hit=cache_hit,
                    api=api,
                    request_id=request_id,
                    response_code=response_code,
                    company_id=company_id,
                    job_id=job_id,
                    error_code=error_code,
                    event_metadata=metadata or {},
                )
            )
        except Exception:
            pass

    # -- Lifecycle events ---------------------------------------------------

    def lifecycle(
        self,
        *,
        event_code: str,
        triggered_by: str = "system",
        lead_id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
        job_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._writer.write_lifecycle_event(
                LifecycleEvent(
                    event_code=event_code,
                    triggered_by=triggered_by,
                    lead_id=lead_id,
                    company_id=company_id,
                    from_state=from_state,
                    to_state=to_state,
                    job_id=job_id,
                    actor_user_id=actor_user_id,
                    event_payload=payload or {},
                )
            )
        except Exception:
            pass
