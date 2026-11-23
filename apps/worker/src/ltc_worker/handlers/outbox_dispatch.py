from __future__ import annotations

from .base import UseCaseBackedHandler


class OutboxDispatchHandler(UseCaseBackedHandler):
    job_type = "platform.dispatch_outbox.v1"
    use_case_attr = "outbox_dispatch"
