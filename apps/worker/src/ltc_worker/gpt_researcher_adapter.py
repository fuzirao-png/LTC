"""Research-provider boundary used by the Customer Analysis Worker.

GPT Researcher is imported lazily so the Worker can still boot when a local
installation intentionally omits the optional provider package.  Production
containers install the pinned package and use it before the direct Exa
fallback.  Both paths return the same normalized record shape.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any, Callable, Protocol

import httpx


def configure_gpt_researcher_environment(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
) -> None:
    """Map LTC provider settings to GPT Researcher's documented variables."""
    os.environ.setdefault("RETRIEVER", "exa")
    os.environ.setdefault("OPENAI_API_KEY", api_key)
    os.environ.setdefault("OPENAI_BASE_URL", base_url)
    llm = f"openai:{model_name}"
    os.environ.setdefault("FAST_LLM", llm)
    os.environ.setdefault("SMART_LLM", llm)
    os.environ.setdefault("STRATEGIC_LLM", llm)
    os.environ.setdefault("EMBEDDING", "custom:text-embedding-3-small")
    os.environ.setdefault("LANGUAGE", "chinese")


class ExternalResearchProvider(Protocol):
    async def __call__(
        self, query: str, *, request_id: str | None = None
    ) -> list[dict[str, Any]]: ...


class GPTResearcherAdapter:
    def __init__(
        self,
        provider: ExternalResearchProvider | None = None,
        *,
        fallback: ExternalResearchProvider | None = None,
        researcher_factory: Callable[..., Any] | None = None,
        max_subtopics: int = 3,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.provider = provider
        self.fallback = fallback
        self.researcher_factory = researcher_factory
        self.max_subtopics = max(1, min(max_subtopics, 8))
        self.timeout_seconds = max(5.0, timeout_seconds)
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._provider_disabled = False

    async def research(
        self, query: str, *, request_id: str | None = None
    ) -> list[dict[str, Any]]:
        cached = self._cache.get(query)
        if cached is not None:
            return [dict(item) for item in cached]
        result: list[dict[str, Any]] = []
        if self.provider is not None and not self._provider_disabled:
            try:
                candidate = await asyncio.wait_for(
                    asyncio.to_thread(
                        _run_provider_in_thread,
                        self.provider,
                        query,
                        request_id,
                    ),
                    timeout=self.timeout_seconds,
                )
                result = [dict(item) for item in candidate if isinstance(item, dict)]
            except Exception:
                # GPT Researcher is a provider optimization, not a reason to
                # lose the Exa-only report path.
                result = []
                self._provider_disabled = True
        if not result and self.fallback is not None:
            candidate = await self.fallback(query, request_id=request_id)
            result = [dict(item) for item in candidate if isinstance(item, dict)]
        self._cache[query] = result
        return [dict(item) for item in result]


class RealGPTResearchProvider:
    """Thin async wrapper around the official GPT Researcher API."""

    def __init__(
        self,
        *,
        max_subtopics: int = 3,
        researcher_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.max_subtopics = max(1, min(max_subtopics, 8))
        self.researcher_factory = researcher_factory

    async def __call__(self, query: str, *, request_id: str | None = None) -> list[dict[str, Any]]:
        del request_id
        factory = self.researcher_factory
        if factory is None:
            try:
                from gpt_researcher import GPTResearcher
            except ImportError:
                return []
            factory = GPTResearcher
        researcher = factory(
            query=query,
            report_type="research_report",
            verbose=False,
            max_subtopics=self.max_subtopics,
        )
        await researcher.conduct_research()
        report = await researcher.write_report()
        sources = researcher.get_research_sources() or []
        costs = researcher.get_costs()
        normalized: list[dict[str, Any]] = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                continue
            url = str(source.get("url") or source.get("href") or "").strip()
            text = str(
                source.get("text")
                or source.get("content")
                or source.get("body")
                or source.get("raw_content")
                or ""
            ).strip()
            if not url and not text:
                continue
            normalized.append(
                {
                    "id": str(source.get("id") or f"gptr-{index}"),
                    "title": str(source.get("title") or source.get("name") or url or "GPT Researcher source"),
                    "url": url or None,
                    "text": text,
                    "highlights": source.get("highlights") or [],
                    "metadata": {
                        "research_provider": "gpt_researcher",
                        "research_cost_usd": costs,
                        "report_excerpt": str(report or "")[:500],
                    },
                }
            )
        if not normalized:
            urls = researcher.get_source_urls() or []
            excerpt = str(report or "").strip()
            normalized = [
                {
                    "id": f"gptr-url-{index}",
                    "title": str(url),
                    "url": str(url),
                    "text": excerpt,
                    "metadata": {
                        "research_provider": "gpt_researcher",
                        "research_cost_usd": costs,
                    },
                }
                for index, url in enumerate(urls)
                if str(url).strip()
            ]
        return normalized


def _run_provider_in_thread(
    provider: ExternalResearchProvider,
    query: str,
    request_id: str | None,
) -> Any:
    """Run a provider in an isolated event loop so sync SDK work cannot block Worker polling."""
    result = provider(query, request_id=request_id)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


class ExaResearchProvider:
    """Exa contents search used by the GPT Researcher boundary."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.exa.ai",
        timeout_seconds: float = 20.0,
        result_count: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.result_count = max(1, min(result_count, 20))
        self._client = client

    async def __call__(
        self, query: str, *, request_id: str | None = None
    ) -> list[dict[str, Any]]:
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/search",
                headers={
                    "x-api-key": self.api_key,
                    "Accept": "application/json",
                    "X-Request-ID": request_id or "",
                },
                json={
                    "query": query,
                    "numResults": self.result_count,
                    "contents": {"text": True, "highlights": {"numSentences": 3}},
                },
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results", []) if isinstance(payload, dict) else []
            return [dict(row) for row in rows if isinstance(row, dict)]
        finally:
            if close_client:
                await client.aclose()
