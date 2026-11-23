from __future__ import annotations

from contextlib import contextmanager
import unittest
from uuid import UUID
from unittest.mock import patch

from ltc.modules.sales_crm.application.contact_roster_service import (
    ContactRosterError,
    ContactRosterService,
)
from ltc.modules.sales_crm.domain.contact_priority import RANKING_VERSION


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
CONTACT_ID = UUID("00000000-0000-0000-0000-000000000002")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000003")


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.calls.append((" ".join(query.split()), params))


class DummyDatabase:
    @contextmanager
    def transaction(self):
        yield object()


class _RosterCursor:
    def __init__(self, connection: "_RosterConnection") -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.connection.calls.append((" ".join(query.split()), params))

    def fetchall(self):
        return [{
            "contact_id": CONTACT_ID,
            "full_name": "Ada Lovelace",
            "title": "CTO",
            "department": "Technology",
            "status": "active",
            "email_status": "valid",
            "primary_email": "ada@example.com",
            "updated_at": None,
            "ranking_version": "contact-top5-v1",
            "priority_score": 70.0,
            "score_breakdown": {"role_relevance": 30.0},
            "last_contacted_at": None,
            "computed_last_engagement_at": None,
        }]


class _RosterConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self, **kwargs: object):
        return _RosterCursor(self)


class _FallbackRosterCursor:
    def __init__(self, connection: "_FallbackRosterConnection") -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.connection.calls.append((" ".join(query.split()), params))

    def fetchall(self):
        return [{
            "contact_id": CONTACT_ID,
            "company_id": COMPANY_ID,
            "full_name": "Global Marketing Contact",
            "title": "Director",
            "title_normalized": "director",
            "department": "Marketing",
            "relationship_role": "decision_maker",
            "status": "active",
            "email_status": "unknown",
            "primary_email": None,
            "normalized_email": None,
            "last_verified_at": None,
            "source_primary_email": "global.marketing@51tgt.com",
            "source_normalized_email": "global.marketing@51tgt.com",
            "source_email_status": "valid",
            "source_last_seen_at": None,
            "roster_status": "active",
            "position": 1,
            "ranking_version": "contact-top5-v1",
            "priority_score": 71.0,
            "score_breakdown": {"role_relevance": 30.0},
            "last_contacted_at": None,
            "computed_last_engagement_at": None,
        }]


class _FallbackRosterConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self, **kwargs: object):
        return _FallbackRosterCursor(self)


