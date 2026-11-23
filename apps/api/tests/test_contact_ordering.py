from __future__ import annotations

import unittest

from ltc.platform.contact_ordering import sort_contacts


class ContactOrderingTests(unittest.TestCase):
    def test_procurement_then_commercial_then_administrative_seniority(self) -> None:
        contacts = [
            {"full_name": "Mina", "title": "Operations Manager"},
            {"full_name": "Chris", "title": "Chief Executive Officer"},
            {"full_name": "Bianca", "title": "Commercial Manager"},
            {"full_name": "Parker", "title": "Procurement Manager"},
            {"full_name": "Dylan", "title": "Director of Technology"},
        ]

        ordered = sort_contacts(contacts)

        self.assertEqual(
            ["Parker", "Bianca", "Chris", "Dylan", "Mina"],
            [contact["full_name"] for contact in ordered],
        )
        self.assertEqual(["P1", "P2", "P3", "P3", "P3"], [contact["priority"] for contact in ordered])

    def test_chinese_titles_follow_the_same_priority(self) -> None:
        contacts = [
            {"full_name": "王总", "title": "首席执行官"},
            {"full_name": "李经理", "title": "商务经理"},
            {"full_name": "赵经理", "title": "采购经理"},
        ]

        ordered = sort_contacts(contacts)

        self.assertEqual(["赵经理", "李经理", "王总"], [contact["full_name"] for contact in ordered])


if __name__ == "__main__":
    unittest.main()
