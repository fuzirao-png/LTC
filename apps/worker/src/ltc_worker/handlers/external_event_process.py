from __future__ import annotations

from .base import UseCaseBackedHandler


class ExternalEventProcessHandler(UseCaseBackedHandler):
    job_type = "platform.process_external_event.v1"
    use_case_attr = "external_event_process"
