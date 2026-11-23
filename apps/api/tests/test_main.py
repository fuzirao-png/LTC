from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from ltc.main import _build_inbound_mail_pollers, create_app
from ltc.modules.customer_analysis.infrastructure.bootstrap import postgres_connection_factory
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.platform.config import AppSettings


class MainAppTests(unittest.TestCase):
    @patch('psycopg.connect')
    def test_customer_analysis_connection_factory_uses_runtime_settings(self, connect: Mock) -> None:
        settings = AppSettings(
            database_host='db.example',
            database_port=55432,
            database_name='ltc_test',
            database_user='tester',
            database_password='secret',
            database_sslmode='prefer',
        )

        connection_factory = postgres_connection_factory(settings)
        connection_factory()

        connect.assert_called_once_with(settings.database_dsn)

    @patch('ltc.main.build_local_container')
    def test_create_app_passes_customer_analysis_connection_factory_from_settings(self, build_container: Mock) -> None:
        settings = AppSettings(
            database_host='db.example',
            database_port=55432,
            database_name='ltc_test',
            database_user='tester',
            database_password='secret',
            database_sslmode='prefer',
        )
        build_container.return_value = Mock(service=Mock())

        create_app(settings=settings)

        connection_factory = build_container.call_args.kwargs.get('connection_factory')
        self.assertTrue(callable(connection_factory))
        with patch('psycopg.connect') as connect:
            connection_factory()
        connect.assert_called_once_with(settings.database_dsn)

    def test_live_health_endpoint_returns_runtime_status(self) -> None:
        client = TestClient(create_app())

        response = client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("environment", response.json())
        self.assertIn("modules", response.json())

    def test_auth_me_endpoint_requires_authentication(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 401)

    def test_logout_returns_no_content_and_clears_session_cookies(self) -> None:
        app = create_app()
        service = Mock()
        app.state.iam_authentication_service = service
        session_id = uuid4()
        actor = CurrentActor(
            user_id=uuid4(),
            username="sales.test",
            display_name="Sales Test",
            account_type="sales",
            sales_tier="MA",
            region_code="EA",
            capacity_limit=10,
            token_version=1,
            capabilities=(),
        )
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, session_id)
        client = TestClient(app)
        client.cookies.set("ltc_access_token", "access-token")
        client.cookies.set("ltc_refresh_token", "refresh-token")

        response = client.post("/api/v1/auth/logout")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        service.logout.assert_called_once_with(session_id)
        set_cookie_headers = response.headers.get_list("set-cookie")
        self.assertTrue(any(header.startswith("ltc_access_token=") and "Max-Age=0" in header for header in set_cookie_headers))
        self.assertTrue(any(header.startswith("ltc_refresh_token=") and "Max-Age=0" in header for header in set_cookie_headers))

    @patch('ltc.main.list_enabled_mailbox_monitors')
    def test_inbound_pollers_share_default_notification_store(self, list_monitors: Mock) -> None:
        list_monitors.return_value = [{
            "host": "imap.example.com",
            "port": 993,
            "username": "sales@example.com",
            "secretValue": "secret",
            "mailboxName": "INBOX",
            "salesUserId": "sales-1",
            "pollSeconds": 60,
        }]

        pollers = _build_inbound_mail_pollers(AppSettings(inbound_mail_enabled=True))

        self.assertEqual(len(pollers), 1)
        self.assertIsNone(pollers[0].processor.data_dir)
        self.assertIsNone(pollers[0].processor.notification_service.data_dir)


if __name__ == "__main__":
    unittest.main()
