from __future__ import annotations

import unittest

from ltc.modules.lead_intelligence.domain.field_mapping import map_company_fields, merge_company_sources


class FieldMappingTests(unittest.TestCase):
    def test_aliases_nested_values_and_unknown_fields_are_lossless(self):
        mapped = map_company_fields({
            "organization": {"name": "Acme", "num_employees": "1,200"},
            "公司简介": "企业差旅平台",
            "business_model": "B2B OTA",
        })
        self.assertEqual(mapped["recognized"]["company_name"], "Acme")
        self.assertEqual(mapped["recognized"]["employee_count"], 1200)
        self.assertEqual(mapped["recognized"]["company_intro"], "企业差旅平台")
        self.assertEqual(mapped["extras"]["business_model"], "B2B OTA")

    def test_provider_values_win_and_bad_city_linkedin_are_rejected(self):
        mapped = merge_company_sources(
            {
                "organization_name": "株式会社JTBビジネストラベルソリューションズ",
                "organization_website_url": "https://bts.jtbbwt.com/",
                "organization_country": "Japan",
                "organization_city": "Makati",
                "organization_linkedin_url": "https://www.linkedin.com/company/bridge-australia",
            },
            {"snippet": "Business travel management with offices in Tokyo and Osaka; serving 400+ corporate customers"},
            {"company_name": "株式会社JTBビジネストラベルソリューションズ", "city": "Sydney", "linkedin_company_url": "https://www.linkedin.com/company/jtb-business-travel"},
        )
        self.assertEqual(mapped["recognized"]["country_code"], "JP")
        self.assertEqual(mapped["recognized"]["city"], "Tokyo")
        self.assertEqual(mapped["recognized"]["industry_code"], "TMC")
        self.assertEqual(mapped["recognized"]["linkedin_company_url"], "https://www.linkedin.com/company/jtb-business-travel")
        self.assertIn("customer_count", mapped["extras"])

    def test_company_intro_is_cleaned_and_bounded_without_losing_source_text(self):
        raw_intro = "<style>.hidden{display:none}</style><p># **Travel &amp; expense platform**</p> [官网](https://acme.example)" + (" detail" * 400)
        mapped = merge_company_sources({"company_name": "Acme", "text": raw_intro})

        intro = mapped["recognized"]["company_intro"]
        self.assertNotIn("<style>", intro)
        self.assertNotIn("<p>", intro)
        self.assertNotIn("#", intro)
        self.assertNotIn("**", intro)
        self.assertNotIn("https://", intro)
        self.assertIn("Travel & expense platform", intro)
        self.assertLessEqual(len(intro), 1200)
        self.assertIn(raw_intro, mapped["extras"]["source_text"])

    def test_ota_identity_overrides_generic_business_travel_wording(self):
        cases = (
            ({
                "company_name": "携程集团",
                "industry_code": "TMC",
                "company_intro": "综合在线旅行服务平台，提供商旅管理及目的地服务。",
            }, "TRAVEL_OTA"),
            ({
                "company_name": "Trip.com Group",
                "industry_code": "OTHER",
                "company_intro": "A global travel service provider with corporate travel products.",
            }, "TRAVEL_OTA"),
            ({
                "company_name": "Ctrip",
                "company_intro": "Provides flights, hotels, holidays, and business travel services.",
            }, "TRAVEL_OTA"),
            ({
                "company_name": "Trip.Biz",
                "company_intro": "A digital corporate travel management platform.",
            }, "TRAVEL_OTA"),
            ({
                "company_name": "Expedia Group",
                "company_intro": "An online travel platform serving leisure and business travelers.",
            }, "TRAVEL_OTA"),
        )

        for source, expected in cases:
            with self.subTest(company_name=source["company_name"]):
                mapped = merge_company_sources(source)
                self.assertEqual(mapped["recognized"]["industry_code"], expected)

    def test_tmc_and_fintech_classifications_remain_distinct(self):
        cases = (
            ({
                "company_name": "American Express Global Business Travel",
                "industry_code": "TMC",
                "company_intro": "A travel management company serving corporate clients.",
            }, "TMC"),
            ({
                "company_name": "Brex",
                "industry_code": "FINTECH",
                "company_intro": "A fintech platform offering cards, expense, and travel management.",
            }, "FINTECH"),
        )

        for source, expected in cases:
            with self.subTest(company_name=source["company_name"]):
                mapped = merge_company_sources(source)
                self.assertEqual(mapped["recognized"]["industry_code"], expected)


if __name__ == "__main__":
    unittest.main()
