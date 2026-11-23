import logging
import time
from typing import Any, Callable

from ltc.modules.customer_operation.application.skills_registry import SKILL_REGISTRY
from ltc.modules.customer_operation.application.email_quality_guard import inspect_email_quality
from ltc.modules.customer_operation.infrastructure.email_context_builder import build_email_agent_context


_logger = logging.getLogger(__name__)
AGENT_NAME = "email-agent"
SUPPORTED_OPERATIONS = {"generate", "optimize", "translate", "rewrite", "analyze"}
_DEFAULT_SKILL_NAMES = {
    "generate": ["email_generate"],
    "optimize": ["email_edit", "email_optimize"],
    "translate": ["email_translate"],
    "rewrite": ["email_edit", "email_rewrite"],
    "analyze": ["email_analysis"],
}
TRANSLATION_MARKERS = ("translate", "翻译", "翻成", "译成")


def _skill_names_for_operation(registry: Any, operation: str) -> list[str]:
    names_for_operation = getattr(registry, "names_for_operation", None)
    if callable(names_for_operation):
        names = list(names_for_operation(operation))
    else:
        names = [name for name in _DEFAULT_SKILL_NAMES[operation] if name in registry][:1]
    if not names:
        raise RuntimeError(f"No email Skills registered for operation: {operation}")
    return names


def plan_email_skills(
    operation: str,
    instruction: str,
    target_language: str,
    registry: Any = SKILL_REGISTRY,
) -> list[str]:
    if operation != "rewrite":
        return _skill_names_for_operation(registry, operation)
    rewrite_skills = _skill_names_for_operation(registry, "rewrite")
    wants_translation = bool(target_language) and any(
        marker in instruction.lower() for marker in TRANSLATION_MARKERS
    )
    if not wants_translation:
        return rewrite_skills
    return _skill_names_for_operation(registry, "translate") + rewrite_skills


class EmailAgent:
    def __init__(
        self,
        registry: dict[str, Any] | None = None,
        context_builder: Callable[[dict[str, Any]], dict[str, Any]] = build_email_agent_context,
    ) -> None:
        self._registry = registry or SKILL_REGISTRY
        self._context_builder = context_builder

    @staticmethod
    def _validate_request(
        payload: dict[str, Any],
        operation: str,
        instruction: str,
        target_language: str,
    ) -> None:
        if operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported email agent operation: {operation}")
        current_body = str(payload.get("body") or payload.get("currentBody") or "").strip()
        if operation in {"optimize", "translate", "rewrite", "analyze"} and not current_body:
            raise ValueError("body is required for this email agent operation")
        if operation == "rewrite" and not instruction:
            raise ValueError("instruction is required for rewrite")
        if operation == "translate" and target_language not in {"ja", "en", "fr", "de", "es", "zh"}:
            raise ValueError(f"Unsupported targetLanguage: {target_language}")

    @staticmethod
    def _validate_skill_result(result: dict[str, Any]) -> dict[str, Any]:
        subject = str(result.get("subject") or "").strip()
        body = str(result.get("body") or "").strip()
        translated_segments = result.get("translatedSegments")
        if not body and not isinstance(translated_segments, list):
            raise RuntimeError("LLM did not return an email body.")
        changes = result.get("changes") or []
        if not isinstance(changes, list) or not all(isinstance(item, str) for item in changes):
            raise RuntimeError("Email Skill returned invalid changes.")
        if translated_segments is not None and not isinstance(translated_segments, list):
            raise RuntimeError("Email Skill returned invalid translatedSegments.")
        return {
            "subject": subject,
            "body": body,
            "translatedSegments": translated_segments,
            "language": str(result.get("language") or ""),
            "changes": changes,
            "model": str(result.get("model") or ""),
        }

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        operation = str(payload.get("operation") or "").strip()
        instruction = str(payload.get("instruction") or payload.get("customPrompt") or "").strip()
        target_language = str(payload.get("targetLanguage") or "").strip()
        skill_names: list[str] = []
        try:
            self._validate_request(payload, operation, instruction, target_language)
            context = dict(payload) if operation == "analyze" else self._context_builder(payload)
            skill_names = plan_email_skills(
                operation,
                instruction,
                target_language,
                self._registry,
            )
            current = dict(context)
            current["operation"] = operation
            current["customPrompt"] = instruction
            if operation == "analyze":
                result = await self._registry[skill_names[0]].run(current)
                return {"success": True, "agent": AGENT_NAME, "operation": operation, "skills": skill_names, **result}
            changes: list[str] = []
            model = ""
            quality_flags: list[str] = []
            for skill_name in skill_names:
                result = await self._registry[skill_name].run(current)
                normalized = self._validate_skill_result(result)
                inspection = inspect_email_quality(
                    input_data=current,
                    subject=normalized["subject"],
                    body=normalized["body"],
                )
                quality_flags.extend(inspection.flags)
                current["currentSubject"] = inspection.subject
                current["currentBody"] = inspection.body
                current["subject"] = inspection.subject
                current["body"] = inspection.body
                if normalized.get("translatedSegments") is not None:
                    current["translatedSegments"] = normalized["translatedSegments"]
                changes.extend(normalized["changes"])
                model = normalized["model"] or model
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _logger.info(
                "email_agent_completed",
                extra={
                    "agent_name": AGENT_NAME,
                    "operation": operation,
                    "skill_names": skill_names,
                    "company_id": str(payload.get("companyId") or ""),
                    "contact_id": str(payload.get("contactId") or ""),
                    "model": model,
                    "duration_ms": duration_ms,
                    "quality_flags": list(dict.fromkeys(quality_flags)),
                    "status": "success",
                },
            )
            return {
                "success": True,
                "agent": AGENT_NAME,
                "operation": operation,
                "subject": current.get("currentSubject", ""),
                "body": current.get("currentBody", ""),
                "translatedSegments": current.get("translatedSegments"),
                "language": target_language or None,
                "skills": skill_names,
                "changes": changes,
                "model": model,
                "message": "邮件草稿已生成，请确认后使用",
            }
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _logger.info(
                "email_agent_failed",
                extra={
                    "agent_name": AGENT_NAME,
                    "operation": operation,
                    "skill_names": skill_names,
                    "company_id": str(payload.get("companyId") or ""),
                    "contact_id": str(payload.get("contactId") or ""),
                    "duration_ms": duration_ms,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                },
            )
            raise


EMAIL_AGENT = EmailAgent()


async def run_email_agent_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return await EMAIL_AGENT.run(payload)
