"""Tests for CustomerActivity domain model."""

from __future__ import annotations

import uuid
import unittest

from ltc.modules.customer_operation.domain.customer_activity import CustomerActivity


class CustomerActivityTests(unittest.TestCase):
    def test_default_activity_is_system_type(self) -> None:
        activity = CustomerActivity()
        self.assertEqual("system", activity.activity_type)
        self.assertEqual("system", activity.source_type)
        self.assertIsInstance(activity.activity_id, uuid.UUID)

    def test_manual_call_activity(self) -> None:
        cid = uuid.uuid4()
        uid = uuid.uuid4()
        activity = CustomerActivity(
            company_id=cid,
            activity_type="call",
            direction="outbound",
            subject="Introduction call",
            body="Discussed product fit",
            outcome_code="interested",
            actor_user_id=uid,
            source_type="manual",
        )
        self.assertTrue(activity.is_manual())
        self.assertTrue(activity.is_outbound())
        self.assertEqual("call", activity.activity_type)
        self.assertEqual("interested", activity.outcome_code)

    def test_system_generated_activity_is_not_manual(self) -> None:
        activity = CustomerActivity(source_type="system")
        self.assertFalse(activity.is_manual())

    def test_inbound_direction(self) -> None:
        activity = CustomerActivity(direction="inbound")
        self.assertFalse(activity.is_outbound())

    def test_occurred_at_defaults_to_now(self) -> None:
        from datetime import datetime, timezone

        activity = CustomerActivity()
        self.assertIsInstance(activity.occurred_at, datetime)
        self.assertIsInstance(activity.created_at, datetime)
        # Both should be very close to now
        now = datetime.now(timezone.utc)
        delta = abs((now - activity.occurred_at).total_seconds())
        self.assertLess(delta, 5, "occurred_at should be within 5s of now")

    def test_payload_defaults_to_empty_dict(self) -> None:
        activity = CustomerActivity()
        self.assertEqual({}, activity.payload)

    def test_payload_with_custom_data(self) -> None:
        activity = CustomerActivity(
            payload={"call_duration_seconds": 120, "recording_url": "https://example.com/rec"}
        )
        self.assertEqual(120, activity.payload["call_duration_seconds"])

    def test_source_external_key(self) -> None:
        activity = CustomerActivity(
            source_type="manual",
            source_external_key="ext-ref-12345",
        )
        self.assertEqual("ext-ref-12345", activity.source_external_key)
