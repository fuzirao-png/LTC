from ltc.modules.customer_operation.application.skills_registry import SKILL_REGISTRY
from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient


EmailTranslateSkill = type(SKILL_REGISTRY["email_translate"])
