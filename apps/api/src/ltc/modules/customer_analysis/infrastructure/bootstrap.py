"""Composition helpers kept outside the domain and application layers."""
from __future__ import annotations
from dataclasses import dataclass
import os
from typing import Any, Callable
from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.infrastructure.adapters import InMemoryAnalysisContextPort, InMemoryCustomerAnalysisRepository, InlineAnalysisJobPort, OpenAICompatibleReportGenerator, QueuedAnalysisJobPort, TemplateReportGenerator
from ltc.modules.customer_analysis.infrastructure.demo_data import demo_contexts
from ltc.modules.customer_analysis.infrastructure.postgres_engagement_evidence import PostgresEngagementEvidenceReadPort
from ltc.modules.customer_analysis.infrastructure.postgres_context import PostgresAnalysisContextPort
from ltc.modules.customer_analysis.infrastructure.postgres_repository import PostgresCustomerAnalysisRepository
from ltc.platform.config import AppSettings

@dataclass(frozen=True)
class CustomerAnalysisContainer:
    service: CustomerAnalysisService
    repository: Any
    contexts: Any

def postgres_connection_factory(settings: AppSettings) -> Callable[[], Any]:
    def connect() -> Any:
        import psycopg

        return psycopg.connect(settings.database_dsn)

    return connect

def build_local_container(*, report_generator: object | None = None, seed_demo_data: bool = True, llm_base_url: str | None = None, llm_api_key: str | None = None, llm_model_name: str | None = None, repository: Any | None = None, connection_factory: Any | None = None) -> CustomerAnalysisContainer:
    if repository is None and connection_factory is None:
        connection_factory = _runtime_connection_factory()
    repository = repository or (PostgresCustomerAnalysisRepository(connection_factory) if connection_factory is not None else InMemoryCustomerAnalysisRepository())
    contexts = PostgresAnalysisContextPort(connection_factory) if connection_factory is not None else InMemoryAnalysisContextPort()
    engagement_evidence = PostgresEngagementEvidenceReadPort(connection_factory) if connection_factory is not None else None
    jobs = QueuedAnalysisJobPort(connection_factory) if connection_factory is not None else InlineAnalysisJobPort()
    if report_generator is None:
        llm_base_url = llm_base_url or os.getenv("LTC_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        llm_api_key = llm_api_key or os.getenv("LTC_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        llm_model_name = llm_model_name or os.getenv("LTC_LLM_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("FULL_REPORT_MODEL") or os.getenv("DEFAULT_OPENAI_MODEL") or "gpt-5.5-openai-compact"
        report_generator = OpenAICompatibleReportGenerator(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model_name=llm_model_name,
            timeout_seconds=float(
                os.getenv(
                    "LTC_ANALYSIS_REPORT_TIMEOUT_SECONDS",
                    os.getenv("LTC_ANALYSIS_LLM_TIMEOUT_SECONDS", "600"),
                )
            ),
            max_retries=int(os.getenv("LTC_ANALYSIS_LLM_MAX_RETRIES", "0")),
        ) if llm_base_url and llm_api_key and llm_model_name else TemplateReportGenerator()
    service = CustomerAnalysisService(
        repository=repository,
        context_port=contexts,
        report_generator=report_generator,
        job_port=jobs,
        # External research is owned by the Research Worker.  The application
        # service keeps an optional SearchPort seam for compatibility/tests,
        # but the API composition root never performs provider calls.
        search_port=None,
        engagement_evidence_port=engagement_evidence,
    )
    jobs.bind(service.execute_analysis)
    if seed_demo_data and isinstance(contexts, InMemoryAnalysisContextPort):
        for context in demo_contexts():
            contexts.put_context(context)
    return CustomerAnalysisContainer(service=service, repository=repository, contexts=contexts)

def _runtime_connection_factory() -> Any | None:
    host = os.getenv("LTC_DB_HOST")
    if not host:
        return None
    port = int(os.getenv("LTC_DB_PORT", "5432"))
    dbname = os.getenv("LTC_DB_NAME", "ltc")
    user = os.getenv("LTC_DB_USER", "ltc")
    password = os.getenv("LTC_DB_PASSWORD", "ltc_local_change_me")
    sslmode = os.getenv("LTC_DB_SSLMODE", "disable")
    try:
        import psycopg
    except ImportError:
        return None
    def connect() -> Any:
        return psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            sslmode=sslmode,
        )
    return connect
