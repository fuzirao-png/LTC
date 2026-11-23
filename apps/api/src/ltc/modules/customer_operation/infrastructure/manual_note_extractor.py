"""
LLM-based extraction service for manual notes.
Calls the configured LLM to extract structured fields from raw sales text
into the PRD §4.2 extracted_fields_json format.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ltc.platform.config import get_settings

# The 17 analysis points plus the three customer-view portrait fields.
_EXTRACTION_PROMPT = """你是一个客户信息提取助手。销售会用自然语言输入一段客户沟通记录，你需要从中提取出与以下四大维度 17 个信息点及画像结构 3 个客户视角字段相关的结构化信息。

## 四大维度：
- D1 采购意愿：采购状态、预算区间、时间紧迫度、决策速度
- D2 决策链：决策人角色、影响人/执行人、组织适配度、竞争态势
- D3 业务信号：扩容/新项目信号、技术痛点、供应商不满、合规/认证需求
- D4 企业画像：公司规模、行业细分、地域覆盖、技术栈
- 画像结构.客户视角：关注点、合作方、觉得我们如何（客户对我方的评价、态度或印象）

## 规则：
1. 从文本中逐条提取，每条标注所属维度、提取值、置信度(0-1)。
2. 如果原文没有提到某个维度，不要强行编造。
3. 之前已存储的值可以留空（前端会从数据库读取原值进行对比）。
4. 无法匹配任何维度的内容单独列出到 "unidentified"。
5. 返回JSON格式，不要有其他内容。

## 输入文本：
{raw_text}

## 返回格式（仅JSON）：
{{
  "fields": [
    {{
      "dimension": "D2.决策链.决策人",
      "extracted": "提取的具体值",
      "confidence": 0.85,
      "action": "覆盖"
    }}
  ],
  "unidentified": "无法匹配的内容描述"
}}
"""


class ManualNoteExtractor:
    """Calls the LLM to extract structured fields from raw manual note text."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._timeout = 60.0

    def extract(self, raw_text: str) -> dict[str, Any]:
        """Extract structured fields from raw text using LLM.

        Returns a dict with 'fields' (list of extraction results) and 'unidentified' (str).
        """
        if not self._api_key or not self._base_url:
            return self._fallback_extraction(raw_text)

        prompt = _EXTRACTION_PROMPT.format(raw_text=raw_text)

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": "你是一个精确的客户信息提取助手，只返回JSON，不编造信息。"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
                content = payload["choices"][0]["message"]["content"]

                # Try to extract JSON from LLM response
                result = self._parse_llm_json(content)
                if result:
                    return self._normalize_result(result)
        except Exception:
            pass  # Fall through to fallback

        return self._fallback_extraction(raw_text)

    def _parse_llm_json(self, content: str) -> dict[str, Any] | None:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` block
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding any JSON object
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
        fields = result.get("fields")
        if not isinstance(fields, list):
            return result
        normalized_fields: list[dict[str, Any]] = []
        for item in fields:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            dimension = str(normalized.get("dimension") or "")
            if any(label in dimension for label in ("竞争对手", "竞争态势", "竞对", "竞品")):
                normalized["extracted"] = _normalize_competitor_value(
                    str(normalized.get("extracted") or "")
                )
            normalized_fields.append(normalized)
        return {**result, "fields": normalized_fields}
    def _fallback_extraction(self, raw_text: str) -> dict[str, Any]:
        """Simple regex-based fallback when LLM is unavailable."""
        fields: list[dict[str, Any]] = []
        unidentified_parts: list[str] = []

        # Simple pattern matching for common fields
        patterns = [
            (r'(?:客户)?(?:最)?(?:关注点|关注|最关心)(?:是|为|包括|：|:)?\s*([^，。；;\n]+)', "画像结构.客户视角.关注点", "覆盖"),
            (r'(?:合作方|合作伙伴)(?:是|为|包括|有|：|:)?\s*([^，。；;\n]+)', "画像结构.客户视角.合作方", "覆盖"),
            (r'(?:客户)?(?:觉得我们如何|对我方的?(?:看法|评价|印象)|对我们的?(?:看法|评价|印象))(?:是|为|：|:)?\s*([^，。；;\n]+)', "画像结构.客户视角.觉得我们如何", "覆盖"),
            (r'(?:竞争对手|竞对|对标|竞品)(?:是|为|有|包括|：|:)?\s*([^，。；;\n]+)', "D2.决策链.竞争对手", "覆盖"),
            (r'(?:决策人|关键决策|决策者)(?:是|为|从)(\S+)', "D2.决策链.决策人", "覆盖"),
            (r'(?:预算|价格|费用).*?(\d+\s*万[美日中人]?[元币金]?)', "D1.采购意愿.预算区间", "新增"),
            (r'(?:CTO|CFO|CEO|技术负责人|财务负责人)', "D2.决策链.决策人", "新增"),
            (r'(?:扩容|扩张|增长|拓展|新项目|新团队)', "D3.业务信号.扩容/新项目信号", "新增"),
            (r'(?:团队|规模|员工).*?(\d+\s*人)', "D4.企业画像.公司规模", "新增"),
            (r'(?:Q[1-4]|季度|明年|下半年|上半年)', "D1.采购意愿.时间紧迫度", "新增"),
        ]

        found_any = False
        for pattern, dimension, action in patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                value = m.group(1) if m.lastindex else m.group(0)
                if dimension == "D2.决策链.竞争对手":
                    value = _normalize_competitor_value(value)
                fields.append({
                    "dimension": dimension,
                    "extracted": value.strip(),
                    "previous": None,
                    "confidence": 0.6,
                    "action": action,
                    "selected": True,
                })
                found_any = True

        if not found_any:
            unidentified_parts.append("未能从文本中自动识别到明确的维度信息，请人工确认。")
        else:
            # Mark remaining text as unidentified
            remaining = raw_text
            for f in fields:
                remaining = remaining.replace(f["extracted"], "")
            remaining = remaining.strip().strip("，。,. ")
            if len(remaining) > 5:
                unidentified_parts.append(remaining[:100])

        return {
            "fields": fields,
            "unidentified": "；".join(unidentified_parts) if unidentified_parts else "（无）",
        }
_COMPETITOR_CONNECTORS = re.compile(
    r"\s*(?:、|，|,|/|\||·|以及|或者|或是|和|与|及|\bvs\.?\b|对比)\s*",
    re.IGNORECASE,
)


def _normalize_competitor_value(value: str) -> str:
    names = [
        item.strip(" 。；;:：")
        for item in _COMPETITOR_CONNECTORS.split(value.strip())
        if item.strip(" 。；;:：")
    ]
    return "、".join(dict.fromkeys(names))
