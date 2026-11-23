"""Application service for promoting Lead Candidates into Sales Leads.

Bridges Lead Intelligence (candidate/ICP/scale) → Sales CRM (company/contact/lead).

This is a pure DDD application service: it coordinates domain objects through
ports without depending on FastAPI, psycopg, or any infrastructure detail.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Protocol

from ..domain.models import CompanyCandidate
from ..domain.ports import LeadRepositoryPort


# ── Result types ───────────────────────────────────────────────────

class PromotionResult:
    """Value object carrying the outcome of a single candidate promotion."""

    def __init__(
        self,
        candidate_id: str,
        company_id: str | None = None,
        lead_id: str | None = None,
        icp_id: str | None = None,
        scale_id: str | None = None,
        promotion_result: str = "created_lead",
        allocation_status: str = "claimable",
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.candidate_id = candidate_id
        self.company_id = company_id
        self.lead_id = lead_id
        self.icp_id = icp_id
        self.scale_id = scale_id
        self.promotion_result = promotion_result
        self.allocation_status = allocation_status
        self.error_code = error_code
        self.error_message = error_message

    @property
    def is_success(self) -> bool:
        return self.error_code is None

    def to_success_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "company_id": self.company_id,
            "lead_id": self.lead_id,
            "selected_icp_assessment_id": self.icp_id,
            "selected_scale_assessment_id": self.scale_id,
            "promotion_result": self.promotion_result,
            "allocation_status": self.allocation_status,
        }

    def to_failure_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "code": self.error_code,
            "message": self.error_message or "",
        }


# ── Port definitions (application layer owns these) ────────────────


class CandidatePromotionPort(Protocol):
    """Read side: fetch candidate + assessments for promotion gate checks."""

    def fetch_candidate_for_promotion(self, candidate_id: str) -> dict | None: ...

    def fetch_current_icp(self, candidate_id: str) -> dict | None: ...

    def fetch_current_scale(self, candidate_id: str) -> dict | None: ...

    def check_open_sales_lead(self, candidate_id: str) -> dict | None: ...


class SalesLeadWritePort(Protocol):
    """Write side: create Company, Contact, Sales Lead in one transaction."""

    def promote_candidate(
        self,
        candidate: dict,
        icp: dict,
        scale: dict,
        actor_id: str,
        override: bool,
        override_reason: str | None,
        request_id: str,
    ) -> dict: ...


# ── Service ────────────────────────────────────────────────────────


class CandidatePromotionService:
    """Orchestrates batch candidate → sales lead promotion.

    Each item executes in its own transaction and may succeed or fail
    independently (partial-success batch pattern per PRD §3.9).
    """

    def __init__(
        self,
        candidate_port: CandidatePromotionPort,
        sales_lead_port: SalesLeadWritePort,
    ) -> None:
        self._candidates = candidate_port
        self._sales = sales_lead_port

    def promote_batch(
        self,
        items: list[dict],
        actor_id: str,
        request_id: str,
    ) -> dict:
        succeeded: list[dict] = []
        failed: list[dict] = []

        for item in items:
            result = self._promote_one(
                candidate_id=str(item["candidate_id"]),
                expected_version=int(item["expected_version"]),
                override=bool(item.get("override", False)),
                override_reason=item.get("override_reason"),
                actor_id=actor_id,
                request_id=request_id,
            )
            if result.is_success:
                succeeded.append(result.to_success_dict())
            else:
                failed.append(result.to_failure_dict())

        return {"succeeded": succeeded, "failed": failed}

    def _promote_one(
        self,
        *,
        candidate_id: str,
        expected_version: int,
        override: bool,
        override_reason: str | None,
        actor_id: str,
        request_id: str,
    ) -> PromotionResult:
        # ── Gate 1: fetch candidate ──
        candidate = self._candidates.fetch_candidate_for_promotion(candidate_id)
        if not candidate:
            return PromotionResult(candidate_id, error_code="CANDIDATE_NOT_FOUND", error_message="Candidate not found or already merged")

        # ── Version guard ──
        if int(candidate.get("version", -1)) != expected_version:
            return PromotionResult(candidate_id, error_code="VERSION_CONFLICT", error_message="Candidate has been modified; reload and retry")

        status = str(candidate.get("processing_status") or "")

        # ── Gate 2: already promoted ──
        if status == "promoted":
            return PromotionResult(candidate_id, error_code="CANDIDATE_ALREADY_PROMOTED", error_message="Already promoted to a Sales Lead")

        # ── Gate 3: not eligible ──
        if status == "merged":
            return PromotionResult(candidate_id, error_code="CANDIDATE_ALREADY_MERGED", error_message="Candidate has been merged")
        if status == "archived":
            return PromotionResult(candidate_id, error_code="CANDIDATE_ARCHIVED", error_message="Candidate is archived")

        # ── Gate 4: assessments stale ──
        if candidate.get("assessments_stale"):
            return PromotionResult(candidate_id, error_code="CANDIDATE_ASSESSMENTS_STALE", error_message="Assessments are stale; refresh enrichment first")

        # ── Gate 5: check for reuse (same company already has a lead) ──
        open_lead = self._candidates.check_open_sales_lead(candidate_id)

        # ── Gate 6: override vs normal eligibility ──
        if override:
            if status not in ("scored", "eligible"):
                return PromotionResult(candidate_id, error_code="CANDIDATE_NOT_READY", error_message="Override requires current ICP/Scale assessment")
            if not override_reason:
                return PromotionResult(candidate_id, error_code="PROMOTION_OVERRIDE_REASON_REQUIRED", error_message="override_reason is required")
        else:
            if status not in ("eligible", "scored"):
                return PromotionResult(candidate_id, error_code="CANDIDATE_NOT_READY", error_message="Candidate must be eligible or scored (current status: {})".format(status))

        # ── Gate 7: fetch ICP & Scale ──
        icp = self._candidates.fetch_current_icp(candidate_id)
        scale = self._candidates.fetch_current_scale(candidate_id)
        if not icp:
            return PromotionResult(candidate_id, error_code="CANDIDATE_NOT_READY", error_message="Missing current ICP assessment")
        if not scale:
            return PromotionResult(candidate_id, error_code="CANDIDATE_NOT_READY", error_message="Missing current scale assessment")

        # ── Execute promotion (one transaction) ──
        try:
            result = self._sales.promote_candidate(
                candidate=candidate,
                icp=icp,
                scale=scale,
                actor_id=actor_id,
                override=override,
                override_reason=override_reason,
                request_id=request_id,
            )
            return PromotionResult(
                candidate_id=candidate_id,
                company_id=str(result["company_id"]),
                lead_id=str(result["lead_id"]),
                icp_id=str(result["icp_assessment_id"]),
                scale_id=str(result["scale_assessment_id"]),
                promotion_result=result.get("promotion_result", "created_lead"),
                allocation_status=result.get("allocation_status", "claimable"),
            )
        except Exception as exc:
            return PromotionResult(candidate_id, error_code="PROMOTION_FAILED", error_message=str(exc))
