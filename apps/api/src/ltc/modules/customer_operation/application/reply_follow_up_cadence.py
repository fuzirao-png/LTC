from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


ACTIVE_INTENTS = {"interested", "pricing", "product_question"}
TERMINAL_INTENTS = {"proposal", "won", "not_interested", "unsubscribe"}

StepCode = Literal["D0", "D2", "D5", "D7", "D10"]
TaskType = Literal["email", "meeting", "proposal"]


@dataclass(frozen=True)
class ReplyFollowUpTaskSpec:
    step_code: StepCode
    task_type: TaskType
    title: str
    description: str
    due_at: datetime
    priority: int
    idempotency_key: str


@dataclass(frozen=True)
class ReplyFollowUpCadencePlan:
    pause_existing: bool
    tasks: tuple[ReplyFollowUpTaskSpec, ...]


_STEP_DEFINITIONS: tuple[tuple[StepCode, int, TaskType, str, int], ...] = (
    ("D0", 0, "email", "立即跟进", 100),
    ("D2", 2, "email", "二次跟进", 90),
    ("D5", 5, "email", "价值补充", 80),
    ("D7", 7, "meeting", "预约会议", 70),
    ("D10", 10, "email", "最终跟进", 60),
)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_task_description(intent_level: str, next_action: str, step_code: StepCode) -> str:
    normalized_next_action = next_action.strip() or "继续推进客户沟通。"
    if step_code == "D0":
        return normalized_next_action
    if step_code == "D2":
        return f"二次跟进：确认客户是否阅读回复，并继续推进 {intent_level} 线索。"
    if step_code == "D5":
        return "补充案例、证据或补充说明，保持对话热度。"
    if step_code == "D7":
        return "邀请客户安排一次简短会议，推动下一步确认。"
    return "发送最终跟进后暂停，等待客户回音。"


def build_reply_follow_up_cadence(
    *,
    intent_level: str,
    next_action: str,
    source_email_id: str,
    occurred_at: datetime,
) -> ReplyFollowUpCadencePlan:
    normalized_intent = str(intent_level or "").strip()
    if normalized_intent in TERMINAL_INTENTS:
        return ReplyFollowUpCadencePlan(pause_existing=True, tasks=())
    if normalized_intent not in ACTIVE_INTENTS:
        return ReplyFollowUpCadencePlan(pause_existing=False, tasks=())

    base_time = _normalize_datetime(occurred_at)
    tasks = []
    for step_code, offset_days, task_type, title, priority in _STEP_DEFINITIONS:
        due_at = base_time + timedelta(days=offset_days)
        tasks.append(
            ReplyFollowUpTaskSpec(
                step_code=step_code,
                task_type=task_type,
                title=f"{step_code} · {title}",
                description=_build_task_description(normalized_intent, next_action, step_code),
                due_at=due_at,
                priority=priority,
                idempotency_key=f"reply-cadence:{source_email_id}:{step_code}",
            )
        )
    return ReplyFollowUpCadencePlan(pause_existing=False, tasks=tuple(tasks))
