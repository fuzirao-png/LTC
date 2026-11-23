"""LLM-based meeting summary adapter via OpenAI-compatible chat completions.

Outputs a structured JSON object conforming to
ltc.validate_meeting_summary_v1:
  customer_needs, pain_points, buying_signals,
  action_items, decisions, risks, keywords, next_step
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from opentelemetry.trace import StatusCode, get_current_span

from ltc.modules.meeting_analysis.domain.errors import SummaryGenerationError
from ltc.modules.meeting_analysis.infrastructure.text_normalizer import normalize_to_simplified, to_simplified_text


SUMMARY_PROMPT = """你是一个专业的销售会议分析助手。请根据以下会议转录文本，用**简体中文**提取关键信息，
严格按照 JSON 格式输出，不要有任何额外的文字说明。

输出格式必须为：
{
  "customer_needs": ["客户需求1", "客户需求2", ...],
  "pain_points": ["痛点1", "痛点2", ...],
  "buying_signals": ["购买意向信号1", "购买意向信号2", ...],
  "action_items": [
    {"task": "待办事项描述", "owner": "负责人", "due_at": "2025-01-01T00:00:00Z"}
  ],
  "decisions": ["决定1", "决定2", ...],
  "risks": ["风险1", "风险2", ...],
  "keywords": ["关键词1", "关键词2", ...],
  "next_step": "整体下一步行动建议"
}

要求：
- customer_needs / pain_points / buying_signals / decisions / risks / keywords 字段必须为字符串数组
- action_items 字段必须为对象数组，每个对象包含 task（必填）、owner（可为null）、due_at（ISO8601字符串，可为null）
- next_step 字段为字符串或null
- 不包含会议转录文本中的具体姓名、公司名等PII信息
- 如果某个字段无法从会议中提取，请使用空数组 []
"""

_DEFAULT_MODEL = "gpt-5.6-terra"


class SummaryAdapter:
    """Calls an OpenAI-compatible chat completions endpoint for meeting summarization."""

    def __init__(self, *, api_key: str, base_url: str, model: str = _DEFAULT_MODEL, timeout_seconds: float = 300.0, event_emitter: Any = None) -> None:
        self._model = model
        self._configured = bool(api_key)
        self._emitter = event_emitter
        if self._configured:
            self._client: OpenAI | None = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
        else:
            self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    @classmethod
    def from_settings(cls, settings: object) -> "SummaryAdapter":
        """Create a SummaryAdapter from application settings."""
        llm_api_key = str(getattr(settings, "llm_api_key", ""))
        llm_base_url = str(getattr(settings, "llm_base_url", ""))
        llm_model = str(getattr(settings, "llm_model", _DEFAULT_MODEL))
        return cls(api_key=llm_api_key, base_url=llm_base_url, model=llm_model)

    def summarize(self, transcript: str) -> dict[str, object]:
        """Generate a structured meeting summary from transcript text."""
        if not self._configured or self._client is None:
            # No LLM configured — return empty placeholder
            return {
                "customer_needs": [],
                "pain_points": [],
                "buying_signals": [],
                "action_items": [],
                "decisions": [],
                "risks": [],
                "keywords": [],
                "next_step": None,
            }

        try:
            transcript_normalized = to_simplified_text(transcript)
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": transcript_normalized[:64000]},
                ],
            )
            content = response.choices[0].message.content
            _emit_meeting_ai_event(self._emitter, self._model, response, success=True)
            parsed = _parse_summary_json(content or "{}")
            normalized = normalize_to_simplified(parsed)
            return self._fill_defaults(normalized)
        except SummaryGenerationError:
            raise
        except Exception as exc:
            get_current_span().set_status(StatusCode.ERROR, type(exc).__name__)
            # Fallback: partial summary with error marker
            _emit_meeting_ai_event(self._emitter, self._model, None, success=False)
            return {
                "customer_needs": [],
                "pain_points": [],
                "buying_signals": [],
                "action_items": [],
                "decisions": [],
                "risks": [f"Summary generation error: {exc}"],
                "keywords": [],
                "next_step": None,
            }

    @staticmethod
    def _fill_defaults(data: dict[str, object]) -> dict[str, object]:
        return {
            "customer_needs": data.get("customer_needs", []),
            "pain_points": data.get("pain_points", []),
            "buying_signals": data.get("buying_signals", []),
            "action_items": data.get("action_items", []),
            "decisions": data.get("decisions", []),
            "risks": data.get("risks", []),
            "keywords": data.get("keywords", []),
            "next_step": data.get("next_step", None),
        }


def _parse_summary_json(content: str) -> dict[str, object]:
    """Parse the LLM response into a dict, handling content-list and
    markdown-fence wrappers that some models emit."""
    # Handle list-of-content-blocks (some providers)
    text = content
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            text = ""
            for item in parsed:
                if isinstance(item, dict) and "text" in item:
                    text += item["text"]
                elif isinstance(item, str):
                    text += item
        elif isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Extract JSON between first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]

    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            raise SummaryGenerationError("Summary JSON is not a dictionary")
        return result
    except json.JSONDecodeError as exc:
        raise SummaryGenerationError(f"Failed to parse summary JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# AI event tracking — best-effort
# ---------------------------------------------------------------------------

_SUMMARY_MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (5.0, 15.0),
    "deepseek-v4-pro": (0.14, 0.28),
}


def _emit_meeting_ai_event(
    emitter: Any | None,
    model: str,
    raw_response: Any | None,
    *,
    success: bool,
) -> None:
    if emitter is None:
        return
    try:
        usage = {}
        if raw_response is not None and hasattr(raw_response, "usage") and raw_response.usage is not None:
            usage = {
                "prompt_tokens": raw_response.usage.prompt_tokens or 0,
                "completion_tokens": raw_response.usage.completion_tokens or 0,
            }
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        prices = _SUMMARY_MODEL_PRICING_PER_1M.get(model)
        cost = 0.0
        if prices is not None:
            cost = round((input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1], 6)
        emitter.ai_call(
            agent_name="MeetingSummaryAgent",
            model=model,
            prompt_version="v1",
            input_token=input_tokens,
            output_token=output_tokens,
            cost=cost,
            success=success,
            triggered_by="system",
        )
    except Exception:
        pass
