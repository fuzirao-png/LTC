"""Telemetry writer — persistence protocol + Postgres implementation for telemetry events.

Unlike outbox events (which go through the outbox pattern for cross-module delivery),
telemetry events are written directly via best-effort INSERT so that:
- A failed telemetry write never blocks the business transaction.
- Telemetry tables are append-only and have no FK constraints on business tables.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from ..domain.telemetry_events import AiEvent, LifecycleEvent, ToolEvent


def _jsonb(obj: dict[str, Any]) -> str:
    """Serialize a dict to a JSONB-compatible string for psycopg."""
    return json.dumps(obj, ensure_ascii=False, default=str)


class TelemetryWriter(Protocol):
    """Protocol for persisting telemetry events (AI, Tool, Lifecycle).

    Implementations must be safe to call from any layer (domain / application /
    infrastructure). A failed write must not raise — telemetry is best-effort.
    """

    def write_ai_event(self, event: AiEvent) -> None: ...

    def write_tool_event(self, event: ToolEvent) -> None: ...

    def write_lifecycle_event(self, event: LifecycleEvent) -> None: ...


class PostgresTelemetryWriter:
    """Best-effort telemetry writer backed by a psycopg connection pool."""

    def __init__(self, database: Any) -> None:
        self._db = database  # PostgresDatabase instance

    def write_ai_event(self, event: AiEvent) -> None:
        self._try_write(
            """INSERT INTO ltc.ai_event (
                   agent_name, prompt_version, model, input_token, output_token,
                   response_time_ms, confidence, retry_count, cost, success,
                   input_hash, output_hash, company_id, lead_id, triggered_by,
                   job_id, event_metadata, occurred_at
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                event.agent_name,
                event.prompt_version,
                event.model,
                event.input_token,
                event.output_token,
                event.response_time_ms,
                event.confidence,
                event.retry_count,
                event.cost,
                event.success,
                event.input_hash,
                event.output_hash,
                event.company_id,
                event.lead_id,
                event.triggered_by,
                event.job_id,
                _jsonb(event.event_metadata),
                event.occurred_at,
            ),
        )

    def write_tool_event(self, event: ToolEvent) -> None:
        self._try_write(
            """INSERT INTO ltc.tool_event (
                   tool_name, provider, api, request_id, response_code,
                   duration_ms, retry, cost, cache_hit, company_id,
                   job_id, error_code, event_metadata, occurred_at
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                event.tool_name,
                event.provider,
                event.api,
                event.request_id,
                event.response_code,
                event.duration_ms,
                event.retry,
                event.cost,
                event.cache_hit,
                event.company_id,
                event.job_id,
                event.error_code,
                _jsonb(event.event_metadata),
                event.occurred_at,
            ),
        )

    def write_lifecycle_event(self, event: LifecycleEvent) -> None:
        self._try_write(
            """INSERT INTO ltc.lead_lifecycle_event (
                   lead_id, company_id, event_code, from_state, to_state,
                   triggered_by, job_id, actor_user_id, event_payload, occurred_at
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                event.lead_id,
                event.company_id,
                event.event_code,
                event.from_state,
                event.to_state,
                event.triggered_by,
                event.job_id,
                event.actor_user_id,
                _jsonb(event.event_payload),
                event.occurred_at,
            ),
        )

    def _try_write(self, sql: str, params: tuple) -> None:
        try:
            with self._db._connection() as conn:  # type: ignore[union-attr]
                conn.execute(sql, params)
                conn.commit()
        except Exception:
            pass  # best-effort — never fail the caller


class InMemoryTelemetryWriter:
    """Collects telemetry events in memory — for tests only."""

    def __init__(self) -> None:
        self.ai_events: list[AiEvent] = []
        self.tool_events: list[ToolEvent] = []
        self.lifecycle_events: list[LifecycleEvent] = []

    def write_ai_event(self, event: AiEvent) -> None:
        self.ai_events.append(event)

    def write_tool_event(self, event: ToolEvent) -> None:
        self.tool_events.append(event)

    def write_lifecycle_event(self, event: LifecycleEvent) -> None:
        self.lifecycle_events.append(event)

    def clear(self) -> None:
        self.ai_events.clear()
        self.tool_events.clear()
        self.lifecycle_events.clear()
