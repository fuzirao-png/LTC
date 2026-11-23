from __future__ import annotations

from .base import UseCaseBackedHandler


class NotifyHandler(UseCaseBackedHandler):
    job_type = "platform.notify.v1"
    use_case_attr = "notify"
