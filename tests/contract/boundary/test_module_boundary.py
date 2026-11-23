"""Module boundary contract: table ownership, data model alignment, and legacy isolation."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api" / "src" / "ltc"
WORKER_ROOT = ROOT / "apps" / "worker" / "src" / "ltc_worker"
WEB_ROOT = ROOT / "apps" / "web"
OWNERSHIP_MIGRATIONS = (
    ROOT / "db" / "migrations" / "0001_v3_6_initial.sql",
    ROOT / "db" / "migrations" / "0017_contact_priority_roster.sql",
    ROOT / "db" / "migrations" / "0024_email_automation_agent.sql",
    ROOT / "db" / "migrations" / "0039_resumable_meeting_transcription.sql",
)
SEED = ROOT / "db" / "seeds" / "0001_region_country_v5.sql"
OPENAPI = ROOT / "contracts" / "openapi" / "LTC_OpenAPI_v3.6.yaml"

sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from ltc.modules.registry import MODULE_OWNED_TABLES, PLATFORM_OWNED_TABLES  # noqa: E402


class TableOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = "\n".join(
            path.read_text(encoding="utf-8") for path in OWNERSHIP_MIGRATIONS
        )

    def test_all_migration_tables_have_an_owner(self) -> None:
        migration_tables = set(re.findall(r"(?im)^CREATE TABLE ltc\.([a-z_]+)", self.sql))
        owned_tables = {
            table
            for ownership in (MODULE_OWNED_TABLES, PLATFORM_OWNED_TABLES)
            for tables in ownership.values()
            for table in tables
        }
        self.assertEqual(48, len(migration_tables), "Expected exactly 48 owned tables")
        self.assertEqual(
            migration_tables,
            owned_tables,
            f"Unclaimed tables: {migration_tables - owned_tables}; "
            f"Zombie claims: {owned_tables - migration_tables}",
        )

    def test_key_views_and_triggers_present(self) -> None:
        self.assertIn("CREATE OR REPLACE VIEW ltc.v_sales_lead_pool", self.sql)
        self.assertIn("ct_sales_lead_assignment_consistency_on_lead", self.sql)
        self.assertIn("ct_user_assignment_consistency", self.sql)


class ScopeExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.combined = (
            "\n".join(path.read_text(encoding="utf-8") for path in OWNERSHIP_MIGRATIONS)
            + "\n"
            + OPENAPI.read_text(encoding="utf-8")
        ).lower()

    def test_no_deferred_scene_codes(self) -> None:
        self.assertIsNone(
            re.search(r"\bS4\b|\bS5\b", self.combined),
            "S4/S5 scene codes must not appear in SQL or OpenAPI",
        )

    def test_no_deferred_account_types(self) -> None:
        for token in ("manager", "boss"):
            self.assertNotIn(
                token, self.combined, f"'{token}' must not appear in SQL or OpenAPI"
            )

    def test_no_deferred_business_domains(self) -> None:
        for token in ("hospitality_airline", "app_studio"):
            self.assertNotIn(
                token, self.combined, f"'{token}' must not appear in SQL or OpenAPI"
            )

    def test_apollo_not_a_public_api_surface(self) -> None:
        self.assertNotIn("/apollo", self.combined)
        match = re.search(
            r"(?ms)^\s{4}LeadSearchRunCreateRequest:\n(.*?)(?=^\s{4}[A-Za-z].*:\n|\Z)",
            OPENAPI.read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(match, "LeadSearchRunCreateRequest schema missing")
        self.assertNotIn("provider_code:", match.group(1).lower())


class RegionSeedTests(unittest.TestCase):
    def test_seed_complete_and_versioned(self) -> None:
        seed = SEED.read_text(encoding="utf-8")
        self.assertIn("seed_count <> 205 OR region_count <> 6", seed)
        self.assertIn("region-country-v5", seed)


class LegacyIsolationTests(unittest.TestCase):
    _FORBIDDEN = (
        "sqlite3",
        "127.0.0.1:8765",
        "127.0.0.1:8787",
        "127.0.0.1:8790",
    )

    def test_runtime_never_imports_legacy_or_sqlite(self) -> None:
        runtime_roots = [p for p in (API_ROOT, WORKER_ROOT, WEB_ROOT / "src") if p.exists()]
        violations: list[str] = []
        for root in runtime_roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".ts", ".vue"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for token in self._FORBIDDEN:
                    if token in text:
                        violations.append(f"{path.relative_to(ROOT)} -> {token}")
        self.assertEqual(
            [], violations, f"Legacy/sqlite references in runtime: {violations}"
        )
