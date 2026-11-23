from __future__ import annotations

import unittest

from pydantic import ValidationError

from ltc.modules.lead_intelligence.interfaces.schemas import LeadSearchRunCreate


class Utf8InputTests(unittest.TestCase):
    def test_unicode_query_is_preserved(self):
        request = LeadSearchRunCreate(query_text="找一家美国商旅OTA")
        self.assertEqual(request.query_text, "找一家美国商旅OTA")

    def test_replacement_question_marks_are_rejected(self):
        with self.assertRaises(ValidationError):
            LeadSearchRunCreate(query_text="??????????OTA")


if __name__ == "__main__":
    unittest.main()
