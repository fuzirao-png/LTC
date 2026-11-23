from pathlib import Path

from ltc.modules.customer_operation.application.email_skill_loader import discover_email_skills


CUSTOMER_OPERATION_ROOT = Path(__file__).resolve().parents[1]
EMAIL_SKILLS_ROOT = CUSTOMER_OPERATION_ROOT / "skills"
EMAIL_AGENT_ROOT = CUSTOMER_OPERATION_ROOT / "agents" / "email_agent"
SKILL_REGISTRY = discover_email_skills(
    EMAIL_SKILLS_ROOT,
    EMAIL_AGENT_ROOT / "skills.json",
)
