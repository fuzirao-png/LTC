from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock
from pathlib import Path

from ltc.modules.lead_intelligence.application.email_automation_service import EmailAutomationService

from ltc.modules.lead_intelligence.agents.email_outreach_agent.agent import (
    AutoTouchConfig,
    EmailAutomationAgent,
    choose_template,
    choose_template_details,
    target_language_for_candidate,
    PARTNER_TEMPLATE_BODY,
    ENTERPRISE_TEMPLATE_BODY,
    append_sales_signature,
    template_blueprint_for_candidate,
    build_translation_segments,
    reassemble_translation_segments,
)


class FakeStore:
    def __init__(self, candidates):
        self.candidates = candidates
        self.claimed = []
        self.successes = []
        self.failures = []
        self.failed_runs = []
        self.existing_deliveries = {}

    def find_candidates(self, config):
        return list(self.candidates)

    def claim_candidate(self, *, run_id, company_id, contact_id):
        if company_id in self.claimed:
            return False
        self.claimed.append(company_id)
        return True

    def mark_success(self, *, run_id, company_id, contact_id, message_id):
        self.successes.append((company_id, message_id))

    def mark_failure(self, *, run_id, company_id, contact_id, error):
        self.failures.append((company_id, error))

    def find_existing_delivery(self, *, company_id, contact_id):
        return self.existing_deliveries.get((company_id, contact_id))

    def fail_run(self, *, run_id, error):
        self.failed_runs.append((run_id, error))

    def start_run(self, config):
        return "run-1"

    def finish_run(self, *, run_id, summary):
        return summary


