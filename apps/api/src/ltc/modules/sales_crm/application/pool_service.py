"""Application service for the Sales CRM claimable pool."""

from __future__ import annotations

from uuid import UUID

from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.sales_crm.domain.ports import SalesPoolQuery


class SalesPoolService:
    def __init__(self, database: object, query: SalesPoolQuery) -> None:
        self._database = database
        self._query = query

    def list_for_actor(self, actor: CurrentActor, cursor: UUID | None, limit: int) -> list[dict[str, object]]:
        if actor.account_type != "sales" or actor.sales_tier is None or actor.region_code is None:
            raise PermissionError("SALES_POOL_REQUIRED")
        with self._database.transaction() as connection:
            return self._query.list_claimable_for_sales(
                connection=connection,
                user_id=actor.user_id,
                region_code=actor.region_code,
                sales_tier=actor.sales_tier,
                lead_cursor=cursor,
                limit=limit,
            )
