import unittest
from unittest.mock import patch

from ltc.modules.lead_intelligence.infrastructure.email_automation_store import (
    effective_failed_count,
    effective_sent_count,
    build_failure_summary,
    build_reply_summary,
    normalize_reply_detail,
    normalize_failure_detail,
    effective_candidate_count,
    effective_touch_count,
    rebuild_failure_details,
    effective_run_status,
    EmailAutomationStore,
)


class EmailAutomationFailureTests(unittest.TestCase):
    def test_effective_candidate_count_uses_processed_details_when_record_is_zero(self):
        self.assertEqual(
            effective_candidate_count(0, [
                {"status": "failed", "contactId": "contact-1"},
                {"status": "sent", "contactId": "contact-2"},
                {"status": "skipped", "contactId": "contact-3"},
            ]),
            3,
        )

    def test_rebuilds_unfinished_reserved_touches_as_failures(self):
        result = rebuild_failure_details([], [
            ("company-1", "Hotelbeds", "contact-1", "Unfinished", "unfinished@example.com", None, "reserved"),
        ])
        self.assertEqual(1, len(result))
        self.assertEqual("RUN_INTERRUPTED", result[0]["code"])
        self.assertEqual("本轮运行中断，邮件未完成发送", result[0]["message"])

    def test_rebuilds_failure_details_when_run_details_are_empty(self):
        result = rebuild_failure_details([], [
            ("company-1", "Egencia", "contact-1", "Rory Hall", "rory@example.com", "Status code: 550 5.1.10"),
            ("company-1", "Egencia", "contact-2", "Tonja Meierhans", "tonja@example.com", "Status code: 550 5.1.10"),
        ])
        self.assertEqual(2, len(result))
        self.assertEqual("SMTP_REJECT", result[0]["code"])
        self.assertEqual("Rory Hall", result[0]["contactName"])
        self.assertEqual("rory@example.com", result[0]["recipientEmail"])

    def test_failure_message_is_short_chinese(self):
        result = normalize_failure_detail({
            "status": "failed",
            "code": "HARD_BOUNCE",
            "error": "Status code 554 5.4.14",
        })
        self.assertEqual("\u786c\u9000\u4fe1\uff1a\u90ae\u4ef6\u8def\u7531\u5f02\u5e38\uff08554 5.4.14\uff09", result["message"])

    def test_post_send_sla_constraint_failure_is_displayed_as_completed(self):
        error = "ck_sales_lead_first_touch_sla"
        self.assertEqual("completed", effective_run_status("failed", error))
        self.assertEqual("failed", effective_run_status("failed", "SMTP connection failed"))
        self.assertEqual("completed", effective_run_status("completed", error))

    def test_effective_touch_count_fills_missing_run_counters(self) -> None:
        touch_summary = {"candidate_count": 49, "sent_count": 43, "failed_count": 3, "reserved_count": 3}
        self.assertEqual(49, effective_touch_count(0, "candidate_count", touch_summary))
        self.assertEqual(43, effective_touch_count(0, "sent_count", touch_summary))
        self.assertEqual(3, effective_touch_count(0, "failed_count", touch_summary))

    def test_effective_failed_count_includes_unfinished_reserved_touches(self) -> None:
        self.assertEqual(effective_failed_count(3, {"hard_bounce": 1, "reserved_count": 3}), 7)

    def test_effective_failed_count_includes_later_delivery_bounces(self) -> None:
        self.assertEqual(effective_failed_count(1, {"hard_bounce": 2, "soft_bounce": 1}), 4)

    def test_effective_sent_count_excludes_later_delivery_bounces(self) -> None:
        self.assertEqual(effective_sent_count(16, {"hard_bounce": 1, "soft_bounce": 0}), 15)

    def test_normalizes_translation_signature_failure(self):
        result = normalize_failure_detail({
            "status": "failed",
            "attempts": 3,
            "companyId": "company-1",
            "error": "Template translation did not preserve the sales signature.",
        })
        self.assertEqual("compose", result["phase"])
        self.assertEqual("TRANSLATION_SIGNATURE", result["code"])
        self.assertEqual("\u7ffb\u8bd1\u672a\u4fdd\u7559\u9500\u552e\u7b7e\u540d", result["message"])
        self.assertEqual("\u5c06 sales_name \u6539\u4e3a\u771f\u4eba\u59d3\u540d", result["hint"])

    def test_failure_messages_are_displayed_in_chinese(self):
        result = normalize_failure_detail({
            "status": "failed",
            "error": "Status code 554 5.4.14",
            "code": "HARD_BOUNCE",
        })
        self.assertEqual("\u786c\u9000\u4fe1\uff1a\u90ae\u4ef6\u8def\u7531\u5f02\u5e38\uff08554 5.4.14\uff09", result["message"])

    def test_replaces_corrupted_failure_hint_with_chinese_fallback(self):
        result = normalize_failure_detail({
            "status": "failed",
            "error": "Template translation did not preserve the contact name.",
            "hint": "?????????????",
            "companyName": "Dr. Tigges Reise\u00fcro",
        })

        self.assertEqual("请查看失败原因并人工确认", result["hint"])

    def test_summary_groups_failed_details(self):
        result = build_failure_summary([
            {"status": "sent"},
            {"status": "failed", "error": "SMTP recipient refused"},
            {"status": "failed", "error": "SMTP recipient refused"},
        ])
        self.assertEqual({"total": 2, "byCode": {"SMTP_REJECT": 2}, "unavailable": False}, result)

    def test_missing_details_is_unavailable(self):
        self.assertEqual({"total": 0, "byCode": {}, "unavailable": True}, build_failure_summary(None))

    def test_normalizes_historical_reply_by_subject_when_category_is_stale(self):
        result = normalize_reply_detail({
            "emailId": "email-auto-2",
            "messageCategory": "customer_reply",
            "subject": "Out of office: Re: Partnership",
            "fromAddress": "buyer@example.com",
            "bodyText": "I am away until Monday.",
            "intentLevel": "interested",
        })
        self.assertEqual("automatic_reply", result["messageCategory"])
        self.assertEqual("automatic_reply", result["analysis"]["intentLevel"])
        self.assertIsNone(result["analysis"]["nextAction"])

    def test_normalizes_automatic_reply_without_next_action_or_confidence(self):
        result = normalize_reply_detail({
            "emailId": "email-auto-3",
            "messageCategory": "automatic_reply",
            "subject": "OOO: Re: Partnership",
            "bodyText": "I am away until Monday.",
            "intentLevel": "interested",
            "nextAction": "????",
            "next_action": "?????????????????",
            "intentPayload": {"confidence": 0.35},
        })
        self.assertIsNone(result["analysis"]["nextAction"])
        self.assertIsNone(result["analysis"]["confidence"])

    def test_normalizes_historical_automatic_reply_without_intent_level(self):
        result = normalize_reply_detail({
            "emailId": "email-auto-1",
            "messageCategory": "automatic_reply",
            "intentLevel": "interested",
            "bodyText": "Out of office",
        })
        self.assertEqual("automatic_reply", result["messageCategory"])
        self.assertEqual("automatic_reply", result["analysis"]["intentLevel"])

    def test_normalizes_reply_detail_for_history(self):
        result = normalize_reply_detail({
            "emailId": "email-1",
            "companyName": "Acme",
            "contactName": "Ada",
            "fromAddress": "ada@example.com",
            "subject": "Re: Pricing",
            "bodyText": "Please send pricing.",
            "intentLevel": "pricing",
            "nextAction": "Send pricing deck.",
            "receivedAt": "2026-09-01T10:00:00+00:00",
        })
        self.assertEqual("email-1", result["emailId"])
        self.assertEqual("ada@example.com", result["emailAddress"])
        self.assertEqual("Please send pricing.", result["content"])
        self.assertEqual("pricing", result["analysis"]["intentLevel"])

    def test_list_replies_reads_total_count_from_last_selected_column(self):
        class Cursor:
            def __init__(self):
                self.calls = 0

            def execute(self, *_args):
                self.calls += 1

            def fetchone(self):
                return (1,)

            def fetchall(self):
                return [
                    (
                        "email-1", "company-1", "Acme", "contact-1", "Ada",
                        "ada@example.com", "sales@example.com", "Re: Pricing",
                        "Please send pricing.", "pricing", {}, "Send pricing deck.",
                        None, None, 1,
                    )
                ]

            def close(self):
                pass

        class Connection:
            def __init__(self):
                self.cursor_instance = Cursor()

            def cursor(self):
                return self.cursor_instance

            def close(self):
                pass

        store = EmailAutomationStore()
        with patch.object(store, "_connect", return_value=Connection()):
            result = store.list_replies("run-1")

        self.assertEqual(1, result["total"])
        self.assertEqual("email-1", result["items"][0]["emailId"])

    def test_reply_summary_counts_customer_and_automatic_replies(self):
        result = build_reply_summary([
            {"messageCategory": "customer_reply"},
            {"messageCategory": "automatic_reply"},
            {"messageCategory": "customer_reply"},
        ])
        self.assertEqual(3, result["total"])

if __name__ == "__main__":
    unittest.main()
