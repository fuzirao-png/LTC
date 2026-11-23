"""Dependency direction contract: domain stays pure, application stays transport-free."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api" / "src" / "ltc"


class DomainPurityTests(unittest.TestCase):
    _FORBIDDEN = ("fastapi", "sqlalchemy")

    def test_domain_never_imports_framework_or_infrastructure(self) -> None:
        violations: list[str] = []
        for path in API_ROOT.glob("modules/*/domain/**/*.py"):
            for imported in self._imports(path):
                if imported.startswith(self._FORBIDDEN) or ".infrastructure" in imported:
                    violations.append(f"{path.relative_to(ROOT)} -> {imported}")
        self.assertEqual(
            [],
            violations,
            f"Domain layer must not import framework or infrastructure:\n"
            + "\n".join(violations),
        )

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


class ApplicationPurityTests(unittest.TestCase):
    _FORBIDDEN = ("fastapi", "sqlalchemy")

    def test_application_never_imports_transport_or_persistence_frameworks(self) -> None:
        violations: list[str] = []
        for path in API_ROOT.glob("modules/*/application/**/*.py"):
            for imported in self._imports(path):
                if imported.startswith(self._FORBIDDEN) or ".interfaces" in imported:
                    violations.append(f"{path.relative_to(ROOT)} -> {imported}")
        self.assertEqual(
            [],
            violations,
            f"Application layer must not import transport or persistence frameworks:\n"
            + "\n".join(violations),
        )

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
