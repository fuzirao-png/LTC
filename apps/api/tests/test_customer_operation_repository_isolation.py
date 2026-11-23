from __future__ import annotations

from ltc.modules.customer_operation.infrastructure.postgres_repository import (
    PostgresCustomerOperationRepository,
)
from ltc.modules.customer_operation.domain.read_models import Contact


class RecordingCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = ()
        self.rows = []

    def execute(self, sql: str, params: tuple) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list:
        return self.rows


def test_meeting_query_filters_by_owner_user_id() -> None:
    cursor = RecordingCursor()
    PostgresCustomerOperationRepository()._list_meetings(cursor, "company-1", "sales-1")
    assert "owner_user_id = %s" in cursor.sql
    assert cursor.params == ("company-1", "sales-1")


def test_task_query_filters_by_assignee_user_id() -> None:
    cursor = RecordingCursor()
    PostgresCustomerOperationRepository()._list_tasks(cursor, "company-1", "sales-1")
    assert "assignee_user_id = %s" in cursor.sql
    assert cursor.params == ("company-1", "sales-1")


def test_activity_query_filters_by_sales_owned_source() -> None:
    cursor = RecordingCursor()
    PostgresCustomerOperationRepository()._list_activities(cursor, "company-1", "sales-1")
    assert "actor_user_id = %s" in cursor.sql
    assert "email_message" in cursor.sql
    assert "meeting" in cursor.sql
    assert "follow_up_task" in cursor.sql
    assert cursor.params == ("company-1", "sales-1", "sales-1", "sales-1", "sales-1")


def test_email_history_only_includes_processed_inbound_and_sent_outbound() -> None:
    cursor = RecordingCursor()

    PostgresCustomerOperationRepository()._list_emails(cursor, "company-1", "sales-1")

    normalized_sql = " ".join(cursor.sql.split())
    assert "e.direction = 'inbound' AND e.status = 'processed'" in normalized_sql
    assert "e.direction = 'outbound' AND e.status IN ('sent', 'delivered', 'opened', 'clicked', 'replied', 'bounced')" in normalized_sql
    assert cursor.params == ("company-1", "sales-1")


def test_contact_query_falls_back_to_source_candidate_email() -> None:
    cursor = RecordingCursor()
    cursor.rows = [("contact-1", "company-1", "Ada Lovelace", "Procurement Manager", "ada@example.com", "decision_maker")]

    contacts = PostgresCustomerOperationRepository()._list_contacts(cursor, "company-1")

    assert "LEFT JOIN ltc.candidate_contact" in cursor.sql
    assert "COALESCE(ct.primary_email, cc.email)" in cursor.sql
    assert contacts[0].email == "ada@example.com"


def test_contact_email_fill_does_not_spread_single_email_to_multiple_contacts(monkeypatch) -> None:
    monkeypatch.setattr(
        PostgresCustomerOperationRepository,
        "_raw_candidate_emails",
        staticmethod(lambda cur, company_id: ["shared@example.com"]),
    )
    contacts = [
        Contact(contact_id="contact-1", company_id="company-1", name="Ada", title="", email="", role=""),
        Contact(contact_id="contact-2", company_id="company-1", name="Grace", title="", email="", role=""),
    ]

    filled = PostgresCustomerOperationRepository._fill_missing_contact_emails(RecordingCursor(), "company-1", contacts)

    assert [item.email for item in filled] == ["", ""]
