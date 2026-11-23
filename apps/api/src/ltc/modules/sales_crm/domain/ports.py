"""Ports for Sales CRM queries."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class SalesPoolQuery(Protocol):
    def list_claimable_for_sales(
        self,
        connection: object,
        user_id: UUID,
        region_code: str,
        sales_tier: str,
        cursor: UUID | None,
        limit: int,
    ) -> list[dict[str, object]]: ...
