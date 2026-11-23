from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID
from uuid import uuid4

import psycopg


def test_mail_credential_cipher_round_trip() -> None:
    from cryptography.fernet import Fernet

    from ltc.modules.customer_operation.infrastructure.mail_credential_cipher import MailCredentialCipher

    cipher = MailCredentialCipher(Fernet.generate_key().decode("ascii"))
    encrypted = cipher.encrypt("mail-secret")

    assert encrypted != "mail-secret"
    assert cipher.decrypt(encrypted) == "mail-secret"


def test_mail_credential_cipher_requires_key() -> None:
    from ltc.modules.customer_operation.infrastructure.mail_credential_cipher import MailCredentialCipher

    with unittest.TestCase().assertRaisesRegex(RuntimeError, "LTC_MAIL_CREDENTIAL_KEY"):
        MailCredentialCipher("")


def test_notifications_are_filtered_by_sales_user(tmp_path: Path) -> None:
    from ltc.modules.customer_operation.application.pa_notification_service import PaNotificationService

    service = PaNotificationService(data_dir=tmp_path)
    service.create_from_event({"messageId": "one", "salesUserId": "sales-a"})
    service.create_from_event({"messageId": "two", "salesUserId": "sales-b"})

    items = service.list_notifications(user_id="sales-a")

    assert [item["messageId"] for item in items] == ["one"]


def test_strategic_account_can_access_sales_mail_notifications() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
    from ltc.modules.iam.domain.models import CurrentActor
    from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

    actor = CurrentActor(
        user_id=UUID("55555555-5555-4555-8555-555555555555"),
        username="strategy.ops",
        display_name="Strategy Ops",
        account_type="strategic",
        sales_tier=None,
        region_code=None,
        capacity_limit=None,
        token_version=0,
        capabilities=(),
    )
    service = Mock()
    service.list_notifications.return_value = [{"id": "sales-mail"}]
    app = FastAPI()
    app.include_router(build_customer_operation_router(service))
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        actor=actor,
        session_id=UUID("66666666-6666-4666-8666-666666666666"),
    )
    client = TestClient(app)

    listed = client.get("/inbound-mail/notifications")
    marked = client.patch("/inbound-mail/notifications/sales-mail/read")
    detail = client.get("/inbound-mail/notifications/sales-mail")

    assert listed.status_code == 200
    assert listed.json()["items"] == [{"id": "sales-mail"}]
    service.list_notifications.assert_called_once_with(role="sales", unread_only=False, user_id="")
    assert marked.status_code == 403
    assert detail.status_code == 404


def test_send_route_overrides_payload_user_with_authenticated_actor() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
    from ltc.modules.iam.domain.models import CurrentActor
    from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

    actor = CurrentActor(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        username="sales.a",
        display_name="Sales A",
        account_type="sales",
        sales_tier="MA",
        region_code="EA",
        capacity_limit=100,
        token_version=0,
        capabilities=(),
    )
    app = FastAPI()
    app.include_router(build_customer_operation_router(object()))
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        actor=actor,
        session_id=UUID("22222222-2222-4222-8222-222222222222"),
    )

    async def fake_send(payload: dict) -> dict:
        return {"success": True, "userId": payload.get("userId")}

    with patch("ltc.modules.customer_operation.interfaces.router.send_email_for_payload", side_effect=fake_send):
        response = TestClient(app).post(
            "/email/send",
            json={
                "customerName": "Customer",
                "recipientName": "Recipient",
                "recipientEmail": "recipient@example.com",
                "subject": "Subject",
                "body": "Body",
                "userId": "attacker-user",
            },
        )

    assert response.status_code == 200
    assert response.json()["userId"] == str(actor.user_id)


def test_mail_ownership_scopes_customer_home_cards() -> None:
    from ltc.modules.customer_operation.infrastructure.mail_store import PostgresMailStore
    from ltc.modules.customer_operation.infrastructure.postgres_customer_home_card_store import PostgresCustomerHomeCardStore
    from ltc.platform.config import get_settings

    settings = get_settings()
    marker = uuid4().hex
    subjects = [f"owner-li-{marker}", f"owner-zong-{marker}"]
    with psycopg.connect(settings.database_dsn) as connection:
        users = dict(
            connection.execute(
                "SELECT username, user_id::text FROM ltc.user_account WHERE username IN ('li.ming', 'zong.lin')"
            ).fetchall()
        )

    store = PostgresMailStore()
    stored = [
        store.record_inbound_email(
            from_email=f"buyer@li-{marker}.example",
            to_email="global.marketing@51tgt.com",
            subject=subjects[0],
            body_text="test",
            body_preview="test",
            message_id_header=f"<{subjects[0]}@test>",
            sales_user_id=users["li.ming"],
        ),
        store.record_inbound_email(
            from_email=f"buyer@zong-{marker}.example",
            to_email="zonglin.yang@51tgt.com",
            subject=subjects[1],
            body_text="test",
            body_preview="test",
            message_id_header=f"<{subjects[1]}@test>",
            sales_user_id=users["zong.lin"],
        ),
    ]
    try:
        home_store = PostgresCustomerHomeCardStore()
        li_ids = {item["companyId"] for item in home_store.list_home_cards(owner_user_id=users["li.ming"])}
        zong_ids = {item["companyId"] for item in home_store.list_home_cards(owner_user_id=users["zong.lin"])}

        assert stored[0].company_id in li_ids
        assert stored[0].company_id not in zong_ids
        assert stored[1].company_id in zong_ids
        assert stored[1].company_id not in li_ids
    finally:
        company_ids = [item.company_id for item in stored]
        with psycopg.connect(settings.database_dsn) as connection:
            connection.execute("DELETE FROM ltc.follow_up_task WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.customer_activity WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.email_message WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.contact WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.company WHERE company_id = ANY(%s)", (company_ids,))
            connection.commit()


