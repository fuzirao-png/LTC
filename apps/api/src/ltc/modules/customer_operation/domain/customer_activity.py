"""CustomerActivity — domain model for customer-facing interaction events.

Owned by the customer_operation module (see ``ltc.customer_activity`` table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class CustomerActivity:
    """A customer interaction event — call, email, demo, note, or system action.

    Design:
    - Pure value object with no framework dependencies.
    - ``occurred_at`` is required; callers must supply the real-world timestamp.
    - ``source_type`` defaults to ``"system"`` for automated events.
    """

    activity_id: uuid.UUID = field(default_factory=uuid.uuid4)
    company_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    assignment_id: uuid.UUID | None = None
    activity_type: str = "system"
    direction: str | None = None
    subject: str | None = None
    body: str | None = None
    outcome_code: str | None = None
    actor_user_id: uuid.UUID | None = None
    source_type: str = "system"
    source_job_id: uuid.UUID | None = None
    source_external_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    # Set by infrastructure layer
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_manual(self) -> bool:
        return self.source_type == "manual"

    def is_outbound(self) -> bool:
        return self.direction == "outbound"
