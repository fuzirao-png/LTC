"""Best-effort bridge from customer operations to customer analysis."""

from __future__ import annotations

import logging
from uuid import UUID

from ltc.modules.customer_operation.application.ports import (
    AnalysisRunResult,
    AnalysisTriggerPort,
)


_logger = logging.getLogger(__name__)
_analysis_trigger: AnalysisTriggerPort | None = None


def set_analysis_trigger(port: AnalysisTriggerPort | None) -> None:
    global _analysis_trigger
    _analysis_trigger = port


def get_analysis_trigger() -> AnalysisTriggerPort | None:
    return _analysis_trigger


def trigger_customer_analysis_best_effort(
    company_id: UUID | str | None,
    *,
    source: str,
) -> AnalysisRunResult | None:
    """Queue analysis after an operation without failing the source operation."""
    if not company_id or _analysis_trigger is None:
        return None
    try:
        normalized_company_id = (
            company_id if isinstance(company_id, UUID) else UUID(str(company_id))
        )
        return _analysis_trigger.request_analysis(
            normalized_company_id,
            trigger_type="operation",
            trigger_context={"source": source},
        )
    except Exception:
        _logger.exception(
            "Customer analysis trigger failed source=%s company_id=%s",
            source,
            company_id,
        )
        return None
