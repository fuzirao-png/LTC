"""Audit event — pure domain value object for business audit trails."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class AuditEvent:
    """An immutable record of a business-significant action.

    Design constraints:
    - Framework-free — importable from any layer.
    - ``actor_user_id`` is None for system-initiated actions.
    - ``occurred_at`` defaults to now but can be injected for event replay.
    """

    action: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Timestamps — set by infrastructure, not by callers
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def with_occurred_at(self, value: datetime) -> AuditEvent:
        """Return a copy with a different occurred_at (useful for replay)."""
        from dataclasses import replace

        return replace(self, occurred_at=value)
