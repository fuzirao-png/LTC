from ltc.modules.customer_operation.application.skills_registry import SKILL_REGISTRY
from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient


EmailOptimizeSkill = type(SKILL_REGISTRY["email_edit"])
