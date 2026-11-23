from typing import Any

from pathlib import Path

from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient


def normalize_email_draft(result: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    subject = str(result.get("subject") or "").strip()
    body = str(result.get("body") or "").strip()
    if not body:
        raise RuntimeError("LLM did not return an email body.")
    if not subject:
        subject = (
            f"Re: Connectivity Plan for {context['customerName']}"
            if context.get("mode") == "regenerate"
            else f"Enterprise eSIM support for {context['customerName']}"
        )
    return {
        "subject": subject,
        "body": body,
        "language": str(result.get("language") or context.get("targetLanguage") or "zh"),
        "changes": ["根据客户上下文生成主题和正文"],
        "model": str(result.get("model") or ""),
    }


class EmailGenerateSkill:
    name = "email_generate"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        required = ["salesName", "customerName", "recipientName", "recipientEmail"]
        missing = [key for key in required if not input_data.get(key)]
        if missing:
            raise RuntimeError(f"Missing email generation fields: {', '.join(missing)}")
        if input_data.get("mode") == "regenerate" and (
            not input_data.get("currentSubject") or not input_data.get("currentBody")
        ):
            raise RuntimeError("Regenerate mode requires currentSubject and currentBody.")

        user_prompt = "\n".join(
            [
                f"Salesperson display name: {input_data['salesName']}",
                f"Customer company: {input_data['customerName']}",
                f"Recipient: {input_data['recipientName']}",
                f"Recipient email: {input_data['recipientEmail']}",
                f"Recipient title: {input_data.get('recipientTitle') or 'Not provided'}",
                f"Recipient role: {input_data.get('recipientRole') or 'Not provided'}",
                f"Target language: {input_data.get('targetLanguage') or 'English'}",
                f"Audience angle: {input_data.get('audience') or 'general'}",
                f"PRD template blueprint (preserve exactly): {input_data.get('templateBlueprint') or 'No fixed blueprint'}",
                f"Email purpose: {input_data.get('purpose') or 'first_touch'}",
                f"Customer profile: {input_data.get('customerProfile') or 'Not provided'}",
                f"Recent emails: {input_data.get('recentEmails') or 'None'}",
                f"Latest meeting: {input_data.get('latestMeeting') or 'None'}",
                f"Open tasks: {input_data.get('openTasks') or 'None'}",
                f"Recent activities: {input_data.get('recentActivities') or 'None'}",
                f"Mode: {input_data.get('mode') or 'initial'}",
                f"Current subject: {input_data.get('currentSubject') or 'None'}",
                f"Current body: {input_data.get('currentBody') or 'None'}",
                f"User extra instruction: {input_data.get('customPrompt') or 'None'}",
            ]
        )
        result = await LlmClient().chat_json(
            system_prompt=(Path(__file__).resolve().parents[1] / "references" / "email-generation.md").read_text(encoding="utf-8-sig"),
            user_prompt=user_prompt,
        )
        return normalize_email_draft(result, input_data)
