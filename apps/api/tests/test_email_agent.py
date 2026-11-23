import asyncio
import unittest
from unittest.mock import Mock, patch

from ltc.modules.customer_operation.application.email_agent import EmailAgent
from ltc.modules.customer_operation.application.email_quality_guard import inspect_email_quality
from ltc.modules.customer_operation.infrastructure.email_context_builder import (
    _try_postgres_context,
    build_email_agent_context,
)
from ltc.modules.customer_operation.skills.email_generate_skill import EmailGenerateSkill
from ltc.modules.customer_operation.skills.email_optimize_skill import EmailOptimizeSkill
from ltc.modules.customer_operation.skills.email_rewrite_skill import EmailRewriteSkill
from ltc.modules.customer_operation.skills.email_translate_skill import EmailTranslateSkill


class RecordingSkill:
    def __init__(self, name: str, result: dict) -> None:
        self.name = name
        self.result = result
        self.calls: list[dict] = []

    async def run(self, input_data: dict) -> dict:
        self.calls.append(dict(input_data))
        return dict(self.result)


class EmailAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        result = {
            "subject": "Result subject",
            "body": "Result body",
            "language": "en",
            "changes": ["Changed"],
            "model": "test-model",
        }
        self.skills = {
            name: RecordingSkill(name, dict(result))
            for name in ("email_generate", "email_edit", "email_translate")
        }
        self.context_builder = Mock(return_value={
            "salesName": "Zong Lin",
            "customerName": "Example Co",
            "recipientName": "Alex",
            "recipientEmail": "alex@example.com",
            "currentSubject": "Current subject",
            "currentBody": "Current body",
            "customPrompt": "",
        })
        self.agent = EmailAgent(registry=self.skills, context_builder=self.context_builder)

    def test_generate_routes_only_to_generate_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "generate",
        }))
        self.assertEqual(result["agent"], "email-agent")
        self.assertEqual(result["skills"], ["email_generate"])
        self.assertEqual(len(self.skills["email_generate"].calls), 1)
        self.assertEqual(self.skills["email_edit"].calls, [])

    def test_optimize_routes_only_to_optimize_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "optimize",
            "body": "Current body",
        }))
        self.assertEqual(result["skills"], ["email_edit"])
        self.assertEqual(self.skills["email_edit"].calls[0]["operation"], "optimize")

    def test_rewrite_uses_rewrite_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "rewrite",
            "body": "Current body",
            "instruction": "Make it shorter",
        }))
        self.assertEqual(result["skills"], ["email_edit"])
        self.assertEqual(self.skills["email_edit"].calls[0]["operation"], "rewrite")

    def test_rewrite_can_translate_then_rewrite(self) -> None:
        self.skills["email_translate"].result["body"] = "Translated body"
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "rewrite",
            "body": "当前正文",
            "instruction": "翻译成英文并缩短一些",
            "targetLanguage": "en",
        }))
        self.assertEqual(result["skills"], ["email_translate", "email_edit"])
        self.assertEqual(self.skills["email_edit"].calls[0]["currentBody"], "Translated body")

    def test_rewrite_requires_instruction(self) -> None:
        with self.assertRaisesRegex(ValueError, "instruction is required"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "rewrite",
                "body": "Current body",
            }))

    def test_translate_requires_body(self) -> None:
        with self.assertRaisesRegex(ValueError, "body is required"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "translate",
                "targetLanguage": "en",
            }))

    def test_send_is_not_a_supported_operation(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported email agent operation"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "send",
            }))