class ContactRosterServiceTests(unittest.TestCase):
    def test_needs_refresh_when_score_snapshot_changes(self) -> None:
        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        company = {
            "employee_count": 120,
            "company_intro": "Business travel platform",
            "integration": "",
            "esim_scenario": "",
        }
        rows = [
            {
                "contact_id": CONTACT_ID,
                "full_name": "Contact",
                "title": "CTO",
                "department": "Technology",
                "status": "active",
                "email_status": "valid",
                "primary_email": "cto@example.com",
                "updated_at": None,
                "ranking_version": "contact-top5-v1",
                "priority_score": 70.0,
                "score_breakdown": {"role_relevance": 30.0},
            }
        ]

        self.assertTrue(service._needs_refresh(company, rows))

    def test_needs_refresh_when_ranking_version_changes(self) -> None:
        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        company = {
            "employee_count": 120,
            "company_intro": "",
            "integration": "",
            "esim_scenario": "",
        }
        current = service._score_contact_for_company(company, {
            "contact_id": CONTACT_ID,
            "full_name": "Contact",
            "title": "BD Manager",
            "department": "Commercial",
            "status": "active",
            "email_status": "valid",
            "primary_email": "bd@example.com",
            "updated_at": None,
        })
        rows = [{
            "contact_id": CONTACT_ID,
            "full_name": "Contact",
            "title": "BD Manager",
            "department": "Commercial",
            "status": "active",
            "email_status": "valid",
            "primary_email": "bd@example.com",
            "updated_at": None,
            "ranking_version": "contact-top5-v1",
            "priority_score": current.score,
            "score_breakdown": current.breakdown,
        }]

        self.assertNotEqual("contact-top5-v1", RANKING_VERSION)
        self.assertTrue(service._needs_refresh(company, rows))

    def test_active_contact_without_email_requires_refresh(self) -> None:
        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        company = {
            "employee_count": 120,
            "company_intro": "Business travel platform",
            "integration": "",
            "esim_scenario": "",
        }
        rows = [
            {
                "contact_id": CONTACT_ID,
                "full_name": "Contact",
                "title": "CTO",
                "department": "Technology",
                "status": "active",
                "email_status": "unknown",
                "primary_email": "",
                "updated_at": None,
                "ranking_version": "contact-top5-v1",
                "priority_score": 55.8,
                "score_breakdown": {
                    "role_relevance": 37.8,
                    "seniority": 20.0,
                    "scene_relevance": 8.0,
                    "contact_quality": 0.0,
                    "freshness": 0.0,
                    "interaction": 0.0,
                    "company_size_bonus": 0.0,
                    "risk_deduction": 10.0,
                    "diversity_deduction": 0.0,
                },
                "roster_status": "active",
            }
        ]

        self.assertTrue(service._needs_refresh(company, rows))

    def test_contact_without_email_cannot_be_activated(self) -> None:
        with self.assertRaisesRegex(ContactRosterError, "联系人缺少邮箱"):
            service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
            service._activate(
                RecordingConnection(),
                COMPANY_ID,
                {
                    "contact_id": CONTACT_ID,
                    "roster_status": "backup",
                    "blocked_reason": "联系人缺少邮箱",
                },
                actor_user_id=ACTOR_ID,
                replace_contact_id=None,
                reason="manual activation",
            )
    def test_public_roster_row_exposes_contact_version_for_editing(self) -> None:
        row = {
            "contact_id": CONTACT_ID,
            "company_id": COMPANY_ID,
            "full_name": "Contact",
            "version": 7,
            "roster_version": 3,
        }

        public = ContactRosterService._public_row(row)

        self.assertEqual(7, public["version"])
        self.assertEqual(3, public["roster_version"])

    def test_get_roster_fills_primary_email_from_source_candidate(self) -> None:
        connection = _FallbackRosterConnection()

        class _Database:
            @contextmanager
            def transaction(self):
                yield connection

        service = ContactRosterService(_Database())  # type: ignore[arg-type]

        with (
            patch.object(service, "_require_company", return_value={"employee_count": 120, "company_intro": "", "integration": "", "esim_scenario": ""}),
            patch.object(service, "_needs_refresh", return_value=False),
        ):
            roster = service.get_roster(COMPANY_ID)

        self.assertEqual("global.marketing@51tgt.com", roster["active"][0]["primary_email"])
        self.assertEqual("valid", roster["active"][0]["email_status"])

    def test_contact_rows_join_candidate_contact_by_company_origin_candidate(self) -> None:
        connection = _RosterConnection()

        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        with patch.object(connection, "cursor", wraps=connection.cursor):
            service._contact_rows(connection, COMPANY_ID)  # type: ignore[arg-type]

        roster_query = next(query for query, _ in connection.calls if "FROM ltc.contact ct" in query)
        self.assertIn("LEFT JOIN LATERAL", roster_query)
        self.assertIn("origin_candidate_id", roster_query)

    def test_get_roster_recalculates_when_scores_are_stale(self) -> None:
        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        rows = [
            {
                "contact_id": CONTACT_ID,
                "full_name": "Contact",
                "title": "CTO",
                "department": "Technology",
                "status": "active",
                "email_status": "valid",
                "primary_email": "cto@example.com",
                "updated_at": None,
                "ranking_version": "contact-top5-v1",
                "priority_score": 70.0,
                "score_breakdown": {"role_relevance": 30.0},
            }
        ]

        with (
            patch.object(service, "_require_company", return_value={"employee_count": 120, "company_intro": "", "integration": "", "esim_scenario": ""}),
            patch.object(service, "_contact_rows", side_effect=[rows, rows]),
            patch.object(service, "_needs_refresh", return_value=True),
            patch.object(service, "_recalculate_locked", return_value={"refreshed": True}),
            patch.object(service, "_roster_payload_from_rows", return_value={"payload": True}),
        ):
            result = service.get_roster(COMPANY_ID)

        self.assertEqual(result, {"payload": True})

    def test_pin_moves_active_contact_to_top_and_shifts_preceding_contacts(self) -> None:
        connection = RecordingConnection()

        ContactRosterService._pin_to_top(
            connection,
            COMPANY_ID,
                {
                    "contact_id": CONTACT_ID,
                    "roster_status": "active",
                    "position": 4,
                    "primary_email": "ada@example.com",
                },
            actor_user_id=ACTOR_ID,
            reason="manual pin",
        )

        self.assertEqual(5, len(connection.calls))
        self.assertIn("roster_status='backup', position=NULL", connection.calls[0][0])
        self.assertEqual([3, 2, 1], [call[1][2] for call in connection.calls[1:4]])
        self.assertEqual([4, 3, 2], [call[1][0] for call in connection.calls[1:4]])
        self.assertIn("roster_status='active', position=1", connection.calls[4][0])
        self.assertEqual("manual pin", connection.calls[4][1][0])

    def test_pin_first_contact_only_updates_pin_state(self) -> None:
        connection = RecordingConnection()

        ContactRosterService._pin_to_top(
            connection,
            COMPANY_ID,
                {
                    "contact_id": CONTACT_ID,
                    "roster_status": "active",
                    "position": 1,
                    "primary_email": "ada@example.com",
                },
            actor_user_id=None,
            reason=None,
        )

        self.assertEqual(1, len(connection.calls))
        self.assertIn("is_pinned=true", connection.calls[0][0])

    def test_move_to_backup_requires_reason(self) -> None:
        with self.assertRaises(ContactRosterError) as context:
            ContactRosterService._move_to_backup(
                RecordingConnection(),
                {
                    "contact_id": CONTACT_ID,
                    "company_id": COMPANY_ID,
                    "is_pinned": False,
                    "engagement_locked": False,
                    "roster_status": "active",
                },
                reason="",
            )
        self.assertIn("原因", str(context.exception))

    def test_backup_contact_cannot_be_pinned(self) -> None:
        with self.assertRaisesRegex(ContactRosterError, "不能置顶"):
            ContactRosterService._pin_to_top(
                RecordingConnection(),
                COMPANY_ID,
                {
                    "contact_id": CONTACT_ID,
                    "roster_status": "backup",
                    "position": None,
                    "primary_email": "ada@example.com",
                },
                actor_user_id=None,
                reason=None,
            )

    def test_cannot_activate_contact_without_email(self) -> None:
        service = ContactRosterService(DummyDatabase())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ContactRosterError, "CONTACT_MISSING_EMAIL"):
            service._activate(
                RecordingConnection(),
                COMPANY_ID,
                {
                    "contact_id": CONTACT_ID,
                    "roster_status": "backup",
                    "primary_email": None,
                    "blocked_reason": None,
                },
                actor_user_id=ACTOR_ID,
                replace_contact_id=None,
                reason="manual add",
            )


if __name__ == "__main__":
    unittest.main()
