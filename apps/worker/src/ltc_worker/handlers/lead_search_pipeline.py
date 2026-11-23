from __future__ import annotations

from .base import UseCaseBackedHandler


class LeadSearchPipelineHandler(UseCaseBackedHandler):
    job_type = "lead.search_pipeline.v1"
    use_case_attr = "lead_search_pipeline"
