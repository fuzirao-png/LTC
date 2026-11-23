from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sys
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from uuid import UUID

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from ltc.main import create_app
from ltc.platform.config import get_settings
from ltc.modules.customer_operation.application.pa_notification_service import PaNotificationService
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "db" / "seeds").is_dir():
            return parent
    # The unittest Docker image imports this pytest-only module without the
    # repository tree. Keep import-time path resolution valid in that layout.
    return Path("/workspace")


ROOT = _repository_root()
SEED_SQL = ROOT / "db" / "seeds" / "0002_customer_operation_demo.sql"
COMPANY_ID = "22222222-2222-4222-8222-222222222222"
NO_ACTIVITY_COMPANY_ID = "99999999-9999-4999-8999-999999999991"
SALES_ID = "11111111-1111-4111-8111-111111111111"


def _seed_demo_data() -> None:
    with closing(
        psycopg.connect(
            host="127.0.0.1",
            port=55432,
            dbname="ltc",
            user="ltc",
            password="ltc_local_change_me",
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(SEED_SQL.read_text(encoding="utf-8"))
            cur.execute(
                """
                INSERT INTO ltc.customer_operation_owner (company_id, sales_user_id, ownership_source)
                VALUES (%s, %s, 'manual')
                ON CONFLICT (company_id) DO UPDATE SET sales_user_id = EXCLUDED.sales_user_id,
                    ownership_source = EXCLUDED.ownership_source,
                    updated_at = clock_timestamp()
                """,
                (COMPANY_ID, SALES_ID),
            )
        conn.commit()


def _client(*, sales: bool = False) -> TestClient:
    get_settings.cache_clear()
    env = {
        "LTC_DB_HOST": "127.0.0.1",
        "LTC_DB_PORT": "55432",
        "LTC_DB_NAME": "ltc",
        "LTC_DB_USER": "ltc",
        "LTC_DB_PASSWORD": "ltc_local_change_me",
        "INBOUND_MAIL_ENABLED": "false",
    }
    with patch.dict("os.environ", env, clear=False):
        get_settings.cache_clear()
        app = create_app()
        actor = CurrentActor(
            user_id=UUID(SALES_ID if sales else "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            username="sales.test" if sales else "strategic.test",
            display_name="Sales Test" if sales else "Strategic Test",
            account_type="sales" if sales else "strategic",
            sales_tier="MA" if sales else None,
            region_code="EA" if sales else None,
            capacity_limit=10 if sales else None,
            token_version=1,
            capabilities=(),
        )
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            actor=actor,
            session_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        )
        return TestClient(app)


def _seed_company_without_activity() -> None:
    with closing(
        psycopg.connect(
            host="127.0.0.1",
            port=55432,
            dbname="ltc",
            user="ltc",
            password="ltc_local_change_me",
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ltc.company (
                    company_id,
                    company_name,
                    normalized_company_name,
                    lifecycle_status,
                    created_at,
                    updated_at
                ) VALUES (%s, %s, %s, 'prospect', %s, %s)
                ON CONFLICT (company_id) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    normalized_company_name = EXCLUDED.normalized_company_name,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    archived_at = NULL
                """,
                (
                    NO_ACTIVITY_COMPANY_ID,
                    "No Activity Company",
                    "no activity company",
                    "2026-07-29T01:30:00+00:00",
                    "2026-07-29T01:30:00+00:00",
                ),
            )
        conn.commit()


def _delete_company_without_activity() -> None:
    with closing(
        psycopg.connect(
            host="127.0.0.1",
            port=55432,
            dbname="ltc",
            user="ltc",
            password="ltc_local_change_me",
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ltc.company WHERE company_id = %s", (NO_ACTIVITY_COMPANY_ID,))
        conn.commit()


def test_four_layer_customer_operation_routes_read_postgres_loop() -> None:
    _seed_demo_data()
    client = _client()

    operations = client.get(f"/api/v1/customers/{COMPANY_ID}/operations")
    timeline = client.get(f"/api/v1/customers/{COMPANY_ID}/timeline")
    tasks = client.get(f"/api/v1/customers/{COMPANY_ID}/tasks")

    assert operations.status_code == 200
    body = operations.json()["data"]
    assert body["company"]["company_name"] == "Pacific TMC Japan"
    assert body["contacts"][0]["email"] == "james@pacific-tmc.example.com"
    assert [item["direction"] for item in body["emails"]] == ["inbound", "outbound"]
    assert "pricing deck" in body["meetings"][0]["summary"]["next_step"].lower()
    assert body["stage"] == "meeting"

    assert timeline.status_code == 200
    event_types = [item["activity_type"] for item in timeline.json()["items"]]
    assert "meeting_completed" in event_types
    assert "task_created" in event_types
    assert "email_replied" in event_types

    assert tasks.status_code == 200
    assert {item["status"] for item in tasks.json()["items"]} == {"pending"}


def test_four_layer_manual_note_and_export_routes_use_postgres() -> None:
    _seed_demo_data()
    client = _client(sales=True)
    raw_text = "Customer budget is 5 万美元 and CFO is the decision maker."
    fields = [
        {"dimension": "D1.采购意愿.预算区间", "extracted": "5 万美元", "selected": True},
        {"dimension": "D2.决策链.决策人", "extracted": "CFO", "selected": True},
    ]

    with closing(
        psycopg.connect(host="127.0.0.1", port=55432, dbname="ltc", user="ltc", password="ltc_local_change_me")
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ltc.manual_note WHERE raw_text = %s", (raw_text,))
            before_notes = cur.fetchone()[0]

    extracted = client.post(
        f"/api/v1/customers/{COMPANY_ID}/manual-notes/extract",
        json={"rawText": raw_text},
    )
    assert extracted.status_code == 200
    assert isinstance(extracted.json()["fields"], list)

    with closing(
        psycopg.connect(host="127.0.0.1", port=55432, dbname="ltc", user="ltc", password="ltc_local_change_me")
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ltc.manual_note WHERE raw_text = %s", (raw_text,))
            assert cur.fetchone()[0] == before_notes

    created = client.post(
        f"/api/v1/customers/{COMPANY_ID}/manual-notes",
        json={
            "salesId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "rawText": raw_text,
            "extractedFields": fields,
            "confirmStatus": "confirmed",
        },
    )
    assert created.status_code == 200
    note_id = created.json()["note"]["noteId"]
    assert created.json()["note"]["confirmStatus"] == "confirmed"
    assert created.json()["note"]["salesId"] == SALES_ID
    assert created.json()["note"]["extractedFields"] == fields

    with closing(
        psycopg.connect(host="127.0.0.1", port=55432, dbname="ltc", user="ltc", password="ltc_local_change_me")
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extracted_fields_json, confirm_status FROM ltc.manual_note WHERE note_id = %s", (note_id,))
            stored_fields, status = cur.fetchone()
            assert stored_fields == fields
            assert status == "confirmed"
            cur.execute("SELECT count(*) FROM ltc.customer_activity WHERE source_external_key = %s", (f"manual_note:{note_id}",))
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM ltc.audit_log WHERE resource_id = %s AND action = 'manual_note.confirmed'", (note_id,))
            assert cur.fetchone()[0] == 1

    exported = _client().get("/api/v1/internal/customers/export")
    assert exported.status_code == 200
    item = next(item for item in exported.json()["items"] if item["companyName"] == "Pacific TMC Japan")
    assert item["contactCount"] >= 1
    assert item["emailCount"] >= 2
    assert item["meetingCount"] >= 1
    assert item["taskCount"] >= 2


def test_customer_operation_home_cards_include_stage_dates_and_tags() -> None:
    _seed_demo_data()
    client = _client()
    response = client.get("/api/v1/internal/customers/home-cards")
    assert response.status_code == 200

    items = response.json()["items"]
    item = next(item for item in items if item["companyId"] == COMPANY_ID)
    assert item["tag"] == "差旅平台"
    assert item["stageDates"]
    assert item["stageDates"]["acquiredAt"] is not None
    assert item["stageDates"]["emailedAt"] is not None
    assert item["stageDates"]["repliedAt"] is not None
    assert item["stageDates"]["meetingAt"] is not None
    assert item["outboundEmailCount"] == 1
    assert item["inboundEmailCount"] == 1
    assert item["payload"]["outbound_email_count"] == 1
    assert item["payload"]["inbound_email_count"] == 1
    assert item["payload"]["company_name"] == "Pacific TMC Japan"
    assert item["payload"]["legal_name"] == "Pacific TMC Japan Ltd."
    assert item["display_name"] == "Pacific TMC Japan Ltd."
    assert item["payload"]["country_code"] == "JP"
    assert item["payload"]["region_code"] == "EA"
    assert item["payload"]["city"] == "Tokyo"
    assert item["signal"] == f"2封邮件 · {item['payload']['meeting_count']}场会议"
    assert "信号：" not in item["signal"]
    assert "其他" not in item["signal"]


def test_customer_operation_home_cards_fall_back_to_company_created_at() -> None:
    _seed_company_without_activity()
    try:
        client = _client()
        response = client.get("/api/v1/internal/customers/home-cards")
        assert response.status_code == 200

        items = response.json()["items"]
        item = next(item for item in items if item["companyId"] == NO_ACTIVITY_COMPANY_ID)
        assert item["stageDates"]["acquiredAt"] == "2026-07-29T01:30:00+00:00"
    finally:
        _delete_company_without_activity()


def test_customer_operation_email_history_route_reads_seeded_emails() -> None:
    _seed_demo_data()
    client = _client()

    response = client.get(f"/api/v1/customers/{COMPANY_ID}/email-history")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) >= 2
    assert items[0]["subject"]
    assert items[0]["direction"] in {"inbound", "outbound"}

    inbound = next(item for item in items if item["email_id"] == "66666666-6666-4666-8666-666666666666")
    assert inbound["from_address"] == "James Wilson <james@pacific-tmc.example.com>"
    assert inbound["to_address"] == "global.marketing@51tgt.com"
    assert inbound["message_id"] == "<demo-inbound-pacific-tmc@example.com>"
    assert inbound["contact_name"] == "James Wilson"
    assert inbound["contact_email"] == "james@pacific-tmc.example.com"

    outbound = next(item for item in items if item["email_id"] == "44444444-4444-4444-8444-444444444444")
    assert outbound["from_address"] == "global.marketing@51tgt.com"
    assert outbound["to_address"] == "james@pacific-tmc.example.com"


def test_pa_notification_keeps_jump_metadata_for_email_links(tmp_path: Path) -> None:
    service = PaNotificationService(data_dir=tmp_path)

    notification = service.create_from_event(
        {
            "eventType": "imap.received",
            "messageId": "<demo-message-id>",
            "customerName": "Pacific TMC Japan",
            "subject": "Re: Enterprise eSIM pilot for Pacific TMC Japan",
            "from": "james@pacific-tmc.example.com",
            "to": "global.marketing@51tgt.com",
            "notificationTitle": "收到邮件提醒",
            "notificationBody": "客户回复了报价与覆盖问题。",
            "createdAt": "2026-07-22T15:30:00+08:00",
            "companyId": COMPANY_ID,
            "emailId": "66666666-6666-4666-8666-666666666666",
            "notificationTarget": {
                "companyId": COMPANY_ID,
                "emailId": "66666666-6666-4666-8666-666666666666",
                "messageId": "<demo-message-id>",
            },
        }
    )

    assert notification["companyId"] == COMPANY_ID
    assert notification["emailId"] == "66666666-6666-4666-8666-666666666666"
    assert notification["notificationTarget"]["messageId"] == "<demo-message-id>"


def test_pa_notification_mark_read_removes_it_from_unread_list(tmp_path: Path) -> None:
    service = PaNotificationService(data_dir=tmp_path)
    notification = service.create_from_event(
        {
            "eventType": "imap.received",
            "messageId": "<read-test>",
            "customerName": "Pacific TMC Japan",
            "subject": "Read test",
            "from": "james@pacific-tmc.example.com",
            "to": "global.marketing@51tgt.com",
            "notificationTitle": "收到邮件提醒",
            "notificationBody": "Test body",
            "createdAt": "2026-07-22T15:30:00+08:00",
            "companyId": COMPANY_ID,
            "emailId": "66666666-6666-4666-8666-666666666666",
        }
    )

    assert notification["read"] is False
    marked = service.mark_read(notification["id"])
    assert marked["read"] is True
    assert service.list_notifications(role="sales", unread_only=True) == []
