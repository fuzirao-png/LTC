"""Telemetry event value objects — AI, Tool, and Lifecycle events for v3.3 instrumentation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# AI Event
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AiEvent:
    """One row per LLM/Agent invocation. Immutable; persisted via TelemetryWriter."""

    agent_name: str
    model: str
    input_token: int = 0
    output_token: int = 0
    response_time_ms: int = 0
    retry_count: int = 0
    cost: float = 0.0
    success: bool = True
    triggered_by: str = "system"
    prompt_version: str | None = None
    confidence: float | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    company_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    event_metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Tool Event
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ToolEvent:
    """One row per external API / provider call."""

    tool_name: str
    provider: str
    duration_ms: int = 0
    retry: int = 0
    cost: float = 0.0
    cache_hit: bool = False
    api: str | None = None
    request_id: str | None = None
    response_code: int | None = None
    company_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    error_code: str | None = None
    event_metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Lead Lifecycle Event
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LifecycleEvent:
    """One row per lead lifecycle state transition (EVT-01 through EVT-25)."""

    event_code: str
    triggered_by: str = "system"
    lead_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    from_state: str | None = None
    to_state: str | None = None
    job_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
