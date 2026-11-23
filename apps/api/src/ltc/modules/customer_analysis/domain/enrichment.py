"""Deterministic enrichment and provider-candidate validation rules."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from ltc.modules.customer_analysis.domain.field_catalog import (
    CORE_MEDDPICC_FIELDS,
    CORE_PROFILE_FIELDS,
)
from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.modules.customer_analysis.domain.output_schema import (
    CoreMeddpiccCandidateSet,
    ProfileCandidateSet,
    missing_field_candidate,
    missing_meddpicc_candidate,
)


def internal_evidence_refs(context: AnalysisContext) -> tuple[dict[str, Any], ...]:
    refs = [
        {
            "evidence_id": "internal:company",
            "source_type": "internal_company",
            "title": "客户主数据",
            "url": None,
        },
        {
            "evidence_id": "internal:profile",
            "source_type": "internal_profile",
            "title": "已确认客户画像",
            "url": None,
        },
        {
            "evidence_id": "internal:lead",
            "source_type": "internal_lead",
            "title": "销售线索资料",
            "url": None,
        },
        {
            "evidence_id": "internal:assessment",
            "source_type": "internal_assessment",
            "title": "ICP与客户规模评估",
            "url": None,
        },
    ]
    if context.meddpicc:
        refs.append(
            {
                "evidence_id": "internal:meddpicc",
                "source_type": "internal_meddpicc",
                "title": "已确认MEDDPICC",
                "url": None,
            }
        )
    if context.engagement and not any(
        item.get("source_type") in {"internal_email", "internal_manual_note", "internal_meeting"}
        for item in context.evidence_refs
    ):
        refs.append(
            {
                "evidence_id": "internal:engagement",
                "source_type": "internal_engagement",
                "title": "销售沟通摘要",
                "url": None,
            }
        )
    if context.contacts:
        refs.append(
            {
                "evidence_id": "internal:contacts",
                "source_type": "internal_contacts",
                "title": "已知客户联系人",
                "url": None,
            }
        )
    return tuple(refs)


def build_deterministic_candidates(
    context: AnalysisContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = {
        name: missing_field_candidate(f"未识别到 {name}")
        for name in CORE_PROFILE_FIELDS
    }

    profile_sources: dict[str, tuple[Any, str, str]] = {
        "company_type": (
            _first(context.profile, context.company, keys=("company_type", "industry", "industry_code")),
            "internal:company",
            "公司主数据中的行业或类型",
        ),
        "business_model": (
            _first(context.profile, context.company, context.sales_lead, keys=("business_model", "revenue_model")),
            "internal:company",
            "公司或线索中的业务模式",
        ),
        "employee_scale": (
            _employee_scale(context),
            "internal:assessment",
            "Lead/Scale 富化中的员工规模",
        ),
        "region_text": (
            _first(context.profile, context.company, keys=("region_text", "region", "region_code", "country", "country_code")),
            "internal:company",
            "公司主数据中的区域",
        ),
        "esim_scenario": (
            _first(context.profile, context.company, context.sales_lead, keys=("esim_scenario", "scenario", "scene_code")),
            "internal:lead",
            "线索或画像中的 eSIM 场景",
        ),
        "coverage": (
            _first(context.profile, context.company, context.sales_lead, keys=("coverage", "geography", "target_market")),
            "internal:lead",
            "公司或线索中的覆盖信息",
        ),
        "estimated_usage": (
            _first(context.profile, context.sales_lead, context.adopted_scale, keys=("estimated_usage", "usage", "monthly_usage")),
            "internal:assessment",
            "线索或规模评估中的用量",
        ),
        "integration": (
            _first(context.profile, context.company, context.sales_lead, keys=("integration", "integration_mode", "technology_stack")),
            "internal:lead",
            "公司或线索中的集成信息",
        ),
        "compliance": (
            _first(context.profile, context.company, context.sales_lead, keys=("compliance", "compliance_requirements")),
            "internal:lead",
            "公司或线索中的合规信息",
        ),
        "budget_text": (
            _first(context.profile, context.engagement, context.sales_lead, keys=("budget_text", "budget")),
            "internal:engagement",
            "销售沟通中的预算信息",
        ),
        "decision_maker_text": (
            _first(context.profile, context.engagement, context.sales_lead, keys=("decision_maker_text", "decision_maker", "economic_buyer")),
            "internal:engagement",
            "销售沟通中的决策人信息",
        ),
        "decision_maker_contact_id": (
            _decision_maker_contact_id(context),
            "internal:contacts",
            "已知联系人中的决策角色",
        ),
        "decision_cycle_text": (
            _first(context.profile, context.engagement, context.sales_lead, keys=("decision_cycle_text", "decision_cycle", "purchase_cycle")),
            "internal:engagement",
            "销售沟通中的决策周期",
        ),
    }
    for field_id, (value, evidence_id, reason) in profile_sources.items():
        if _has_value(value):
            profile[field_id] = {
                "value": str(value),
                "confidence": 0.95,
                "evidence_ids": [evidence_id],
                "quote": str(value),
                "reason": reason,
                "missing_reason": None,
                "source_kind": "internal",
            }

    engagement_profile, engagement_meddpicc = _engagement_candidates(context)
    for field_id, candidate in engagement_profile.items():
        if _has_value(candidate.get("value")):
            profile[field_id] = candidate

    meddpicc: dict[str, Any] = {}
    for code in CORE_MEDDPICC_FIELDS:
        raw = context.meddpicc.get(code, {}) if isinstance(context.meddpicc, dict) else {}
        raw = raw if isinstance(raw, dict) else {}
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
        summary = raw.get("summary") or raw.get("desc") or payload.get("summary")
        if _has_value(summary) or any(_has_value(value) for value in payload.values()):
            meddpicc[code] = {
                "status": raw.get("status") if raw.get("status") in {"partial", "confirmed"} else "partial",
                "summary": str(summary) if _has_value(summary) else None,
                "detail": _text_or_none(payload.get("detail") or payload.get("description")),
                "metric": _text_or_none(payload.get("metric") or payload.get("value")),
                "actors": _string_list(payload.get("actors") or payload.get("people")),
                "process_steps": _string_list(payload.get("process_steps") or payload.get("steps")),
                "next_question": _text_or_none(payload.get("next_question") or payload.get("sales_question")),
                "risk": _text_or_none(payload.get("risk")),
                "confidence": 0.95,
                "evidence_ids": ["internal:meddpicc"],
                "missing_reason": None,
            }
        else:
            meddpicc[code] = missing_meddpicc_candidate(f"未识别到 {code}")
    for code, candidate in engagement_meddpicc.items():
        if candidate.get("status") != "unknown":
            meddpicc[code] = candidate

    competition_candidate = meddpicc.pop("competition", None)
    validated_meddpicc = CoreMeddpiccCandidateSet.model_validate(meddpicc).model_dump()
    if competition_candidate is not None:
        validated_meddpicc["competition"] = competition_candidate
    return (
        ProfileCandidateSet.model_validate(profile).model_dump(),
        validated_meddpicc,
    )


def merge_candidate_sets(
    provider_profile: dict[str, Any],
    provider_meddpicc: dict[str, Any],
    deterministic_profile: dict[str, Any],
    deterministic_meddpicc: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Deterministic candidates contain every required field, including unknown
    # placeholders. Start from that complete contract so omitted provider fields
    # can never turn the merged object into an invalid partial candidate set.
    profile = dict(deterministic_profile)
    for field_id, candidate in provider_profile.items():
        if isinstance(candidate, dict) and _has_value(candidate.get("value")):
            profile[field_id] = candidate

    provider_competition = provider_meddpicc.get("competition")
    deterministic_competition = deterministic_meddpicc.get("competition")
    meddpicc = {
        key: value for key, value in deterministic_meddpicc.items()
        if key != "competition"
    }
    for code, candidate in provider_meddpicc.items():
        if (
            code != "competition"
            and isinstance(candidate, dict)
            and candidate.get("status") not in (None, "unknown")
        ):
            meddpicc[code] = candidate

    if provider_competition is not None:
        meddpicc["competition"] = provider_competition
    elif deterministic_competition is not None:
        meddpicc["competition"] = deterministic_competition

    return (
        ProfileCandidateSet.model_validate(profile).model_dump(),
        {
            **CoreMeddpiccCandidateSet.model_validate(
                {key: value for key, value in meddpicc.items() if key != "competition"}
            ).model_dump(),
            **({"competition": meddpicc["competition"]} if "competition" in meddpicc else {}),
        },
    )


def validate_candidate_references(
    context: AnalysisContext,
    profile_candidates: dict[str, Any],
    meddpicc_candidates: dict[str, Any],
) -> None:
    valid_ids = {
        str(item.get("evidence_id"))
        for item in context.evidence_refs
        if item.get("evidence_id")
    }
    for field_id, candidate in {**profile_candidates, **meddpicc_candidates}.items():
        invalid = set(candidate.get("evidence_ids") or ()) - valid_ids
        if invalid:
            raise ValueError(
                f"{field_id} references unknown evidence: {', '.join(sorted(invalid))}"
            )

    for field_id, candidate in profile_candidates.items():
        if _has_value(candidate.get("value")) and not candidate.get("evidence_ids"):
            raise ValueError(f"{field_id} has a value without evidence")
        if (
            _has_value(candidate.get("value"))
            and candidate.get("source_kind") in {"exa", "web", "internal_and_web"}
            and not candidate.get("quote")
        ):
            raise ValueError(f"{field_id} has a web value without a supporting quote")
    for code, candidate in meddpicc_candidates.items():
        if candidate.get("status") != "unknown" and not candidate.get("evidence_ids"):
            raise ValueError(f"{code} has a value without evidence")

    contact_candidate = profile_candidates["decision_maker_contact_id"].get("value")
    if contact_candidate:
        known_ids = {
            str(item.get("contact_id") or item.get("id"))
            for item in context.contacts
            if item.get("contact_id") or item.get("id")
        }
        existing_id = context.profile.get("decision_maker_contact_id")
        if existing_id:
            known_ids.add(str(existing_id))
        if str(contact_candidate) not in known_ids:
            raise ValueError("decision_maker_contact_id is not a known contact")


def confirmed_manual_note_updates(
    context: AnalysisContext,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Return newest unambiguous write targets from confirmed manual-note evidence."""
    profile: dict[str, dict[str, Any]] = {}
    meddpicc: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    manual_refs = [
        item
        for item in context.evidence_refs
        if item.get("source_type") == "internal_manual_note"
    ]
    for evidence in reversed(manual_refs):
        metadata = dict(evidence.get("metadata") or {})
        fields = metadata.get("extracted_fields")
        if not isinstance(fields, list):
            continue
        for item in fields:
            if not isinstance(item, dict) or item.get("selected") is False:
                continue
            if str(item.get("action") or "").casefold() in {"keep_original", "保留原值"}:
                continue
            value = item.get("extracted_value", item.get("extracted", item.get("value")))
            if not _has_value(value):
                continue
            target = str(item.get("target_column") or item.get("field_id") or "")
            dimension = str(item.get("dimension_point") or item.get("dimension") or "")
            if target in {"competitor", "competitors"} or any(
                label in dimension for label in ("竞争对手", "竞争态势", "竞对", "竞品", "竞争方案")
            ):
                target = "competition"
            target_table = str(item.get("target_table") or "")
            target_version = item.get("target_version")
            current_value = _current_value(context, target, dimension)
            conflict_reason = _manual_note_conflict_reason(
                target=target,
                dimension=dimension,
                target_version=target_version,
                current_value=current_value,
                proposed_value=str(value),
            )
            update = {
                "value": str(value),
                "evidence": evidence,
                "target_version": int(target_version) if isinstance(target_version, int) else None,
                "confidence": float(item.get("confidence") or 1.0),
            }
            if conflict_reason is not None:
                conflicts.append(
                    {
                        "target": target or dimension,
                        "dimension": dimension or target,
                        "proposed_value": str(value),
                        "current_value": current_value,
                        "target_version": int(target_version) if isinstance(target_version, int) else None,
                        "evidence_id": str(evidence.get("evidence_id") or ""),
                        "reason": conflict_reason,
                    }
                )
            if target in CORE_PROFILE_FIELDS and target != "decision_maker_contact_id":
                profile.setdefault(target, update)
                continue
            if (target in CORE_MEDDPICC_FIELDS or target == "competition") and (
                target_table in {"", "customer_meddpicc_dimension", "ltc.customer_meddpicc_dimension"}
            ):
                meddpicc.setdefault(target, update)
                continue
            for alias, field_id in _LEGACY_PROFILE_ALIASES:
                if alias in dimension:
                    profile.setdefault(field_id, update)
                    break
            if any(label in dimension for label in ("技术痛点", "业务痛点", "痛点识别")):
                meddpicc.setdefault("identify_pain", update)
    return profile, meddpicc, conflicts


