import json
from pathlib import Path
from typing import Any

from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient


LANGUAGE_LABELS = {
    "ja": "Japanese",
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "zh": "Chinese",
}


class EmailTranslateSkill:
    name = "email_translate"

    async def run(self, input_data: dict[str, Any]) -> dict[str, str]:
        source_subject = str(
            input_data.get("currentSubject")
            or input_data.get("subject")
            or input_data.get("sourceSubject")
            or ""
        ).strip()
        source_text = str(
            input_data.get("currentBody")
            or input_data.get("body")
            or input_data.get("sourceText")
            or ""
        ).strip()
        target_language = str(input_data.get("targetLanguage") or "").strip()
        customer_name = str(input_data.get("customerName") or "").strip()
        recipient_name = str(input_data.get("recipientName") or "").strip()
        custom_prompt = str(input_data.get("customPrompt") or "").strip()

        if not source_text:
            raise RuntimeError("sourceText is required.")
        if target_language not in LANGUAGE_LABELS:
            raise RuntimeError(f"Unsupported targetLanguage: {target_language}")

        source_segments = input_data.get("translationSegments") or []
        structured = bool(input_data.get("structuredTranslation") and source_segments)
        if structured:
            source_content = json.dumps(source_segments, ensure_ascii=False)
            source_label = "Source translation segments:"
            output_instruction = "Return JSON with translatedSubject and translatedSegments. Each translatedSegments item must contain the exact original id and translated text; do not add, remove, or reorder ids."
        else:
            source_content = source_text
            source_label = "Source email body:"
            output_instruction = "Return JSON with translatedSubject and translatedText."
        prompt_parts = [
            f"Target language: {LANGUAGE_LABELS[target_language]}",
            f"Customer company: {customer_name or 'Not provided'}",
            f"Recipient: {recipient_name or 'Not provided'}",
            output_instruction,
        ]
        if custom_prompt:
            prompt_parts.extend(["Translation correction instructions:", custom_prompt])
        prompt_parts.extend([
            "Source subject:",
            source_subject or "Not provided",
            source_label,
            source_content,
        ])
        user_prompt = "\n".join(prompt_parts)
        result = await LlmClient().chat_json(
            system_prompt=(
                Path(__file__).resolve().parents[1] / "references" / "email-translation.md"
            ).read_text(encoding="utf-8-sig"),
            user_prompt=user_prompt,
        )
        translated_subject = str(result.get("translatedSubject") or "").strip()
        translated_segments = result.get("translatedSegments")
        if structured:
            if not isinstance(translated_segments, list):
                raise RuntimeError("Structured translation did not return translatedSegments.")
            normalized_segments = []
            for item in translated_segments:
                if not isinstance(item, dict) or not item.get("id"):
                    raise RuntimeError("Structured translation returned an invalid segment.")
                text = item.get("text") or item.get("translatedText") or item.get("translated_text")
                if not str(text or "").strip():
                    raise RuntimeError("Structured translation returned an empty segment.")
                normalized_segments.append({"id": str(item["id"]), "text": str(text).strip()})
            return {
                "translatedSubject": translated_subject,
                "subject": translated_subject or source_subject,
                "body": "",
                "translatedSegments": normalized_segments,
                "model": str(result.get("model") or ""),
                "language": target_language,
                "changes": [f"???{LANGUAGE_LABELS[target_language]}"],
            }
        translated = str(result.get("translatedText") or "").strip()
        if source_subject and not translated_subject:
            raise RuntimeError("LLM did not return translatedSubject.")
        if not translated:
            raise RuntimeError("LLM did not return translatedText.")
        return {
            "translatedSubject": translated_subject,
            "subject": translated_subject or source_subject,
            "body": translated,
            "translatedText": translated,
            "model": str(result.get("model") or ""),
            "language": target_language,
            "changes": [f"翻译为{LANGUAGE_LABELS[target_language]}"],
        }
