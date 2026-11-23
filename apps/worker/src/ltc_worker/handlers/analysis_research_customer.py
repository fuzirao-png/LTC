from __future__ import annotations

from .base import UseCaseBackedHandler


class AnalysisResearchCustomerHandler(UseCaseBackedHandler):
    job_type = "analysis.research_customer.v1"
    use_case_attr = "research_customer"

