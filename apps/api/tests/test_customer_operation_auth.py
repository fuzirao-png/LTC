from __future__ import annotations

import base64
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
from ltc.modules.customer_operation.infrastructure.email_draft_store import DraftVersionConflict
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


def _actor(account_type: str) -> CurrentActor:
    is_sales = account_type == "sales"
    return CurrentActor(
        uuid4(),
        f"{account_type}.actor",
        "API Actor",
        account_type,
        "MA" if is_sales else None,
        "EA" if is_sales else None,
        10 if is_sales else None,
        1,
        (),
    )


def _app(service: Mock) -> FastAPI:
    app = FastAPI()
    app.include_router(build_customer_operation_router(service), prefix="/api/v1")
    return app


class CustomerOperationAuthTests(unittest.TestCase):
    def test_sales_cannot_access_customer_operation_routes_without_ownership(self) -> None:
        service = Mock()
        service.can_sales_access_company.return_value = False
        actor = _actor("sales")
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, uuid4())
        company_id = uuid4()

        requests = (
            ("GET", f"/api/v1/customers/{company_id}/operations", None),
            ("GET", f"/api/v1/customers/{company_id}/timeline", None),
            ("GET", f"/api/v1/customers/{company_id}/tasks", None),
            ("GET", f"/api/v1/customers/{company_id}/email-history", None),
            ("POST", f"/api/v1/customers/{company_id}/manual-notes/extract", {"rawText": "private"}),
            ("POST", f"/api/v1/customers/{company_id}/manual-notes", {"rawText": "private"}),
        )

        with TestClient(app) as client:
            for method, path, payload in requests:
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, json=payload)
                    self.assertEqual(response.status_code, 404, response.text)

        self.assertEqual(service.can_sales_access_company.call_count, len(requests))
        self.assertFalse(service.get_customer_operations.called)
        self.assertFalse(service.list_timeline.called)
        self.assertFalse(service.list_tasks.called)
        self.assertFalse(service.list_email_history.called)
        self.assertFalse(service.extract_manual_note_fields.called)
        self.assertFalse(service.create_manual_note.called)

    def test_sales_customer_reads_pass_sales_user_id_to_service(self) -> None:
        service = Mock()
        service.can_sales_access_company.return_value = True
        company_id = uuid4()
        service.get_customer_operations.return_value = {
            "company": {"company_id": str(company_id), "company_name": "Owned"},
            "contacts": [],
            "emails": [],
            "meetings": [],
            "tasks": [],
            "activities": [],
            "stage": "assigned",
        }
        service.list_timeline.return_value = []
        service.list_tasks.return_value = []
        actor = _actor("sales")
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, uuid4())

        with TestClient(app) as client:
            self.assertEqual(client.get(f"/api/v1/customers/{company_id}/operations").status_code, 200)
            self.assertEqual(client.get(f"/api/v1/customers/{company_id}/timeline").status_code, 200)
            self.assertEqual(client.get(f"/api/v1/customers/{company_id}/tasks").status_code, 200)

        sales_user_id = str(actor.user_id)
        service.get_customer_operations.assert_called_once_with(company_id, sales_user_id=sales_user_id)
        service.list_timeline.assert_called_once_with(company_id, sales_user_id=sales_user_id)
        service.list_tasks.assert_called_once_with(company_id, sales_user_id=sales_user_id)

    def test_inbound_mail_notifications_require_authentication(self) -> None:
        app = _app(Mock())

        with TestClient(app) as client:
            response = client.get("/api/v1/inbound-mail/notifications")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "AUTH_INVALID_SESSION")


    def test_customer_operation_compatibility_routes_require_authentication(self) -> None:
        service = Mock()
        app = _app(service)
        company_id = uuid4()
        note_id = uuid4()
        requests = (
            ("GET", f"/api/v1/customers/{company_id}/operations", None),
            ("GET", f"/api/v1/customers/{company_id}/timeline", None),
            ("GET", f"/api/v1/customers/{company_id}/tasks", None),
            ("GET", f"/api/v1/customers/{company_id}/email-history", None),
            ("POST", f"/api/v1/customers/{company_id}/manual-notes", {"rawText": "private note"}),
            ("POST", f"/api/v1/customers/{company_id}/manual-notes/extract", {"rawText": "private note"}),
            ("PATCH", f"/api/v1/manual-notes/{note_id}", {"confirmStatus": "confirmed"}),
            ("GET", "/api/v1/internal/customers/export", None),
            ("POST", "/api/v1/email/translate", {"body": "private email"}),
            (
                "POST",
                "/api/v1/customer-operation/email/agent",
                {"companyId": str(company_id), "contactId": str(uuid4()), "operation": "generate"},
            ),
            ("GET", "/api/v1/meeting/job?id=private-job", None),
            ("POST", "/api/v1/meeting/upload", {"fileName": "private.wav"}),
            ("GET", "/api/v1/meeting/audio?id=private-meeting", None),
        )

        with TestClient(app) as client:
            for method, path, payload in requests:
                with self.subTest(method=method, path=path):
                    response = client.request(method, path, json=payload)
                    self.assertEqual(response.status_code, 401, response.text)
                    self.assertEqual(response.json()["detail"]["code"], "AUTH_INVALID_SESSION")

        self.assertEqual(service.mock_calls, [])

    def test_sales_email_agent_requires_company_access(self) -> None:
        service = Mock()
        service.can_sales_access_company.return_value = False
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())

        with patch("ltc.modules.customer_operation.interfaces.router.run_email_agent_for_payload") as run_agent:
            response = TestClient(app).post(
                "/api/v1/customer-operation/email/agent",
                json={
                    "companyId": str(uuid4()),
                    "contactId": str(uuid4()),
                    "operation": "generate",
                },
            )

        self.assertEqual(response.status_code, 404)
        run_agent.assert_not_called()

    def test_email_agent_injects_authenticated_sales_identity(self) -> None:
        company_id = uuid4()
        service = Mock()
        service.can_sales_access_company.return_value = True
        actor = _actor("sales")
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, uuid4())
        result = {"success": True, "agent": "email-agent", "subject": "S", "body": "B"}

        with patch(
            "ltc.modules.customer_operation.interfaces.router.run_email_agent_for_payload",
            new=AsyncMock(return_value=result),
        ) as run_agent:
            response = TestClient(app).post(
                "/api/v1/customer-operation/email/agent",
                json={
                    "companyId": str(company_id),
                    "contactId": str(uuid4()),
                    "operation": "generate",
                    "salesName": "Spoofed Name",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = run_agent.await_args.args[0]
        self.assertEqual(payload["salesName"], actor.display_name)
        self.assertEqual(payload["salesUserId"], str(actor.user_id))


    def test_authenticated_sales_can_read_inbound_mail_notifications(self) -> None:
        service = Mock()
        service.list_notifications.return_value = []
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())

        with TestClient(app) as client:
            response = client.get("/api/v1/inbound-mail/notifications")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "items": []})


    def test_authenticated_sales_can_send_multipart_email_with_attachment(self) -> None:
        app = _app(Mock())
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())
        delivery_result = {
            "success": True,
            "message": "sent",
            "record": {"messageId": "<p0-07@example.test>"},
        }

        with patch(
            "ltc.modules.customer_operation.interfaces.router.send_email_for_payload",
            new=AsyncMock(return_value=delivery_result),
        ) as send_email:
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/email/send",
                    data={
                        "companyId": str(uuid4()),
                        "contactId": str(uuid4()),
                        "purpose": "reply_followup",
                        "draftId": str(uuid4()),
                        "customerName": "Example Co",
                        "recipientName": "Alex",
                        "recipientEmail": "alex@example.com",
                        "subject": "Attachment contract",
                        "body": "Please see the attachment.",
                    },
                    files={"attachments": ("acceptance-note.txt", b"acceptance attachment", "text/plain")},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), delivery_result)
        self.assertEqual(response.json()["record"]["messageId"], "<p0-07@example.test>")
        payload = send_email.await_args.args[0]
        self.assertEqual(payload["attachments"], [{
            "filename": "acceptance-note.txt",
            "content": base64.b64encode(b"acceptance attachment").decode("ascii"),
            "contentType": "text/plain",
            "size": 21,
        }])
        self.assertEqual(payload["recipientEmail"], "alex@example.com")
        self.assertTrue(payload["companyId"])
        self.assertTrue(payload["contactId"])
        self.assertEqual(payload["purpose"], "reply_followup")
        self.assertTrue(payload["draftId"])
        self.assertTrue(payload["userId"])

    def test_sales_email_draft_list_is_isolated_by_user(self) -> None:
        service = Mock()
        service.can_sales_access_company.return_value = True
        service.email_drafts.return_value = []
        actor = _actor("sales")
        company_id = uuid4()
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, uuid4())

        with TestClient(app) as client:
            response = client.get(f"/api/v1/customers/{company_id}/email-drafts")

        self.assertEqual(response.status_code, 200)
        service.email_drafts.assert_called_once_with(company_id, str(actor.user_id))

    def test_strategic_user_cannot_use_sales_email_drafts(self) -> None:
        service = Mock()
        company_id = uuid4()
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("strategic"), uuid4())

        with TestClient(app) as client:
            response = client.get(f"/api/v1/customers/{company_id}/email-drafts")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "FORBIDDEN_SALES_REQUIRED")

    def test_email_draft_update_returns_version_conflict(self) -> None:
        service = Mock()
        service.update_email_draft.side_effect = DraftVersionConflict("stale")
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())
        email_id = uuid4()

        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/email-drafts/{email_id}",
                headers={"If-Match": "2"},
                json={
                    "contactId": str(uuid4()),
                    "subject": "Subject",
                    "body": "Body",
                    "purpose": "first_touch",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "DRAFT_VERSION_CONFLICT")


    def test_mailbox_monitor_configuration_requires_strategic_role(self) -> None:
        service = Mock()
        service.list_mailbox_monitors.return_value = []
        app = _app(service)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())

        with TestClient(app) as client:
            forbidden = client.get("/api/v1/inbound-mail/monitors")

            app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("strategic"), uuid4())
            allowed = client.get("/api/v1/inbound-mail/monitors")

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["detail"]["code"], "FORBIDDEN_STRATEGIC_REQUIRED")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json(), {"success": True, "items": []})


if __name__ == "__main__":
    unittest.main()
