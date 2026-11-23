from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_database.py"
INITIALIZER = ROOT / "scripts" / "init_database_container.sh"


def load_verification_module():
    spec = importlib.util.spec_from_file_location("verify_database", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatabaseVerificationContractTests(unittest.TestCase):
    def test_acceptance_uses_every_migration_in_filename_order(self) -> None:
        module = load_verification_module()
        expected = tuple(sorted((ROOT / "db" / "migrations").glob("*.sql")))

        self.assertEqual(expected, module.migration_files())
        self.assertIn(ROOT / "db" / "migrations" / "0004_relax_analysis_run_constraints.sql", expected)
        self.assertEqual((55, 3), module.expected_catalog_shape(expected))

    def test_initializer_does_not_reject_new_migration_tables(self) -> None:
        initializer = INITIALIZER.read_text(encoding="utf-8")

        self.assertNotIn("catalog_table_count", initializer)
        self.assertIn("catalog=$catalog_shape", initializer)

    def test_nested_docker_flow_does_not_bind_mount_container_paths(self) -> None:
        verification = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn('"-v", f"{CUSTOMER_ANALYSIS_PY}', verification)
        self.assertIn('"docker", "cp", str(CUSTOMER_ANALYSIS_PY)', verification)


if __name__ == "__main__":
    unittest.main()
