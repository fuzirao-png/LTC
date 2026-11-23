from __future__ import annotations

import ast
import hashlib
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "api" / "src" / "ltc"
WORKER_ROOT = ROOT / "apps" / "worker" / "src" / "ltc_worker"
WEB_ROOT = ROOT / "apps" / "web"
OWNERSHIP_MIGRATIONS = (
    ROOT / "db" / "migrations" / "0001_v3_6_initial.sql",
    ROOT / "db" / "migrations" / "0017_contact_priority_roster.sql",
)
SEED = ROOT / "db" / "seeds" / "0001_region_country_v5.sql"
OPENAPI = ROOT / "contracts" / "openapi" / "LTC_OpenAPI_v3.6.yaml"
CHECKSUM_MANIFEST = ROOT / "contracts" / "v3.6.sha256"
OWNERSHIP_EXTENSIONS = (
    ROOT / "db" / "migrations" / "0024_email_automation_agent.sql",
    ROOT / "db" / "migrations" / "0039_resumable_meeting_transcription.sql",
)

sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from ltc.modules.registry import MODULE_OWNED_TABLES, PLATFORM_OWNED_TABLES  # noqa: E402


class RepositoryShapeTests(unittest.TestCase):
    def test_architecture_defined_top_level_layout_exists(self) -> None:
        required = [
            API_ROOT,
            WORKER_ROOT / "handlers",
            WEB_ROOT / "src" / "app",
            WEB_ROOT / "src" / "features",
            WEB_ROOT / "src" / "entities",
            WEB_ROOT / "src" / "shared" / "api",
            ROOT / "db" / "migrations",
            ROOT / "db" / "seeds",
            ROOT / "tests" / "unit",
            ROOT / "tests" / "integration",
            ROOT / "tests" / "contract",
            ROOT / "tests" / "e2e",
            ROOT / "archive" / "legacy",
        ]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
        self.assertEqual([], missing)

    def test_all_current_backend_modules_have_the_defined_layers(self) -> None:
        for module in (
            "iam",
            "lead_intelligence",
            "sales_crm",
            "customer_analysis",
            "customer_operation",
        ):
            for layer in ("interfaces", "application", "domain", "infrastructure"):
                self.assertTrue((API_ROOT / "modules" / module / layer).is_dir(), f"{module}/{layer}")
        self.assertTrue((API_ROOT / "modules" / "read_models" / "interfaces").is_dir())
        self.assertTrue((API_ROOT / "modules" / "read_models" / "queries").is_dir())

    def test_deferred_frontend_sales_management_is_not_scaffolded(self) -> None:
        forbidden = list(WEB_ROOT.rglob("*sales-management*")) if WEB_ROOT.exists() else []
        self.assertEqual([], forbidden)

    def test_docker_is_the_complete_local_execution_boundary(self) -> None:
        required = (
            ROOT / "compose.yaml",
            ROOT / "apps" / "api" / "Dockerfile",
            ROOT / "apps" / "worker" / "Dockerfile",
            ROOT / "apps" / "web" / "Dockerfile",
            ROOT / "tests" / "integration" / "Dockerfile",
            ROOT / "scripts" / "init_database_container.sh",
        )
        self.assertEqual([], [str(path.relative_to(ROOT)) for path in required if not path.is_file()])


class FrozenContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = "\n".join(
            path.read_text(encoding="utf-8") for path in OWNERSHIP_MIGRATIONS
        )
        cls.seed = SEED.read_text(encoding="utf-8")
        cls.openapi = OPENAPI.read_text(encoding="utf-8")

    def test_database_contract_is_the_reviewed_v36_shape(self) -> None:
        migration_tables = set(re.findall(r"(?im)^CREATE TABLE ltc\.([a-z_]+)", self.sql))
        owned_tables = {
            table
            for ownership in (MODULE_OWNED_TABLES, PLATFORM_OWNED_TABLES)
            for tables in ownership.values()
            for table in tables
        }
        self.assertEqual(44, len(migration_tables))
        extension_tables = {
            table for path in OWNERSHIP_EXTENSIONS
            for table in re.findall(r"(?im)^CREATE TABLE ltc\.([a-z_]+)", path.read_text(encoding="utf-8"))
        }
        self.assertEqual(migration_tables | extension_tables, owned_tables)
        self.assertIn("CREATE OR REPLACE VIEW ltc.v_sales_lead_pool", self.sql)
        self.assertIn("ct_sales_lead_assignment_consistency_on_lead", self.sql)
        self.assertIn("ct_user_assignment_consistency", self.sql)

    def test_frozen_architecture_artifacts_match_manifest(self) -> None:
        failures: list[str] = []
        for line in CHECKSUM_MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            expected, relative_path = line.split("  ", 1)
            artifact = ROOT / relative_path
            if not artifact.is_file():
                failures.append(f"missing: {relative_path}")
                continue
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f"checksum drift: {relative_path}")
        self.assertEqual([], failures)

    def test_region_seed_is_complete_and_versioned(self) -> None:
        self.assertIn("seed_count <> 205 OR region_count <> 6", self.seed)
        self.assertIn("region-country-v5", self.seed)

    def test_current_scope_excludes_deferred_contracts(self) -> None:
        combined = f"{self.sql}\n{self.openapi}".lower()
        for token in ("manager", "boss", "hospitality_airline", "app_studio"):
            self.assertNotIn(token, combined)
        self.assertIsNone(re.search(r"\bS4\b|\bS5\b", f"{self.sql}\n{self.openapi}"))

    def test_apollo_is_not_a_public_api_surface(self) -> None:
        self.assertNotIn("/apollo", self.openapi.lower())
        self.assertNotIn("provider_code:", self._search_request_block().lower())

    def test_email_agent_contract_is_declared(self) -> None:
        self.assertIn("/customer-operation/email/agent:", self.openapi)
        self.assertIn("operationId: runEmailAgent", self.openapi)
        self.assertIn("EmailAgentRequest:", self.openapi)
        self.assertIn("EmailAgentResult:", self.openapi)

    def _search_request_block(self) -> str:
        match = re.search(
            r"(?ms)^\s{4}LeadSearchRunCreateRequest:\n(.*?)(?=^\s{4}[A-Za-z].*:\n|\Z)",
            self.openapi,
        )
        self.assertIsNotNone(match, "LeadSearchRunCreateRequest schema missing")
        return match.group(1)  # type: ignore[union-attr]


class DependencyDirectionTests(unittest.TestCase):
    def test_domain_does_not_import_framework_or_infrastructure(self) -> None:
        forbidden_prefixes = ("fastapi", "sqlalchemy")
        violations: list[str] = []
        for path in API_ROOT.glob("modules/*/domain/**/*.py"):
            for imported in self._imports(path):
                if imported.startswith(forbidden_prefixes) or ".interfaces" in imported:
                    violations.append(f"{path.relative_to(ROOT)} -> {imported}")
        self.assertEqual([], violations)

    def test_application_does_not_import_transport_or_persistence_frameworks(self) -> None:
        forbidden_prefixes = ("fastapi", "sqlalchemy")
        violations: list[str] = []
        for path in API_ROOT.glob("modules/*/application/**/*.py"):
            for imported in self._imports(path):
                if imported.startswith(forbidden_prefixes) or ".interfaces" in imported:
                    violations.append(f"{path.relative_to(ROOT)} -> {imported}")
        self.assertEqual([], violations)

    @staticmethod
    def _imports(path: Path) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return imports


class LegacyIsolationTests(unittest.TestCase):
    def test_new_runtime_does_not_import_legacy_services_or_sqlite(self) -> None:
        runtime_roots = [path for path in (API_ROOT, WORKER_ROOT, WEB_ROOT / "src") if path.exists()]
        forbidden = (
            "sqlite3",
            "127.0.0.1:8765",
            "127.0.0.1:8787",
            "127.0.0.1:8790",
        )
        violations: list[str] = []
        for root in runtime_roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".ts", ".vue"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in text:
                        violations.append(f"{path.relative_to(ROOT)} -> {token}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
