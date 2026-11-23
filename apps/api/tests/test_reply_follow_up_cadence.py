from __future__ import annotations

from datetime import datetime, timezone

from ltc.modules.customer_operation.application.reply_follow_up_cadence import build_reply_follow_up_cadence
from ltc.modules.customer_operation.infrastructure.mail_store import PostgresMailStore


class RecordingCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 0

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executions.append((sql, params))
        if "UPDATE ltc.follow_up_task" in sql:
            self.rowcount = 3


def test_reply_follow_up_cadence_builds_d0_to_d10_steps() -> None:
    plan = build_reply_follow_up_cadence(
        intent_level="pricing",
        next_action="Send pricing deck and schedule a 30-minute pricing discussion.",
        source_email_id="email-1",
        occurred_at=datetime(2026, 8, 3, 6, 5, 10, tzinfo=timezone.utc),
    )

    assert plan.pause_existing is False
    assert [step.step_code for step in plan.tasks] == ["D0", "D2", "D5", "D7", "D10"]
    assert [step.task_type for step in plan.tasks] == ["email", "email", "email", "meeting", "email"]
    assert plan.tasks[0].due_at.isoformat() == "2026-08-03T06:05:10+00:00"
    assert plan.tasks[1].due_at.isoformat() == "2026-08-05T06:05:10+00:00"
    assert plan.tasks[-1].due_at.isoformat() == "2026-08-13T06:05:10+00:00"
    assert plan.tasks[0].idempotency_key == "reply-cadence:email-1:D0"


def test_reply_follow_up_cadence_pauses_terminal_intents() -> None:
    plan = build_reply_follow_up_cadence(
        intent_level="won",
        next_action="Record the confirmed deal and prepare customer handoff.",
        source_email_id="email-2",
        occurred_at=datetime(2026, 8, 3, 6, 5, 10, tzinfo=timezone.utc),
    )

    assert plan.pause_existing is True
    assert plan.tasks == ()


def test_mail_store_creates_reply_follow_up_tasks_and_cancels_parent_cadence() -> None:
    cursor = RecordingCursor()
    plan = PostgresMailStore()._create_reply_follow_up_cadence(
        cursor,
        company_id="company-1",
        sales_user_id="sales-1",
        source_email_id="email-2",
        parent_email_id="email-1",
        intent_level="product_question",
        next_action="Reply with product details and propose a technical discussion.",
        occurred_at=datetime(2026, 8, 3, 6, 5, 10, tzinfo=timezone.utc),
    )

    insert_queries = [sql for sql, _ in cursor.executions if "INSERT INTO ltc.follow_up_task" in sql]
    assert len(plan.tasks) == 5
    assert len(insert_queries) == 5
    assert any("UPDATE ltc.follow_up_task" in sql and "status = 'cancelled'" in sql for sql, _ in cursor.executions)
    assert any(params[0:3] == ("company-1", "sales-1", "email-2") for _, params in cursor.executions)


def test_mail_store_terminal_reply_only_cancels_parent_cadence() -> None:
    cursor = RecordingCursor()
    plan = PostgresMailStore()._create_reply_follow_up_cadence(
        cursor,
        company_id="company-1",
        sales_user_id="sales-1",
        source_email_id="email-3",
        parent_email_id="email-2",
        intent_level="won",
        next_action="Record the confirmed deal and prepare customer handoff.",
        occurred_at=datetime(2026, 8, 3, 6, 5, 10, tzinfo=timezone.utc),
    )

    assert plan.pause_existing is True
    assert plan.tasks == ()
    assert any("UPDATE ltc.follow_up_task" in sql for sql, _ in cursor.executions)
    assert not any("INSERT INTO ltc.follow_up_task" in sql for sql, _ in cursor.executions)