def test_generate_route_uses_authenticated_sales_display_name() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
    from ltc.modules.iam.domain.models import CurrentActor
    from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

    actor = CurrentActor(
        user_id=UUID("33333333-3333-4333-8333-333333333333"),
        username="zong.lin",
        display_name="Zong Lin",
        account_type="sales",
        sales_tier="MA",
        region_code="NA",
        capacity_limit=100,
        token_version=0,
        capabilities=(),
    )
    app = FastAPI()
    app.include_router(build_customer_operation_router(object()))
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        actor=actor,
        session_id=UUID("44444444-4444-4444-8444-444444444444"),
    )

    async def fake_generate(payload: dict) -> dict:
        return {"success": True, "salesName": payload.get("salesName")}

    with patch("ltc.modules.customer_operation.interfaces.router.generate_email_for_payload", side_effect=fake_generate):
        response = TestClient(app).post(
            "/email/generate",
            json={
                "customerName": "Customer",
                "recipientName": "Recipient",
                "recipientEmail": "recipient@example.com",
                "salesName": "Li Ming",
            },
        )

    assert response.status_code == 200
    assert response.json()["salesName"] == "Zong Lin"


def test_email_generation_context_and_prompt_include_sales_display_name() -> None:
    from ltc.modules.customer_operation.infrastructure.email_context_builder import build_email_generation_memory
    from ltc.modules.customer_operation.skills.email_generate_skill import EmailGenerateSkill

    context = build_email_generation_memory(
        {
            "customerName": "Customer",
            "recipientName": "Recipient",
            "recipientEmail": "recipient@example.com",
            "salesName": "Zong Lin",
        }
    )
    captured: dict[str, str] = {}

    async def fake_chat_json(*, system_prompt: str, user_prompt: str) -> dict:
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return {"subject": "Subject", "body": "Body\n\nZong Lin"}

    with patch(
        "ltc.modules.customer_operation.skills.email_generate_skill.LlmClient.chat_json",
        side_effect=fake_chat_json,
    ):
        asyncio.run(EmailGenerateSkill().run(context))

    assert context["salesName"] == "Zong Lin"
    assert "Salesperson display name: Zong Lin" in captured["user_prompt"]
    assert "End with the exact salesperson display name" in captured["system_prompt"]


def test_customer_operation_does_not_show_demo_customers_for_empty_results() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "web"
        / "src"
        / "features"
        / "customer-operation"
        / "CustomerOperation.vue"
    ).read_text(encoding="utf-8")

    assert "return fallbackCustomers;" not in source


def test_home_card_email_counts_only_include_current_sales_mail() -> None:
    from ltc.modules.customer_operation.infrastructure.mail_store import PostgresMailStore
    from ltc.modules.customer_operation.infrastructure.postgres_customer_home_card_store import PostgresCustomerHomeCardStore
    from ltc.platform.config import get_settings

    settings = get_settings()
    marker = uuid4().hex
    sender = f"shared@shared-{marker}.example"
    with psycopg.connect(settings.database_dsn) as connection:
        users = dict(
            connection.execute(
                "SELECT username, user_id::text FROM ltc.user_account WHERE username IN ('li.ming', 'zong.lin')"
            ).fetchall()
        )

    store = PostgresMailStore()
    li_mail = store.record_inbound_email(
        from_email=sender,
        to_email="global.marketing@51tgt.com",
        subject=f"shared-li-{marker}",
        body_text="li",
        body_preview="li",
        message_id_header=f"<shared-li-{marker}@test>",
        sales_user_id=users["li.ming"],
    )
    zong_mail = store.record_inbound_email(
        from_email=sender,
        to_email="zonglin.yang@51tgt.com",
        subject=f"shared-zong-{marker}",
        body_text="zong",
        body_preview="zong",
        message_id_header=f"<shared-zong-{marker}@test>",
        sales_user_id=users["zong.lin"],
    )
    try:
        item = next(
            card
            for card in PostgresCustomerHomeCardStore().list_home_cards(owner_user_id=users["zong.lin"])
            if card["companyId"] == zong_mail.company_id
        )

        assert item["inboundEmailCount"] == 1
        assert item["outboundEmailCount"] == 0
        assert item["payload"]["email_count"] == 1
        assert item["latestTitle"] == f"shared-zong-{marker}"
    finally:
        company_ids = [li_mail.company_id]
        with psycopg.connect(settings.database_dsn) as connection:
            connection.execute("DELETE FROM ltc.follow_up_task WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.customer_activity WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.email_message WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.contact WHERE company_id = ANY(%s)", (company_ids,))
            connection.execute("DELETE FROM ltc.company WHERE company_id = ANY(%s)", (company_ids,))
            connection.commit()


def test_home_cards_exclude_internal_and_mail_provider_domains() -> None:
    from ltc.modules.customer_operation.infrastructure.postgres_customer_home_card_store import PostgresCustomerHomeCardStore
    from ltc.platform.config import get_settings

    settings = get_settings()
    with psycopg.connect(settings.database_dsn) as connection:
        zong_user_id = str(
            connection.execute("SELECT user_id FROM ltc.user_account WHERE username = 'zong.lin'").fetchone()[0]
        )

    company_names = {
        str(item["companyName"]).lower()
        for item in PostgresCustomerHomeCardStore().list_home_cards(owner_user_id=zong_user_id)
    }

    assert "51tgt.com" not in company_names
    assert "exmail.weixin.qq.com" not in company_names
