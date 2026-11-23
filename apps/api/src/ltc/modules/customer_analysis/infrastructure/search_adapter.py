"""Adapts ltc.platform.search to the CustomerAnalysis.SearchPort protocol."""

from __future__ import annotations

from typing import Any

from ltc.platform.search import build_search_adapter


class PlatformSearchAdapter:
    """Delegates company-source search to the platform search layer.

    When EXA_API_KEY is set the adapter uses Exa; otherwise it falls
    back to DuckDuckGo.  The adapter is stateless — every call hits the
    live search API so results are always fresh.
    """

    def __init__(self) -> None:
        self._adapter = build_search_adapter()

    def search_company_sources(self, company_name: str) -> list[dict[str, Any]]:
        return self._adapter.search_company_sources(company_name)
