"""Tests for worker registry: all versioned handler types registered."""

from __future__ import annotations

import unittest

from ltc_worker.registry import build_current_phase_registry


class RegistryTests(unittest.TestCase):
    def test_registry_contains_all_handler_types(self) -> None:
        registry = build_current_phase_registry()
        self.assertEqual(
            (
                "analysis.generate_report.v1",
                "analysis.research_customer.v1",
                "crm.auto_release_overdue.v1",
                "crm.pipeline_consumer.v1",
                "data_completion.region.v1",
                "data_completion.scale.v1",
                "engagement.generate_email_draft.v1",
                "engagement.process_meeting.v1",
                "engagement.reconcile_email.v1",
                "engagement.send_email.v1",
                "lead.refresh_candidate.v1",
                "lead.search_pipeline.v1",
                "manual_note.extract.v1",
                "platform.dispatch_outbox.v1",
                "platform.notify.v1",
                "platform.process_external_event.v1",
            ),
            registry.job_types(),
        )

    def test_registry_raises_for_legacy_sqlite_jobs(self) -> None:
        registry = build_current_phase_registry()
        for legacy_type in (
            "analysis.generate_report",  # unversioned
            "lead.import_csv",           # not in architecture
        ):
            self.assertIsNone(registry.resolve(legacy_type))


if __name__ == "__main__":
    unittest.main()
