from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import psycopg

from ltc.modules.customer_operation.application.email_delivery_service import send_email_for_payload
from ltc.modules.customer_operation.application.inbound_mail_service import (
    PROCESSED_FILE,
    InboundEmail,
    InboundMailProcessor,
)
from ltc.modules.customer_operation.infrastructure.mail_store import (
    PostgresMailStore,
    _is_personal_email_domain,
    classify_inbound_message,
)
from ltc.modules.customer_operation.infrastructure.email_attachment_service import EmailAttachmentInput
from ltc.modules.customer_operation.infrastructure.postgres_repository import (
    PostgresCustomerOperationRepository,
)
from ltc.platform.config import get_settings


_ASSERTIONS = unittest.TestCase()


class _Cursor:
    def __init__(self, row=None, *, rows=None) -> None:
        self.row = row
        self.rows = iter(rows) if rows is not None else None
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executions.append((query, params))

    def fetchone(self):
        if self.rows is not None:
            return next(self.rows, None)
        return self.row

    def fetchall(self):
        return []


def test_personal_email_domains_are_not_used_to_create_companies() -> None:
    assert _is_personal_email_domain("buyer@gmail.com")
    assert _is_personal_email_domain("Buyer <buyer@qq.com>")
    assert not _is_personal_email_domain("buyer@company.example")


def test_same_mailbox_message_id_is_deduplicated_across_sales_users() -> None:
    settings = get_settings()
    marker = uuid4().hex
    message_id = f"<{marker}@dedupe.test>"
    store = PostgresMailStore()
    first = store.record_inbound_email(
        from_email=f"buyer-{marker}@qq.com",
        to_email="global.marketing@51tgt.com",
        subject="Re: historical dedupe",
        body_text="Same physical message.",
        body_preview="Same physical message.",
        message_id_header=message_id,
        sales_user_id="a3000000-0000-4000-8000-000000000003",
    )
    second = store.record_inbound_email(
        from_email=f"buyer-{marker}@qq.com",
        to_email="global.marketing@51tgt.com",
        subject="Re: historical dedupe",
        body_text="Same physical message.",
        body_preview="Same physical message.",
        message_id_header=message_id,
        sales_user_id="a4000000-0000-4000-8000-000000000004",
    )
    try:
        assert first is not None
        assert second is not None
        assert first.email_id == second.email_id
        with psycopg.connect(settings.database_dsn) as connection:
            count = connection.execute(
                "SELECT count(*) FROM ltc.email_message WHERE direction='inbound' AND message_id_header=%s",
                (message_id,),
            ).fetchone()[0]
        assert count == 1
    finally:
        with psycopg.connect(settings.database_dsn) as connection:
            connection.execute("DELETE FROM ltc.email_message WHERE message_id_header=%s", (message_id,))
            connection.commit()


def test_inbound_message_classifier_separates_customer_auto_reply_and_dsn() -> None:
    assert classify_inbound_message(subject="Re: proposal", body_text="Please send pricing") == "customer_reply"
    assert classify_inbound_message(subject="Automatic reply: vacation", body_text="I am away") == "automatic_reply"
    assert classify_inbound_message(subject="Delivery Status Notification", body_text="Status: 5.1.1") == "delivery_notification"


def test_unknown_personal_sender_is_preserved_without_company_or_contact() -> None:
    settings = get_settings()
    marker = uuid4().hex
    message_id = f"<{marker}@personal.test>"
    result = PostgresMailStore().record_inbound_email(
        from_email=f"buyer-{marker}@qq.com",
        to_email="sales@example.com",
        subject="Hello",
        body_text="I would like to learn more.",
        body_preview="I would like to learn more.",
        message_id_header=message_id,
    )
    try:
        assert result is not None
        assert result.company_id is None
        assert result.contact_id is None
        with psycopg.connect(settings.database_dsn) as connection:
            row = connection.execute(
                "SELECT company_id, contact_id, message_category FROM ltc.email_message WHERE email_id=%s",
                (result.email_id,),
            ).fetchone()
        assert row == (None, None, "customer_reply")
    finally:
        with psycopg.connect(settings.database_dsn) as connection:
            connection.execute("DELETE FROM ltc.email_message WHERE message_id_header=%s", (message_id,))
            connection.commit()


