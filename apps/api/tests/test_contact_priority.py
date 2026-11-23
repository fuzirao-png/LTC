from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ltc.modules.sales_crm.domain.contact_priority import score_contact, select_top_contacts


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _contact(contact_id: str, title: str, **values: object) -> dict[str, object]:
    return {
        "contact_id": contact_id,
        "full_name": f"Contact {contact_id}",
        "title": title,
        "title_normalized": title.casefold(),
        "status": "active",
        "email_status": "valid",
        "primary_email": f"{contact_id}@example.com",
        "updated_at": NOW,
        **values,
    }


def _contact_without_email(contact_id: str, title: str, **values: object) -> dict[str, object]:
    contact = _contact(contact_id, title, **values)
    contact["primary_email"] = ""
    contact["email_status"] = "unknown"
    return contact


class ContactPriorityTests(unittest.TestCase):
    def test_score_contact_prefers_relevant_procurement_role(self) -> None:
        procurement = score_contact(
            _contact("procurement", "Head of Procurement"),
            now=NOW,
            scene_text="Cross-border eSIM API integration",
        )
        unrelated = score_contact(
            _contact("hr", "HR Coordinator"),
            now=NOW,
            scene_text="Cross-border eSIM API integration",
        )

        self.assertEqual(procurement.role_group, "procurement")
        self.assertGreater(procurement.score, unrelated.score)
        self.assertEqual(procurement.breakdown["contact_quality"], 10)

    def test_email_verification_status_affects_score(self) -> None:
        verified = score_contact(_contact("valid", "BD Manager"), now=NOW)
        unknown = score_contact(
            _contact("unknown", "BD Manager", email_status="unknown"), now=NOW
        )
        risky = score_contact(
            _contact("risky", "BD Manager", email_status="risky"), now=NOW
        )

        self.assertTrue(unknown.eligible)
        self.assertGreater(verified.score, unknown.score)
        self.assertEqual(unknown.score, risky.score)
        self.assertEqual(verified.breakdown["contact_quality"], 10)
        self.assertEqual(unknown.breakdown["contact_quality"], 6)
        self.assertEqual(unknown.breakdown["risk_deduction"], 15)

    def test_verified_email_scores_higher_than_unverified_email(self) -> None:
        verified = score_contact(_contact("verified", "BD Manager", email_status="valid"), now=NOW)
        unverified = score_contact(
            _contact("unverified", "BD Manager", email_status="unknown"), now=NOW
        )

        self.assertEqual(verified.breakdown["contact_quality"], 10)
        self.assertEqual(unverified.breakdown["contact_quality"], 6)
        self.assertEqual(unverified.breakdown["risk_deduction"], 15)
        self.assertGreater(verified.score, unverified.score)

    def test_linkedin_only_contact_gets_prd_quality_score(self) -> None:
        linkedin_only = score_contact(
            _contact(
                "linkedin",
                "BD Manager",
                primary_email="",
                linkedin_url="https://www.linkedin.com/in/example",
            ),
            now=NOW,
        )

        self.assertEqual(linkedin_only.breakdown["contact_quality"], 3)

    def test_last_verified_at_takes_priority_over_updated_at_for_freshness(self) -> None:
        contact = score_contact(
            _contact(
                "fresh",
                "BD Manager",
                updated_at=NOW.replace(year=2024),
                last_verified_at=NOW,
            ),
            now=NOW,
        )

        self.assertEqual(contact.breakdown["freshness"], 5)

    def test_scene_relevance_does_not_come_from_company_keywords(self) -> None:
        contact = score_contact(
            _contact("hr", "HR Manager", department="Human Resources"),
            now=NOW,
            scene_text="Travel API esim telecom",
        )

        self.assertEqual(contact.breakdown["scene_relevance"], 0)

    def test_director_does_not_match_cto_abbreviation(self) -> None:
        commercial = score_contact(_contact("commercial", "Commercial Director"), now=NOW)
        product = score_contact(_contact("product", "Product Director"), now=NOW)

        self.assertEqual(commercial.seniority_level, "director_head")
        self.assertEqual(commercial.role_group, "commercial")
        self.assertEqual(product.seniority_level, "director_head")
        self.assertEqual(product.role_group, "product")

    def test_contact_without_email_is_ineligible(self) -> None:
        result = score_contact(
            _contact("no-email", "Head of Procurement", primary_email=""),
            now=NOW,
        )

        self.assertFalse(result.eligible)
        self.assertEqual("联系人缺少邮箱", result.blocked_reason)

    def test_contact_with_whitespace_email_is_ineligible(self) -> None:
        result = score_contact(
            _contact("blank-email", "VP Commercial", primary_email="   "),
            now=NOW,
        )

        self.assertFalse(result.eligible)
        self.assertEqual("联系人缺少邮箱", result.blocked_reason)

    def test_contact_without_email_does_not_consume_top_five_slot(self) -> None:
        contacts = [
            _contact("no-email", "Head of Procurement", primary_email=""),
            _contact("commercial", "VP Commercial"),
        ]

        selected = select_top_contacts(score_contact(item, now=NOW) for item in contacts)

        self.assertEqual(
            ["commercial"],
            [item.contact["contact_id"] for item in selected],
        )
    def test_first_touch_can_allow_any_non_empty_email_status(self) -> None:
        result = score_contact(
            _contact("invalid-first-touch", "BD Manager", email_status="invalid"),
            now=NOW,
            allow_any_email_status=True,
        )

        self.assertTrue(result.eligible)
        self.assertIsNone(result.blocked_reason)
    def test_suppressed_departed_or_bounced_contacts_are_ineligible(self) -> None:
        suppressed = score_contact(_contact("a", "CTO", is_suppressed=True), now=NOW)
        departed = score_contact(
            _contact("b", "VP Commercial", employment_status="departed"), now=NOW
        )
        bounced = score_contact(
            _contact("c", "Product Director", email_status="bounced"), now=NOW
        )

        self.assertFalse(suppressed.eligible)
        self.assertFalse(departed.eligible)
        self.assertFalse(bounced.eligible)

    def test_top_five_uses_role_slots_and_department_limit(self) -> None:
        contacts = [
            _contact("p1", "Head of Procurement", department="Procurement"),
            _contact("p2", "Procurement Manager", department="Procurement"),
            _contact("p3", "Purchasing Manager", department="Procurement"),
            _contact("c1", "VP Commercial", department="Commercial"),
            _contact("b1", "General Manager", department="Business"),
            _contact("t1", "CTO", department="Technology"),
            _contact("o1", "Operations Manager", department="Operations"),
        ]
        selected = select_top_contacts(score_contact(item, now=NOW) for item in contacts)

        self.assertEqual(len(selected), 5)
        self.assertEqual(
            [item.role_group for item in selected[:4]],
            ["procurement", "commercial", "business", "technical"],
        )
        self.assertLessEqual(
            sum(item.contact["department"] == "Procurement" for item in selected), 2
        )

    def test_top_five_skips_contacts_without_email(self) -> None:
        contacts = [
            _contact_without_email("p1", "Head of Procurement", department="Procurement"),
            _contact_without_email("c1", "VP Commercial", department="Commercial"),
            _contact("b1", "General Manager", department="Business"),
        ]
        selected = select_top_contacts(score_contact(item, now=NOW) for item in contacts)

        self.assertEqual([item.contact["contact_id"] for item in selected], ["b1"])

    def test_pinned_contact_is_preserved_during_recalculation(self) -> None:
        pinned = _contact("pinned", "Marketing Assistant", is_pinned=True, position=1)
        selected = select_top_contacts([
            score_contact(pinned, now=NOW),
            score_contact(_contact("procurement", "Procurement Director"), now=NOW),
            score_contact(_contact("commercial", "BD Director"), now=NOW),
        ])

        self.assertEqual(selected[0].contact["contact_id"], "pinned")


if __name__ == "__main__":
    unittest.main()
