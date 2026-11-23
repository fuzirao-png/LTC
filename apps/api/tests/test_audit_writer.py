"""Tests for AuditEvent domain model and InMemoryAuditWriter."""

from __future__ import annotations

import asyncio
import uuid
import unittest
from datetime import datetime, timezone

from ltc.platform.observability.domain.audit_event import AuditEvent
from ltc.platform.observability.infrastructure.audit_writer import InMemoryAuditWriter


class AuditEventTests(unittest.TestCase):
    def test_defaults_produce_valid_event(self) -> None:
        event = AuditEvent(action="user.login", resource_type="auth_session")
        self.assertEqual("user.login", event.action)
        self.assertEqual("auth_session", event.resource_type)
        self.assertIsNone(event.resource_id)
        self.assertIsNone(event.actor_user_id)
        self.assertIsInstance(event.occurred_at, datetime)

    def test_all_fields_populated_roundtrip(self) -> None:
        rid = uuid.uuid4()
        uid = uuid.uuid4()
        jid = uuid.uuid4()
        event = AuditEvent(
            action="lead.claimed",
            resource_type="sales_lead",
            resource_id=rid,
            actor_user_id=uid,
            job_id=jid,
            before_data={"status": "claimable"},
            after_data={"status": "claimed", "owner_id": str(uid)},
            metadata={"ip": "10.0.0.1"},
        )
        self.assertEqual("lead.claimed", event.action)
        self.assertEqual(rid, event.resource_id)
        self.assertEqual(uid, event.actor_user_id)
        self.assertEqual(jid, event.job_id)
        self.assertEqual({"status": "claimable"}, event.before_data)
        self.assertEqual({"status": "claimed", "owner_id": str(uid)}, event.after_data)
        self.assertEqual({"ip": "10.0.0.1"}, event.metadata)

    def test_with_occurred_at_returns_new_instance_with_different_time(self) -> None:
        original = AuditEvent(action="test", resource_type="test")
        new_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        copy = original.with_occurred_at(new_time)
        self.assertEqual(new_time, copy.occurred_at)
        self.assertNotEqual(original.occurred_at, copy.occurred_at)
        self.assertEqual(original.action, copy.action)

    def test_slots_prevent_attribute_creation(self) -> None:
        event = AuditEvent(action="x", resource_type="y")
        with self.assertRaises(AttributeError):
            event.non_existent_field = 1  # type: ignore[attr-defined]


class InMemoryAuditWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = InMemoryAuditWriter()

    def test_writes_are_collected(self) -> None:
        event = AuditEvent(action="lead.created", resource_type="sales_lead")
        asyncio.run(self.writer.record(event))
        self.assertEqual(1, len(self.writer.records))
        self.assertEqual("lead.created", self.writer.records[0].action)

    def test_clear_resets_records(self) -> None:
        asyncio.run(self.writer.record(AuditEvent(action="x", resource_type="y")))
        self.writer.clear()
        self.assertEqual(0, len(self.writer.records))

    def test_actions_returns_ordered_action_list(self) -> None:
        asyncio.run(self.writer.record(AuditEvent(action="a", resource_type="x")))
        asyncio.run(self.writer.record(AuditEvent(action="b", resource_type="x")))
        asyncio.run(self.writer.record(AuditEvent(action="c", resource_type="x")))
        self.assertEqual(["a", "b", "c"], self.writer.actions())

    def test_for_resource_filters_correctly(self) -> None:
        rid = uuid.uuid4()
        asyncio.run(
            self.writer.record(
                AuditEvent(action="lead.claimed", resource_type="sales_lead", resource_id=rid)
            )
        )
        asyncio.run(
            self.writer.record(
                AuditEvent(action="lead.released", resource_type="sales_lead", resource_id=rid)
            )
        )
        asyncio.run(
            self.writer.record(
                AuditEvent(action="company.created", resource_type="company")
            )
        )
        matches = self.writer.for_resource("sales_lead", rid)
        self.assertEqual(2, len(matches))
