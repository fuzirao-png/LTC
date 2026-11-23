import asyncio
import unittest

from ltc.modules.customer_operation.skills.email_analysis_skill import EmailAnalysisSkill


TENCENT_BOUNCE = """很抱歉您发送的邮件被退回，以下是该邮件的相关信息：
被退回邮件  主 题：Exploring eSIM partnership with Hostway Travel
无法发送到 christiane.pacelli@hostway.travel
退信原因  收件人（christiane.pacelli@hostway.travel）或其所在服务商拒绝接收来自你邮箱（global.marketing@51tgt.com）的邮件。
host hostway-travel.mail.protection.outlook.com said: 550 5.4.1 Recipient address rejected: Access denied.
"""


class EmailAnalysisSkillTests(unittest.TestCase):
    def test_analyzes_tencent_bounce_without_llm(self):
        result = asyncio.run(EmailAnalysisSkill().run({
            "subject": "腾讯企业邮退信通知",
            "body": TENCENT_BOUNCE,
            "fromEmail": "postmaster@qq.com",
        }))
        self.assertEqual("delivery_notification", result["messageCategory"])
        self.assertEqual("hard_bounce", result["deliveryStatus"])
        self.assertEqual(["christiane.pacelli@hostway.travel"], result["recipients"])
        self.assertEqual("Exploring eSIM partnership with Hostway Travel", result["originalSubject"])
        self.assertFalse(result["countsAsReply"])

    def test_does_not_mark_customer_message_that_mentions_out_of_office_as_automatic(self):
        result = asyncio.run(EmailAnalysisSkill().run({
            "subject": "Re: Partnership",
            "body": "Thanks for following up. I am back from out of office and would like to discuss pricing.",
            "fromEmail": "buyer@example.com",
        }))
        self.assertEqual("customer_reply", result["messageCategory"])

    def test_detects_automatic_reply_with_french_subject(self):
        result = asyncio.run(EmailAnalysisSkill().run({
            "subject": "R\u00e9ponse automatique : Partnership",
            "body": "Je suis absent jusqu\u2019\u00e0 lundi.",
            "fromEmail": "buyer@example.com",
        }))
        self.assertEqual("automatic_reply", result["messageCategory"])

    def test_marks_automatic_reply_as_a_reply(self):
        result = asyncio.run(EmailAnalysisSkill().run({
            "subject": "Automatic reply: vacation",
            "body": "I am away until Monday.",
            "fromEmail": "buyer@example.com",
        }))
        self.assertEqual("automatic_reply", result["messageCategory"])
        self.assertEqual("automatic_reply", result["intentLevel"])
        self.assertTrue(result["countsAsReply"])
        self.assertIsNone(result["nextAction"])


if __name__ == "__main__":
    unittest.main()
