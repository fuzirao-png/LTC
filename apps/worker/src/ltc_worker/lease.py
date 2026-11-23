from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class JobLease:
    job_id: str
    job_type: str
    lock_token: str
    queue_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 0
    concurrency_key: str | None = None