def _first(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if _has_value(value):
                return value
    return None


def _employee_scale(context: AnalysisContext) -> str | None:
    explicit = _first(
        context.profile,
        context.company,
        context.sales_lead,
        context.adopted_scale,
        keys=("employee_scale", "employee_range"),
    )
    if explicit:
        return str(explicit)
    count = _first(
        context.company,
        context.sales_lead,
        context.adopted_scale,
        keys=("employee_count", "employees", "headcount"),
    )
    if count is None:
        return None
    match = re.search(r"\d+", str(count).replace(",", ""))
    if not match:
        return str(count)
    number = int(match.group())
    if number <= 50:
        return "1-50 人"
    if number <= 200:
        return "51-200 人"
    if number <= 500:
        return "201-500 人"
    if number <= 2000:
        return "501-2000 人"
    return "2000+ 人"


def _decision_maker_contact_id(context: AnalysisContext) -> str | None:
    existing = context.profile.get("decision_maker_contact_id")
    if existing:
        return str(existing)
    for contact in context.contacts:
        role = " ".join(
            str(contact.get(key) or "")
            for key in ("role", "title", "job_title", "seniority")
        )
        if re.search(r"decision|buyer|owner|head|director|vp|chief|负责人|总监|采购", role, re.I):
            contact_id = contact.get("contact_id") or contact.get("id")
            if contact_id:
                try:
                    return str(UUID(str(contact_id)))
                except ValueError:
                    continue
    return None


def _has_value(value: Any) -> bool:
    return value not in (None, "", "待确认", "待分析", [], {})


def _text_or_none(value: Any) -> str | None:
    return str(value) if _has_value(value) else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if _has_value(item)]
    return [str(value)] if _has_value(value) else []


