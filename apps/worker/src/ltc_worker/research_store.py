"""PostgreSQL context/result port for Customer Analysis research jobs."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row


class PostgresResearchStore:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def load_research_context(self, *, company_id: UUID, run_id: UUID) -> dict[str, Any]:
        return await asyncio.to_thread(self._load, company_id, run_id)

    def _load(self, company_id: UUID, run_id: UUID) -> dict[str, Any]:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT company_id, input_snapshot, trigger_context
                         FROM ltc.analysis_run
                        WHERE analysis_run_id=%s""",
                    (run_id,),
                )
                row = cursor.fetchone()
        if row is None or row["company_id"] != company_id:
            raise ValueError("analysis run does not belong to the requested company")
        snapshot = dict(row["input_snapshot"] or {})
        snapshot["research_policy"] = dict(row["trigger_context"] or {})
        return snapshot

    async def write_research_result(self, *, run_id: UUID, result: dict[str, Any]) -> None:
        await asyncio.to_thread(self._write, run_id, result)

    def _write(self, run_id: UUID, result: dict[str, Any]) -> None:
        evidence = list(result.get("evidence_refs") or [])
        metrics = dict(result.get("metrics") or {})
        conflicts = list(result.get("conflicts") or [])
        snapshot_ids = dict(result.get("snapshot_ids") or {})
        tool_trace = list(result.get("tool_trace") or [])
        with self.database.transaction() as connection:
            connection.execute(
                """UPDATE ltc.analysis_run
                      SET input_snapshot=jsonb_set(
                              input_snapshot,
                              '{evidence_refs}',
                              %s::jsonb,
                              true
                          ),
                          trigger_context=trigger_context || %s::jsonb,
                          version=version+1
                    WHERE analysis_run_id=%s""",
                (
                    json.dumps(evidence),
                    json.dumps(
                        {
                            "research_metrics": metrics,
                            "weknora_status": metrics.get("weknora_status", "not_configured"),
                            "exa_status": metrics.get("exa_status", "not_configured"),
                            "gpt_researcher_status": metrics.get(
                                "gpt_researcher_status", "not_configured"
                            ),
                            "research_scope": metrics.get("research_scope"),
                            "research_conflicts": conflicts,
                            "research_job_id": result.get("job_id"),
                            "research_tool_trace": tool_trace,
                            "weknora_snapshot_id": snapshot_ids.get("weknora"),
                            "exa_snapshot_id": snapshot_ids.get("exa"),
                        }
                    ),
                    run_id,
                ),
            )
