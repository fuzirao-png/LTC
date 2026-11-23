from pathlib import Path
from typing import Any

from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient


class EmailEditSkill:
    name = "email_edit"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        current_body = str(input_data.get("currentBody") or input_data.get("body") or "").strip()
        current_subject = str(input_data.get("currentSubject") or input_data.get("subject") or "").strip()
        instruction = str(input_data.get("customPrompt") or input_data.get("instruction") or "").strip()
        operation = str(input_data.get("operation") or ("rewrite" if instruction else "optimize")).strip()
        if not current_body:
            raise RuntimeError("currentBody is required for email editing.")
        if operation not in {"optimize", "rewrite"}:
            raise RuntimeError(f"Unsupported email edit operation: {operation}")
        if operation == "rewrite" and not instruction:
            raise RuntimeError("customPrompt is required for email rewriting.")

        editing_instruction = (
            instruction
            if operation == "rewrite"
            else instruction or "Improve clarity, professionalism, concision, structure, and the call to action."
        )
        user_prompt = "\n".join(
            [
                f"Editing mode: {operation}",
                f"Customer company: {input_data.get('customerName') or 'Not provided'}",
                f"Recipient: {input_data.get('recipientName') or 'Not provided'}",
                f"Customer profile: {input_data.get('customerProfile') or 'Not provided'}",
                f"Current subject: {current_subject or 'None'}",
                "Current body:",
                current_body,
                f"Editing instruction: {editing_instruction}",
            ]
        )
        result = await LlmClient().chat_json(
            system_prompt=(
                Path(__file__).resolve().parents[1] / "references" / "email-editing.md"
            ).read_text(encoding="utf-8-sig"),
            user_prompt=user_prompt,
        )
        subject = str(result.get("subject") or current_subject).strip()
        body = str(result.get("body") or "").strip()
        if not body:
            raise RuntimeError("LLM did not return an email body.")
        changes = (
            ["优化语气、结构和行动号召"]
            if operation == "optimize"
            else ["根据用户指令改写邮件"]
        )
        return {
            "subject": subject,
            "body": body,
            "language": str(result.get("language") or input_data.get("targetLanguage") or ""),
            "changes": changes,
            "model": str(result.get("model") or ""),
        }
