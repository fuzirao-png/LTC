import asyncio
from typing import Any

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient
from ltc.modules.customer_operation.domain.read_models import FollowUpTask


ALLOWED_TASK_TYPES = {"email", "meeting", "proposal"}


def _fallback_strategy(intent_level: str, next_action: str) -> dict[str, Any]:
    if intent_level == "pricing":
        return {
            "task_type": "proposal",
            "title": "Prepare pricing follow-up",
            "description": next_action,
            "priority": 70,
        }
    if intent_level == "product_question":
        return {
            "task_type": "email",
            "title": "Answer product questions",
            "description": next_action,
            "priority": 80,
        }
    if intent_level == "interested":
        return {
            "task_type": "meeting",
            "title": "Schedule next discussion",
            "description": next_action,
            "priority": 60,
        }
    return {
        "task_type": "email",
        "title": "Review customer reply",
        "description": next_action,
        "priority": 100,
    }


async def _create_follow_up_strategy_by_llm(
    *,
    intent_level: str,
    next_action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    result = await LlmClient().chat_json(
        system_prompt=(
            "You are a B2B customer operation follow-up strategist. Return JSON only "
            "with task_type, title, description, priority. task_type must be one of "
            "email, meeting, proposal. priority is an integer from 0 to 1000 where lower is more urgent."
        ),
        user_prompt=(
            f"Intent: {intent_level}\n"
            f"Suggested next action: {next_action}\n"
            f"Context: {context}"
        ),
    )
    task_type = str(result.get("task_type") or "").strip()
    title = str(result.get("title") or "").strip()
    description = str(result.get("description") or "").strip()
    priority = int(result.get("priority") or 100)
    if task_type not in ALLOWED_TASK_TYPES or not title or not description:
        raise RuntimeError("LLM returned invalid follow-up strategy.")
    return {
        "task_type": task_type,
        "title": title,
        "description": description,
        "priority": max(0, min(priority, 1000)),
    }


def create_follow_up_strategy(
    *,
    intent_level: str,
    next_action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if get_settings().llm_api_key:
        try:
            return asyncio.run(
                _create_follow_up_strategy_by_llm(
                    intent_level=intent_level,
                    next_action=next_action,
                    context=context or {},
                )
            )
        except Exception:
            pass
    return _fallback_strategy(intent_level, next_action)


def create_follow_up_task(
    company_id: str,
    sales_id: str,
    task_type: str,
    description: str,
    *,
    intent_level: str | None = None,
    context: dict[str, Any] | None = None,
) -> FollowUpTask:
    strategy = create_follow_up_strategy(
        intent_level=intent_level or task_type,
        next_action=description,
        context=context,
    )
    return FollowUpTask(
        company_id=company_id,
        sales_id=sales_id,
        task_type=strategy["task_type"],
        description=strategy["description"],
        status="pending",
    )



