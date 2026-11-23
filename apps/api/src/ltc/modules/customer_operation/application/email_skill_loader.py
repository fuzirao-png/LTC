from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_EMAIL_OPERATIONS = frozenset({"generate", "optimize", "translate", "rewrite", "analyze"})
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REGISTRY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class EmailSkillDefinition:
    name: str
    description: str
    registry_name: str
    operations: tuple[str, ...]
    order: int
    entrypoint: str
    directory: Path
    handler: Any


class EmailSkillRegistry(Mapping[str, Any]):
    def __init__(self, definitions: list[EmailSkillDefinition]) -> None:
        ordered = sorted(definitions, key=lambda item: (item.order, item.registry_name))
        self._definitions = tuple(ordered)
        self._handlers = {item.registry_name: item.handler for item in ordered}
        self._by_operation = {
            operation: tuple(item for item in ordered if operation in item.operations)
            for operation in SUPPORTED_EMAIL_OPERATIONS
        }

    def __getitem__(self, name: str) -> Any:
        return self._handlers[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)

    def names(self) -> list[str]:
        return [item.registry_name for item in sorted(
            self._definitions,
            key=lambda item: (item.order, item.registry_name),
        )]

    def operations(self) -> set[str]:
        return {operation for item in self._definitions for operation in item.operations}

    def definitions_for_operation(self, operation: str) -> tuple[EmailSkillDefinition, ...]:
        return self._by_operation.get(operation, ())

    def skills_for_operation(self, operation: str) -> list[Any]:
        return [item.handler for item in self.definitions_for_operation(operation)]

    def names_for_operation(self, operation: str) -> list[str]:
        return [item.registry_name for item in self.definitions_for_operation(operation)]


def _parse_skill_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise ValueError(f"{path}: SKILL.md must start with YAML frontmatter")
    try:
        closing_index = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{path}: SKILL.md frontmatter is not closed") from exc
    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"{path}: invalid SKILL.md frontmatter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    if not metadata.get("name") or not metadata.get("description"):
        raise ValueError(f"{path}: SKILL.md frontmatter requires name and description")
    return metadata


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc


def _runtime_specs(root: Path, manifest_path: Path | None) -> list[tuple[Path, dict[str, Any]]]:
    if manifest_path is not None:
        manifest_path = manifest_path.resolve()
        if not manifest_path.is_file():
            raise ValueError(f"Email Agent Skill manifest does not exist: {manifest_path}")
        payload = _read_json(manifest_path)
        entries = payload.get("skills") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{manifest_path}: skills must be a non-empty array")
        specs: list[tuple[Path, dict[str, Any]]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{manifest_path}: each skills entry must be an object")
            directory = str(entry.get("directory") or "")
            if not _NAME_PATTERN.fullmatch(directory):
                raise ValueError(f"{manifest_path}: invalid Skill directory {directory}")
            specs.append((root / directory, entry))
        return specs

    specs = []
    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        runtime_file = skill_dir / "skill.json"
        if not runtime_file.is_file():
            raise ValueError(f"{skill_dir}: every legacy Skill requires skill.json")
        specs.append((skill_dir, _read_json(runtime_file)))
    return specs


def _load_handler(skill_dir: Path, entrypoint: str, registry_name: str) -> Any:
    if ":" not in entrypoint:
        raise ValueError(f"{skill_dir}: entrypoint must use path/to/file.py:ClassName")
    relative_file, class_name = entrypoint.split(":", 1)
    skill_root = skill_dir.resolve()
    handler_path = (skill_root / relative_file).resolve()
    try:
        handler_path.relative_to(skill_root)
    except ValueError as exc:
        raise ValueError(f"{skill_dir}: handler entrypoint leaves the Skill directory") from exc
    if handler_path.suffix != ".py" or not handler_path.is_file():
        raise ValueError(f"{skill_dir}: invalid handler entrypoint {entrypoint}")
    module_name = f"ltc_email_skill_{registry_name}_{abs(hash(handler_path))}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{skill_dir}: cannot load handler module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler_class = getattr(module, class_name, None)
    if not isinstance(handler_class, type):
        raise ValueError(f"{skill_dir}: handler class {class_name} was not found")
    handler = handler_class()
    if getattr(handler, "name", None) != registry_name:
        raise ValueError(f"{skill_dir}: handler name must match registry_name {registry_name}")
    if not callable(getattr(handler, "run", None)):
        raise ValueError(f"{skill_dir}: handler must define run(input_data)")
    return handler


def discover_email_skills(root: Path, manifest_path: Path | None = None) -> EmailSkillRegistry:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Email Skill directory does not exist: {root}")
    definitions: list[EmailSkillDefinition] = []
    registry_names: set[str] = set()
    directories: set[Path] = set()
    for skill_dir, runtime in _runtime_specs(root, manifest_path):
        skill_dir = skill_dir.resolve()
        if skill_dir in directories:
            raise ValueError(f"{skill_dir}: duplicate Skill directory")
        directories.add(skill_dir)
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError(f"{skill_dir}: every Skill requires SKILL.md")
        skill_metadata = _parse_skill_frontmatter(skill_file)
        name = str(skill_metadata["name"])
        description = str(skill_metadata["description"])
        registry_name = str(runtime.get("registry_name") or "")
        configured_operations = runtime.get("operations")
        if configured_operations is None:
            configured_operations = [runtime.get("operation")]
        entrypoint = str(runtime.get("entrypoint") or "")
        order = runtime.get("order")
        if skill_dir.name != name or not _NAME_PATTERN.fullmatch(name):
            raise ValueError(f"{skill_dir}: directory and SKILL.md name must match kebab-case")
        if not _REGISTRY_NAME_PATTERN.fullmatch(registry_name):
            raise ValueError(f"{skill_dir}: invalid registry_name")
        if registry_name in registry_names:
            raise ValueError(f"{skill_dir}: duplicate registry_name {registry_name}")
        if not isinstance(configured_operations, list) or not configured_operations:
            raise ValueError(f"{skill_dir}: operations must be a non-empty array")
        operations = tuple(dict.fromkeys(str(operation or "") for operation in configured_operations))
        unsupported_operations = [
            operation for operation in operations if operation not in SUPPORTED_EMAIL_OPERATIONS
        ]
        if unsupported_operations:
            raise ValueError(f"{skill_dir}: unsupported operation {unsupported_operations[0]}")
        if not isinstance(order, int) or order < 0:
            raise ValueError(f"{skill_dir}: order must be a non-negative integer")
        handler = _load_handler(skill_dir, entrypoint, registry_name)
        registry_names.add(registry_name)
        definitions.append(EmailSkillDefinition(
            name=name,
            description=description,
            registry_name=registry_name,
            operations=operations,
            order=order,
            entrypoint=entrypoint,
            directory=skill_dir,
            handler=handler,
        ))
    if not definitions:
        raise ValueError(f"No Email Skills found in {root}")
    return EmailSkillRegistry(definitions)
