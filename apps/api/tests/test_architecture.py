from __future__ import annotations

import ast
import unittest
from pathlib import Path

from ltc.modules.registry import (
    MODULE_DEFINITIONS,
    MODULE_OWNED_TABLES,
    MODULE_OWNERSHIP,
    PLATFORM_OWNED_TABLES,
    READ_MODEL_LAYER_NAMES,
    STANDARD_LAYER_NAMES,
)


TESTS_ROOT = Path(__file__).resolve().parent
API_ROOT = TESTS_ROOT.parent
SRC_ROOT = API_ROOT / "src"
MODULES_ROOT = SRC_ROOT / "ltc" / "modules"
PLATFORM_ROOT = SRC_ROOT / "ltc" / "platform"

FORBIDDEN_LAYER_IMPORTS = {
    "interfaces": (".infrastructure",),
    "application": (".interfaces",),
    "domain": (".interfaces", ".application", ".infrastructure"),
    "infrastructure": (".interfaces",),
}

FORBIDDEN_FRAMEWORK_IMPORTS = {
    "domain": ("fastapi", "sqlalchemy"),
}

EXPECTED_OWNED_TABLES = {
    "iam": (
        "user_account",
        "auth_session",
        "ref_region_country",
    ),
    "lead_intelligence": (
        "lead_search_run",
        "search_provider_execution",
        "search_evidence",
        "lead_candidate",
        "candidate_observation",
        "candidate_evidence",
        "candidate_contact",
        "lead_enrichment_run",
        "enrichment_evidence",
        "lead_icp_assessment",
        "customer_scale_assessment",
        "lead_negative_filter_result",
        "email_automation_config",
        "email_automation_run",
        "email_automation_touch",
    ),
    "sales_crm": (
        "company",
        "contact",
        "company_contact_roster",
        "sales_lead",
        "lead_assignment",
        "lead_stage_transition",
    ),
    "customer_analysis": (
        "customer_profile",
        "customer_meddpicc_dimension",
        "analysis_run",
        "analysis_report",
        "analysis_suggestion",
    ),
    "customer_operation": (
        "email_message",
        "email_attachment",
        "email_delivery_attempt",
        "email_suppression",
        "company_outreach_state",
        "follow_up_task",
        "customer_activity",
        "manual_note",
    ),
    "meeting_analysis": (
        "meeting",
        "meeting_segment",
        "media_asset",
    ),
    "read_models": (),
}

EXPECTED_PLATFORM_OWNED_TABLES = {
    "jobs": (
        "job",
        "job_attempt",
        "job_progress_event",
    ),
    "idempotency": ("idempotency_record",),
    "events": (
        "outbox_event",
        "external_event",
        "audit_log",
    ),
}


def _import_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


class ArchitectureTests(unittest.TestCase):
    def test_module_registry_matches_expected_directories(self) -> None:
        module_names = {definition.name for definition in MODULE_DEFINITIONS}
        self.assertEqual(module_names, set(MODULE_OWNERSHIP))
        self.assertEqual(module_names, set(MODULE_OWNED_TABLES))
        self.assertEqual(len(module_names), 7)

        for definition in MODULE_DEFINITIONS:
            module_root = MODULES_ROOT / definition.name
            self.assertTrue(module_root.is_dir(), msg=f"missing module directory: {module_root}")
            layer_names = (
                READ_MODEL_LAYER_NAMES
                if definition.name == "read_models"
                else STANDARD_LAYER_NAMES
            )
            for layer_name in layer_names:
                self.assertTrue(
                    (module_root / layer_name / "__init__.py").is_file(),
                    msg=f"missing layer package for {definition.name}.{layer_name}",
                )
            if definition.name == "read_models":
                for disallowed_name in ("application", "domain", "infrastructure"):
                    self.assertFalse(
                        (module_root / disallowed_name).exists(),
                        msg=f"read_models must not expose {disallowed_name}",
                    )

    def test_platform_capability_packages_exist(self) -> None:
        expected_packages = (
            "db",
            "auth",
            "jobs",
            "events",
            "idempotency",
            "media",
            "providers",
            "observability",
        )
        for package_name in expected_packages:
            self.assertTrue(
                (PLATFORM_ROOT / package_name / "__init__.py").is_file(),
                msg=f"missing platform package: {package_name}",
            )

    def test_layer_import_rules_hold(self) -> None:
        for definition in MODULE_DEFINITIONS:
            layer_names = (
                READ_MODEL_LAYER_NAMES
                if definition.name == "read_models"
                else STANDARD_LAYER_NAMES
            )
            for layer_name in layer_names:
                if layer_name not in FORBIDDEN_LAYER_IMPORTS:
                    continue
                layer_root = MODULES_ROOT / definition.name / layer_name
                for source_file in layer_root.rglob("*.py"):
                    source_text = source_file.read_text(encoding="utf-8")
                    import_names = _import_names(ast.parse(source_text))
                    for import_name in import_names:
                        for suffix in FORBIDDEN_LAYER_IMPORTS[layer_name]:
                            # Skip files with a # noqa: FORBIDDEN_LAYER comment
                            if "# noqa: FORBIDDEN_LAYER" in source_text:
                                continue
                            self.assertFalse(
                                import_name.startswith("ltc.modules.") and suffix in import_name,
                                msg=f"{source_file} imports forbidden layer via {import_name}",
                            )
                        for forbidden_prefix in FORBIDDEN_FRAMEWORK_IMPORTS.get(layer_name, ()):
                            self.assertFalse(
                                import_name == forbidden_prefix or import_name.startswith(f"{forbidden_prefix}."),
                                msg=f"{source_file} imports forbidden framework via {import_name}",
                            )

    def test_owned_tables_match_v36_data_model(self) -> None:
        self.assertEqual(MODULE_OWNED_TABLES, EXPECTED_OWNED_TABLES)
        self.assertEqual(PLATFORM_OWNED_TABLES, EXPECTED_PLATFORM_OWNED_TABLES)

        all_tables = [
            table
            for ownership in (MODULE_OWNED_TABLES, PLATFORM_OWNED_TABLES)
            for tables in ownership.values()
            for table in tables
        ]
        self.assertEqual(47, len(all_tables))
        self.assertEqual(47, len(set(all_tables)), "each table must have exactly one owner")


if __name__ == "__main__":
    unittest.main()
