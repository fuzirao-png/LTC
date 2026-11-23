"""OpenAI-compatible language-model adapter with safe local fallbacks."""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from openai import OpenAI

from ltc.platform.config import get_settings

from ..domain.models import DimensionScore


OTA_SCORE_RULES = {
    "D1": {"name": "跨境出行", "scores": (0, 10, 20, 30, 40)},
    "D2": {"name": "企业客户服务能力", "scores": (0, 7.5, 15, 22.5, 30)},
    "D3": {"name": "平台规模/用户量", "scores": (0, 5, 10, 15, 20)},
    "D4": {"name": "技术/系统对接能力", "scores": (0, 2.5, 5, 7.5, 10)},
}
SCALE_SCORE_RULES = {
    "D1_SCALE": {"name": "规模数量", "scores": (0, 10, 20, 30, 40)},
    "D2_COMMERCIAL": {"name": "营收/商业价值", "scores": (0, 8.75, 17.5, 26.25, 35)},
    "D3_COVERAGE": {"name": "全球办公点/区域覆盖", "scores": (0, 6.25, 12.5, 18.75, 25)},
}


class ChineseLanguageModel:
    # OpenAI-compatible gateways may enforce per-account rate limits. Without a
    # global cap N parallel candidates each fanning out 7 scoring calls would
    # hit the gateway with N×6 concurrent requests and trigger timeouts.
    # This limiter lives at the infrastructure layer because it's a property
    # of the external LLM gateway, not of the application orchestration.
    _RATE_LIMIT_SEMAPHORE: threading.BoundedSemaphore | None = None
    _RATE_LIMIT_MAX_CONCURRENT = 4

    def __init__(self, *, api_key: str | None = None, model: str | None = None, timeout: float = 90, event_emitter: Any | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or os.getenv("LEAD_ANALYSIS_LLM_API_KEY") or settings.llm_api_key
        self.model = model or os.getenv("LEAD_ANALYSIS_LLM_MODEL") or settings.llm_model or "gpt-5.6-terra"
        base_url = os.getenv("LEAD_ANALYSIS_LLM_BASE_URL") or settings.llm_base_url or "https://api.openai.com/v1"
        self.timeout = timeout
        self._local = threading.local()
        self._emitter = event_emitter
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
        ) if self.api_key else None
        if ChineseLanguageModel._RATE_LIMIT_SEMAPHORE is None:
            ChineseLanguageModel._RATE_LIMIT_SEMAPHORE = threading.BoundedSemaphore(self._RATE_LIMIT_MAX_CONCURRENT)

    @property
    def last_error(self) -> str | None:
        return getattr(self._local, "last_error", None)

    @last_error.setter
    def last_error(self, value: str | None) -> None:
        self._local.last_error = value

    def _ask(self, instruction: str, payload: object) -> dict:
        self.last_error = None
        if not self.api_key:
            self.last_error = "llm_not_configured"
            return {}
        # Enforce the infrastructure-level rate limit so parallel candidates
        # don't overwhelm the external gateway.
        sem = ChineseLanguageModel._RATE_LIMIT_SEMAPHORE
        acquired = sem.acquire(timeout=self.timeout) if sem else True
        if not acquired:
            self.last_error = "llm_rate_limited"
            return {}
        # Keep the request compatible with the existing OpenAI-compatible
        # gateway used by the legacy agent. Some gateways reject
        # `response_format` or newer model-only parameters with 403.
        body = {"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": "你是LTC线索智能助手。必须只用中文输出，严格返回JSON，不编造没有证据的字段。"},
            {"role": "user", "content": instruction + "\n输入数据:\n" + json.dumps(payload, ensure_ascii=False)},
        ]}
        try:
            if self._client is None:
                self.last_error = "llm_not_configured"
                return {}
            response = self._client.chat.completions.create(**body)
            data = response.model_dump()
            content = response.choices[0].message.content
            _emit_llm_event(self._emitter, self.model, data, success=True)
            return json.loads(content) if isinstance(content, str) else {}
        except Exception as exc:
            # A provider outage must not discard the already-created search run.
            # Callers use deterministic field/query fallbacks and retain the
            # precise failure reason for trace and scoring diagnostics.
            self.last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            _emit_llm_event(self._emitter, self.model, None, success=False)
            return {}
        finally:
            if sem is not None:
                sem.release()

    def plan_query(self, *, request, memory):
        result = self._ask("读取记忆后，理解用户意图，生成一次用于Exa发现企业的精准中文/英文搜索词。不要复述用户原话，只返回 {query: string}。", {"request": request.__dict__ if hasattr(request, "__dict__") else str(request), "memory": memory[:120]})
        return str(result.get("query") or f"{request.query_text} company official website LinkedIn")

    def extract_candidates(self, *, request, results, memory):
        result = self._ask("从Exa结果中提取符合用户地区、行业和公司要求的企业，只返回 {candidates: [{company_name, website, country_code}]}。排除国家、政府、媒体和百科。", {"request": request.query_text, "results": results, "memory": memory[:120]})
        candidates = result.get("candidates") if result else None
        if isinstance(candidates, list) and candidates:
            return [item for item in candidates if isinstance(item, dict)]
        out = []
        for item in results:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url and not any(x in title.lower() for x in ("government", "wikipedia", "country profile", "population")):
                out.append({"company_name": title, "website": url})
        return out

    def summarize_missing(self, *, request, candidate, leads_finder):
        fields = ("website", "company_intro", "industry_code", "employee_count", "country_code", "city", "linkedin_company_url")
        provider_aliases = {
            "website": ("organization_website_url", "organization_primary_domain"),
            "company_intro": ("organization_description",),
            "industry_code": ("organization_industry",),
            "employee_count": ("organization_size",),
            "country_code": ("organization_country", "country"),
            "city": ("organization_city", "city"),
            "linkedin_company_url": ("organization_linkedin_url",),
        }
        missing = [field for field in fields if not candidate.get(field) and not any(leads_finder.get(alias) for alias in provider_aliases.get(field, (field, "organization_" + field)))]
        result = self._ask("判断Leads Finder基础字段还缺哪些字段，并为一次Exa补缺生成搜索词。只返回 {missing_fields: [], search_query: string}。", {"candidate": candidate, "leads_finder": leads_finder})
        if result:
            return {"missing_fields": result.get("missing_fields") or missing, "search_query": result.get("search_query") or candidate.get("company_name")}
        return {"missing_fields": missing, "search_query": f"{candidate.get('company_name')} official website headquarters company size LinkedIn"}

    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence):
        result = self._ask(
            "总结企业全部基础字段，优先使用Leads Finder，Exa只补缺，联系人使用LinkedIn结果。"
            "company_intro 必须将外文资料翻译并概括为1至2句简体中文纯文本，禁止Markdown、标题符号、列表符号和链接。"
            "只返回JSON字段 company_name,website,company_intro,industry_code,employee_count,region_code,country_code,city,linkedin_company_url。",
            {"candidate": candidate, "company_evidence": company_evidence, "contacts": contacts, "exa_evidence": exa_evidence},
        )
        merged = dict(candidate)
        merged.update({k: v for k, v in (result or {}).items() if v not in (None, "", [])})
        return merged

    def score_dimension(self, *, candidate, dimension_code, evidence, score_type, scene_code="S1"):
        rules = SCALE_SCORE_RULES if score_type == "scale" else OTA_SCORE_RULES
        rule = rules.get(dimension_code, {"name": dimension_code, "scores": (0,)})
        instruction = (
            "你是LTC评分Agent。根据真实证据为一个维度评分，只返回JSON "
            "{score: number, explanation: string, evidence_summary: string}。"
            "评分只能从允许档位中选择，禁止因为字段缺失直接给0；必须使用员工数、官网、客户案例、"
            "目的地/区域、技术对接等代理证据。只有证据明确表明该维度完全不存在时才给0。"
            f"当前维度={dimension_code}（{rule['name']}），允许分数={list(rule['scores'])}，场景={scene_code}。"
            "解释必须中文，并说明使用了哪条证据。"
        )
        result = self._ask(instruction, {"candidate": candidate, "dimension_code": dimension_code, "score_type": score_type, "evidence": evidence})
        unavailable = not result and self.last_error is not None
        if unavailable:
            score, explanation = _deterministic_score(candidate, dimension_code, evidence)
            return DimensionScore(dimension_code=dimension_code, score=score, explanation=explanation, evidence=evidence[:5], provider_status="fallback", error_message=self.last_error)
        try:
            score = float(result.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        allowed = tuple(rule["scores"])
        score = min(allowed, key=lambda value: abs(value - score))
        score, fact_note = _apply_hard_facts(candidate, dimension_code, score)
        explanation = str(result.get("explanation") or "证据不足，暂不加分")
        if fact_note:
            explanation = f"{explanation}；{fact_note}"
        return DimensionScore(dimension_code=dimension_code, score=score, explanation=explanation, evidence=evidence[:5], provider_status="succeeded", error_message=None)


def _deterministic_score(candidate, dimension_code, evidence):
    """Conservative fallback using only facts already collected."""
    employee_count = candidate.get("employee_count")
    if dimension_code == "D1_SCALE":
        try:
            count = int(employee_count)
        except (TypeError, ValueError):
            count = 0
        if count >= 500:
            return 40.0, f"评分模型不可用；Leads Finder 已返回员工数 {count}，按规模规则 D1=40。"
        if count >= 100:
            return 30.0, f"评分模型不可用；Leads Finder 已返回员工数 {count}，按规模规则 D1=30。"
        if count >= 50:
            return 20.0, f"评分模型不可用；Leads Finder 已返回员工数 {count}，按规模规则 D1=20。"
        if count > 0:
            return 10.0, f"评分模型不可用；Leads Finder 已返回员工数 {count}，按规模规则 D1=10。"
    text = " ".join(str(item.get(key) or "") for item in evidence for key in ("title", "snippet", "url")).casefold()
    if dimension_code == "D2" and any(token in text for token in ("business travel", "corporate travel", "商旅", "企业差旅", "corporate")):
        return 15.0, "评分模型不可用；证据包含企业商旅服务描述，按 OTA 企业服务能力保守计 D2=15。"
    if dimension_code == "D1" and any(token in text for token in ("international", "global", "worldwide", "跨境", "海外")):
        return 20.0, "评分模型不可用；证据包含国际/跨境服务描述，按 OTA 跨境出行保守计 D1=20。"
    if dimension_code == "D3_COVERAGE" and any(token in text for token in ("international", "global", "worldwide", "multiple countries", "跨境", "全球")):
        return 6.25, "评分模型不可用；证据包含跨区域服务描述，按区域覆盖最低代理档计 D3=6.25。"
    return 0.0, "评分模型不可用，现有证据未能支持该维度加分。"


def _apply_hard_facts(candidate, dimension_code, score):
    """Prevent an LLM result from contradicting explicit collected facts."""
    if dimension_code != "D1_SCALE":
        return score, ""
    try:
        employees = int(candidate.get("employee_count"))
    except (TypeError, ValueError):
        return score, ""
    minimum = 40.0 if employees >= 500 else 30.0 if employees >= 100 else 20.0 if employees >= 50 else 10.0 if employees > 0 else 0.0
    if score < minimum:
        return minimum, f"已按明确员工数 {employees} 应用规模评分下限 D1_SCALE={minimum}"
    return score, ""


# ---------------------------------------------------------------------------
# AI event tracking — best-effort telemetry
# ---------------------------------------------------------------------------

_LLM_MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-v4-pro": (0.14, 0.28),
}


def _emit_llm_event(
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
        prices = _LLM_MODEL_PRICING_PER_1M.get(model)
        cost = 0.0
        if prices is not None:
            cost = round((input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1], 6)
        emitter.ai_call(
            agent_name="IcpScoreAgent",
            model=model,
            input_token=input_tokens,
            output_token=output_tokens,
            cost=cost,
            success=success,
            triggered_by="system",
        )
    except Exception:
        pass