def test_parse_delivery_notification_extracts_message_id_recipient_and_hard_bounce() -> None:
    result = PostgresMailStore.parse_delivery_notification(
        subject="Undelivered Mail Returned to Sender",
        body_text="Final-Recipient: rfc822; customer@example.com\nAction: failed\nStatus: 5.1.1\nOriginal-Message-ID: <original@example.com>",
    )

    assert result == {
        "message_ids": ["<original@example.com>"],
        "recipients": ["customer@example.com"],
        "status": "hard_bounce",
        "bounce_type": "5xx",
    }


def test_parse_delivery_notification_classifies_soft_bounce() -> None:
    result = PostgresMailStore.parse_delivery_notification(
        subject="Delivery Status Notification",
        body_text="Final-Recipient: rfc822; customer@example.com\nAction: delayed\nStatus: 4.2.0",
    )

    assert result["status"] == "soft_bounce"
    assert result["bounce_type"] == "4xx"


def test_parse_delivery_notification_requires_reconciliation_for_unknown_status() -> None:
    result = PostgresMailStore.parse_delivery_notification(
        subject="Delivery Status Notification",
        body_text="Final-Recipient: rfc822; customer@example.com\nAction: failed\nOriginal-Message-ID: <original@example.com>",
    )

    assert result["status"] == "reconcile_required"
    assert result["bounce_type"] is None


def test_store_email_attachments_persists_asset_and_link() -> None:
    cursor = Mock()
    cursor.fetchone.side_effect = [("asset-1",), ("attachment-1",)]
    stored = Mock(
        storage_key="email-attachments/email-1/offer.txt",
        safe_filename="offer.txt",
        content_type="text/plain",
        size_bytes=12,
        sha256="a" * 64,
        extracted_text="方案一：年度方案",
        extraction_status="extracted",
    )
    service = Mock()
    service.max_message_bytes = 1024
    service.store.return_value = stored
    store = PostgresMailStore()
    store.attachment_service = service

    result = store._store_email_attachments(
        cursor,
        company_id="company-1",
        email_id="email-1",
        attachments=[EmailAttachmentInput("offer.txt", "text/plain", b"proposal")],
        source="imap",
    )

    assert result == [{
        "attachment_id": "attachment-1",
        "media_asset_id": "asset-1",
        "filename": "offer.txt",
        "extracted_text": "方案一：年度方案",
        "extraction_status": "extracted",
    }]
    assert cursor.execute.call_count == 2
    service.store.assert_called_once()


def test_parent_email_lookup_returns_its_company_and_contact() -> None:
    cursor = _Cursor(("email-1", "company-1", "contact-1"))

    result = PostgresMailStore()._find_email_context_by_message_id(cursor, "<parent@example.com>")

    assert result == ("email-1", "company-1", "contact-1")
    query, params = cursor.executions[0]
    assert "SELECT email_id, company_id, contact_id" in query
    assert params == ("<parent@example.com>",)


def test_internal_mailbox_lookup_uses_bound_user_mailboxes() -> None:
    cursor = _Cursor((1,))

    result = PostgresMailStore()._is_internal_mailbox_address(
        cursor, "Global Marketing <GLOBAL.MARKETING@51TGT.COM>"
    )

    assert result is True
    query, params = cursor.executions[0]
    assert "FROM ltc.user_mailbox" in query
    assert params == ("global.marketing@51tgt.com",)


def test_internal_mailbox_cannot_be_created_as_customer_contact() -> None:
    cursor = _Cursor((1,))

    with _ASSERTIONS.assertRaisesRegex(ValueError, "Internal mailbox"):
        PostgresMailStore()._ensure_contact(
            cursor,
            company_id="company-1",
            contact_name="Global Marketing",
            recipient_email="global.marketing@51tgt.com",
        )

    assert len(cursor.executions) == 1


