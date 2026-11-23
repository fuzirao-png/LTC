"""Pure report, Sales Guide, suggestion, and input-hash rules."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import hashlib
import json
from typing import Any, Final
from urllib.parse import urlparse
from uuid import UUID, uuid4

from ltc.modules.customer_analysis.domain.enrichment import (
    build_deterministic_candidates,
)
from ltc.modules.customer_analysis.domain.field_catalog import (
    CORE_MEDDPICC_FIELDS,
    CORE_PROFILE_FIELDS,
)
from ltc.modules.customer_analysis.domain.models import (
    MEDDPICC_DIMENSIONS,
    AnalysisContext,
    AnalysisSuggestion,
    CustomerProfile,
    GeneratedReportContent,
    MeddpiccDimension,
)


MODULE_BLUEPRINTS: Final[dict[str, dict[str, Any]]] = {
    "market": {
        "title": "市场分析",
        "purpose": "判断客户扩张方向、目标市场覆盖优先级与首期试点切入逻辑。",
        "sections": ("覆盖判断", "市场机会", "放大路径"),
    },
    "company": {
        "title": "公司分析",
        "purpose": "理解客户业务闭环、平台嵌入方式和中长期扩展空间。",
        "sections": ("核心场景", "平台嵌入", "扩展方向"),
    },
    "competitor": {
        "title": "竞对分析",
        "purpose": "明确竞对格局、ROI 讲法和企业级竞争策略。",
        "sections": ("竞对范围", "ROI测算", "竞争策略"),
    },
    "pain": {
        "title": "需求痛点",
        "purpose": "锁定客户管理痛点、技术约束和合规门槛。",
        "sections": ("三层痛点", "技术集成", "合规门槛"),
    },
    "product": {
        "title": "产品建议",
        "purpose": "指导销售组织方案、配置、报价和阶段性交付路径。",
        "sections": ("推荐方案", "配置方案", "交付路径"),
    },
}

PROMPT_VERSION: Final[str] = "customer-analysis-prompt-v1"
SCHEMA_VERSION: Final[str] = "customer-analysis-schema-v1"
PROMPT_REGISTRY: Final[dict[str, dict[str, str]]] = {
    PROMPT_VERSION: {
        "purpose": "evidence-grounded five-module customer analysis and sales guidance",
        "schema_version": SCHEMA_VERSION,
    }
}


def prompt_metadata() -> dict[str, str]:
    """Return immutable prompt metadata for report/audit consumers."""
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "purpose": PROMPT_REGISTRY[PROMPT_VERSION]["purpose"],
    }


def canonical_input_hash(
    context: AnalysisContext,
    *,
    prompt_version: str,
    schema_version: str,
    model_name: str | None,
    generation_parameters: dict[str, Any] | None = None,
) -> str:
    snapshot = context.snapshot()
    # The cutoff is audit metadata. Evidence IDs, content hashes and versions
    # determine cache invalidation; hashing wall-clock time would disable reuse.
    snapshot.pop("engagement_cutoff_at", None)
    payload = {
        "input_snapshot": snapshot,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "model_name": model_name,
        "generation_parameters": generation_parameters or {},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def meddpicc_revision(dimensions: list[MeddpiccDimension]) -> str:
    payload = [item.to_dict() for item in sorted(dimensions, key=lambda item: item.dimension_code)]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def health_grade(icp_score: float) -> str:
    if icp_score >= 85:
        return "A-"
    if icp_score >= 72:
        return "B+"
    return "C+"


def intention_level(icp_score: float, engagement: dict[str, Any]) -> str:
    explicit = str(engagement.get("intent_level") or "").strip().lower()
    if explicit in {"interested", "pricing"}:
        return "强意向"
    if explicit == "product_question" or icp_score >= 85:
        return "中高"
    if icp_score >= 60:
        return "中等"
    return "待确认"


def _text(value: Any, default: str = "待确认") -> str:
    if value in (None, "", [], {}):
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _profile(context: AnalysisContext, field: str, legacy_field: str | None = None) -> Any:
    return context.profile.get(field, context.profile.get(legacy_field or field))


def _dimension(context: AnalysisContext, code: str) -> dict[str, Any]:
    raw = context.meddpicc.get(code, {})
    payload = raw.get("payload", {}) if isinstance(raw, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return {**payload, **({key: raw[key] for key in ("level", "status", "summary") if key in raw} if isinstance(raw, dict) else {})}


def _dimension_description(context: AnalysisContext, code: str, default: str) -> str:
    dimension = _dimension(context, code)
    return _text(dimension.get("summary") or dimension.get("desc") or dimension.get("description"), default)


def _paragraph(context: AnalysisContext, subtitle: str) -> str:
    company_name = _text(context.company.get("company_name") or context.company.get("name"), "该客户")
    company_type = _text(_profile(context, "company_type"), "客户类型待确认")
    business_model = _text(_profile(context, "business_model"), "业务模式待确认")
    region = _text(_profile(context, "region_text", "region"), "目标区域待确认")
    coverage = _text(_profile(context, "coverage"), "覆盖范围待确认")
    scenario = _text(_profile(context, "esim_scenario"), "通信场景待确认")
    integration = _text(_profile(context, "integration"), "集成方式待确认")
    compliance = _text(_profile(context, "compliance"), "合规要求待确认")
    pain = _dimension_description(context, "identify_pain", "当前痛点待确认")
    competition = _dimension_description(context, "competition", "竞对情况待确认")
    communications = context.engagement.get("communications", [])
    communication_text = "；".join(
        str(item.get("summary"))
        for item in communications[-3:]
        if isinstance(item, dict) and item.get("summary")
    ) or _text(context.engagement.get("latest_summary"), "最新沟通记录待确认")
    evidence_text = "；".join(
        str(item.get("title") or item.get("url") or "未命名证据")
        for item in context.evidence_refs[-5:]
        if isinstance(item, dict)
    ) or "暂无外部证据引用"
    evidence_hint = evidence_text if evidence_text != "暂无外部证据引用" else "当前没有可核验的外部资料"
    templates = {
        "覆盖判断": (
            f"{company_name}公开定位为{company_type}，业务区域暂记录为{region}。"
            f"从现有客户资料和证据《{evidence_hint}》看，可先把{scenario}作为待验证场景；"
            "覆盖范围、目标国家和实际用户规模尚未得到客户直接确认。"
        ),
        "市场机会": (
            f"围绕{company_name}所在的{company_type}领域，现有资料更支持从{region}的业务覆盖、"
            f"服务效率和系统集成需求观察机会。当前没有足够证据量化市场规模，市场趋势只能作为销售假设，"
            f"下一步应结合客户沟通（{communication_text}）确认优先区域和时间表。"
        ),
        "放大路径": (
            f"如果{company_name}确实存在{scenario}需求，首期可以围绕{integration}集成和{compliance}合规要求设计小范围验证。"
            f"目前证据只能支持提出这一进入假设，不能证明客户已经启动采购；应先确认试点国家、用户数量、验收指标和负责人。"
        ),
        "核心场景": (
            f"{company_name}当前可识别的业务类型是{company_type}，业务模式线索为{business_model}。"
            f"现有资料尚未说明其在{scenario}场景中的具体流程、用户规模和内部责任人，销售需要结合最近沟通（{communication_text}）补齐。"
        ),
        "竞对范围": (
            f"关于{company_name}的竞对范围，目前资料只显示需要关注{competition}，尚不足以确认具体供应商、合同期限或替代路径。"
            f"建议销售先询问客户当前方案、正在比较的选项以及切换成本，再建立可验证的对比表。"
        ),
        "竞争策略": (
            f"在尚未确认具体竞品的情况下，LTC不应直接声称存在价格或功能优势。"
            f"可以围绕{coverage}覆盖、{integration}集成、{compliance}合规和交付响应建立比较维度，"
            "待客户提供现有方案与评估标准后再形成差异化结论。"
        ),
        "ROI测算": (
            f"当前没有足够内部资料确认{company_name}的预算、现有成本或采购价格，因此不能给出确定ROI或报价。"
            f"后续应从{scenario}的用户数、国家数量、人工处理成本和验收目标采集基线，再与替代方案进行测算。"
        ),
        "推荐方案": (
            f"基于{company_name}的{company_type}属性和待确认的{scenario}场景，建议先评估企业eSIM管理方案的适配性。"
            f"推荐成立的前提是客户确认{integration}接口范围、{compliance}合规要求、首期覆盖区域和验收指标；当前不代表客户已同意采购。"
        ),
        "配置方案": (
            f"方案配置应先围绕{integration}集成、账号权限、账单审计和{compliance}合规边界展开。"
            f"由于{company_name}的实际系统、用户数量和运营流程尚未确认，当前只能提供验证清单，不能提前锁定套餐、价格或交付周期。"
        ),
    }
    return templates.get(subtitle, (
        f"{company_name}的{subtitle}目前只能依据{company_type}、{region}和已有沟通资料形成初步判断。"
        f"现有证据显示客户关注{pain}，但{integration}、{compliance}和{competition}仍待确认；"
        "销售应在下一次沟通中补齐事实、影响和决策条件，再决定推进方式。"
    ))


def _competitors(context: AnalysisContext) -> list[str]:
    dimension = _dimension(context, "competition")
    values = dimension.get("competitors")
    if not isinstance(values, list):
        description = str(dimension.get("summary") or dimension.get("desc") or "")
        values = [item.strip() for item in description.replace("、", "，").replace(",", "，").split("，") if item.strip()]
    values = [str(value) for value in values if value][:3]
    return values + [f"待确认竞品{index}" for index in range(len(values) + 1, 4)]


def _section_confidence(context: AnalysisContext, module_name: str, subtitle: str) -> float:
    """Compute a bounded, explainable confidence for one report section."""
    evidence = len(context.evidence_refs)
    contacts = len(context.contacts)
    communication = bool(context.engagement.get("latest_summary") or context.engagement.get("communications"))
    score = 0.35 + min(0.25, evidence * 0.05) + min(0.15, contacts * 0.03)
    if communication:
        score += 0.10
    if module_name == "competitor" and subtitle == "竞对范围":
        score += 0.05
    return round(min(1.0, score), 4)


def _with_section_confidence(context: AnalysisContext, report_payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(report_payload)
    section_confidence: dict[str, float] = {}
    for module_name, blueprint in MODULE_BLUEPRINTS.items():
        module = dict(result.get(module_name) or {})
        sections = []
        for subtitle in blueprint["sections"]:
            confidence = _section_confidence(context, module_name, subtitle)
            section_confidence[f"{module_name}.{subtitle}"] = confidence
            content = next(
                (item.get("content") for item in module.get("sections", []) if item.get("subtitle") == subtitle),
                None,
            )
            sections.append({"subtitle": subtitle, "content": content or "待确认", "confidence": confidence})
        module["sections"] = sections
        _ensure_claim_structure(context, module_name, module)
        result[module_name] = module
    result["_meta"] = {**prompt_metadata(), "section_confidence": section_confidence}
    return result


def _ensure_claim_structure(
    context: AnalysisContext, module_name: str, module: dict[str, Any]
) -> None:
    """Keep legacy sections while exposing explicit evidence layers."""
    selected_evidence = _select_module_evidence(context, module_name)
    default_refs = [str(item["evidence_id"]) for item in selected_evidence]
    sections = module.get("sections") or []
    if not module.get("facts"):
        evidence_facts = [
            {
                "text": _evidence_fact(item),
                "evidence_ids": [str(item["evidence_id"])],
                "confidence": 0.72 if item.get("url") else 0.6,
            }
            for item in selected_evidence
        ]
        module["facts"] = evidence_facts or [
            {
                "text": str(item.get("content") or "待确认"),
                "evidence_ids": list(default_refs),
                "confidence": float(item.get("confidence") or 0),
            }
            for item in sections[:3]
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        ]
    if not module.get("inferences"):
        module["inferences"] = [{
            "text": _module_inference(context, module_name, selected_evidence),
            "evidence_ids": list(default_refs),
            "confidence": 0.55 if len(default_refs) >= 2 else 0.3 if default_refs else 0,
        }]
    if not module.get("unknowns"):
        module["unknowns"] = [{
            "item": _module_unknown(module_name),
            "reason": "公开资料不能替代客户确认，当前内部证据中没有直接结论",
        }]
    if not module.get("sales_recommendations"):
        actions = module.get("actions") or []
        if not isinstance(actions, list):
            actions = [actions]
        module["sales_recommendations"] = [
            {
                "action": str(action),
                "reason": _module_recommendation_reason(module_name),
                "evidence_ids": list(default_refs),
            }
            for action in actions[:3]
            if str(action).strip()
        ] or [{
            "action": _module_recommendation(module_name),
            "reason": _module_recommendation_reason(module_name),
            "evidence_ids": list(default_refs),
        }]


_MODULE_EVIDENCE_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "market": ("market", "industry", "trend", "growth", "forecast", "global"),
    "company": ("about", "company", "business", "revenue", "funding", "product"),
    "competitor": ("competitor", "comparison", " versus ", " vs ", "alternative", "pricing"),
    "pain": ("integration", "security", "compliance", "travel", "expense", "support"),
    "product": ("product", "platform", "integration", "api", "implementation", "global"),
}


def _select_module_evidence(
    context: AnalysisContext, module_name: str, limit: int = 3
) -> list[dict[str, Any]]:
    keywords = _MODULE_EVIDENCE_KEYWORDS.get(module_name, ())
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(context.evidence_refs):
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        text = " ".join(
            str(item.get(key) or "") for key in ("title", "text", "excerpt")
        ).casefold()[:5000]
        score = sum(text.count(keyword) for keyword in keywords)
        if item.get("url"):
            score += 2
        if str(item.get("source_type") or "") in {"exa", "web", "external_web"}:
            score += 1
        candidates.append((score, -index, item))
    candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)

    selected: list[dict[str, Any]] = []
    origins: set[str] = set()
    for _, _, item in candidates:
        origin = _evidence_origin(item)
        if origin and origin in origins:
            continue
        selected.append(item)
        if origin:
            origins.add(origin)
        if len(selected) >= limit:
            break
    return selected


def _evidence_origin(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    if url:
        host = (urlparse(url).hostname or "").casefold()
        return host.removeprefix("www.")
    return str(item.get("source_type") or "internal")


def _evidence_fact(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "未命名来源").strip()
    source_type = str(item.get("source_type") or "").strip()
    source_label = "联网资料" if source_type in {"exa", "web", "external_web"} else "内部资料"
    return (
        f"已检索到与本模块相关的{source_label}《{title}》。"
        "该资料已作为分析依据输入，具体结论仍需结合客户沟通和销售确认，不能直接视为客户已确认事实。"
    )


def _module_inference(
    context: AnalysisContext,
    module_name: str,
    evidence: list[dict[str, Any]],
) -> str:
    company_name = _text(
        context.company.get("company_name") or context.company.get("name"), "该客户"
    )
    labels = {
        "market": "市场进入与区域扩张机会",
        "company": "业务模式、产品组合与组织需求",
        "competitor": "替代方案和差异化切入点",
        "pain": "潜在业务痛点及实施约束",
        "product": "产品匹配和首期试点路径",
    }
    titles = "、".join(str(item.get("title") or "公开来源") for item in evidence[:3])
    if len(evidence) < 2:
        return f"关于{company_name}的{labels.get(module_name, '业务机会')}，当前来源不足，暂不形成确定判断。"
    return (
        f"综合《{titles}》可推断，{company_name}的{labels.get(module_name, '业务机会')}值得进一步验证；"
        "该判断来自公开资料交叉分析，不代表客户已确认采购需求。"
    )


def _module_unknown(module_name: str) -> str:
    return {
        "market": "目标区域优先级、可服务市场规模和进入时间表",
        "company": "内部业务目标、预算归属和项目负责人",
        "competitor": "当前供应商、替代方案、合同期限和切换门槛",
        "pain": "客户已确认的痛点强度、影响范围和量化损失",
        "product": "首期国家、用户规模、接口范围、预算和验收指标",
    }.get(module_name, "预算、决策人和实施窗口")


def _module_recommendation(module_name: str) -> str:
    return {
        "market": "用公开市场信号验证优先区域，并向客户确认扩张时间表",
        "company": "围绕客户现有产品与运营模式访谈业务负责人",
        "competitor": "建立当前方案、替代方案与我方能力的可验证对比表",
        "pain": "在下一次沟通中量化痛点频率、影响和现有处理成本",
        "product": "基于已确认范围设计小规模试点和验收指标",
    }.get(module_name, "安排下一次沟通核实关键假设")


def _module_recommendation_reason(module_name: str) -> str:
    return (
        f"基于{MODULE_BLUEPRINTS.get(module_name, {}).get('title', '当前模块')}的多来源公开证据，"
        "先验证事实与客户意愿，再推进方案和商业承诺"
    )


def _add_compat_sections(report_payload: dict[str, Any]) -> dict[str, Any]:
    """Expose the legacy five-module section contract without changing domain shape."""
    section_sources = {
        "market": (("覆盖判断", "structure.coverage_judgement"), ("市场机会", "trend"), ("放大路径", "scenario_opportunity")),
        "company": (("核心场景", "operation"), ("平台嵌入", "product.integration"), ("扩展方向", "target_market")),
        "competitor": (("竞对范围", "products"), ("ROI测算", "pricing"), ("竞争策略", "services")),
        "pain": (("三层痛点", "layers"), ("技术集成", "layers.1")),
        "product": (("推荐方案", "recommended"), ("配置方案", "recommended.0.our_diff"), ("交付路径", "recommended_price.payment_terms")),
    }

    def resolve(value: Any, path: str) -> Any:
        current = value
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return "待确认"
        return current if current not in (None, "", [], {}) else "待确认"

    result = deepcopy(report_payload)
    for module_name, specs in section_sources.items():
        module = dict(result.get(module_name) or {})
        module["sections"] = [
            {"subtitle": subtitle, "content": resolve(module, path)}
            for subtitle, path in specs
        ]
        result[module_name] = module
    return result


def build_template_report(context: AnalysisContext) -> GeneratedReportContent:
    profile_candidates, meddpicc_candidates = build_deterministic_candidates(context)
    context = _context_with_candidates(
        context, profile_candidates, meddpicc_candidates
    )
    name = _text(context.company.get("company_name") or context.company.get("name"), "该客户")
    scenario = _text(_profile(context, "esim_scenario"))
    coverage = _text(_profile(context, "coverage"))
    budget = _text(_profile(context, "budget_text", "budget"))
    business_model = _text(_profile(context, "business_model"))
    integration = _text(_profile(context, "integration"))
    compliance = _text(_profile(context, "compliance"))
    score = float(context.adopted_icp.get("total_score") or 0)
    competitors = _competitors(context)
    pain = _dimension_description(context, "identify_pain", "客户核心痛点待确认")
    latest_engagement = _text(context.engagement.get("latest_summary"), "最新沟通记录待确认")
    extra_payload = context.profile.get("extra_payload", {})
    if not isinstance(extra_payload, dict):
        extra_payload = {}

    report_payload = {
        "header": {
            "name": name,
            "tag": "高优先级战略客户" if score >= 85 else "重点跟进客户",
            "subtitle": f"{coverage} · {scenario} · {business_model}",
        },
        "customer_view": {
            "concerns": _text(extra_payload.get("concerns") or pain, "待分析"),
            "partners": _text(extra_payload.get("partners"), "待确认"),
            "impression_of_us": _text(
                extra_payload.get("impression_of_us") or context.engagement.get("latest_summary"),
                "待评估",
            ),
        },
        "market": {
            "module_title": MODULE_BLUEPRINTS["market"]["title"],
            "structure": {
                "tam": "市场总规模待确认：需要补充行业公开数据和统计口径。",
                "sam": "可服务市场待确认：需要结合区域、客户类型和合规边界测算。",
                "som": "可获取市场待确认：需要结合首期试点资源、销售覆盖和转化率测算。",
                "competitor_landscape": competitors,
                "coverage_judgement": _paragraph(context, "覆盖判断"),
            },
            "trend": _paragraph(context, "市场机会"),
            "scenario_demand": [{"scenario": scenario, "demand": pain, "evidence": latest_engagement}],
            "scenario_opportunity": [{"scenario": scenario, "opportunity": _paragraph(context, "放大路径"), "size": budget, "our_fit": f"采用的四维 ICP 为 {score:g} 分"}],
        },
        "company": {
            "module_title": MODULE_BLUEPRINTS["company"]["title"],
            "operation": _paragraph(context, "核心场景"),
            "business": {
                "main_business": _text(_profile(context, "company_type")),
                "revenue_model": business_model,
                "geography": coverage,
                "employee_scale": _text(_profile(context, "employee_scale")),
            },
            "product": {"esim_scenario": scenario, "integration": integration, "estimated_usage": _text(_profile(context, "estimated_usage"))},
            "compliance": compliance,
            "decision_chain": {code: _dimension(context, code) for code in ("economic_buyer", "champion", "decision_criteria", "decision_process", "paper_process")},
            "target_market": f"优先围绕 {coverage} 的 {scenario} 场景验证首期试点。",
        },
        "competitor": {
            "module_title": MODULE_BLUEPRINTS["competitor"]["title"],
            "products": [{"name": item, "position": "待确认", "analysis": _paragraph(context, "竞对范围")} for item in competitors],
            "services": [{"name": item, "coverage": coverage, "analysis": _paragraph(context, "竞争策略")} for item in competitors],
            "pricing": [{"name": item, "price_range": budget, "analysis": _paragraph(context, "ROI测算")} for item in competitors],
            "advantages": _dimension(context, "competition").get("advantages", []),
            "weaknesses": _dimension(context, "competition").get("weaknesses", []),
        },
        "pain": {
            "module_title": MODULE_BLUEPRINTS["pain"]["title"],
            "requirement": pain,
            "layers": [pain, f"技术集成：{integration}", f"合规门槛：{compliance}"],
            "scenarios": [scenario],
        },
        "product": {
            "module_title": MODULE_BLUEPRINTS["product"]["title"],
            "requirement": pain,
            "recommended": [{"name": "企业 eSIM 管理方案", "price": budget, "rationale": _paragraph(context, "推荐方案"), "our_diff": _paragraph(context, "配置方案")}],
            "actions": [
                "先确认首期国家、用户规模、系统接口和验收指标。",
                "安排 API、后台权限、账单和审计能力的技术评审。",
                "完成两周试点并按覆盖率、激活成功率和交付周期复盘。",
                "试点达标后确认扩容国家、采购合同和长期 SLA。",
            ],
            "recommended_price": {"range": budget, "rationale": _paragraph(context, "ROI测算"), "payment_terms": _text(_profile(context, "decision_cycle_text", "decision_cycle"))},
        },
    }
    summary = (
        f"{name} 当前采用的四维 ICP 为 {score:g} 分，建议围绕 {scenario}、"
        f"{integration} 和 {compliance} 组织首期试点并补齐决策链证据。"
    )
    confidence = round(min(1.0, 0.35 + len(context.evidence_refs) * 0.05 + len(context.contacts) * 0.03), 4)
    section_confidence = {name: confidence for name in MODULE_BLUEPRINTS}
    report_payload = _with_section_confidence(context, _add_compat_sections(report_payload))
    return GeneratedReportContent(
        summary=summary,
        report_payload=report_payload,
        sales_guide_payload=build_sales_guide(context),
        content_source="template",
        model_name=None,
        confidence=confidence,
        section_confidence=dict(report_payload["_meta"]["section_confidence"]),
        evidence_refs=context.evidence_refs,
        profile_candidates=profile_candidates,
        meddpicc_candidates=meddpicc_candidates,
    )


def _context_with_candidates(
    context: AnalysisContext,
    profile_candidates: dict[str, Any],
    meddpicc_candidates: dict[str, Any],
) -> AnalysisContext:
    profile = dict(context.profile)
    for field_id, candidate in profile_candidates.items():
        if profile.get(field_id) in (None, "", "待确认") and isinstance(candidate, dict):
            value = candidate.get("value")
            if value not in (None, "", "待确认"):
                profile[field_id] = value
    meddpicc = dict(context.meddpicc)
    for code, candidate in meddpicc_candidates.items():
        if not isinstance(candidate, dict) or candidate.get("status") == "unknown":
            continue
        current = meddpicc.get(code, {})
        current = dict(current) if isinstance(current, dict) else {}
        if current.get("summary") not in (None, "", "待确认"):
            continue
        meddpicc[code] = {
            **current,
            "status": candidate.get("status"),
            "summary": candidate.get("summary"),
            "payload": {
                key: candidate.get(key)
                for key in (
                    "detail",
                    "metric",
                    "actors",
                    "process_steps",
                    "next_question",
                    "risk",
                )
                if candidate.get(key) not in (None, "", [], {})
            },
        }
    return replace(context, profile=profile, meddpicc=meddpicc)


def _guide_item(context: AnalysisContext, code: str, title: str, default: str) -> dict[str, Any]:
    dimension = _dimension(context, code)
    return {"title": title, "status": dimension.get("level") or dimension.get("status") or "待确认", "analysis": _dimension_description(context, code, default)}


def build_sales_guide(context: AnalysisContext) -> dict[str, Any]:
    return {
        "customer_need": {
            "badge": _dimension(context, "identify_pain").get("status", "unknown"),
            "items": [_guide_item(context, "identify_pain", "痛点识别", "待确认客户核心痛点"), _guide_item(context, "metrics", "需求量化", "待确认量化口径")],
            "questions": ["当前跨国差旅人数和月度峰值分别是多少？", "继续沿用现有方案的年度额外成本是多少？", "试点国家与部门如何选择？", "统一后台优先解决哪些管理问题？"],
            "actions": ["完成痛点、影响和量化三步确认。", "明确试点国家、人数和时间表。", "输出需求确认纪要并锁定优先级。", "下一轮沟通前补齐使用规模与采购窗口。"],
            "email_draft": {"subject": "确认客户痛点与 eSIM API 试点范围", "body": "您好，基于近期沟通，我们建议先确认跨国使用规模、优先国家、后台权限和 API 对接边界，再共同定义两周试点的验收指标。请您补充月度峰值、目标部门及采购窗口，我们将据此返回方案和时间表。"},
            "talk_track": ["先确认当前痛点及其对业务、成本和交付的影响。", "追问试点国家、人数、系统接口和成功指标。", "把客户回答记录为可验证的需求与证据。", "约定下一次评审时间和双方负责人。"],
        },
        "decision_chain": {
            "badge": _dimension(context, "economic_buyer").get("status", "unknown"),
            "items": [_guide_item(context, code, title, default) for code, title, default in (("economic_buyer", "预算决策人", "待确认预算角色"), ("decision_criteria", "选型标准", "待确认选型标准"), ("decision_process", "决策流程", "待确认决策流程"), ("paper_process", "合同审批", "待确认合同流程"), ("champion", "内部推动者", "待确认 Champion"))],
            "questions": ["最终拍板人和预算审批人是谁？", "技术、采购、业务三方分别关注什么指标？", "试点通过后进入合同流程需要多久？", "谁愿意作为内部推动者共同推进？"],
            "actions": ["建立预算人、评估人、使用人角色图谱。", "准备法务与采购材料包。", "安排技术评审。", "沉淀决策链路图。"],
            "email_draft": {"subject": "对齐预算决策链与技术评审安排", "body": "您好，为确保试点顺利推进，建议本周对齐预算决策人、技术评估人、采购与法务流程，并确认 API、权限、审计和 SLA 的验收要求。请协助安排相关同事参加下一次评审，我们会提前发送材料清单。"},
            "talk_track": ["请客户明确最终拍板人和预算审批人。", "分别确认业务、技术、采购和法务的准入条件。", "寻找愿意推动试点的 Champion 并约定职责。", "把决策流程、材料和时间节点写入行动清单。"],
        },
        "competitive_edge": {
            "badge": _dimension(context, "competition").get("status", "unknown"),
            "items": [_guide_item(context, "competition", "竞对态势", "待确认竞对态势")],
            "questions": ["当前还在比较哪些替代方案？", "客户更关注价格、覆盖还是后台能力？", "试点成功标准是什么？", "现有方案最大痛点是什么？"],
            "actions": ["准备竞对差异表。", "用试点数据和 TCO 回答价格比较。", "展示可复制的全球覆盖能力。", "用阶段性试点降低切换成本。"],
            "email_draft": {"subject": "用试点数据比较 TCO 与竞对方案", "body": "您好，我们可以按覆盖、 API 稳定性、后台管理、 SLA 和实施成本建立统一的竞对对比表，并用试点数据核算 TCO。建议先确认客户正在比较的替代方案及成功标准，再安排差异化演示。"},
            "talk_track": ["先确认客户正在比较的供应商和替代方案。", "围绕覆盖、 API、后台、 SLA 与 TCO 逐项对比。", "用试点数据验证差异，不对未知竞品做无依据断言。", "约定竞对评审和采购决策的下一步。"],
        },
    }


def normalize_sales_guide(context: AnalysisContext, candidate: Any) -> dict[str, Any]:
    """Merge provider output with the complete, executable sales-guide contract."""
    fallback = build_sales_guide(context)
    if not isinstance(candidate, dict):
        return fallback
    result = deepcopy(fallback)
    for module_name, fallback_module in fallback.items():
        value = candidate.get(module_name)
        if not isinstance(value, dict):
            continue
        merged = deepcopy(fallback_module)
        merged.update(value)
        for key in ("questions", "actions", "talk_track"):
            provided = merged.get(key)
            if not isinstance(provided, list) or len(provided) < 3:
                merged[key] = fallback_module[key]
        draft = merged.get("email_draft")
        if not isinstance(draft, dict) or not str(draft.get("subject") or "").strip() or not str(draft.get("body") or "").strip():
            merged["email_draft"] = fallback_module["email_draft"]
        result[module_name] = merged
    return result


def build_analysis_suggestions(
    *,
    company_id: UUID,
    report_id: UUID,
    content: GeneratedReportContent,
    profile: CustomerProfile,
    dimensions: list[MeddpiccDimension],
) -> list[AnalysisSuggestion]:
    suggestions: list[AnalysisSuggestion] = []
    for path in CORE_PROFILE_FIELDS:
        candidate = content.profile_candidates.get(path, {})
        proposed = candidate.get("value") if isinstance(candidate, dict) else None
        current = getattr(profile, path)
        confidence = _candidate_confidence(candidate, content.confidence)
        if (
            proposed not in (None, "", "待确认")
            and proposed != _json_comparable(current)
            and confidence is not None
            and confidence >= 0.55
        ):
            suggestions.append(AnalysisSuggestion(
                suggestion_id=uuid4(), company_id=company_id, report_id=report_id,
                target_type="profile", dimension_code=None, target_path=path,
                target_version_at_creation=profile.version, current_value_snapshot=current,
                proposed_value=proposed,
                evidence_refs=_candidate_evidence(candidate, content.evidence_refs),
                confidence=confidence,
            ))
    by_code = {item.dimension_code: item for item in dimensions}
    for code in CORE_MEDDPICC_FIELDS:
        candidate = content.meddpicc_candidates.get(code, {})
        if not isinstance(candidate, dict):
            continue
        proposed = {
            "status": candidate.get("status", "partial"),
            "summary": candidate.get("summary"),
            "payload": {
                key: candidate.get(key)
                for key in (
                    "detail", "metric", "actors", "process_steps",
                    "next_question", "risk",
                )
                if candidate.get(key) not in (None, "", [], {})
            },
        }
        current = by_code[code]
        has_value = proposed["summary"] not in (None, "") or bool(proposed["payload"])
        differs = (
            proposed["summary"] != current.summary
            or proposed["payload"] != current.payload
        )
        confidence = _candidate_confidence(candidate, content.confidence)
        if (
            candidate.get("status") != "unknown"
            and has_value
            and differs
            and confidence is not None
            and confidence >= 0.55
        ):
            suggestions.append(AnalysisSuggestion(
                suggestion_id=uuid4(), company_id=company_id, report_id=report_id,
                target_type="meddpicc", dimension_code=code, target_path=code,
                target_version_at_creation=current.version, current_value_snapshot=current.payload,
                proposed_value=proposed,
                evidence_refs=_candidate_evidence(candidate, content.evidence_refs),
                confidence=confidence,
            ))
    return suggestions


def _candidate_confidence(candidate: Any, fallback: float | None) -> float | None:
    if not isinstance(candidate, dict):
        return fallback
    try:
        return max(0.0, min(1.0, float(candidate.get("confidence"))))
    except (TypeError, ValueError):
        return fallback


def _candidate_evidence(
    candidate: Any, evidence_refs: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], ...]:
    ids = set(candidate.get("evidence_ids") or ()) if isinstance(candidate, dict) else set()
    return tuple(
        {
            key: item.get(key)
            for key in (
                "evidence_id", "url", "title", "source_type", "published_at",
            )
            if item.get(key) is not None
        }
        for item in evidence_refs
        if str(item.get("evidence_id")) in ids
    )


def _json_comparable(value: Any) -> Any:
    return str(value) if isinstance(value, UUID) else value
