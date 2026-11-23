from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from ltc.modules.customer_operation.skills.email_translate_skill import EmailTranslateSkill


class EmailTranslateSkillTests(unittest.TestCase):
    def test_email_translation_translates_subject_and_body(self) -> None:
        captured: dict[str, str] = {}

        async def fake_chat_json(*, system_prompt: str, user_prompt: str) -> dict[str, str]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "translatedSubject": "Translated subject",
                "translatedText": "Translated body",
            }

        with patch(
            "ltc.modules.customer_operation.skills.email_translate_skill.LlmClient.chat_json",
            side_effect=fake_chat_json,
        ):
            result = asyncio.run(
                EmailTranslateSkill().run(
                    {
                        "sourceSubject": "原始主题",
                        "sourceText": "原始正文",
                        "targetLanguage": "en",
                        "customerName": "Customer",
                        "recipientName": "Recipient",
                    }
                )
            )

        self.assertIn("Source subject:\n原始主题", captured["user_prompt"])
        self.assertIn("Source email body:\n原始正文", captured["user_prompt"])
        self.assertIn('"translatedSubject":"..."', captured["system_prompt"])
        self.assertEqual(result["translatedSubject"], "Translated subject")
        self.assertEqual(result["translatedText"], "Translated body")
