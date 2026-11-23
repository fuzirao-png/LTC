from __future__ import annotations

from .base import UseCaseBackedHandler


class AnalysisGenerateReportHandler(UseCaseBackedHandler):
    job_type = "analysis.generate_report.v1"
    use_case_attr = "customer_analysis"
