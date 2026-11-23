from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ltc.modules.customer_operation.application.email_delivery_service import (
    send_email_for_payload,
)


class EmailDraftSendTests(unittest.TestCase):
    @staticmethod
    def _draft_store() -> Mock:
        draft_store = Mock()
        draft_store.get.return_value = {
            "email_id": "draft-1",
            "company_id": "company-1",
            "contact_id": "contact-1",
            "subject": "Saved subject",
            "body_text": "Saved body",
            "purpose": "reply_followup",
            "status": "draft",
        }
        draft_store.attachment_payloads.return_value = []
        return draft_store

    def test_saved_draft_is_sent_and_same_message_is_marked_sent(self) -> None:
        draft_store = Mock()
        draft_store.get.return_value = {
            "email_id": "draft-1",
            "company_id": "company-1",
            "contact_id": "contact-1",
            "subject": "Saved subject",
            "body_text": "Saved body",
            "purpose": "reply_followup",
            "status": "draft",
        }
        draft_store.attachment_payloads.return_value = [{
            "filename": "proposal.pdf",
            "contentType": "application/pdf",
            "size": 3,
            "content": "YWJj",
        }]
        draft_store.mark_sent.return_value = True

        mail_store = Mock()
        mail_store.resolve_outbound_target.return_value = (
            "Customer",
            "Buyer",
            "buyer@example.com",
        )
        smtp = Mock()
        smtp.send = AsyncMock(return_value={
            "deliveredTo": "buyer@example.com",
            "mode": "mock",
            "provider": "mock",
            "messageId": "message-1",
        })

        with (
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.EmailDraftStore",
                return_value=draft_store,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.PostgresMailStore",
                return_value=mail_store,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.SmtpEmailClient",
                return_value=smtp,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.LegacyFileStore"
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.trigger_customer_analysis_best_effort"
            ) as analysis_trigger,
        ):
            result = asyncio.run(send_email_for_payload({
                "draftId": "draft-1",
                "companyId": "company-1",
                "userId": "sales-1",
                "subject": "Unsaved subject must not win",
                "body": "Unsaved body must not win",
            }))

        draft_store.get.assert_called_once_with(
            email_id="draft-1", sales_user_id="sales-1"
        )
        smtp.send.assert_awaited_once_with(
            recipient_email="buyer@example.com",
            subject="Saved subject",
            body="Saved body",
            attachments=draft_store.attachment_payloads.return_value,
        )
        draft_store.mark_sent.assert_called_once()
        mail_store.record_outbound_email.assert_not_called()
        analysis_trigger.assert_called_once_with("company-1", source="outbound_email")
        self.assertEqual(result["record"]["emailId"], "draft-1")

    def test_failed_delivery_keeps_saved_draft_editable(self) -> None:
        draft_store = self._draft_store()
        mail_store = Mock()
        mail_store.resolve_outbound_target.return_value = (
            "Customer", "Buyer", "buyer@example.com"
        )
        smtp = Mock()
        smtp.send = AsyncMock(side_effect=RuntimeError("smtp unavailable"))

        with (
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.EmailDraftStore",
                return_value=draft_store,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.PostgresMailStore",
                return_value=mail_store,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.SmtpEmailClient",
                return_value=smtp,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "smtp unavailable"):
                asyncio.run(send_email_for_payload({
                    "draftId": "draft-1",
                    "companyId": "company-1",
                    "userId": "sales-1",
                }))

        draft_store.mark_sent.assert_not_called()
        draft_store.mark_failed.assert_not_called()
        mail_store.record_failed_outbound_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
