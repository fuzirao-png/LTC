from __future__ import annotations

import unittest

from ltc.modules.customer_operation.infrastructure.manual_note_extractor import ManualNoteExtractor


class ManualNoteExtractorTests(unittest.TestCase):
    def test_competitor_sentence_extracts_company_name(self) -> None:
        extractor = object.__new__(ManualNoteExtractor)

        result = extractor._fallback_extraction("竞争对手是美团")
        fields = {item["dimension"]: item["extracted"] for item in result["fields"]}

        self.assertIn("D2.决策链.竞争对手", fields)
        self.assertEqual("美团", fields["D2.决策链.竞争对手"])
        self.assertEqual("（无）", result["unidentified"])

    def test_competitor_connectors_are_normalized(self) -> None:
        extractor = object.__new__(ManualNoteExtractor)

        for text in (
            "竞争对手是飞猪或者任意公司",
            "竞争对手是飞猪以及任意公司",
            "竞争对手是飞猪 vs 任意公司",
            "竞争对手是飞猪对比任意公司",
        ):
            with self.subTest(text=text):
                result = extractor._fallback_extraction(text)
                fields = {item["dimension"]: item["extracted"] for item in result["fields"]}

                self.assertEqual("飞猪、任意公司", fields["D2.决策链.竞争对手"])

if __name__ == "__main__":
    unittest.main()
