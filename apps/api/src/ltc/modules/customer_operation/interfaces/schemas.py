from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CustomerOperationResponse(BaseModel):
    data: dict[str, Any]