class EmailAutomationAgentTests(unittest.TestCase):
    def test_translation_segments_preserve_paragraph_and_bullet_order(self):
        source = """Hello {contact},

We help {company} connect globally.

We offer:
- Coverage;
- Flexible plans;

Would you be available for a call?"""

        segments = build_translation_segments(source)

        self.assertEqual([item["id"] for item in segments], ["P1", "P2", "P3", "B1", "B2", "P4"])
        translated = reassemble_translation_segments(segments, {
            "P1": "Bonjour A,",
            "P2": "Nous aidons One ? rester connect?.",
            "P3": "Nous proposons :",
            "B1": "Couverture ;",
            "B2": "Forfaits flexibles ;",
            "P4": "Seriez-vous disponible pour un appel ?",
        })
        self.assertEqual(translated, """Bonjour A,

Nous aidons One ? rester connect?.

Nous proposons :
- Couverture ;
- Forfaits flexibles ;

Seriez-vous disponible pour un appel ?""")

    def test_translation_segments_join_wrapped_bullet_lines(self):
        segments = build_translation_segments("Offer:\n- Fast activation for international\n  business travelers;\n- Flexible plans;")
        self.assertEqual([item["id"] for item in segments], ["P1", "B1", "B2"])
        self.assertEqual(segments[1]["text"], "Fast activation for international business travelers;")

    def test_reassemble_translation_segments_rejects_missing_ids(self):
        segments = build_translation_segments("Hello.\n\nNext paragraph.")
        with self.assertRaisesRegex(RuntimeError, "missing translation segment"):
            reassemble_translation_segments(segments, {"P1": "Bonjour."})

    def test_reassemble_translation_segments_rejects_extra_ids(self):
        segments = build_translation_segments("Hello.\n\nNext paragraph.")
        with self.assertRaisesRegex(RuntimeError, "unexpected segment"):
            reassemble_translation_segments(segments, {"P1": "Bonjour.", "P2": "Suite.", "P3": "Extra."})

    def test_append_sales_signature_adds_standard_signoff_when_missing(self):
        body = "Bonjour, voici notre proposition."

        result = append_sales_signature(body, "Global Marketing Team")

        self.assertEqual(
            result,
            "Bonjour, voici notre proposition.\n\nBest regards,\nGlobal Marketing Team",
        )

    def test_append_sales_signature_does_not_duplicate_existing_signoff(self):
        body = "Bonjour, voici notre proposition.\n\nBest regards,\nGlobal Marketing Team"

        result = append_sales_signature(body, "Global Marketing Team")

        self.assertEqual(result, body)

    def test_template_selection_follows_prd_categories(self):
        self.assertEqual(
            choose_template({"industry_code": "TMC", "company_intro": "corporate travel"}),
            "partner",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "global offices"}),
            "enterprise",
        )
        self.assertEqual(
            choose_template({"industry_code": "TMC", "company_intro": "enterprise travel management for business customers"}),
            "partner",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "global offices and multi-country remote team"}),
            "enterprise",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "跨境远程团队"}),
            "enterprise",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "frequent international business travel"}),
            "enterprise",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "online travel platform for tour packages"}),
            "partner",
        )
        self.assertEqual(
            choose_template({"industry_code": "OTHER", "company_intro": "local software company"}),
            "enterprise",
        )

    def test_all_template_blueprints_are_complete(self):
        enterprise = template_blueprint_for_candidate({"industry_code": "OTHER", "company_intro": "global offices"})
        fallback = template_blueprint_for_candidate({"industry_code": "OTHER", "company_intro": "unknown business"})
        self.assertEqual(enterprise, ENTERPRISE_TEMPLATE_BODY)
        self.assertEqual(fallback, ENTERPRISE_TEMPLATE_BODY)
        for blueprint in (PARTNER_TEMPLATE_BODY, ENTERPRISE_TEMPLATE_BODY):
            self.assertIn("Hi {contact}", blueprint)
            self.assertIn("{company}", blueprint)
            self.assertIn("20-minute", blueprint)
            self.assertIn("Best regards,\n{sales}", blueprint)

    def test_b_template_fallback_matches_prd_structure(self):
        self.assertIn("With this in mind, we would like to explore potential collaboration", PARTNER_TEMPLATE_BODY)
        self.assertIn("professional,\npersonalized travel services", PARTNER_TEMPLATE_BODY)
        self.assertIn("We believe eSIM services could complement", PARTNER_TEMPLATE_BODY)
        self.assertIn("- As a value-added service alongside flights, hotels, or travel packages;", PARTNER_TEMPLATE_BODY)
        self.assertIn("Would you be available for a 20-minute online meeting in the near future?", PARTNER_TEMPLATE_BODY)
        self.assertIn("Best regards,\n{sales}", PARTNER_TEMPLATE_BODY)
        self.assertIn("Centralized purchase, distribution, and management", ENTERPRISE_TEMPLATE_BODY)
        self.assertIn("Optional branded or customized solutions", ENTERPRISE_TEMPLATE_BODY)

    def test_target_language_follows_country_and_defaults_to_english(self):
        self.assertEqual(target_language_for_candidate({"country_code": "FR"}), "fr")
        self.assertEqual(target_language_for_candidate({"country_code": "DE"}), "de")
        self.assertEqual(target_language_for_candidate({"country_code": "US"}), "en")
        self.assertEqual(target_language_for_candidate({}), "en")

    def test_template_selection_exposes_matching_reason(self):
        self.assertEqual(
            choose_template_details({"industry_code": "TMC"}),
            ("partner", "travel_channel_industry"),
        )
        self.assertEqual(
            choose_template_details({"company_intro": "multi-country remote team"}),
            ("enterprise", "enterprise_direct_markers"),
        )
        self.assertEqual(
            choose_template_details({"company_intro": "unknown business"}),
            ("enterprise", "default_enterprise"),
        )

    def test_disabled_agent_never_sends(self):
        store = FakeStore([{"company_id": "c1", "contact_id": "p1"}])
        generator = AsyncMock()
        sender = AsyncMock()
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=False)))

        self.assertEqual(result["status"], "disabled")
        sender.assert_not_awaited()
        generator.assert_not_awaited()

    def test_english_first_touch_ignores_configured_fallback_and_sends_prd_template(self):
        candidate = {
            "company_id": "c1",
            "contact_id": "p1",
            "company_name": "One Travel",
            "contact_name": "A",
            "country_code": "US",
            "industry_code": "TMC",
        }
        store = FakeStore([candidate])
        generator = AsyncMock()
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(
            enabled=True,
            sales_name="Sales",
            template_subject="Configured subject",
            template_body="Configured short fallback",
        )))

        self.assertEqual(result["sent"], 1)
        generator.assert_not_awaited()
        sent_payload = sender.await_args.args[0]
        self.assertIn("providing professional,\npersonalized travel services", sent_payload["body"])
        self.assertNotIn("Configured short fallback", sent_payload["body"])
        self.assertTrue(sent_payload["subject"].startswith(("Exploring eSIM", "eSIM as a value-add", "Connectivity as part")))

    def test_non_english_first_touch_translates_complete_template(self):
        candidate = {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A", "country_code": "DE"}
        store = FakeStore([candidate])
        async def translate(payload):
            return {"subject": payload["subject"], "body": payload["body"]}

        generator = AsyncMock(side_effect=translate)
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(result["sent"], 1)
        self.assertEqual(generator.await_args.args[0]["operation"], "translate")
        self.assertIn("Preserve every paragraph", generator.await_args.args[0]["customPrompt"])

    def test_structured_translation_is_reassembled_before_sending(self):
        candidate = {
            "company_id": "c1", "contact_id": "p1", "company_name": "One",
            "contact_name": "A", "country_code": "DE",
        }
        store = FakeStore([candidate])
        async def translate(payload):
            return {
                "subject": "Internationale eSIM f?r One",
                "translatedSegments": [
                    {"id": item["id"], "text": item["text"].replace("Hi", "Hallo").replace("We", "Wir")}
                    for item in payload["translationSegments"]
                ],
            }
        generator = AsyncMock(side_effect=translate)
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True, sales_name="Sales")))

        self.assertEqual(result["sent"], 1)
        sent_body = sender.await_args.args[0]["body"]
        self.assertIn("\n\n", sent_body)
        self.assertIn("-", sent_body)
        self.assertTrue(sent_body.endswith("Best regards,\nSales"))

    def test_missing_translated_signature_is_appended_before_sending(self):
        candidate = {
            "company_id": "c1",
            "contact_id": "p1",
            "company_name": "One",
            "contact_name": "A",
            "country_code": "FR",
        }
        store = FakeStore([candidate])

        async def translate(payload):
            return {
                "subject": payload["subject"],
                "body": payload["body"].rsplit("\n\nBest regards,", 1)[0],
            }

        generator = AsyncMock(side_effect=translate)
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True, sales_name="Sales")))

        self.assertEqual(result["sent"], 1)
        sent_payload = sender.await_args.args[0]
        self.assertTrue(sent_payload["body"].endswith("Best regards,\nSales"))

    def test_incomplete_translation_is_rejected_before_sending(self):
        candidate = {
            "company_id": "c1",
            "contact_id": "p1",
            "company_name": "One",
            "contact_name": "A",
            "country_code": "DE",
        }
        store = FakeStore([candidate])
        generator = AsyncMock(return_value={"subject": "Betreff One", "body": "Kurzer Text 20 eSIM Sales"})
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True, sales_name="Sales")))

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(generator.await_count, 3)
        sender.assert_not_awaited()
        self.assertIn("paragraph structure", store.failures[0][1])

    def test_sender_result_uses_message_id_from_delivery_record(self):
        candidate = {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A"}
        store = FakeStore([candidate])
        sender = AsyncMock(return_value={"success": True, "record": {"messageId": "<m1@example.com>"}})
        agent = EmailAutomationAgent(store=store, email_agent=AsyncMock(), sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(result["sent"], 1)
        self.assertEqual(store.successes, [("c1", "<m1@example.com>")])

    def test_existing_delivery_after_sender_error_is_not_sent_again(self):
        candidate = {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A"}
        store = FakeStore([candidate])

        async def send_once(_payload):
            store.existing_deliveries[("c1", "p1")] = "<existing@example.com>"
            raise RuntimeError("database write failed after SMTP acceptance")

        sender = AsyncMock(side_effect=send_once)
        agent = EmailAutomationAgent(store=store, email_agent=AsyncMock(), sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(sender.await_count, 1)
        self.assertEqual(store.successes, [("c1", "<existing@example.com>")])

    def test_run_failure_is_persisted_when_candidate_query_raises(self):
        store = FakeStore([])
        store.find_candidates = lambda _config: (_ for _ in ()).throw(RuntimeError("database unavailable"))
        agent = EmailAutomationAgent(store=store, email_agent=AsyncMock(), sender=AsyncMock())

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(len(store.failed_runs), 1)
        self.assertIn("database unavailable", store.failed_runs[0][1])

    def test_one_failed_candidate_does_not_stop_other_candidates(self):
        candidates = [
            {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A"},
            {"company_id": "c2", "contact_id": "p2", "company_name": "Two", "contact_name": "B"},
        ]
        store = FakeStore(candidates)
        generator = AsyncMock(side_effect=[RuntimeError("llm unavailable"), {"subject": "S", "body": "B"}])
        sender = AsyncMock(return_value={"messageId": "m2"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(store.successes), 2)
        self.assertEqual(sender.await_count, 2)

    def test_concurrent_claim_is_idempotent(self):
        candidate = {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A"}
        store = FakeStore([candidate])
        generator = AsyncMock(return_value={"subject": "S", "body": "B"})
        sender = AsyncMock(return_value={"messageId": "m1"})
        agent = EmailAutomationAgent(store=store, email_agent=generator, sender=sender)

        first = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))
        second = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(sender.await_count, 1)

    def test_candidates_are_processed_concurrently(self):
        candidates = [
            {"company_id": "c1", "contact_id": "p1", "company_name": "One", "contact_name": "A"},
            {"company_id": "c2", "contact_id": "p2", "company_name": "Two", "contact_name": "B"},
        ]
        store = FakeStore(candidates)

        async def generate(_payload):
            await asyncio.sleep(0.1)
            return {"subject": "S", "body": "B"}

        async def send(_payload):
            await asyncio.sleep(0.1)
            return {"messageId": "m1"}

        agent = EmailAutomationAgent(store=store, email_agent=generate, sender=send)
        started = time.perf_counter()
        result = asyncio.run(agent.run_once(AutoTouchConfig(enabled=True)))
        elapsed = time.perf_counter() - started

        self.assertEqual(result["sent"], 2)
        self.assertLess(elapsed, 0.35)


class EmailAutomationQueryRegressionTests(unittest.TestCase):
    def test_failed_first_touch_email_does_not_block_preview(self):
        query_source = Path(
            "apps/api/src/ltc/modules/lead_intelligence/infrastructure/email_automation_store.py"
        ).read_text(encoding="utf-8")
        self.assertIn("'smtp_submitted'", query_source)
        self.assertIn("'delivery_confirmed'", query_source)

    def test_first_touch_preview_accepts_any_non_empty_email_status(self):
        query_source = (Path(__file__).parents[1] / "src/ltc/modules/lead_intelligence/infrastructure/email_automation_store.py").read_text(encoding="utf-8")
        self.assertNotIn("AND ct.email_status = 'valid'", query_source)
        self.assertIn("AND NULLIF(ct.primary_email, '') IS NOT NULL", query_source)

class UserMailboxBindingRegressionTests(unittest.TestCase):
    def test_user_mailbox_shared_email_migration_keeps_user_uniqueness(self):
        migration = Path("db/migrations/0034_allow_shared_user_mailbox_email.sql").read_text(encoding="utf-8")
        self.assertIn("DROP CONSTRAINT IF EXISTS uq_user_mailbox_email", migration)
        self.assertNotIn("DROP CONSTRAINT IF EXISTS uq_user_mailbox_user", migration)


if __name__ == "__main__":
    unittest.main()


class PreviewStore:
    def load_config(self):
        return AutoTouchConfig(enabled=False)

    def find_candidates(self, config):
        return [
            {"company_id": "c1", "company_name": "One", "contact_id": "p1", "contact_name": "A", "recipient_email": "a@example.com", "region_code": "NA", "industry_code": "TMC", "icp_score": 90, "contact_score": 70,},
            {"company_id": "c1", "company_name": "One", "contact_id": "p2", "contact_name": "B", "recipient_email": "b@example.com", "region_code": "NA", "industry_code": "TMC", "icp_score": 90, "contact_score": 60,},
            {"company_id": "c1", "company_name": "One", "contact_id": "p3", "contact_name": "C", "recipient_email": "c@example.com", "region_code": "NA", "industry_code": "TMC", "icp_score": 90, "contact_score": 50,},
        ]

    def save_config(self, payload):
        return AutoTouchConfig()

    def list_runs(self, limit=20):
        return []


class EmailAutomationPreviewTests(unittest.TestCase):
    def test_preview_groups_company_and_keeps_all_three_contacts(self):
        result = EmailAutomationService(store=PreviewStore()).preview()

        self.assertEqual(1, result["totalCompanies"])
        self.assertEqual(3, result["totalContacts"])
        self.assertEqual(["p1", "p2", "p3"], [item["contactId"] for item in result["companies"][0]["contacts"]])
