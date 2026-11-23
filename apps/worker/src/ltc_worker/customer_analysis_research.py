"""Research Worker primitives for Customer Analysis.

The worker owns provider credentials and turns provider-specific responses into
the evidence contract consumed by the API/report writer.  It deliberately does
not expose WeKnora management operations to the research model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

import httpx


LOGGER = logging.getLogger("ltc.worker.customer_analysis")
ALLOWED_WEKNORA_TOOLS = frozenset({"hybrid_search"})
SOURCE_PRIORITY = {"sales_confirmed": 4, "internal": 3, "weknora": 2, "exa": 1, "web": 1}


class ResearchPolicyError(ValueError):
    """Raised when a job attempts to violate the research policy."""


class KnowledgeRetriever(Protocol):
    async def hybrid_search(
        self,
        *,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int,
        filters: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> list["KnowledgeChunk"]: ...


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    knowledge_base_id: str
    document_id: str | None
    title: str
    text: str
    score: float | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    source_type: str
    source_priority: int
    title: str
    text: str
    url: str | None = None
    highlights: tuple[str, ...] = ()
    retrieved_at: str = ""
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_priority": self.source_priority,
            "title": self.title,
            "text": self.text,
            "excerpt": self.text[:240],
            "url": self.url,
            "highlights": list(self.highlights),
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "metadata": dict(self.metadata),
        }


class WeKnoraError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WeKnoraRestAdapter:
    """Read-only WeKnora REST adapter with bounded transport retries."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        allowed_knowledge_base_ids: set[str] | frozenset[str] = frozenset(),
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.allowed_knowledge_base_ids = frozenset(allowed_knowledge_base_ids)
        self._client = client

    async def hybrid_search(
        self,
        *,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int,
        filters: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> list[KnowledgeChunk]:
        if not query.strip():
            return []
        requested_ids = [str(item) for item in knowledge_base_ids]
        if (
            not self.allowed_knowledge_base_ids
            or not requested_ids
            or not set(requested_ids).issubset(self.allowed_knowledge_base_ids)
        ):
            raise WeKnoraError("knowledge_base_forbidden", "knowledge base is not allowlisted")
        payload = {
            "query": query,
            "knowledge_base_ids": requested_ids,
            "top_k": max(1, min(int(top_k), 100)),
            "filters": filters or {},
        }
        request_id = request_id or f"ltc-{uuid4()}"
        headers = {
            "X-API-Key": self.api_key,
            "X-Request-ID": request_id,
            "Accept": "application/json",
        }
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        f"{self.base_url}/api/v1/knowledge-search",
                        json=payload,
                        headers=headers,
                    )
                    if response.status_code in {401, 403}:
                        raise WeKnoraError("authorization_failed", "knowledge search authorization failed")
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < self.max_retries:
                            continue
                        raise WeKnoraError("provider_unavailable", f"knowledge search returned {response.status_code}")
                    if response.status_code >= 400:
                        raise WeKnoraError("provider_error", f"knowledge search returned {response.status_code}")
                    return self._parse_chunks(response.json(), requested_ids)
                except WeKnoraError:
                    raise
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt >= self.max_retries:
                        raise WeKnoraError("timeout", "knowledge search transport failed") from exc
            return []
        finally:
            if close_client:
                await client.aclose()

    @staticmethod
    def _parse_chunks(payload: Any, requested_ids: list[str]) -> list[KnowledgeChunk]:
        rows = payload.get("results", payload.get("data", payload)) if isinstance(payload, dict) else payload
        if isinstance(rows, dict):
            rows = rows.get("results") or rows.get("items") or rows.get("chunks") or []
        if not isinstance(rows, list):
            raise WeKnoraError("invalid_response", "knowledge search response must contain a result list")
        chunks: list[KnowledgeChunk] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            kb_id = str(
                row.get("knowledge_base_id")
                or row.get("kb_id")
                or ""
            )
            # WeKnora's /knowledge-search response identifies the source
            # knowledge document but does not include its parent KB. A single
            # allowlisted KB request makes that parent unambiguous.
            if not kb_id and len(requested_ids) == 1:
                kb_id = requested_ids[0]
            if requested_ids and kb_id not in requested_ids:
                continue
            chunk_id = str(row.get("chunk_id") or row.get("id") or "")
            text = str(
                row.get("text")
                or row.get("content")
                or row.get("chunk_content")
                or ""
            ).strip()
            if not chunk_id or not text:
                continue
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    knowledge_base_id=kb_id,
                    document_id=str(
                        row.get("document_id")
                        or row.get("doc_id")
                        or row.get("file_id")
                        or row.get("knowledge_id")
                        or ""
                    ) or None,
                    title=str(
                        row.get("title")
                        or row.get("document_title")
                        or row.get("source_name")
                        or row.get("knowledge_title")
                        or row.get("knowledge_filename")
                        or "Knowledge base material"
                    ),
                    text=text,
                    score=float(row["score"]) if row.get("score") is not None else None,
                    updated_at=str(row.get("updated_at") or row.get("document_updated_at") or "") or None,
                    metadata=dict(row.get("metadata") or {}),
                )
            )
        return chunks


