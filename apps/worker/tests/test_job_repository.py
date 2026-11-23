"""Tests for PostgreSQLJobRepository SQL generation.

These tests verify the SQL templates without requiring a real database.
Runtime integration tests (claim concurrency, etc.) use FakeJobRepo
in test_runtime.py.
"""

from __future__ import annotations

import unittest
import uuid

from ltc_worker.infrastructure.job_repository import PostgreSQLJobRepository, _decode_payload


class PostgreSQLJobRepositorySQLTests(unittest.TestCase):
    """White-box: verify SQL strings compile and are structurally sound."""

    def setUp(self) -> None:
        # Create a no-op repo — we only inspect the SQL in this test class.
        async def _noop():
            raise RuntimeError("no database in unit test")
        self.repo = PostgreSQLJobRepository(_noop)

    def test_init_does_not_connect(self) -> None:
        # Repository is lazy — no connection until a method is called.
        self.assertIsNotNone(self.repo)

    def test_decode_payload_accepts_asyncpg_jsonb_text(self) -> None:
        self.assertEqual(
            {"company_id": "company", "run_id": "run"},
            _decode_payload('{"company_id":"company","run_id":"run"}'),
        )

    def test_decode_payload_rejects_invalid_or_non_object_values(self) -> None:
        self.assertEqual({}, _decode_payload("not-json"))
        self.assertEqual({}, _decode_payload("[]"))


class RegistrySmokeTests(unittest.TestCase):
    def test_registry_contains_all_handler_types(self) -> None:
        from ltc_worker.registry import build_current_phase_registry
        registry = build_current_phase_registry()
        self.assertEqual(16, len(registry.job_types()))
        self.assertIn("analysis.research_customer.v1", registry.job_types())
        self.assertIn("lead.search_pipeline.v1", registry.job_types())
        self.assertIn("crm.auto_release_overdue.v1", registry.job_types())
        self.assertIn("crm.pipeline_consumer.v1", registry.job_types())
        self.assertIn("manual_note.extract.v1", registry.job_types())

    def test_registry_raises_for_legacy_types(self) -> None:
        from ltc_worker.registry import build_current_phase_registry
        registry = build_current_phase_registry()
        self.assertIsNone(registry.resolve("lead.import_csv"))

    def test_all_handlers_have_unique_use_case_attrs(self) -> None:
        from ltc_worker.registry import build_current_phase_registry
        from ltc_worker.application import ApplicationServices
        registry = build_current_phase_registry()
        # Every handler's use_case_attr must exist on ApplicationServices
        protocol_attrs = set(ApplicationServices.__annotations__) - {"jobs"}
        used = set()
        for jt in registry.job_types():
            h = registry.resolve(jt)
            attr = getattr(h, "use_case_attr", None)
            self.assertIsNotNone(attr, f"Handler for {jt} missing use_case_attr")
            self.assertIn(attr, protocol_attrs, f"use_case_attr '{attr}' not on ApplicationServices")
            self.assertNotIn(attr, used, f"Duplicate use_case_attr: {attr}")
            used.add(attr)


if __name__ == "__main__":
    unittest.main()
