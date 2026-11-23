import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ltc.modules.customer_operation.application.reply_intent_agent import (
    _classify_reply_by_llm,
    classify_reply,
)


class ReplyIntentAgentTests(unittest.TestCase):
    def classify_without_llm(self, content: str):
        with patch(
            "ltc.modules.customer_operation.application.reply_intent_agent.get_settings",
            return_value=SimpleNamespace(llm_api_key=""),
        ):
            return classify_reply(content)

    def test_classify_reply_supports_seven_intents(self) -> None:
        cases = (
            ("We are interested and would like to arrange a demo.", "interested"),
            ("Please provide your pricing and a formal quote.", "pricing"),
            ("Does the product API support regional coverage?", "product_question"),
            ("Please stop contacting me and unsubscribe this address.", "unsubscribe"),
            ("This is not a priority for us right now.", "not_interested"),
            (
                "方案一：按月采购 5000 个账号；方案二：年度采购 80000 个账号，年度方案包含专属 SLA。",
                "proposal",
            ),
            ("方案没问题。", "proposal"),
            ("方案完全没问题，我这边都配合。", "proposal"),
            ("双方已完成合同盖章，并确认按照最终条款正式合作。", "won"),
        )
        for content, expected in cases:
            with self.subTest(content=content):
                self.assertEqual(self.classify_without_llm(content).intent_level, expected)

    def test_proposal_request_does_not_count_as_actual_proposal(self) -> None:
        for content in ("请给我发送一份方案。", "Could you send us a proposal for review?"):
            with self.subTest(content=content):
                self.assertNotEqual(self.classify_without_llm(content).intent_level, "proposal")

    def test_llm_intent_is_used_before_keyword_fallback(self) -> None:
        with patch(
            "ltc.modules.customer_operation.application.reply_intent_agent._run_llm_classifier",
            return_value=SimpleNamespace(
                intent_level="proposal",
                next_action="Track the proposal.",
            ),
        ):
            result = classify_reply("这个版本很合适，我们按此推进。")

        self.assertEqual(result.intent_level, "proposal")

    def test_llm_progress_intent_requires_quote_from_reply(self) -> None:
        class FakeLlmClient:
            async def chat_json(self, **_kwargs):
                return {
                    "intent_level": "proposal",
                    "next_action": "Track the proposal.",
                    "confidence": 0.94,
                    "evidence_quote": "不存在于邮件中的内容",
                    "evidence_type": "proposal_confirmation",
                }

        with patch(
            "ltc.modules.customer_operation.application.reply_intent_agent.LlmClient",
            return_value=FakeLlmClient(),
        ):
            with self.assertRaisesRegex(RuntimeError, "not present"):
                asyncio.run(_classify_reply_by_llm("我们认可这个方向，请继续推进。"))

    def test_llm_can_recognize_semantic_proposal_confirmation(self) -> None:
        class FakeLlmClient:
            async def chat_json(self, **_kwargs):
                return {
                    "intent_level": "proposal",
                    "next_action": "Track the proposal.",
                    "confidence": 0.91,
                    "evidence_quote": "这个版本很合适，我们按此推进",
                    "evidence_type": "proposal_confirmation",
                }

        with patch(
            "ltc.modules.customer_operation.application.reply_intent_agent.LlmClient",
            return_value=FakeLlmClient(),
        ):
            result = asyncio.run(
                _classify_reply_by_llm("这个版本很合适，我们按此推进。")
            )

        self.assertEqual(result.intent_level, "proposal")
        self.assertEqual(result.evidence_type, "proposal_confirmation")

    def test_contract_draft_or_review_does_not_count_as_won(self) -> None:
        cases = (
            "附件是合同草案，请审阅其中的协议条款。",
            "Please review the draft agreement and suggest changes to the terms.",
        )
        for content in cases:
            with self.subTest(content=content):
                self.assertNotEqual(self.classify_without_llm(content).intent_level, "won")


if __name__ == "__main__":
    unittest.main()