_LEGACY_PROFILE_ALIASES: tuple[tuple[str, str], ...] = (
    ("预算区间", "budget_text"),
    ("决策人角色", "decision_maker_text"),
    ("决策人", "decision_maker_text"),
    ("公司规模", "employee_scale"),
    ("行业细分", "company_type"),
    ("行业", "company_type"),
    ("合规/认证需求", "compliance"),
    ("合规", "compliance"),
)


def _engagement_candidates(
    context: AnalysisContext,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    profile: dict[str, dict[str, Any]] = {}
    meddpicc: dict[str, dict[str, Any]] = {}
    ranked: dict[tuple[str, str], tuple[int, str]] = {}
    for evidence in context.evidence_refs:
        source_type = str(evidence.get("source_type") or "")
        metadata = dict(evidence.get("metadata") or {})
        direction = str(metadata.get("direction") or "")
        if source_type == "internal_email" and direction != "inbound":
            continue
        if source_type not in {"internal_email", "internal_manual_note", "internal_meeting"}:
            continue
        priority = 3 if source_type in {"internal_manual_note", "internal_meeting"} else 2
        occurred_at = str(evidence.get("occurred_at") or "")
        evidence_id = str(evidence.get("evidence_id") or "")
        text = str(evidence.get("text") or "")
        extracted = _manual_extracted_candidates(metadata) if source_type == "internal_manual_note" else {}
        semantic_profile, semantic_meddpicc = _semantic_candidates(text)
        extracted.update({key: value for key, value in semantic_profile.items() if key not in extracted})
        extracted_meddpicc = {
            key: value
            for key, value in extracted.items()
            if key in CORE_MEDDPICC_FIELDS or key == "competition"
        }

        for field_id, value in extracted.items():
            if field_id not in CORE_PROFILE_FIELDS or not _has_value(value):
                continue
            key = ("profile", field_id)
            if _wins_candidate(ranked.get(key), priority, occurred_at):
                ranked[key] = (priority, occurred_at)
                profile[field_id] = _profile_candidate(
                    value, evidence_id, text, source_type
                )
        for code, value in {**semantic_meddpicc, **extracted_meddpicc}.items():
            if (code not in CORE_MEDDPICC_FIELDS and code != "competition") or not _has_value(value):
                continue
            key = ("meddpicc", code)
            if _wins_candidate(ranked.get(key), priority, occurred_at):
                ranked[key] = (priority, occurred_at)
                meddpicc[code] = _meddpicc_candidate(
                    code, value, evidence_id, text, source_type
                )
    return profile, meddpicc


def _manual_extracted_candidates(metadata: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    fields = metadata.get("extracted_fields")
    if not isinstance(fields, list):
        return result
    for item in fields:
        if not isinstance(item, dict) or item.get("selected") is False:
            continue
        if str(item.get("action") or "").casefold() in {"keep_original", "保留原值"}:
            continue
        value = item.get("extracted_value", item.get("extracted", item.get("value")))
        if not _has_value(value):
            continue
        target = str(item.get("target_column") or item.get("field_id") or "")
        dimension = str(item.get("dimension_point") or item.get("dimension") or "")
        if target in {"competitor", "competitors"} or any(
            label in dimension for label in ("竞争对手", "竞争态势", "竞对", "竞品", "竞争方案")
        ):
            target = "competition"
        if target in CORE_PROFILE_FIELDS:
            result[target] = str(value)
            continue
        if target == "competition":
            result[target] = str(value)
            continue
        for alias, field_id in _LEGACY_PROFILE_ALIASES:
            if alias in dimension:
                result[field_id] = str(value)
                break
        if any(label in dimension for label in ("竞争对手", "竞争态势", "竞对", "竞品", "竞争方案")):
            result["competition"] = str(value)
        if "时间紧迫度" in dimension or "决策速度" in dimension:
            result["decision_cycle_text"] = str(value)
    return result


def _semantic_candidates(
    text: str,
) -> tuple[dict[str, str], dict[str, str]]:
    profile: dict[str, str] = {}
    meddpicc: dict[str, str] = {}
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return profile, meddpicc

    budget = re.search(
        r"(?:预算|价格上限|费用)[^。；\n]{0,24}?([0-9]+(?:\.[0-9]+)?\s*(?:万|千|百万)?\s*(?:美元|美金|元|人民币|USD|CNY))",
        compact,
        re.I,
    )
    if budget:
        profile["budget_text"] = budget.group(1).strip()
    cycle = re.search(
        r"(?:希望|计划|预计|目标|需要)?[^。；\n]{0,16}?((?:\d{1,2}\s*月|Q[1-4]|第[一二三四]季度|上半年|下半年|年底前)[^。；\n]{0,24})",
        compact,
        re.I,
    )
    if cycle:
        profile["decision_cycle_text"] = cycle.group(1).strip()
    integration = re.search(r"\b(API|Portal)\b|门户接入|手动接入", compact, re.I)
    if integration:
        profile["integration"] = integration.group(0)
    compliance = re.search(
        r"(?:GDPR|SOC\s*2|ISO\s*27001|数据驻留|隐私合规|合规认证|认证要求)", compact, re.I
    )
    if compliance:
        profile["compliance"] = compliance.group(0)
    usage = re.search(
        r"([0-9]+(?:\.[0-9]+)?\s*(?:万|千)?\s*(?:用户|人|张卡|GB|TB|订单|设备))",
        compact,
        re.I,
    )
    if usage:
        profile["estimated_usage"] = usage.group(1).strip()
        meddpicc["metrics"] = usage.group(1).strip()

    pain_sentence = _sentence_with(compact, ("痛点", "问题", "困难", "不满", "受限", "瓶颈"))
    if pain_sentence:
        meddpicc["identify_pain"] = pain_sentence
    process_sentence = _sentence_with(compact, ("审批流程", "采购流程", "法务审核", "合同审批"))
    if process_sentence:
        meddpicc["decision_process"] = process_sentence
    competition = _sentence_with(compact, ("竞争对手", "竞对", "对标", "竞品", "竞争方案"))
    if competition:
        names = _competitor_names(competition)
        if names:
            meddpicc["competition"] = "、".join(names[:3])
    buyer = re.search(
        r"([^，。；\n]{0,24}(?:CFO|CEO|财务负责人|采购负责人|[\u4e00-\u9fff]{2,4}(?:经理|总监))[^，。；\n]{0,24}(?:预算审批|审批预算|最终审批|负责预算)[^，。；\n]{0,16})",
        compact,
        re.I,
    ) or re.search(
        r"([^，。；\n]{0,24}(?:预算审批|审批预算|最终审批|负责预算)[^，。；\n]{0,24}(?:CFO|CEO|财务负责人|采购负责人|[\u4e00-\u9fff]{2,4}(?:经理|总监))[^，。；\n]{0,16})",
        compact,
        re.I,
    )
    if buyer:
        meddpicc["economic_buyer"] = buyer.group(1).strip()
    return profile, meddpicc


def _sentence_with(text: str, keywords: tuple[str, ...]) -> str | None:
    for sentence in re.split(r"[。；\n]", text):
        if any(keyword in sentence for keyword in keywords):
            return sentence.strip()[:300]
    return None


def _competitor_names(text: str) -> list[str]:
    match = re.search(
        r"(?:\u7ade\u4e89\u5bf9\u624b(?:\u662f|\u4e3a|\u6709|\u5305\u62ec)?|\u7ade\u5bf9(?:\u662f|\u4e3a|\u6709|\u5305\u62ec)?|\u5bf9\u6807(?:\u662f|\u4e3a)?|\u7ade\u54c1(?:\u662f|\u4e3a|\u6709|\u5305\u62ec)?)[\uff1a:\u662f\u4e3a]*\s*([^\u3002\uff1b;\n]+)",
        text,
        re.I,
    )
    segment = match.group(1) if match else text
    names: list[str] = []
    for item in re.split(r"[\u3001\uff0c,/|\u548c\u4e0e\u53ca\xb7]+", segment):
        candidate = re.sub(
            r"^(?:\u5ba2\u6237\u5f53\u524d\u4e5f\u5728|\u5ba2\u6237\u4e5f\u5728|\u5f53\u524d\u4e5f\u5728|\u4e5f\u5728|\u8fd8\u5728|\u6b63\u5728|\u8fdb\u884c|\u5bf9\u6bd4|\u6bd4\u8f83|\u5173\u6ce8|\u8003\u8651|\u4e3b\u8981|\u5305\u62ec|\u6709|\u662f|\u4e3a)\s*",
            "",
            item.strip(),
        )
        candidate = candidate.strip(" \u3002\uff1b;:\uff1a")
        if candidate and len(candidate) <= 30:
            names.append(candidate)
    if names:
        return names
    match = re.search(
        r"(?:竞争对手(?:是|为|有|包括)?|竞对(?:是|为|有|包括)?|对标(?:是|为)?|竞品(?:是|为|有|包括)?)[：:是为]*\s*([^。；;\n]+)",
        text,
        re.I,
    )
    segment = match.group(1) if match else text
    names: list[str] = []
    for item in re.split(r"[、，,/|和与及·]+", segment):
        candidate = re.sub(
            r"^(?:客户当前也在|客户也在|当前也在|也在|还在|正在|进行|对比|比较|关注|考虑|主要|包括|有|是|为)\s*",
            "",
            item.strip(),
        )
        candidate = candidate.strip(" 。；;:：")
        if candidate and len(candidate) <= 30:
            names.append(candidate)
    return names


def _current_value(context: AnalysisContext, target: str, dimension: str) -> str | None:
    if target in CORE_PROFILE_FIELDS:
        value = context.profile.get(target)
        return str(value) if _has_value(value) else None
    if target in CORE_MEDDPICC_FIELDS:
        current = context.meddpicc.get(target)
        if isinstance(current, dict):
            value = current.get("summary") or current.get("payload", {}).get("value")
            return str(value) if _has_value(value) else None
    for alias, field_id in _LEGACY_PROFILE_ALIASES:
        if alias in dimension:
            value = context.profile.get(field_id)
            return str(value) if _has_value(value) else None
    return None


def _manual_note_conflict_reason(
    *,
    target: str,
    dimension: str,
    target_version: Any,
    current_value: str | None,
    proposed_value: str,
) -> str | None:
    if not _has_value(proposed_value):
        return None
    if target_version is None:
        return "missing_target_version"
    if current_value is None:
        return "missing_current_value"
    if str(current_value).strip() == str(proposed_value).strip():
        return None
    return "value_differs_from_current"


def _wins_candidate(
    current: tuple[int, str] | None, priority: int, occurred_at: str
) -> bool:
    return current is None or priority > current[0] or (
        priority == current[0] and occurred_at >= current[1]
    )


def _profile_candidate(
    value: str, evidence_id: str, text: str, source_type: str
) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": 0.95 if source_type == "internal_manual_note" else 0.85,
        "evidence_ids": [evidence_id],
        "quote": text[:500] or value,
        "reason": "来自已确认销售记录" if source_type == "internal_manual_note" else "来自客户入站邮件",
        "missing_reason": None,
        "source_kind": "internal",
    }


def _meddpicc_candidate(
    code: str, value: str, evidence_id: str, text: str, source_type: str
) -> dict[str, Any]:
    return {
        "status": "confirmed" if source_type == "internal_manual_note" else "partial",
        "summary": value,
        "detail": text[:500] or value,
        "metric": value if code == "metrics" else None,
        "actors": [value] if code == "economic_buyer" else [],
        "process_steps": [value] if code == "decision_process" else [],
        "next_question": None,
        "risk": None,
        "confidence": 0.95 if source_type == "internal_manual_note" else 0.85,
        "evidence_ids": [evidence_id],
        "missing_reason": None,
    }
