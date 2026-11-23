"""Audit persistence — sync writer that stores records in ltc.audit_log."""

from __future__ import annotations

from typing import Any, Protocol

from ..domain.audit_event import AuditEvent


class AuditWriter(Protocol):
    """Protocol for persisting business audit events.

    Implementations:
    - PostgresIamUnitOfWork — writes audit records atomically within IAM transactions.
    - InMemoryAuditWriter — collects events in a list for testing.
    """

    async def record(self, event: AuditEvent) -> None:
        """Persist a single audit event.

        Must be called within an active database transaction so the
        audit record commits or rolls back atomically with the
        business write.
        """
        ...


class InMemoryAuditWriter:
    """Collects audit events in memory — for tests only."""

    def __init__(self) -> None:
        self.records: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.records.append(event)

    def clear(self) -> None:
        self.records.clear()

    def actions(self) -> list[str]:
        return [r.action for r in self.records]

    def for_resource(self, resource_type: str, resource_id: Any) -> list[AuditEvent]:
        rid = str(resource_id)
        return [r for r in self.records if r.resource_type == resource_type and str(r.resource_id) == rid]