def test_internal_mailbox_with_explicit_manual_contact_is_resolved() -> None:
    store = PostgresMailStore()
    store._find_email_context_by_message_id = Mock(
        return_value=("unrelated-email", "other-company", "other-contact")
    )
    store._is_internal_mailbox_address = Mock(return_value=True)
    store._find_explicit_manual_contact_by_email = Mock(
        return_value=("global-company", "global-contact")
    )

    result = store._resolve_inbound_context(
        _Cursor(),
        from_email="Global Marketing <global.marketing@51tgt.com>",
        in_reply_to="<unrelated-parent@example.com>",
    )

    assert result == (None, "global-company", "global-contact")


def test_internal_mailbox_without_explicit_manual_contact_is_skipped() -> None:
    store = PostgresMailStore()
    store._find_email_context_by_message_id = Mock(return_value=None)
    store._is_internal_mailbox_address = Mock(return_value=True)
    store._find_explicit_manual_contact_by_email = Mock(return_value=None)

    result = store._resolve_inbound_context(
        _Cursor(), from_email="internal@51tgt.com", in_reply_to=None
    )

    assert result is None


def test_explicit_internal_contact_lookup_requires_active_manual_source() -> None:
    cursor = _Cursor(("global-company", "global-contact"))

    result = PostgresMailStore()._find_explicit_manual_contact_by_email(
        cursor, "Global Marketing <GLOBAL.MARKETING@51TGT.COM>"
    )

    assert result == ("global-company", "global-contact")
    query, params = cursor.executions[0]
    assert "ct.source = 'manual'" in query
    assert "ct.status = 'active'" in query
    assert params == ("global.marketing@51tgt.com",)


def test_matching_parent_thread_is_retained_for_explicit_manual_contact() -> None:
    store = PostgresMailStore()
    store._find_email_context_by_message_id = Mock(
        return_value=("global-email", "global-company", "global-contact")
    )
    store._is_internal_mailbox_address = Mock(return_value=True)
    store._find_explicit_manual_contact_by_email = Mock(
        return_value=("global-company", "global-contact")
    )

    result = store._resolve_inbound_context(
        _Cursor(),
        from_email="global.marketing@51tgt.com",
        in_reply_to="<global-parent@example.com>",
    )

    assert result == ("global-email", "global-company", "global-contact")


def test_customer_email_history_excludes_internal_inbound_senders() -> None:
    cursor = _Cursor()

    result = PostgresCustomerOperationRepository()._list_emails(
        cursor, "company-1", "sales-1"
    )

    assert result == []
    query, params = cursor.executions[0]
    assert "FROM ltc.user_mailbox internal_mailbox" in query
    assert "e.direction = 'inbound'" in query
    assert "lower(trim(e.from_address))" in query
    assert "explicit_contact.source = 'manual'" in query
    assert "explicit_contact.contact_id = e.contact_id" in query
    assert params == ("company-1", "sales-1")


def test_internal_mail_is_processed_without_customer_history_or_notification(tmp_path) -> None:
    store = Mock()
    store.is_configured.return_value = True
    store.record_inbound_email.return_value = None
    notifications = Mock()
    processor = InboundMailProcessor(
        data_dir=tmp_path,
        notification_service=notifications,
        sales_user_id="sales-1",
    )
    message = InboundEmail(
        uid="42",
        message_id="<internal@example.com>",
        from_email="global.marketing@51tgt.com",
        to_email="zonglin.yang@51tgt.com",
        subject="Internal reply",
        body_preview="Internal",
        body_text="Internal",
        received_at="2026-07-31T06:05:10+00:00",
    )

    with patch(
        "ltc.modules.customer_operation.application.inbound_mail_service.PostgresMailStore",
        return_value=store,
    ):
        result = processor.process_emails([message])

    assert result == []
    notifications.create_from_event.assert_not_called()
    assert not processor._path(PROCESSED_FILE).exists()
    assert not processor._path("inbound-mail-history.json").exists()


