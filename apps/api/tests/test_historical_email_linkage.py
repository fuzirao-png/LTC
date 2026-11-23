from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ltc.modules.customer_operation.infrastructure.mail_store import (
    _looks_like_delivery_notification,
    _message_id_matches,
    _normalize_message_id_token,
    _normalize_reply_subject,
)
from ltc.scripts.backfill_historical_email_links import plan_backfill


TENCENT_BOUNCE = """\u5f88\u62b1\u6b49\u60a8\u53d1\u9001\u7684\u90ae\u4ef6\u88ab\u9000\u56de\uff0c\u4ee5\u4e0b\u662f\u8be5\u90ae\u4ef6\u7684\u76f8\u5173\u4fe1\u606f\uff1a
\u88ab\u9000\u56de\u90ae\u4ef6\t\u4e3b \u9898\uff1aExploring eSIM partnership with Hostway Travel
\u65e0\u6cd5\u53d1\u9001\u5230 christiane.pacelli@hostway.travel
\u9000\u4fe1\u539f\u56e0\t\u6536\u4ef6\u4eba\uff08christiane.pacelli@hostway.travel\uff09\u6216\u5176\u6240\u5728\u670d\u52a1\u5546\u62d2\u7edd\u63a5\u6536\u6765\u81ea\u4f60\u90ae\u7bb1\uff08global.marketing@51tgt.com\uff09\u7684\u90ae\u4ef6\u3002
host hostway-travel.mail.protection.outlook.com said: 550 5.4.1 Recipient address rejected: Access denied.
\u89e3\u51b3\u65b9\u6848\t\u8bf7\u8054\u7cfb\u4f60\u7684\u6536\u4ef6\u4eba\u6216\u5176\u6240\u5728\u670d\u52a1\u5546\u3002
"""


class HistoricalEmailLinkageTests(unittest.TestCase):
    def test_normalizes_out_of_office_followed_by_reply_prefix(self) -> None:
        self.assertEqual(
            "exploring esim partnership with bizaway",
            _normalize_reply_subject(
                "Out of office Re: Exploring eSIM partnership with BizAway"
            ),
        )
    def test_normalizes_wrapped_message_id(self) -> None:
        self.assertEqual(_normalize_message_id_token("  <abc@example.com>  "), "abc@example.com")

    def test_matches_gateway_prefixed_in_reply_to(self) -> None:
        self.assertTrue(
            _message_id_matches(
                "<2FB70237E98C12F6+65468cd0-5c58-4709-9b8a-395bcfaf7d3b@51tgt.com>",
                "<65468cd0-5c58-4709-9b8a-395bcfaf7d3b@51tgt.com>",
            )
        )

    def test_normalizes_reply_subject_prefixes(self) -> None:
        self.assertEqual(
            _normalize_reply_subject("Réponse automatique: Re:  Partnership  "),
            "partnership",
        )

    def test_delivery_notification_is_not_treated_as_customer_reply(self) -> None:
        self.assertTrue(
            _looks_like_delivery_notification(
                "Delivery Status Notification (Failure)",
                "Final-Recipient: rfc822; buyer@example.com\nAction: failed",
            )
        )

    def test_plan_backfills_tencent_bounce_by_recipient_and_original_subject(self) -> None:
        inbound = {
            "email_id": "in-bounce-1", "from_address": "postmaster@qq.com",
            "subject": "\u817e\u8baf\u4f01\u4e1a\u90ae\u9000\u4fe1\u901a\u77e5", "body_text": TENCENT_BOUNCE,
            "in_reply_to": "", "company_id": None, "contact_id": None,
            "received_at": datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc), "parent_email_id": None,
        }
        outbound = {
            "email_id": "out-hostway-1", "intended_to_address": "christiane.pacelli@hostway.travel",
            "subject": "Exploring eSIM partnership with Hostway Travel",
            "message_id_header": "<original-hostway@51tgt.com>", "provider_message_id": None,
            "company_id": "company-hostway", "contact_id": "contact-christiane",
            "sent_at": datetime(2026, 8, 28, 7, 0, tzinfo=timezone.utc),
        }
        result = plan_backfill([inbound], [outbound], {"global.marketing@51tgt.com"})
        self.assertEqual([item["inbound_id"] for item in result.matched], ["in-bounce-1"])
        self.assertEqual(result.matched[0]["reason"], "delivery_notification")
        self.assertEqual(result.matched[0]["delivery"]["status"], "hard_bounce")
        self.assertEqual(result.matched[0]["delivery"]["recipients"], ["christiane.pacelli@hostway.travel"])



    def test_matches_provider_message_id_when_header_is_missing(self) -> None:
        inbound = {
            "email_id": "in-2", "from_address": "buyer@example.com", "subject": "Re: Offer",
            "in_reply_to": "<parent-123@ltc.local>", "company_id": "company-1", "contact_id": "contact-1",
            "received_at": datetime(2026, 8, 20, tzinfo=timezone.utc), "parent_email_id": None,
        }
        outbound = {
            "email_id": "out-2", "intended_to_address": "buyer@example.com", "subject": "Offer",
            "message_id_header": None, "provider_message_id": "<parent-123@ltc.local>",
            "company_id": "company-1", "contact_id": "contact-1",
            "sent_at": datetime(2026, 8, 19, tzinfo=timezone.utc),
        }
        result = plan_backfill([inbound], [outbound], {"internal@example.com"})
        self.assertEqual([item["inbound_id"] for item in result.matched], ["in-2"])

    def test_plan_skips_ambiguous_candidates(self) -> None:
        inbound = {
            "email_id": "in-1", "from_address": "buyer@example.com", "subject": "Re: Offer",
            "in_reply_to": "", "company_id": "company-1", "contact_id": "contact-1",
            "received_at": datetime(2026, 8, 20, tzinfo=timezone.utc), "parent_email_id": None,
        }
        outbound_a = {
            "email_id": "out-a", "intended_to_address": "buyer@example.com", "subject": "Offer",
            "message_id_header": "<a@example.com>", "company_id": "company-1", "contact_id": "contact-1",
            "sent_at": datetime(2026, 8, 19, tzinfo=timezone.utc),
        }
        outbound_b = {**outbound_a, "email_id": "out-b", "message_id_header": "<b@example.com>"}
        result = plan_backfill([inbound], [outbound_a, outbound_b], {"internal@example.com"})
        self.assertEqual(result.matched, [])
        self.assertEqual(result.ambiguous, ["in-1"])


if __name__ == "__main__":
    unittest.main()

