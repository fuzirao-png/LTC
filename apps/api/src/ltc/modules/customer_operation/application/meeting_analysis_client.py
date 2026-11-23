from pathlib import Path
from typing import Any

import httpx

from ltc.platform.config import get_settings
from ltc.modules.customer_operation.infrastructure.llm_adapter import LlmClient, _http_client_kwargs


def _openai_compatible_url(base_url: str, endpoint: str) -> str:
    base = base_url.rstrip("/")
    endpoint = endpoint.lstrip("/")
    if base.endswith("/v1"):
        return f"{base}/{endpoint}"
    return f"{base}/v1/{endpoint}"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class MeetingAnalysisClient:
    def __init__(self, api_base: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        # api_base is kept for backward-compatible construction, but meeting
        # analysis now runs inside customer-operation-agent through ASR + LLM.
        self.api_base = (api_base or settings.meeting_analysis_api_base).rstrip("/")

    async def analyze_file(
        self,
        file_path: Path,
        *,
        language: str = "zh",
        include_transcript: bool = True,
    ) -> dict[str, Any]:
        transcription = await self._transcribe_file(file_path, language=language)
        transcript = str(transcription.get("transcript") or "").strip()
        if not transcript:
            raise RuntimeError("ASR did not return transcript text.")

        summary_payload = await self._summarize_transcript(transcript)
        return self._normalize_result(
            {
                "file_name": file_path.name,
                "duration_seconds": transcription.get("duration_seconds"),
                "transcript": transcript if include_transcript else "",
                "segments": transcription.get("segments") or [],
                "transcript_provider": transcription.get("provider") or self.settings.asr_model,
                "summary": summary_payload,
            }
        )

    async def _transcribe_file(self, file_path: Path, *, language: str) -> dict[str, Any]:
        if not self.settings.asr_api_key:
            raise RuntimeError("ASR_API_KEY is not configured.")
        if not self.settings.asr_base_url or not self.settings.asr_model:
            raise RuntimeError("ASR_BASE_URL or ASR_MODEL is not configured.")

        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, "application/octet-stream")}
            data = {
                "model": self.settings.asr_model,
                "language": language,
                "response_format": "verbose_json",
            }
            async with httpx.AsyncClient(
                **_http_client_kwargs(timeout=180, proxy_url=self.settings.llm_proxy_url)
            ) as client:
                response = await client.post(
                    _openai_compatible_url(self.settings.asr_base_url, "audio/transcriptions"),
                    headers={"Authorization": f"Bearer {self.settings.asr_api_key}"},
                    files=files,
                    data=data,
                )
        response.raise_for_status()
        result = response.json()
        segments = []
        for item in _as_list(result.get("segments")):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "start": item.get("start", 0),
                    "end": item.get("end", item.get("start", 0)),
                    "speaker_id": item.get("speaker") or item.get("speaker_id"),
                    "text": text,
                }
            )
        return {
            "transcript": str(result.get("text") or result.get("transcript") or "").strip(),
            "segments": segments,
            "duration_seconds": result.get("duration") or result.get("duration_seconds"),
            "provider": self.settings.asr_model,
        }

    async def _summarize_transcript(self, transcript: str) -> dict[str, Any]:
        system_prompt = (
            "你是客户运营会议分析助手。请只返回 JSON 对象，不要 Markdown。"
            "字段包括 summaryText, customer_needs, pain_points, buying_signals, "
            "action_items, decisions, risks, keywords, next_step。"
            "action_items 中每项使用 task, owner, due_at 字段。"
        )
        user_prompt = (
            "请根据以下会议转写，提取客户需求、痛点、购买信号、风险、关键词、"
            "下一步动作和待办事项。\n\n会议转写：\n"
            f"{transcript}"
        )
        return await LlmClient().chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def _normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        action_items = summary.get("action_items") or result.get("action_items") or result.get("actionItems") or []
        decisions = result.get("decisions") or summary.get("decisions") or summary.get("buying_signals") or []
        risks = result.get("risks") or summary.get("risks") or []
        keywords = result.get("keywords") or summary.get("keywords") or summary.get("customer_needs") or []
        summary_text = result.get("summary_text") or result.get("summaryText") or summary.get("summaryText") or ""
        if not summary_text and summary:
            parts = []
            if summary.get("next_step"):
                parts.append(f"下一步：{summary['next_step']}")
            for label, key in (
                ("客户需求", "customer_needs"),
                ("痛点", "pain_points"),
                ("购买信号", "buying_signals"),
            ):
                values = summary.get(key) or []
                if values:
                    parts.append(f"{label}：" + "；".join(str(item) for item in values))
            summary_text = "\n".join(parts)

        return {
            **result,
            "file_name": result.get("file_name") or result.get("fileName") or "",
            "duration_seconds": result.get("duration_seconds") or result.get("durationSeconds"),
            "transcript": result.get("transcript") or "",
            "transcript_provider": result.get("transcript_provider") or self.settings.asr_model,
            "summary": summary_text or "",
            "action_items": action_items,
            "decisions": decisions,
            "risks": risks,
            "keywords": keywords,
            "segments": result.get("segments") if isinstance(result.get("segments"), list) else [],
        }



