from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DepartSalesRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReturnedPool(BaseModel):
    region_code: str
    sales_tier: str
    count: int


class DepartSalesResponseData(BaseModel):
    user_id: UUID
    status: Literal["departed"]
    released_lead_count: int
    returned_pools: list[ReturnedPool]
    departed_at: datetime
    handover_lead_count: int = 0


class DepartSalesResponse(BaseModel):
    request_id: UUID
    data: DepartSalesResponseData
