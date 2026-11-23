"""Versioned analysis research job contract and Worker use case."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from .customer_analysis_research import ResearchPolicyError, ResearchWorker


class ResearchResultWriter(Protocol):
    async def write_research_result(self, *, run_id: UUID, result: dict[str, Any]) -> None: ...


class ResearchContextLoader(Protocol):
    async def load_research_context(self, *, company_id: UUID, run_id: UUID) -> dict[str, Any]: ...


class AnalysisReportExecutor(Protocol):
    async def execute_researched_analysis(self, *, run_id: UUID) -> None: ...


class _NoopAnalysisReportExecutor:
    async def execute_researched_analysis(self, *, run_id: UUID) -> None:
        del run_id


class ResearchCustomerUseCase:
    """Execute one research run without exposing provider credentials in payloads."""

    def __init__(
        self,
        *,
        worker: ResearchWorker,
        context_loader: ResearchContextLoader,
        result_writer: ResearchResultWriter,
        report_executor: AnalysisReportExecutor | None = None,
        default_knowledge_base_ids: list[str] | None = None,
    ) -> None:
        self.worker = worker
        self.context_loader = context_loader
        self.result_writer = result_writer
        self.report_executor = report_executor or _NoopAnalysisReportExecutor()
        self.default_knowledge_base_ids = list(default_knowledge_base_ids or [])

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        del lock_token
        try:
            company_id = UUID(str(payload["company_id"]))
            run_id = UUID(str(payload["run_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ResearchPolicyError("analysis research payload requires company_id and run_id") from exc
        payload_mode = str(payload.get("research_mode") or "internal_only")
        payload_external_allowed = bool(payload.get("external_research_allowed"))
        context = await self.context_loader.load_research_context(company_id=company_id, run_id=run_id)
        research_policy = dict(context.get("research_policy") or {})
        mode = str(research_policy.get("research_mode") or payload_mode)
        external_research_allowed = (
            bool(research_policy.get("external_research_allowed"))
            if "external_research_allowed" in research_policy
            else payload_external_allowed
        )
        if not external_research_allowed:
            mode = "internal_only"
        elif mode != "initial_external":
            raise ResearchPolicyError(
                "external_research_allowed requires research_mode=initial_external"
            )
        if str(research_policy.get("research_job_id") or "") == job_id:
            await self.report_executor.execute_researched_analysis(run_id=run_id)
            return
        result = await self.worker.research(
            context=context,
            research_mode=mode,
            knowledge_base_ids=[
                str(value)
                for value in (payload.get("knowledge_base_ids") or self.default_knowledge_base_ids)
            ],
            top_k=int(payload.get("top_k", 8)),
        )
        result["job_id"] = job_id
        await self.result_writer.write_research_result(run_id=run_id, result=result)
        await self.report_executor.execute_researched_analysis(run_id=run_id)
