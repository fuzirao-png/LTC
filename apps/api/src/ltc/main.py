"""FastAPI entrypoint for the LTC modular monolith skeleton."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ltc.modules.customer_operation.application.inbound_mail_service import (
    ImapInboundMailClient,
    InboundMailPoller,
    InboundMailProcessor,
)
from ltc.modules.customer_operation.application.service import set_analysis_trigger
from ltc.modules.customer_operation.application.email_delivery_service import send_email_for_payload
from ltc.modules.customer_operation.application.email_agent import run_email_agent_for_payload
from ltc.modules.lead_intelligence.agents.email_outreach_agent.agent import run_email_automation_agent
from ltc.modules.lead_intelligence.agents.email_outreach_agent.scheduler import EmailAutomationScheduler
from ltc.modules.lead_intelligence.infrastructure.email_automation_store import EmailAutomationStore
from ltc.modules.customer_operation.infrastructure.bootstrap import build_operation_service
from ltc.modules.customer_operation.infrastructure.mailbox_monitor_store import (
    PostgresMailboxSyncStore,
    list_enabled_mailbox_monitors,
)
from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router

from ltc.modules.customer_analysis.domain.errors import (
    CustomerAnalysisError,
    InvalidDimensionError,
    InvalidStateError,
    ResourceNotFoundError,
    VersionConflictError,
)
from ltc.modules.customer_analysis.infrastructure import CustomerAnalysisContainer, build_local_container
from ltc.modules.customer_analysis.infrastructure.bootstrap import postgres_connection_factory
from ltc.modules.customer_analysis.interfaces import build_customer_analysis_router

# ── IAM ──
from ltc.modules.iam.interfaces.router import router as iam_router
from ltc.modules.iam.application.auth_service import AuthenticationService
from ltc.modules.iam.application.account_service import AccountManagementService
from ltc.modules.iam.infrastructure.passwords import Argon2PasswordVerifier
from ltc.modules.iam.infrastructure.postgres_repository import PostgresIamUnitOfWork

# ── Sales CRM ──
from ltc.modules.sales_crm.infrastructure.departure_repository import PostgresSalesDeparturePort
from ltc.modules.sales_crm.infrastructure.pool_repository import PostgresSalesPoolRepository
from ltc.modules.sales_crm.application.pool_service import SalesPoolService
from ltc.modules.sales_crm.application.lead_service import SalesLeadService
from ltc.modules.sales_crm.application.contact_roster_service import ContactRosterService
from ltc.modules.sales_crm.interfaces.router import router as sales_crm_router

# ── Meeting Analysis ──
from ltc.modules.meeting_analysis.application.meeting_service import MeetingService
from ltc.modules.meeting_analysis.infrastructure import (
    AsrAdapter,
    PostgresMeetingUnitOfWork,
    SummaryAdapter,
    extract_audio_from_video,
    normalize_audio,
    probe_duration,
    split_audio,
)
from ltc.modules.meeting_analysis.interfaces.router import router as meeting_analysis_router

# ── Audio processor adapter ──
class _AudioProcessorAdapter:
    """Implements AudioProcessorPort by delegating to ffmpeg utility functions."""
    def extract_audio_from_video(self, video_path: str, target_dir: str) -> str:
        return extract_audio_from_video(video_path, target_dir)
    def normalize_audio(self, source_path: str, target_dir: str) -> str:
        return normalize_audio(source_path, target_dir)
    def split_audio(self, source_path: str, target_dir: str, chunk_seconds: int) -> list[str]:
        return split_audio(source_path, target_dir, chunk_seconds)
    def probe_duration(self, source_path: str) -> float:
        return probe_duration(source_path)

# ── Platform ──
from ltc.modules.registry import MODULE_DEFINITIONS, MODULE_NAMES
from ltc.platform.config import AppSettings, get_settings
from ltc.platform.db import DatabaseUnavailableError, PostgresDatabase
from ltc.platform.observability import configure_logging, ObservabilityMiddleware
from ltc.platform.observability.tracing import create_trace_provider
from ltc.platform.first_page_cache import FirstPageCache
from ltc.platform.knowledge import KnowledgeService, WeKnoraClient


class LiveHealthResponse(BaseModel):
    status: str
    environment: str
    modules: tuple[str, ...]


class MeResponse(BaseModel):
    display_name: str
    account_type: str


def create_app(
    settings: AppSettings | None = None,
    database: PostgresDatabase | None = None,
    customer_analysis: CustomerAnalysisContainer | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    app = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        openapi_url=f"{runtime_settings.api_prefix}/openapi.json",
        docs_url=f"{runtime_settings.api_prefix}/docs",
        redoc_url=None,
    )

    app.state.settings = runtime_settings
    app.state.first_page_cache = FirstPageCache(runtime_settings.redis_url)
    app.state.module_definitions = MODULE_DEFINITIONS

    # -- Observability: structured logging + trace-id middleware --
    _wire_observability(app, runtime_settings)

    # -- Database --
    app.state.database = database or PostgresDatabase(runtime_settings)
    app.state.email_automation_scheduler = None

    # -- IAM: authentication, account management, departure --
    app.state.iam_authentication_service = AuthenticationService(
        unit_of_work=PostgresIamUnitOfWork(app.state.database),
        password_verifier=Argon2PasswordVerifier(),
    )
    app.state.iam_account_management_service = AccountManagementService(
        unit_of_work=PostgresIamUnitOfWork(app.state.database),
        password_hasher=Argon2PasswordVerifier(),
    )
    app.state.sales_departure_port = PostgresSalesDeparturePort()
    app.state.sales_pool_service = SalesPoolService(app.state.database, PostgresSalesPoolRepository())
    app.state.sales_lead_service = SalesLeadService(app.state.database)
    app.state.contact_roster_service = ContactRosterService(app.state.database)
    app.state.knowledge_service = KnowledgeService(
        client=(
            WeKnoraClient(
                base_url=runtime_settings.weknora_base_url,
                api_key=runtime_settings.weknora_api_key,
                timeout_seconds=runtime_settings.weknora_timeout_seconds,
            )
            if runtime_settings.weknora_base_url and runtime_settings.weknora_api_key
            else None
        ),
        default_knowledge_base_ids=runtime_settings.weknora_knowledge_base_ids,
    )

    # -- Meeting Analysis: upload, transcription, summarization --
    app.state.meeting_uow = PostgresMeetingUnitOfWork(app.state.database)
    app.state.meeting_service = MeetingService(
        audio_processor=_AudioProcessorAdapter(),
        asr_service=AsrAdapter.from_settings(runtime_settings),
        summary_service=SummaryAdapter.from_settings(runtime_settings),
    )

    # -- Customer Analysis: DI container + router --
    customer_analysis = customer_analysis or build_local_container(
        llm_base_url=runtime_settings.llm_base_url or None,
        llm_api_key=runtime_settings.llm_api_key if runtime_settings.llm_api_key else None,
        llm_model_name=runtime_settings.llm_model or None,
        connection_factory=postgres_connection_factory(runtime_settings),
    )
    app.state.customer_analysis = customer_analysis
    app.state.sales_lead_service.set_analysis_trigger(customer_analysis.service)

    # -- Customer Analysis global error handler --
    @app.exception_handler(CustomerAnalysisError)
    async def customer_analysis_error_handler(
        request: Request, exc: CustomerAnalysisError
    ) -> JSONResponse:
        del request
        if isinstance(exc, ResourceNotFoundError):
            status_code, code = 404, "RESOURCE_NOT_FOUND"
        elif isinstance(exc, (VersionConflictError, InvalidStateError)):
            status_code, code = 409, "VERSION_CONFLICT"
        elif isinstance(exc, InvalidDimensionError):
            status_code, code = 422, "INVALID_COMMAND"
        else:
            status_code, code = 400, "INVALID_COMMAND"
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": {
                    "request_id": "req_legacy",
                    "error": {"code": code, "message": str(exc), "details": None},
                }
            },
        )

    # ── Include module routers ──
    app.include_router(iam_router, prefix=runtime_settings.api_prefix)
    app.include_router(sales_crm_router, prefix=runtime_settings.api_prefix)

    from ltc.modules.sales_crm.interfaces.company_router import router as company_router
    app.include_router(company_router, prefix=runtime_settings.api_prefix)

    from ltc.modules.lead_intelligence.interfaces.router import router as lead_intelligence_router
    app.include_router(lead_intelligence_router, prefix=runtime_settings.api_prefix)

    from ltc.modules.lead_intelligence.interfaces.enrichment_router import router as enrichment_router
    app.include_router(enrichment_router, prefix=runtime_settings.api_prefix)

    from ltc.modules.lead_intelligence.interfaces.sse_router import router as sse_router
    app.include_router(sse_router, prefix=runtime_settings.api_prefix)

    from ltc.modules.read_models.interfaces.knowledge_router import router as knowledge_router
    app.include_router(knowledge_router, prefix=runtime_settings.api_prefix)

    module_router = build_customer_analysis_router(customer_analysis.service)
    app.include_router(module_router, prefix=runtime_settings.api_prefix)

    app.include_router(meeting_analysis_router, prefix=runtime_settings.api_prefix)

    app.include_router(
        build_customer_operation_router(build_operation_service()),
        prefix=runtime_settings.api_prefix,
        tags=["customer_operation"],
    )

    # Wire analysis trigger for customer operation → analysis (PRD §5.1)
    set_analysis_trigger(customer_analysis.service)

    # ── Health endpoints ──
    @app.get("/health/live", response_model=LiveHealthResponse, tags=["system"])
    def live_health() -> LiveHealthResponse:
        return LiveHealthResponse(
            status="ok",
            environment=runtime_settings.environment,
            modules=MODULE_NAMES,
        )

    @app.get(f"{runtime_settings.api_prefix}/auth/me", response_model=dict, tags=["iam"])
    def auth_me() -> dict:
        return {"data": MeResponse(display_name="LTC Operator", account_type="sales").model_dump()}

    @app.on_event("startup")
    async def on_startup() -> None:
        app.state.database.open()
        automation_store = EmailAutomationStore()
        app.state.email_automation_scheduler = EmailAutomationScheduler(
            load_config=automation_store.load_config,
            run_once=lambda config: run_email_automation_agent(
                config=config,
                store=automation_store,
                email_agent=run_email_agent_for_payload,
                sender=send_email_for_payload,
            ),
        )
        await app.state.email_automation_scheduler.start()
        if not runtime_settings.inbound_mail_enabled:
            return
        pollers = _build_inbound_mail_pollers(runtime_settings)
        if not pollers:
            print("[inbound-mail] disabled: no configured mailbox monitors")
            return
        app.state.inbound_mail_pollers = pollers
        if len(pollers) == 1:
            app.state.inbound_mail_poller = pollers[0]
        for poller in pollers:
            await poller.start()
        print(f"[inbound-mail] polling started for {len(pollers)} mailbox monitor(s)")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        app.state.first_page_cache.close()
        if app.state.tracer_provider is not None:
            import asyncio

            await asyncio.to_thread(app.state.tracer_provider.shutdown)
        scheduler = getattr(app.state, "email_automation_scheduler", None)
        if scheduler is not None:
            await scheduler.stop()
        pollers = getattr(app.state, "inbound_mail_pollers", None)
        if pollers is not None:
            for poller in pollers:
                await poller.stop()
            return
        poller = getattr(app.state, "inbound_mail_poller", None)
        if poller is not None:
            await poller.stop()

    return app


def _wire_observability(app: FastAPI, settings: AppSettings) -> None:
    configure_logging(service_name=settings.app_name.lower().replace(" ", "-"))
    app.add_middleware(ObservabilityMiddleware)
    app.state.tracer_provider = create_trace_provider("ltc-api")
    if app.state.tracer_provider is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=app.state.tracer_provider, exclude_spans=["receive", "send"],
            excluded_urls="health/live,health/ready",
        )


def _build_inbound_mail_pollers(settings: AppSettings) -> list[InboundMailPoller]:
    monitors = list_enabled_mailbox_monitors(include_secret=True)

    pollers: list[InboundMailPoller] = []
    sync_store = PostgresMailboxSyncStore()
    for monitor in monitors:
        password = str(monitor.get("secretValue") or "").strip()
        if not password:
            env_name = str(monitor.get("secretEnvVar") or "").strip()
            password = os.getenv(env_name, "") if env_name else ""
        if not password:
            secret_label = str(monitor.get("secretEnvVar") or "secret_value").strip()
            print(f"[inbound-mail] skipped monitor {monitor.get('username')} because {secret_label} is not set")
            continue
        pollers.append(
            InboundMailPoller(
                client=ImapInboundMailClient(
                    host=str(monitor.get("host") or ""),
                    port=int(monitor.get("port") or 993),
                    username=str(monitor.get("username") or ""),
                    password=password,
                    mailbox=str(monitor.get("mailboxName") or "INBOX"),
                ),
                processor=InboundMailProcessor(
                    sales_user_id=str(monitor.get("salesUserId") or ""),
                ),
                interval_seconds=int(monitor.get("pollSeconds") or settings.inbound_mail_poll_seconds),
                mailbox_monitor_id=str(monitor.get("mailboxMonitorId") or ""),
                uid_validity=(
                    int(monitor["imapUidValidity"])
                    if monitor.get("imapUidValidity") is not None
                    else None
                ),
                last_processed_uid=(
                    int(monitor["lastProcessedUid"])
                    if monitor.get("lastProcessedUid") is not None
                    else None
                ),
                sync_store=sync_store,
            )
        )
    return pollers


app = create_app()
