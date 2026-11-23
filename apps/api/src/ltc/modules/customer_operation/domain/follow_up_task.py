from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


TaskStatus = Literal["pending", "done", "cancelled"]
TaskSource = Literal["system", "manual"]


@dataclass(frozen=True)
class FollowUpTask:
    task_id: UUID
    company_id: UUID
    description: str
    status: TaskStatus
    due_date: datetime | None
    source: TaskSource
    source_event: str | None
    version: int
    created_at: datetime





