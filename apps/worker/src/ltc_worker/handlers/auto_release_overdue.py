from __future__ import annotations

from .base import UseCaseBackedHandler


class AutoReleaseOverdueHandler(UseCaseBackedHandler):
    job_type = "crm.auto_release_overdue.v1"
    use_case_attr = "auto_release_overdue"
