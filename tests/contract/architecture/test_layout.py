"""Architecture contract: directory layout, module layers, and manifest integrity."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api" / "src" / "ltc"
WORKER_ROOT = ROOT / "apps" / "worker" / "src" / "ltc_worker"
WEB_ROOT = ROOT / "apps" / "web"
CHECKSUM_MANIFEST = ROOT / "contracts" / "v3.6.sha256"


class RepositoryLayoutTests(unittest.TestCase):
    def test_top_level_directories_exist(self) -> None:
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
        missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
        self.assertEqual([], missing, f"Missing directories: {missing}")

    def test_all_backend_modules_have_required_layers(self) -> None:
        for module in (
            "iam",
            "lead_intelligence",
            "sales_crm",
            "customer_analysis",
            "customer_operation",
        ):
            for layer in ("interfaces", "application", "domain", "infrastructure"):
                path = API_ROOT / "modules" / module / layer
                self.assertTrue(path.is_dir(), f"Missing: {module}/{layer}")
        self.assertTrue((API_ROOT / "modules" / "read_models" / "interfaces").is_dir())
        self.assertTrue((API_ROOT / "modules" / "read_models" / "queries").is_dir())

    def test_no_deferred_feature_scaffolding(self) -> None:
        """S4/S5, Manager/Boss, handover, approval, and override scaffolding must not exist."""
        forbidden_dirs = [
            API_ROOT / "modules" / "sales_management",
            API_ROOT / "modules" / "manager",
            API_ROOT / "modules" / "approval",
        ]
        for d in forbidden_dirs:
            self.assertFalse(d.exists(), f"Deferred directory exists: {d}")
        if WEB_ROOT.exists():
            self.assertEqual(
                [],
                list(WEB_ROOT.rglob("*sales-management*")),
                "Deferred frontend sales-management scaffolding found",
            )

    def test_docker_is_complete_execution_boundary(self) -> None:
        required = (
            ROOT / "compose.yaml",
            ROOT / "apps" / "api" / "Dockerfile",
            ROOT / "apps" / "worker" / "Dockerfile",
            ROOT / "apps" / "web" / "Dockerfile",
            ROOT / "tests" / "integration" / "Dockerfile",
            ROOT / "scripts" / "init_database_container.sh",
        )
        missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
        self.assertEqual([], missing, f"Missing Docker boundary files: {missing}")


class ManifestIntegrityTests(unittest.TestCase):
    def test_frozen_artifacts_match_checksums(self) -> None:
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
        self.assertEqual([], failures, f"Manifest mismatch: {failures}")
