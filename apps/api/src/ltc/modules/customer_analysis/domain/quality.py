"""Evidence and citation quality gates for generated customer reports."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse


MODULE_NAMES = ("market", "company", "competitor", "pain", "product")


def evaluate_report_quality(
    report_payload: dict[str, Any], evidence_refs: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in evidence_refs
        if isinstance(item, dict) and item.get("evidence_id")
    }
    available_origins = {
        _origin(item)
        for item in evidence_by_id.values()
        if _origin(item)
    }
    modules: dict[str, Any] = {}
    unsupported_claim_count = 0
    coverage_values: list[float] = []
    diversity_values: list[float] = []
    for module_name in MODULE_NAMES:
        module = report_payload.get(module_name) or {}
        claims = []
        for key in ("facts", "inferences", "sales_recommendations"):
            value = module.get(key) or []
            if isinstance(value, list):
                claims.extend(item for item in value if isinstance(item, dict))
        supported = 0
        origins: set[str] = set()
        for claim in claims:
            ids = [str(value) for value in (claim.get("evidence_ids") or [])]
            resolved = [evidence_by_id[item_id] for item_id in ids if item_id in evidence_by_id]
            if resolved:
                supported += 1
                origins.update(origin for origin in (_origin(item) for item in resolved) if origin)
            else:
                unsupported_claim_count += 1
        coverage = supported / len(claims) if claims else 0.0
        diversity = min(1.0, len(origins) / 2.0)
        coverage_values.append(coverage)
        diversity_values.append(diversity)
        modules[module_name] = {
            "claim_count": len(claims),
            "supported_claim_count": supported,
            "source_count": len(origins),
            "source_origins": sorted(origins),
            "coverage": round(coverage, 4),
            "source_diversity": round(diversity, 4),
            "status": "passed" if claims and coverage == 1 and len(origins) >= 2 else "needs_review",
        }
    source_diversity_score = round(sum(diversity_values) / len(diversity_values), 4) if diversity_values else 0.0
    evidence_coverage_score = round(sum(coverage_values) / len(coverage_values), 4) if coverage_values else 0.0
    passed = bool(available_origins) and all(item["status"] == "passed" for item in modules.values())
    return {
        "quality_status": "passed" if passed else "needs_review",
        "source_diversity_score": source_diversity_score,
        "evidence_coverage_score": evidence_coverage_score,
        "unsupported_claim_count": unsupported_claim_count,
        "needs_review": not passed,
        "available_source_count": len(available_origins),
        "modules": modules,
    }


def _origin(item: dict[str, Any]) -> str | None:
    source_type = str(item.get("source_type") or "").strip()
    url = str(item.get("url") or "").strip()
    if url:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    if source_type:
        metadata = item.get("metadata") or {}
        document = str(metadata.get("document_id") or metadata.get("knowledge_base_id") or "")
        return f"{source_type}:{document}" if document else source_type
    return None
