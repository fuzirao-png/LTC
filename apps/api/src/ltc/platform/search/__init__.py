"""Platform search adapters — Exa, DuckDuckGo, skill bridge.

This package mirrors the contract from clue_agent's web_search_bridge
but lives in the platform layer so every module (lead_intelligence,
customer_analysis, etc.) can reuse the same adapters.

Configuration:
    EXA_API_KEY        — preferred; enables ExaSearchAdapter
    LTC_SEARCH_PROVIDER — ``exa``, ``duckduckgo``, ``auto`` (default: auto)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
import hashlib
from urllib.request import Request, urlopen
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_search_items(
    items: list[dict[str, Any]] | None, *, limit: int | None = None
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in items or []:
        url = str(
            item.get("url") or item.get("href") or item.get("FirstURL") or ""
        ).strip()
        if not url:
            continue
        lowered = url.lower()
        source_type = "official_website"
        if "linkedin.com" in lowered:
            source_type = "linkedin_company_page"
        elif "wikipedia.org" in lowered:
            source_type = "reference_page"
        text = str(
            item.get("text")
            or item.get("content")
            or item.get("snippet")
            or item.get("abstract")
            or item.get("Text")
            or ""
        ).strip()[:12000]
        raw_highlights = item.get("highlights") or []
        highlights = (
            [str(value).strip()[:1200] for value in raw_highlights if str(value).strip()]
            if isinstance(raw_highlights, list)
            else []
        )
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
        evidence_seed = f"{url}|{content_hash or ''}"
        evidence_id = "web:" + hashlib.sha256(
            evidence_seed.encode("utf-8")
        ).hexdigest()[:20]
        sources.append(
            {
                "evidence_id": evidence_id,
                "url": url,
                "source_type": source_type,
                "title": str(
                    item.get("title") or item.get("name") or ""
                )[:200],
                "text": text,
                "highlights": highlights,
                "published_at": item.get("publishedDate") or item.get("published_at"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": f"sha256:{content_hash}" if content_hash else None,
            }
        )
        if limit is not None and len(sources) >= limit:
            break
    return sources


# ---------------------------------------------------------------------------
# Search adapter classes
# ---------------------------------------------------------------------------

class ExaSearchAdapter:
    """Calls https://api.exa.ai/search with automatic retries."""

    provider_name: str = "exa"
    search_url: str = "https://api.exa.ai/search"

    def __init__(self, api_key: str, timeout_seconds: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search_web(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": str(query or "").strip(),
            "numResults": num_results,
            "type": "auto",
            "_limit": num_results,
            "contents": {
                "text": {"maxCharacters": 12000},
                "highlights": {"numSentences": 5, "highlightsPerUrl": 3},
            },
        }
        request = Request(
            self.search_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    raise
                time.sleep(0.8 * (attempt + 1))
        return _normalize_search_items(
            data.get("results") or [], limit=payload["_limit"]
        )

    def search_company_sources(
        self, company_name: str
    ) -> list[dict[str, Any]]:
        return _search_company_queries(self, company_name)


class DuckDuckGoSearchAdapter:
    provider_name: str = "duckduckgo"
    search_url_template: str = (
        "https://duckduckgo.com/?q={query}&format=json&pretty=0"
    )

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search_web(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        from urllib.parse import quote_plus

        q = quote_plus(str(query or "").strip())
        request = Request(
            self.search_url_template.format(query=q),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        related = payload.get("RelatedTopics") or []
        items: list[dict[str, Any]] = []
        for item in related:
            if isinstance(item, dict) and "Topics" in item:
                items.extend(
                    topic
                    for topic in item.get("Topics", [])
                    if isinstance(topic, dict)
                )
            elif isinstance(item, dict):
                items.append(item)
        return _normalize_search_items(items, limit=num_results)

    def search_company_sources(
        self, company_name: str
    ) -> list[dict[str, Any]]:
        return _search_company_queries(self, company_name)


def _search_company_queries(adapter: Any, company_name: str) -> list[dict[str, Any]]:
    company = str(company_name or "").strip()
    if not company:
        return []
    query_suffixes = (
        "official website about business employees",
        "products API integration eSIM coverage countries",
        "security privacy compliance certifications",
        "news leadership interview funding",
        "competitors alternatives pricing procurement",
    )
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for suffix in query_suffixes:
        try:
            query_results = adapter.search_web(f'"{company}" {suffix}', num_results=3)
        except Exception:
            continue
        for item in query_results:
            key = str(item.get("content_hash") or item.get("url") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(item)
    return results[:15]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_search_adapter(
    provider: str = "auto",
    *,
    timeout_seconds: float = 15.0,
) -> ExaSearchAdapter | DuckDuckGoSearchAdapter:
    """Return the best available search adapter based on env vars.

    Resolution order:
    1. ``LTC_SEARCH_PROVIDER=exa``   (requires EXA_API_KEY)
    2. ``LTC_SEARCH_PROVIDER=duckduckgo``
    3. ``auto``: prefer Exa when EXA_API_KEY is set, else DuckDuckGo.
    """
    exa_api_key: str | None = os.environ.get("EXA_API_KEY")
    chosen = os.environ.get("LTC_SEARCH_PROVIDER", provider)

    if chosen == "exa":
        if not exa_api_key:
            raise ValueError("EXA_API_KEY is required for exa search provider")
        return ExaSearchAdapter(api_key=exa_api_key, timeout_seconds=timeout_seconds)

    if chosen == "duckduckgo":
        return DuckDuckGoSearchAdapter(timeout_seconds=timeout_seconds)

    # auto — prefer Exa when available, otherwise free fallback
    if exa_api_key:
        return ExaSearchAdapter(api_key=exa_api_key, timeout_seconds=timeout_seconds)
    return DuckDuckGoSearchAdapter(timeout_seconds=timeout_seconds)