def test_inbound_reply_marks_contact_email_verified_in_database() -> None:
    settings = get_settings()
    marker = uuid4().hex
    company_id = str(uuid4())
    contact_id = str(uuid4())
    email_address = f"buyer-{marker}@example.com"
    received_at = "2026-08-07T06:05:10+00:00"
    store = PostgresMailStore()

    with psycopg.connect(settings.database_dsn) as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ltc.company (
                    company_id, company_name, normalized_company_name,
                    primary_domain, lifecycle_status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, 'prospect', %s, %s)
                """,
                (
                    company_id,
                    f"Buyer {marker}",
                    f"buyer {marker}",
                    f"buyer-{marker}.example",
                    received_at,
                    received_at,
                ),
            )
            cur.execute(
                """
                INSERT INTO ltc.contact (
                    contact_id, company_id, full_name, normalized_name,
                    primary_email, normalized_email, email_status, source,
                    status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'unknown', 'manual', 'active', %s, %s)
                """,
                (
                    contact_id,
                    company_id,
                    "Buyer",
                    "buyer",
                    email_address,
                    email_address,
                    received_at,
                    received_at,
                ),
            )
        connection.commit()

    try:
        result = store.record_inbound_email(
            from_email=email_address,
            to_email="sales@example.com",
            subject="Thanks",
            body_text="Thanks for the reply.",
            body_preview="Thanks for the reply.",
            message_id_header=f"<{marker}@test>",
            received_at=received_at,
            sales_user_id="",
        )
        assert result is not None

        with psycopg.connect(settings.database_dsn) as connection:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT email_status, last_verified_at FROM ltc.contact WHERE contact_id = %s",
                    (contact_id,),
                )
                email_status, last_verified_at = cur.fetchone()

        assert email_status == "valid"
        assert last_verified_at is not None
    finally:
        with psycopg.connect(settings.database_dsn) as connection:
            with connection.cursor() as cur:
                cur.execute("DELETE FROM ltc.follow_up_task WHERE company_id = %s", (company_id,))
                cur.execute("DELETE FROM ltc.customer_activity WHERE company_id = %s", (company_id,))
                cur.execute("DELETE FROM ltc.email_message WHERE company_id = %s", (company_id,))
                cur.execute("DELETE FROM ltc.contact WHERE company_id = %s", (company_id,))
                cur.execute("DELETE FROM ltc.company WHERE company_id = %s", (company_id,))
            connection.commit()


def test_outbound_target_is_resolved_by_company_and_contact_ids() -> None:
    cursor = _Cursor(rows=[
        ("Pacific TMC", "James", "james@example.com", "valid", "active", "allowed"),
        None,
        None,
    ])

    result = PostgresMailStore()._resolve_outbound_target(cursor, "company-1", "contact-1")

    assert result == ("Pacific TMC", "James", "james@example.com")
    query, params = cursor.executions[0]
    assert "ct.contact_id = %s" in query
    assert "ct.company_id = %s" in query
    assert params == ("contact-1", "company-1")


def test_unverified_outbound_contact_is_allowed() -> None:
    cursor = _Cursor(rows=[
        ("Pacific TMC", "James", "james@example.com", "unknown", "active", "allowed"),
        None,
        None,
    ])

    result = PostgresMailStore()._resolve_outbound_target(cursor, "company-1", "contact-1")

    assert result == ("Pacific TMC", "James", "james@example.com")


def test_invalid_outbound_contact_is_blocked() -> None:
    cursor = _Cursor((
        "Pacific TMC", "James", "james@example.com", "invalid", "active", "allowed"
    ))

    with _ASSERTIONS.assertRaisesRegex(ValueError, "invalid"):
        PostgresMailStore()._resolve_outbound_target(cursor, "company-1", "contact-1")


def test_suppressed_outbound_contact_is_blocked() -> None:
    cursor = _Cursor(rows=[
        ("Pacific TMC", "James", "james@example.com", "valid", "active", "allowed"),
        (1,),
    ])

    with _ASSERTIONS.assertRaisesRegex(ValueError, "suppressed"):
        PostgresMailStore()._resolve_outbound_target(cursor, "company-1", "contact-1")


def test_company_outreach_state_does_not_block_outbound_contact() -> None:
    cursor = _Cursor(rows=[
        ("Pacific TMC", "James", "james@example.com", "valid", "active", "allowed"),
        None,
    ])
    result = PostgresMailStore()._resolve_outbound_target(
        cursor, "company-1", "contact-1", purpose="first_touch"
    )

    assert result == ("Pacific TMC", "James", "james@example.com")
    assert all("company_outreach_state" not in query for query, _ in cursor.executions)


def test_customer_reply_locks_contact_without_pausing_company() -> None:
    cursor = _Cursor()
    occurred_at = datetime(2026, 8, 3, tzinfo=timezone.utc)

    PostgresMailStore()._lock_replied_contact(
        cursor,
        company_id="company-1",
        contact_id="contact-1",
        occurred_at=occurred_at,
    )

    assert len(cursor.executions) == 1
    assert "company_outreach_state" not in cursor.executions[0][0]
    assert "engagement_locked=true" in cursor.executions[0][0]
    assert cursor.executions[0][1] == (occurred_at, "company-1", "contact-1")


def test_repeated_unsubscribe_updates_the_active_suppression() -> None:
    cursor = _Cursor()

    PostgresMailStore()._suppress_email_if_needed(
        cursor,
        normalized_email="buyer@example.com",
        email_id="email-2",
        intent_level="unsubscribe",
        occurred_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    query, _ = cursor.executions[0]
    assert "ON CONFLICT (normalized_email) WHERE status = 'active'" in query
    assert "DO UPDATE SET source_email_id = EXCLUDED.source_email_id" in query


def test_send_uses_database_contact_ids_before_smtp_without_real_delivery() -> None:
    store = Mock()
    store.resolve_outbound_target.return_value = (
        "Pacific TMC Japan",
        "James Wilson",
        "james@pacific-tmc.example.com",
    )
    store.is_configured.return_value = True
    store.record_outbound_email.return_value = Mock(
        company_id="company-1", contact_id="contact-1", email_id="email-1"
    )
    smtp = Mock()
    smtp.send = AsyncMock(return_value={
        "deliveredTo": "james@pacific-tmc.example.com",
        "mode": "mock",
        "provider": "mock",
        "messageId": "message-1",
    })

    with (
        patch(
            "ltc.modules.customer_operation.application.email_delivery_service.PostgresMailStore",
            return_value=store,
        ),
        patch(
            "ltc.modules.customer_operation.application.email_delivery_service.SmtpEmailClient",
            return_value=smtp,
        ),
        patch(
            "ltc.modules.customer_operation.application.email_delivery_service.LegacyFileStore"
        ) as legacy_store,
        patch(
            "ltc.modules.customer_operation.application.email_delivery_service.trigger_customer_analysis_best_effort"
        ) as analysis_trigger,
    ):
        result = asyncio.run(send_email_for_payload({
            "companyId": "company-1",
            "contactId": "contact-1",
            "customerName": "wrong company",
            "recipientName": "wrong contact",
            "recipientEmail": "wrong@example.com",
            "subject": "Subject",
            "body": "Body",
        }))

    store.resolve_outbound_target.assert_called_once_with(
        "company-1", "contact-1", "first_touch"
    )
    smtp.send.assert_awaited_once_with(
        recipient_email="james@pacific-tmc.example.com",
        subject="Subject",
        body="Body",
        attachments=[],
    )
    legacy_store.return_value.append_mail_record.assert_called_once()
    analysis_trigger.assert_called_once_with("company-1", source="outbound_email")
    assert result["record"]["companyId"] == "company-1"
    assert result["record"]["contactId"] == "contact-1"


def test_existing_inbound_email_does_not_retrigger_notification_or_analysis(tmp_path) -> None:
    store = Mock()
    store.is_configured.return_value = True
    store.record_inbound_email.return_value = Mock(
        company_id="00000000-0000-0000-0000-000000000041",
        email_id="00000000-0000-0000-0000-000000000051",
        created=False,
    )
    notifications = Mock()
    processor = InboundMailProcessor(
        data_dir=tmp_path,
        notification_service=notifications,
        sales_user_id="sales-1",
    )
    message = InboundEmail(
        uid="43",
        message_id="<customer@example.com>",
        from_email="buyer@example.com",
        to_email="sales@example.com",
        subject="Budget confirmed",
        body_preview="Budget is USD 50,000.",
        body_text="Budget is USD 50,000 and the CFO approves it.",
        received_at="2026-08-05T00:00:00+00:00",
    )

    with (
        patch(
            "ltc.modules.customer_operation.application.inbound_mail_service.PostgresMailStore",
            return_value=store,
        ),
        patch(
            "ltc.modules.customer_operation.application.inbound_mail_service.trigger_customer_analysis_best_effort"
        ) as analysis_trigger,
    ):
        result = processor.process_emails([message])

    assert result == []
    notifications.get_notification.assert_not_called()
    analysis_trigger.assert_not_called()


def test_associated_inbound_email_triggers_customer_analysis(tmp_path) -> None:
    store = Mock()
    store.is_configured.return_value = True
    store.record_inbound_email.return_value = Mock(
        company_id="00000000-0000-0000-0000-000000000041",
        email_id="00000000-0000-0000-0000-000000000051",
        created=True,
    )
    notifications = Mock()
    notifications.get_notification.return_value = None
    processor = InboundMailProcessor(
        data_dir=tmp_path,
        notification_service=notifications,
        sales_user_id="sales-1",
    )
    message = InboundEmail(
        uid="43",
        message_id="<customer@example.com>",
        from_email="buyer@example.com",
        to_email="sales@example.com",
        subject="Budget confirmed",
        body_preview="Budget is USD 50,000.",
        body_text="Budget is USD 50,000 and the CFO approves it.",
        received_at="2026-08-04T06:05:10+00:00",
    )

    with (
        patch(
            "ltc.modules.customer_operation.application.inbound_mail_service.PostgresMailStore",
            return_value=store,
        ),
        patch(
            "ltc.modules.customer_operation.application.inbound_mail_service.trigger_customer_analysis_best_effort"
        ) as analysis_trigger,
    ):
        processor.process_emails([message])

    analysis_trigger.assert_called_once_with(
        "00000000-0000-0000-0000-000000000041",
        source="inbound_email",
    )


_TMP_PATH_TESTS = {
    "test_internal_mail_is_processed_without_customer_history_or_notification",
    "test_associated_inbound_email_triggers_customer_analysis",
    "test_existing_inbound_email_does_not_retrigger_notification_or_analysis",
}


def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for name, test in list(globals().items()):
        if not name.startswith("test_") or not callable(test):
            continue
        if name in _TMP_PATH_TESTS:
            def run_with_temp_path(test=test):
                with TemporaryDirectory() as temp_dir:
                    test(Path(temp_dir))

            runnable = run_with_temp_path
        else:
            runnable = test
        suite.addTest(unittest.FunctionTestCase(runnable, description=name))
    return suite


def test_parse_tencent_bounce_extracts_recipient_subject_and_reason() -> None:
    result = PostgresMailStore.parse_delivery_notification(
        subject="腾讯企业邮退信通知",
        body_text=(
            "很抱歉您发送的邮件被退回，以下是该邮件的相关信息：\n"
            "被退回邮件\t主 题：Exploring eSIM partnership with Hostway Travel\n"
            "无法发送到 christiane.pacelli@hostway.travel\n"
            "退信原因\t收件人或其所在服务商拒绝接收。\n"
            "host hostway-travel.mail.protection.outlook.com said: 550 5.4.1 Recipient address rejected: Access denied"
        ),
    )
    assert result["status"] == "hard_bounce"
    assert result["bounce_type"] == "5xx"
    assert result["recipients"] == ["christiane.pacelli@hostway.travel"]
    assert result["original_subject"] == "Exploring eSIM partnership with Hostway Travel"
    assert "拒绝接收" in result["reason"]
