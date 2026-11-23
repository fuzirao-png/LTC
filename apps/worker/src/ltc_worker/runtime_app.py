"""Composition root for the versioned Worker runtime."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import asyncpg
from opentelemetry.metrics import get_meter, set_meter_provider
from opentelemetry.trace import get_tracer

from ltc.modules.meeting_analysis.infrastructure import AsrAdapter, SummaryAdapter
from ltc.platform.config import get_settings
from ltc.platform.observability.tracing import create_meter_provider, create_trace_provider

from .application import JobExecutionUseCase
from .crm_services import (
    CrmAutoReleaseService,
    CrmAutoReleaseUseCase,
    CrmOutboxConsumer,
    CrmOutboxUseCase,
    CrmWorkerDatabase,
)
from .infrastructure.job_repository import PostgreSQLJobRepository
from .analysis_research_customer import ResearchCustomerUseCase
from .analysis_report_client import AnalysisReportClient
from .customer_analysis_research import ResearchWorker, WeKnoraRestAdapter
from .gpt_researcher_adapter import (
    ExaResearchProvider,
    GPTResearcherAdapter,
    RealGPTResearchProvider,
    configure_gpt_researcher_environment,
)
from .research_store import PostgresResearchStore
from .adaptive_asr import AdaptiveAsr
from .media_job import MediaJobRunner
from .meeting_workflow import MeetingWorkflow


class _NotReadyUseCase:
    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        del lock_token, payload
        raise RuntimeError(f"job type is not wired in this Worker build: {job_id}")


class WorkerApplication:
    """Runtime services with CRM automation wired into the common job port."""

    def __init__(self, database: CrmWorkerDatabase, dsn: str) -> None:
        self._database = database
        self.jobs = PostgreSQLJobRepository(lambda: asyncpg.connect(dsn=dsn))
        self.crm_pipeline_consumer: JobExecutionUseCase = CrmOutboxUseCase(CrmOutboxConsumer(database))
        self.auto_release_overdue: JobExecutionUseCase = CrmAutoReleaseUseCase(CrmAutoReleaseService(database))

        # These remain explicit placeholders until their owning modules provide
        # Worker use cases; CRM wiring must not replace them.
        placeholder = _NotReadyUseCase()
        self.lead_search_pipeline = placeholder
        self.refresh_candidate = placeholder
        self.generate_analysis_report = placeholder
        knowledge_base_ids = [
            value.strip()
            for value in os.getenv("WEKNORA_KNOWLEDGE_BASE_IDS", "").split(",")
            if value.strip()
        ]
        weknora_base_url = os.getenv("WEKNORA_BASE_URL", "").strip()
        weknora_api_key = os.getenv("WEKNORA_API_KEY", "").strip()
        exa_api_key = os.getenv("EXA_API_KEY", "").strip()
        llm_api_key = (
            os.getenv("LTC_LLM_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        llm_base_url = (
            os.getenv("LTC_LLM_BASE_URL", "").strip()
            or os.getenv("OPENAI_BASE_URL", "").strip()
        )
        llm_model = (
            os.getenv("LTC_LLM_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
        )
        knowledge_factory = None
        if weknora_base_url and weknora_api_key and knowledge_base_ids:
            knowledge_factory = lambda: WeKnoraRestAdapter(
                base_url=weknora_base_url,
                api_key=weknora_api_key,
                allowed_knowledge_base_ids=set(knowledge_base_ids),
            )
        exa_factory = None
        if exa_api_key:
            direct_exa = ExaResearchProvider(api_key=exa_api_key)
            if llm_api_key and llm_base_url and llm_model:
                configure_gpt_researcher_environment(
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                    model_name=llm_model,
                )
                exa_factory = lambda: GPTResearcherAdapter(
                    RealGPTResearchProvider(),
                    fallback=direct_exa,
                    timeout_seconds=float(os.getenv("GPT_RESEARCHER_TIMEOUT_SECONDS", "30")),
                ).research
            else:
                exa_factory = lambda: GPTResearcherAdapter(direct_exa).research
        store = PostgresResearchStore(database)
        self._analysis_report_client = AnalysisReportClient(
            base_url=os.getenv("LTC_API_INTERNAL_URL", "http://api:8000/api/v1"),
            worker_token=os.getenv("LTC_INTERNAL_WORKER_TOKEN", ""),
            timeout_seconds=float(os.getenv("LTC_ANALYSIS_REPORT_TIMEOUT_SECONDS", "600")),
        )
        self.research_customer = ResearchCustomerUseCase(
            worker=ResearchWorker(
                knowledge_retriever_factory=knowledge_factory,
                exa_search_factory=exa_factory,
            ),
            context_loader=store,
            result_writer=store,
            report_executor=self._analysis_report_client,
            default_knowledge_base_ids=knowledge_base_ids,
        )
        self.generate_email_draft = placeholder
        self.send_email = placeholder
        self.reconcile_email = placeholder
        settings = get_settings()
        self._tracer_provider = create_trace_provider("ltc-worker")
        self._meter_provider = create_meter_provider("ltc-worker")
        if self._meter_provider:
            set_meter_provider(self._meter_provider)
        tracer = get_tracer("ltc.media", tracer_provider=self._tracer_provider)
        maximum = settings.asr_max_parallel_requests
        gate = AdaptiveAsr(maximum, settings.asr_target_latency_seconds, tracer)
        self.process_meeting = MediaJobRunner(
            self.jobs,
            MeetingWorkflow(
                database, AsrAdapter.from_settings(settings, request_gate=gate.request),
                SummaryAdapter.from_settings(settings), tracer, model=settings.asr_model,
                chunk_seconds=settings.audio_chunk_seconds, parallel=maximum,
            ),
            tracer,
        )
        self._media_pending = get_meter("ltc.media").create_gauge("media_queue_pending")
        self.media_job_concurrency = settings.media_job_concurrency
        self.dispatch_outbox = placeholder
        self.process_external_event = placeholder
        self.send_notification = placeholder
        self.extract_manual_note = placeholder
        self.complete_scale_data = placeholder
        self.complete_region_data = placeholder

    def ensure_crm_jobs(self) -> None:
        """Materialize pending Outbox rows and the hourly CRM scan as Jobs."""
        with self._database.transaction() as connection:
            connection.execute(
                """UPDATE ltc.job
                      SET queue_name='crm', updated_at=clock_timestamp(), version=version+1
                    WHERE job_type IN ('crm.pipeline_consumer.v1', 'crm.auto_release_overdue.v1')
                      AND queue_name <> 'crm'
                      AND status IN ('queued','retry_wait')"""
            )
            connection.execute(
                """INSERT INTO ltc.job
                   (job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload, max_attempts)
                   SELECT 'crm.pipeline_consumer.v1', 'crm', 'outbox_event',
                          event_id, 'crm-outbox-event:' || event_id::text, 'queued',
                          jsonb_build_object('event_id', event_id), 5
                     FROM ltc.outbox_event event
                    WHERE event.status='pending'
                      AND event.event_type IN (
                          'engagement.email_sent.v1',
                          'engagement.email_opened.v1',
                          'engagement.email_clicked.v1',
                          'engagement.email_replied.v1',
                          'engagement.meeting_analyzed.v1',
                          'crm.dynamic_intent_bonus_applied.v1'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM ltc.job job
                           WHERE job.concurrency_key='crm-outbox-event:' || event.event_id::text
                             AND job.status IN ('queued','running','retry_wait','reconcile_required')
                      )
                   ON CONFLICT (concurrency_key)
                   WHERE concurrency_key IS NOT NULL
                     AND status IN ('queued','running','retry_wait','reconcile_required')
                   DO NOTHING"""
            )
            connection.execute(
                """INSERT INTO ltc.job
                   (job_type, queue_name, concurrency_key, status, payload, run_after, max_attempts)
                   SELECT 'crm.auto_release_overdue.v1', 'crm', 'crm:auto-release',
                          'queued', '{}'::jsonb, clock_timestamp(), 3
                    WHERE NOT EXISTS (
                        SELECT 1 FROM ltc.job
                         WHERE concurrency_key='crm:auto-release'
                           AND (
                               status IN ('queued','running','retry_wait','reconcile_required')
                               OR (status='succeeded' AND completed_at > clock_timestamp() - interval '1 hour')
                           )
                    )
                   ON CONFLICT (concurrency_key)
                   WHERE concurrency_key IS NOT NULL
                     AND status IN ('queued','running','retry_wait','reconcile_required')
                   DO NOTHING"""
            )

    async def close(self) -> None:
        self.process_meeting.close()
        await self._analysis_report_client.close()
        await asyncio.to_thread(self._database.close)
        if self._tracer_provider:
            await asyncio.to_thread(self._tracer_provider.shutdown)
        if self._meter_provider:
            await asyncio.to_thread(self._meter_provider.shutdown)

    async def recover_media_jobs(self) -> None:
        self._media_pending.set(await self.jobs.recover_media_jobs())


async def create_application() -> WorkerApplication:
    dsn = get_settings().database_dsn
    database = CrmWorkerDatabase(dsn)
    await asyncio.to_thread(database.open)
    return WorkerApplication(database, dsn)