class EvidenceNormalizer:
    """Normalize internal, WeKnora and Exa records to one evidence shape."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(timezone.utc)

    def internal(self, item: dict[str, Any]) -> Evidence:
        return self._build(
            source_type=str(item.get("source_type") or "internal"),
            raw_id=str(item.get("evidence_id") or item.get("id") or "internal"),
            title=str(item.get("title") or "Internal evidence"),
            text=str(item.get("text") or item.get("excerpt") or "").strip(),
            url=item.get("url"),
            metadata=dict(item.get("metadata") or {}),
        )

    def weknora(self, chunk: KnowledgeChunk) -> Evidence:
        return self._build(
            source_type="weknora",
            raw_id=chunk.chunk_id,
            title=chunk.title,
            text=chunk.text,
            metadata={
                **chunk.metadata,
                "knowledge_base_id": chunk.knowledge_base_id,
                "document_id": chunk.document_id,
                "document_updated_at": chunk.updated_at,
                "score": chunk.score,
                "permission_filtered": True,
            },
        )

    def exa(self, item: dict[str, Any]) -> Evidence:
        highlights = item.get("highlights") or item.get("highlight") or []
        if isinstance(highlights, str):
            highlights = [highlights]
        text = str(item.get("text") or item.get("contents") or item.get("snippet") or "").strip()
        return self._build(
            source_type="exa",
            raw_id=str(item.get("id") or item.get("result_id") or item.get("url") or "exa"),
            title=str(item.get("title") or "External research"),
            text=text,
            url=str(item.get("url") or "") or None,
            highlights=tuple(str(value).strip() for value in highlights if str(value).strip()),
            metadata=dict(item.get("metadata") or {}),
        )

    def _build(
        self,
        *,
        source_type: str,
        raw_id: str,
        title: str,
        text: str,
        url: str | None = None,
        highlights: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> Evidence:
        content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        evidence_metadata = dict(metadata or {})
        prefix = "weknora" if source_type == "weknora" else "exa" if source_type == "exa" else source_type
        sales_confirmed = (
            evidence_metadata.get("evidence_grade") == "A"
            or evidence_metadata.get("confirmation_status") == "confirmed"
        )
        priority = (
            SOURCE_PRIORITY["sales_confirmed"]
            if sales_confirmed
            else 3 if source_type.startswith("internal")
            else SOURCE_PRIORITY.get(source_type, 1)
        )
        preserve_internal_id = source_type.startswith("internal") and ":" in raw_id
        evidence_id = (
            raw_id
            if preserve_internal_id or raw_id.startswith(f"{prefix}:")
            else f"{prefix}:{raw_id}"
        )
        return Evidence(
            evidence_id=evidence_id,
            source_type=source_type,
            source_priority=priority,
            title=title,
            text=text,
            url=url,
            highlights=highlights,
            retrieved_at=self.now.isoformat(),
            content_hash=content_hash,
            metadata=evidence_metadata,
        )


class PriorityMerger:
    """Keep higher-priority facts authoritative and surface equal-level conflicts."""

    def merge(self, evidence: list[Evidence]) -> tuple[list[Evidence], list[dict[str, Any]]]:
        by_hash: dict[str, Evidence] = {}
        conflicts: list[dict[str, Any]] = []
        by_field: dict[str, Evidence] = {}
        for item in evidence:
            field_hints = item.metadata.get("field_hints") or []
            if isinstance(field_hints, str):
                field_hints = [field_hints]
            for field_id in (str(value) for value in field_hints if str(value)):
                previous_field = by_field.get(field_id)
                if previous_field is None or item.source_priority > previous_field.source_priority:
                    if (
                        previous_field is not None
                        and item.content_hash != previous_field.content_hash
                    ):
                        conflicts.append(
                            {
                                "field_id": field_id,
                                "evidence_ids": [previous_field.evidence_id, item.evidence_id],
                                "authoritative_evidence_id": item.evidence_id,
                                "status": "conflict",
                            }
                        )
                    by_field[field_id] = item
                elif item.content_hash != previous_field.content_hash:
                    conflicts.append(
                        {
                            "field_id": field_id,
                            "evidence_ids": [previous_field.evidence_id, item.evidence_id],
                            "authoritative_evidence_id": (
                                previous_field.evidence_id
                                if previous_field.source_priority > item.source_priority
                                else None
                            ),
                            "status": "conflict",
                        }
                    )
            key = item.content_hash or item.evidence_id
            previous = by_hash.get(key)
            if previous is None:
                by_hash[key] = item
                continue
            if previous.source_priority == item.source_priority and previous.text != item.text:
                conflicts.append({"evidence_ids": [previous.evidence_id, item.evidence_id], "status": "conflict"})
            if item.source_priority > previous.source_priority:
                by_hash[key] = item
        return list(by_hash.values()), conflicts


class ResearchWorker:
    """Policy gate and provider orchestration used by the analysis job."""

    def __init__(
        self,
        *,
        knowledge_retriever: KnowledgeRetriever | None = None,
        exa_search: Any | None = None,
        knowledge_retriever_factory: Any | None = None,
        exa_search_factory: Any | None = None,
    ) -> None:
        self.knowledge_retriever = knowledge_retriever
        self.exa_search = exa_search
        self.knowledge_retriever_factory = knowledge_retriever_factory
        self.exa_search_factory = exa_search_factory
        self.normalizer = EvidenceNormalizer()
        self.merger = PriorityMerger()

    async def research(
        self,
        *,
        context: dict[str, Any],
        research_mode: str,
        knowledge_base_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        if research_mode not in {"initial_external", "internal_only"}:
            raise ResearchPolicyError(f"unsupported research_mode: {research_mode}")
        started_at = perf_counter()
        evidence = [self.normalizer.internal(item) for item in context.get("evidence_refs", []) if isinstance(item, dict)]
        tool_trace: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {
            "weknora_requests": 0,
            "exa_requests": 0,
            "weknora_unavailable": False,
            "exa_unavailable": False,
            "discarded_untrusted_evidence": 0,
            "estimated_cost_amount": None,
            "weknora_status": "not_configured",
            "exa_status": "not_configured",
            "gpt_researcher_status": "not_configured",
            "research_scope": "internal_only" if research_mode == "internal_only" else "external",
        }
        if research_mode == "internal_only":
            merged, conflicts = self.merger.merge(evidence)
            metrics["latency_ms"] = round((perf_counter() - started_at) * 1000)
            return {
                "evidence_refs": [item.to_dict() for item in merged],
                "conflicts": conflicts,
                "metrics": metrics,
                "snapshot_ids": {"weknora": None, "exa": None},
                "tool_trace": tool_trace,
            }

        knowledge_retriever = self.knowledge_retriever
        if knowledge_retriever is None and self.knowledge_retriever_factory is not None:
            knowledge_retriever = self.knowledge_retriever_factory()
        exa_search = self.exa_search
        if exa_search is None and self.exa_search_factory is not None:
            exa_search = self.exa_search_factory()

        queries = self._queries(context)
        if knowledge_retriever is not None and knowledge_base_ids:
            metrics["weknora_status"] = "available"
            for query in queries:
                metrics["weknora_requests"] += 1
                request_id = f"ltc-research-{uuid4()}"
                try:
                    chunks = await knowledge_retriever.hybrid_search(
                        query=query,
                        knowledge_base_ids=knowledge_base_ids,
                        top_k=top_k,
                        request_id=request_id,
                    )
                    tool_trace.append(
                        {
                            "tool": "hybrid_search",
                            "query_hash": _query_hash(query),
                            "request_id": request_id,
                            "status": "succeeded",
                            "result_count": len(chunks),
                        }
                    )
                    for chunk in chunks:
                        if _contains_prompt_injection(chunk.text):
                            metrics["discarded_untrusted_evidence"] += 1
                            continue
                        evidence.append(self.normalizer.weknora(chunk))
                    if not chunks and metrics["weknora_status"] == "available":
                        metrics["weknora_status"] = "empty"
                except Exception:
                    metrics["weknora_unavailable"] = True
                    metrics["weknora_status"] = "unavailable"
                    tool_trace.append(
                        {
                            "tool": "hybrid_search",
                            "query_hash": _query_hash(query),
                            "request_id": request_id,
                            "status": "failed",
                            "result_count": 0,
                        }
                    )
                    LOGGER.warning("weknora_unavailable", exc_info=True)

        if exa_search is not None:
            for query in queries:
                metrics["exa_requests"] += 1
                request_id = f"ltc-research-{uuid4()}"
                try:
                    results = await _call_external_search(exa_search, query, request_id)
                    result_count = len(results) if isinstance(results, list) else 0
                    tool_trace.append(
                        {
                            "tool": "exa_search",
                            "query_hash": _query_hash(query),
                            "request_id": request_id,
                            "status": "succeeded",
                            "result_count": result_count,
                        }
                    )
                    if isinstance(results, list):
                        if results and any(
                            str(item.get("metadata", {}).get("research_provider") or "")
                            == "gpt_researcher"
                            for item in results
                            if isinstance(item, dict)
                        ):
                            metrics["gpt_researcher_status"] = "available"
                        for item in results:
                            if not isinstance(item, dict):
                                continue
                            raw_text = str(item.get("text") or item.get("contents") or item.get("snippet") or "")
                            if _contains_prompt_injection(raw_text):
                                metrics["discarded_untrusted_evidence"] += 1
                                continue
                            evidence.append(self.normalizer.exa(item))
                    if result_count == 0 and metrics["exa_status"] == "not_configured":
                        metrics["exa_status"] = "empty"
                    elif result_count:
                        metrics["exa_status"] = "available"
                except Exception:
                    metrics["exa_unavailable"] = True
                    metrics["exa_status"] = "unavailable"
                    tool_trace.append(
                        {
                            "tool": "exa_search",
                            "query_hash": _query_hash(query),
                            "request_id": request_id,
                            "status": "failed",
                            "result_count": 0,
                        }
                    )
                    LOGGER.warning("exa_unavailable", exc_info=True)

        if metrics["gpt_researcher_status"] == "not_configured" and exa_search is not None:
            # A direct Exa adapter is still a valid Exa-only deployment.
            metrics["gpt_researcher_status"] = "unavailable"

        merged, conflicts = self.merger.merge(evidence)
        metrics["latency_ms"] = round((perf_counter() - started_at) * 1000)
        return {
            "evidence_refs": [item.to_dict() for item in merged],
            "conflicts": conflicts,
            "metrics": metrics,
            "snapshot_ids": {
                "weknora": _snapshot_id(merged, "weknora"),
                "exa": _snapshot_id(merged, "exa"),
            },
            "tool_trace": tool_trace,
        }

    @staticmethod
    def _query(context: dict[str, Any]) -> str:
        company = context.get("company") or {}
        return str(company.get("company_name") or company.get("name") or "customer analysis").strip()

    @classmethod
    def _queries(cls, context: dict[str, Any]) -> list[str]:
        company_name = cls._query(context)
        company = context.get("company") or {}
        profile = context.get("profile") or {}
        industry = str(company.get("industry") or profile.get("company_type") or "target industry")
        region = str(profile.get("region_text") or company.get("region") or "target region")
        queries = [
            f"{company_name} company business model products services {region}",
            f"{industry} {region} market size trends competitive landscape",
            f"{company_name} competitors alternatives pricing procurement",
            f"{company_name} technology integration compliance customer pain points",
            f"{company_name} implementation requirements product fit",
        ]
        return list(dict.fromkeys(query.strip() for query in queries if query.strip()))


def validate_tool_allowlist(tool_name: str) -> None:
    if tool_name not in ALLOWED_WEKNORA_TOOLS:
        raise ResearchPolicyError(f"tool is not allowlisted: {tool_name}")


def _query_hash(query: str) -> str:
    return "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()


async def _call_external_search(
    search: Any,
    query: str,
    request_id: str,
) -> Any:
    try:
        parameters = inspect.signature(search).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "request_id" in parameters:
        return await search(query, request_id=request_id)
    return await search(query)


def _snapshot_id(evidence: list[Evidence], source_type: str) -> str | None:
    rows = sorted(
        (item.evidence_id, item.content_hash)
        for item in evidence
        if item.source_type == source_type
    )
    if not rows:
        return None
    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _contains_prompt_injection(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    markers = (
        "ignore previous instructions",
        "ignore all previous",
        "system prompt",
        "developer message",
        "reveal your instructions",
        "call the tool",
        "忽略之前的指令",
        "忽略所有指令",
        "系统提示词",
        "调用工具",
    )
    return any(marker in normalized for marker in markers)
