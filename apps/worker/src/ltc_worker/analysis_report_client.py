"""Authenticated callback from the Research Worker to Customer Analysis."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx


class AnalysisReportClient:
    """Ask the API to generate a report after research evidence is committed."""

    def __init__(
        self,
        *,
        base_url: str,
        worker_token: str,
        timeout_seconds: float = 600.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._worker_token = worker_token
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def execute_researched_analysis(self, *, run_id: UUID) -> None:
        if not self._base_url or not self._worker_token:
            raise RuntimeError("analysis report callback is not configured")
        response = await self._client.post(
            f"{self._base_url}/internal/analysis-runs/{run_id}:execute",
            headers={"X-Worker-Token": self._worker_token},
        )
        response.raise_for_status()
        payload: Any = response.json()
        status = str((payload.get("data") or {}).get("status") or "")
        if status != "completed":
            raise RuntimeError(f"analysis report callback returned status={status or 'unknown'}")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
