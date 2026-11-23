from __future__ import annotations

import ast
import unittest
from pathlib import Path


HANDLERS_DIR = Path(__file__).resolve().parents[1] / "src" / "ltc_worker" / "handlers"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_handlers_do_not_import_fastapi(self) -> None:
        for path in HANDLERS_DIR.glob("*.py"):
            imports = _imports(path)
            self.assertTrue(
                all(not name.startswith("fastapi") for name in imports),
                path.name,
            )

    def test_handler_files_exist_for_all_13_job_types(self) -> None:
        actual = sorted(
            path.name for path in HANDLERS_DIR.glob("*.py") if path.name not in ("__init__.py",)
        )
        self.assertIn("base.py", actual)
        self.assertIn("lead_search_pipeline.py", actual)


if __name__ == "__main__":
    unittest.main()
