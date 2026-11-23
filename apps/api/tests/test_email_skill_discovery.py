from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from ltc.modules.customer_operation.application.email_agent import EmailAgent
from ltc.modules.customer_operation.application.email_skill_loader import discover_email_skills


class EmailSkillDiscoveryTests(unittest.TestCase):
    def _write_skill(
        self,
        root: Path,
        folder: str = "email-test",
        registry_name: str = "email_test",
        operation: str = "optimize",
        order: int = 20,
        class_name: str = "TestSkill",
    ) -> Path:
        skill_dir = root / folder
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {folder}\n"
            "description: Use when testing Skill discovery.\n"
            "---\n\n# Test Skill\n",
            encoding="utf-8",
        )
        (skill_dir / "skill.json").write_text(
            json.dumps({
                "registry_name": registry_name,
                "operation": operation,
                "order": order,
                "entrypoint": f"handler.py:{class_name}",
            }),
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            f"class {class_name}:\n"
            f"    name = {registry_name!r}\n"
            "    async def run(self, input_data):\n"
            "        return {'subject': '', 'body': 'ok', 'changes': []}\n",
            encoding="utf-8",
        )
        return skill_dir

    def test_discovers_and_orders_skills_by_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_skill(root, folder="email-second", registry_name="email_second", order=20)
            self._write_skill(root, folder="email-first", registry_name="email_first", order=10)

            registry = discover_email_skills(root)

            self.assertEqual(registry.names(), ["email_first", "email_second"])
            self.assertEqual(
                [skill.name for skill in registry.skills_for_operation("optimize")],
                ["email_first", "email_second"],
            )

    def test_agent_runs_all_discovered_skills_for_an_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_skill(root, folder="email-first", registry_name="email_first", order=10)
            self._write_skill(root, folder="email-second", registry_name="email_second", order=20)
            registry = discover_email_skills(root)
            agent = EmailAgent(registry=registry, context_builder=lambda payload: dict(payload))

            result = asyncio.run(agent.run({
                "operation": "optimize",
                "body": "Original body",
            }))

            self.assertEqual(result["skills"], ["email_first", "email_second"])
            self.assertEqual(result["body"], "ok")

    def test_central_manifest_loads_nested_skill_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "skills"
            root.mkdir()
            skill_dir = self._write_skill(root, folder="email-nested", registry_name="email_nested")
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (skill_dir / "handler.py").replace(scripts_dir / "nested.py")
            (skill_dir / "skill.json").unlink()
            manifest = Path(temp_dir) / "skills.json"
            manifest.write_text(json.dumps({
                "skills": [{
                    "directory": "email-nested",
                    "registry_name": "email_nested",
                    "operation": "optimize",
                    "order": 25,
                    "entrypoint": "scripts/nested.py:TestSkill",
                }],
            }), encoding="utf-8")

            registry = discover_email_skills(root, manifest)

            self.assertEqual(registry.names(), ["email_nested"])

    def test_one_skill_can_serve_optimize_and_rewrite_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "skills"
            root.mkdir()
            skill_dir = self._write_skill(root, folder="email-edit", registry_name="email_edit")
            (skill_dir / "skill.json").unlink()
            manifest = Path(temp_dir) / "skills.json"
            manifest.write_text(json.dumps({
                "skills": [{
                    "directory": "email-edit",
                    "registry_name": "email_edit",
                    "operations": ["optimize", "rewrite"],
                    "order": 20,
                    "entrypoint": "handler.py:TestSkill",
                }],
            }), encoding="utf-8")

            registry = discover_email_skills(root, manifest)

            self.assertEqual(registry.names_for_operation("optimize"), ["email_edit"])
            self.assertEqual(registry.names_for_operation("rewrite"), ["email_edit"])
            self.assertEqual(registry.operations(), {"optimize", "rewrite"})

    def test_duplicate_registry_names_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_skill(root, folder="email-one", registry_name="duplicate")
            self._write_skill(root, folder="email-two", registry_name="duplicate")

            with self.assertRaisesRegex(ValueError, "duplicate registry_name"):
                discover_email_skills(root)

    def test_malformed_skill_metadata_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "email-invalid"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Missing frontmatter\n", encoding="utf-8")
            (skill_dir / "skill.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SKILL.md.*frontmatter"):
                discover_email_skills(root)


if __name__ == "__main__":
    unittest.main()


def test_email_analysis_skill_is_registered_for_analyze_operation():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "skills"
        skill_dir = root / "email-analysis" / "scripts"
        skill_dir.mkdir(parents=True)
        (root / "email-analysis" / "SKILL.md").write_text(
            "---\nname: email-analysis\ndescription: Analyze inbound email.\n---\n", encoding="utf-8"
        )
        (skill_dir / "analyze.py").write_text(
            "class EmailAnalysisSkill:\n    name = 'email_analysis'\n    async def run(self, input_data):\n        return {}\n", encoding="utf-8"
        )
        manifest = Path(temp_dir) / "skills.json"
        manifest.write_text(json.dumps({"skills": [{"directory": "email-analysis", "registry_name": "email_analysis", "operation": "analyze", "order": 40, "entrypoint": "scripts/analyze.py:EmailAnalysisSkill"}]}), encoding="utf-8")
        registry = discover_email_skills(root, manifest)
        assert registry.names_for_operation("analyze") == ["email_analysis"]