class EmailAgentContextTests(unittest.TestCase):
    def test_agent_fields_map_to_generation_memory(self) -> None:
        with patch(
            "ltc.modules.customer_operation.infrastructure.email_context_builder._try_postgres_context",
            return_value={},
        ):
            context = build_email_agent_context({
                "salesName": "Zong Lin",
                "subject": "Current subject",
                "body": "Current body",
                "instruction": "Make it shorter",
                "operation": "rewrite",
                "targetLanguage": "en",
            })

        self.assertEqual(context["currentSubject"], "Current subject")
        self.assertEqual(context["currentBody"], "Current body")
        self.assertEqual(context["customPrompt"], "Make it shorter")
        self.assertEqual(context["targetLanguage"], "en")
        self.assertEqual(context["mode"], "regenerate")

    def test_recent_email_context_is_scoped_by_contact_and_salesperson(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.executions: list[tuple[str, tuple]] = []
                self.fetchone_values = [
                    ("Example Co", "Profile", "travel", "US", "Boston", "example.com"),
                    ("Alex", "alex@example.com", "Director", "decision_maker"),
                    None,
                ]
                self.fetchall_values = [[], [], []]

            def execute(self, sql: str, params: tuple) -> None:
                self.executions.append((sql, params))

            def fetchone(self):
                return self.fetchone_values.pop(0)

            def fetchall(self):
                return self.fetchall_values.pop(0)

        class FakeConnection:
            def __init__(self, cursor: FakeCursor) -> None:
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def cursor(self) -> FakeCursor:
                return self._cursor

        cursor = FakeCursor()
        with patch(
            "ltc.modules.customer_operation.infrastructure.email_context_builder._is_db_configured",
            return_value=True,
        ), patch(
            "ltc.modules.customer_operation.infrastructure.email_context_builder._connect",
            return_value=FakeConnection(cursor),
        ):
            _try_postgres_context({
                "companyId": "company-1",
                "contactId": "contact-1",
                "salesUserId": "sales-1",
            })

        email_sql, email_params = cursor.executions[2]
        self.assertIn("contact_id::text", email_sql)
        self.assertIn("sales_user_id::text", email_sql)
        self.assertEqual(email_params, ("company-1", "contact-1", "contact-1", "sales-1", "sales-1"))


class EmailSkillContractTests(unittest.TestCase):
    def test_generate_combines_quality_checks_into_one_llm_call(self) -> None:
        calls: list[dict] = []

        async def fake_chat_json(**kwargs) -> dict:
            calls.append(kwargs)
            return {"subject": "Subject", "body": "Body\n\nZong Lin", "model": "test-model"}

        with patch(
            "ltc.modules.customer_operation.skills.email_generate_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ):
            asyncio.run(EmailGenerateSkill().run({
                "salesName": "Zong Lin",
                "customerName": "Example Co",
                "recipientName": "Alex",
                "recipientEmail": "alex@example.com",
            }))

        self.assertEqual(len(calls), 1)
        self.assertIn("same response", calls[0]["system_prompt"])
        self.assertIn("verified context", calls[0]["system_prompt"])
        self.assertIn("brand voice", calls[0]["system_prompt"])

    def test_local_quality_guard_strips_fences_and_reports_missing_verified_tokens(self) -> None:
        result = inspect_email_quality(
            input_data={
                "currentBody": "Contact ops@example.com about pilot 2026-08-20.",
                "salesName": "Zong Lin",
            },
            subject="```\nPilot update\n```",
            body="```text\nPlease review the pilot.\n```",
        )

        self.assertEqual(result.subject, "Pilot update")
        self.assertEqual(result.body, "Please review the pilot.")
        self.assertIn("missing_email:ops@example.com", result.flags)
        self.assertIn("missing_number:2026", result.flags)

    def test_generate_returns_unified_contract(self) -> None:
        async def fake_chat_json(**_kwargs) -> dict:
            return {"subject": "Subject", "body": "Body", "model": "test-model"}

        with patch(
            "ltc.modules.customer_operation.skills.email_generate_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ):
            result = asyncio.run(EmailGenerateSkill().run({
                "salesName": "Zong Lin",
                "customerName": "Example Co",
                "recipientName": "Alex",
                "recipientEmail": "alex@example.com",
            }))

        self.assertEqual(result["language"], "zh")
        self.assertEqual(result["changes"], ["根据客户上下文生成主题和正文"])

    def test_translate_accepts_agent_body_and_keeps_legacy_text(self) -> None:
        async def fake_chat_json(**_kwargs) -> dict:
            return {
                "translatedSubject": "Translated subject",
                "translatedText": "Translated body",
                "model": "test-model",
            }

        with patch(
            "ltc.modules.customer_operation.skills.email_translate_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ):
            result = asyncio.run(EmailTranslateSkill().run({
                "currentSubject": "Subject",
                "currentBody": "Body",
                "targetLanguage": "en",
            }))

        self.assertEqual(result["subject"], "Translated subject")
        self.assertEqual(result["body"], "Translated body")
        self.assertEqual(result["translatedText"], "Translated body")

    def test_optimize_and_rewrite_return_unified_contract(self) -> None:
        async def fake_chat_json(**_kwargs) -> dict:
            return {"subject": "Subject", "body": "Body", "model": "test-model"}

        with patch(
            "ltc.modules.customer_operation.skills.email_optimize_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ), patch(
            "ltc.modules.customer_operation.skills.email_rewrite_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ):
            optimized = asyncio.run(EmailOptimizeSkill().run({"currentBody": "Draft"}))
            rewritten = asyncio.run(EmailRewriteSkill().run({
                "currentBody": "Draft",
                "customPrompt": "Shorter",
            }))

        self.assertEqual(optimized["changes"], ["优化语气、结构和行动号召"])
        self.assertEqual(rewritten["changes"], ["根据用户指令改写邮件"])


if __name__ == "__main__":
    unittest.main()
