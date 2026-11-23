import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from ltc.platform.config import get_settings


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _http_client_kwargs(*, timeout: int, proxy_url: str = "") -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    proxy = proxy_url.strip()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def extract_assistant_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""


def parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if "```" in raw:
        pieces = raw.split("```")
        for piece in pieces:
            candidate = piece.replace("json", "", 1).strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class LlmClient:
    def __init__(self, *, event_emitter: Any = None) -> None:
        self.settings = get_settings()
        self._emitter = event_emitter

    async def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        api_key = self.settings.llm_api_key
        if not api_key:
            raise RuntimeError("LLM_API_KEY is not configured.")
        if not self.settings.llm_base_url or not self.settings.llm_model:
            raise RuntimeError("LLM_BASE_URL or LLM_MODEL is not configured.")

        payload = {
            "model": self.settings.llm_model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(
            **_http_client_kwargs(timeout=90, proxy_url=self.settings.llm_proxy_url)
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.post(
                        _chat_completions_url(self.settings.llm_base_url),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "User-Agent": "ltc-customer-operation-agent",
                        },
                        json=payload,
                    )
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    if attempt >= 2:
                        raise RuntimeError(f"LLM request failed after 3 attempts: {exc}") from exc
                    await asyncio.sleep(2 ** attempt)
        result = response.json()
        _emit_ops_ai_event(self._emitter, self.settings.llm_model, result, success=True)
        content = extract_assistant_text(result.get("choices", [{}])[0].get("message", {}).get("content"))
        parsed = parse_json_object(content)
        if parsed is None:
            raise RuntimeError(f"LLM did not return valid JSON: {content or '[empty]'}")
        parsed.setdefault("model", self.settings.llm_model)
        return parsed


def read_prompt(name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / name
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AI event tracking — best-effort
# ---------------------------------------------------------------------------

_OPS_MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-v4-pro": (0.14, 0.28),
}


def _emit_ops_ai_event(
    emitter: Any | None,
    model: str,
    raw_response: dict[str, Any] | None,
    *,
    success: bool,
) -> None:
    if emitter is None:
        return
    try:
        usage = (raw_response or {}).get("usage") or {}
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        prices = _OPS_MODEL_PRICING_PER_1M.get(model)
        cost = 0.0
        if prices is not None:
            cost = round((input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1], 6)
        emitter.ai_call(
            agent_name="EmailGenerationAgent",
            model=model,
            input_token=input_tokens,
            output_token=output_tokens,
            cost=cost,
            success=success,
            triggered_by="system",
        )
    except Exception:
        pass
