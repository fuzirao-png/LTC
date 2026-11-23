from __future__ import annotations

import unittest
from threading import Event
from time import monotonic
from uuid import uuid4

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.application.service import (
    _filter_company_sources,
    _is_reserved_domain,
)
from ltc.modules.customer_analysis.domain.ports import SearchPort
from ltc.platform.search import (
    DuckDuckGoSearchAdapter,
    ExaSearchAdapter,
    build_search_adapter,
)


class SearchAdapterUnitTests(unittest.TestCase):
    def test_reserved_test_domains_are_not_eligible_for_company_search(self) -> None:
        self.assertTrue(_is_reserved_domain("berlin-mobility.example.com"))

    def test_unrelated_company_sources_are_filtered_out(self) -> None:
        sources = [
            {"url": "https://group.mercedes-benz.com/berlin", "title": "Mercedes-Benz Mobility Services GmbH"},
            {"url": "https://berlin-mobility.com/about", "title": "Berlin Mobility Services"},
        ]
        self.assertEqual(
            [sources[1]],
            _filter_company_sources("Berlin Mobility Services", "berlin-mobility.com", sources),
        )

    def test_build_adapter_auto_returns_duckduckgo_when_no_exa_key(self) -> None:
        adapter = build_search_adapter("auto")
        self.assertIsInstance(adapter, DuckDuckGoSearchAdapter)

    def test_exa_adapter_has_correct_provider_name(self) -> None:
        adapter = ExaSearchAdapter(api_key="test-key")
        self.assertEqual("exa", adapter.provider_name)

    def test_duckduckgo_adapter_has_correct_provider_name(self) -> None:
        adapter = DuckDuckGoSearchAdapter()
        self.assertEqual("duckduckgo", adapter.provider_name)


class SearchServiceIntegrationTests(unittest.TestCase):
    def test_threaded_job_port_dispatches_without_waiting_for_handler(self) -> None:
        from ltc.modules.customer_analysis.infrastructure.adapters import ThreadedAnalysisJobPort

        started = Event()
        release = Event()
        jobs = ThreadedAnalysisJobPort()

        def handler(_run_id) -> None:
            started.set()
            release.wait(timeout=2)

        jobs.bind(handler)
        started_at = monotonic()
        jobs.dispatch(uuid4())
        elapsed = monotonic() - started_at

        self.assertTrue(started.wait(timeout=1))
        self.assertLess(elapsed, 0.5)
        release.set()

    def test_service_accepts_search_port(self) -> None:
        """verify the search port is optional and wired through __init__."""
        from ltc.modules.customer_analysis.infrastructure.adapters import (
            InMemoryCustomerAnalysisRepository,
            InMemoryAnalysisContextPort,
            InlineAnalysisJobPort,
            TemplateReportGenerator,
        )
        from ltc.modules.customer_analysis.infrastructure.search_adapter import (
            PlatformSearchAdapter,
        )

        service = CustomerAnalysisService(
            repository=InMemoryCustomerAnalysisRepository(),
            context_port=InMemoryAnalysisContextPort(),
            report_generator=TemplateReportGenerator(),
            job_port=InlineAnalysisJobPort(),
            search_port=PlatformSearchAdapter(),
        )
        self.assertIsNotNone(service.search_port)

    def test_service_works_without_search_port(self) -> None:
        """search_port is optional — analysis must still work."""
        from ltc.modules.customer_analysis.infrastructure.adapters import (
            InMemoryCustomerAnalysisRepository,
            InMemoryAnalysisContextPort,
            InlineAnalysisJobPort,
            TemplateReportGenerator,
        )

        service = CustomerAnalysisService(
            repository=InMemoryCustomerAnalysisRepository(),
            context_port=InMemoryAnalysisContextPort(),
            report_generator=TemplateReportGenerator(),
            job_port=InlineAnalysisJobPort(),
        )
        self.assertIsNone(service.search_port)


if __name__ == "__main__":
    unittest.main()
