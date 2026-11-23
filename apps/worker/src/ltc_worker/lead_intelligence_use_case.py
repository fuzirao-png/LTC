"""Worker-side composition seam for the lead-intelligence pipeline.

The runtime only knows this small execution protocol. Deployment code injects
the concrete API module pipeline, keeping handlers free of FastAPI and DB code.
"""

from __future__ import annotations

from typing import Any, Protocol


class LeadPipeline(Protocol):
    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None: ...


class LeadSearchPipelineUseCase:
    def __init__(self, pipeline: LeadPipeline) -> None:
        self.pipeline = pipeline

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        await self.pipeline.execute(job_id=job_id, lock_token=lock_token, payload=payload)
