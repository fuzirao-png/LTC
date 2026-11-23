from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Any, Iterable


RANKING_VERSION = "contact-top5-v2"


@dataclass(frozen=True)
class ScoredContact:
    contact: dict[str, Any]
    role_group: str
    seniority_level: str
    score: float
    breakdown: dict[str, float]
    reasons: tuple[str, ...]
    eligible: bool
    blocked_reason: str | None = None


def score_contact(
    contact: dict[str, Any],
    *,
    now: datetime | None = None,
    employee_count: int | None = None,
    scene_text: str = "",
    allow_any_email_status: bool = False,
) -> ScoredContact:
    current_time = now or datetime.now(timezone.utc)
    title = _text(contact.get("title") or contact.get("title_normalized")).casefold()
    department = _text(contact.get("department")).casefold()
    combined = " ".join((title, department))
    role_group, role_base, role_reason = _role_score(title)
    seniority_level, seniority_points = _seniority_score(title)

    scene_points = 0.0
    if any(_contains_term(combined, term) for term in _SCENE_TERMS):
        scene_points = 15.0
    elif role_group in {"procurement", "commercial", "business", "technical", "product", "operations"}:
        scene_points = 8.0

    email = _text(contact.get("primary_email") or contact.get("email"))
    email_status = _text(contact.get("email_status") or "unknown").casefold()
    linkedin = _text(contact.get("linkedin_url"))
    if email and email_status == "valid":
        channel_points = 10.0
    elif email:
        channel_points = 6.0
    elif linkedin:
        channel_points = 3.0
    else:
        channel_points = 0.0

    freshness_reference = _datetime_value(
        contact.get("last_verified_at")
        or contact.get("source_last_seen_at")
        or contact.get("updated_at")
    )
    age_days = (current_time - freshness_reference).days if freshness_reference else None
    if age_days is None:
        freshness_points = 0.0
    elif age_days <= 90:
        freshness_points = 5.0
    elif age_days <= 183:
        freshness_points = 3.0
    elif age_days <= 365:
        freshness_points = 1.0
    else:
        freshness_points = 0.0

    if contact.get("has_reply") or contact.get("has_meeting"):
        interaction_points = 5.0
    elif contact.get("has_open") or contact.get("has_click"):
        interaction_points = 3.0
    else:
        interaction_points = 0.0

    risk = 0.0
    risk_reasons: list[str] = []
    if email and email.split("@", 1)[0].casefold() in _GENERIC_MAILBOXES:
        risk += 12.0
        risk_reasons.append("通用邮箱")
    if email and email_status not in {"valid", "invalid", "bounced", "opted_out"}:
        risk += 15.0
        risk_reasons.append("邮箱未验证")
    if age_days is None or age_days > 365:
        risk += 10.0
        risk_reasons.append("数据超过一年或缺少验证时间")

    company_size_bonus = 0.0
    if role_group == "executive" and employee_count is not None and employee_count < 200:
        company_size_bonus = 6.0

    breakdown = {
        "role_relevance": round(role_base / 100 * 45, 2),
        "seniority": seniority_points,
        "scene_relevance": scene_points,
        "contact_quality": channel_points,
        "freshness": freshness_points,
        "interaction": interaction_points,
        "company_size_bonus": company_size_bonus,
        "risk_deduction": risk,
        "diversity_deduction": 0.0,
    }
    total = max(0.0, min(100.0, sum(value for key, value in breakdown.items() if key not in {"risk_deduction", "diversity_deduction"}) - risk))

    blocked_reason = _blocked_reason(contact, email_status, allow_any_email_status=allow_any_email_status)
    reasons = [role_reason, f"{seniority_level}级别"]
    if scene_points == 15:
        reasons.append("职责与LTC场景直接相关")
    if interaction_points == 5:
        reasons.append("已有回复或参会")
    reasons.extend(risk_reasons)
    if blocked_reason:
        reasons.append(blocked_reason)

    return ScoredContact(
        contact=contact,
        role_group=role_group,
        seniority_level=seniority_level,
        score=round(total, 2),
        breakdown=breakdown,
        reasons=tuple(reasons),
        eligible=blocked_reason is None,
        blocked_reason=blocked_reason,
    )


def select_top_contacts(scored_contacts: Iterable[ScoredContact], limit: int = 5) -> list[ScoredContact]:
    candidates = [
        item for item in scored_contacts
        if item.eligible and _has_email(item.contact)
    ]
    selected: list[ScoredContact] = []

    locked = sorted(
        (item for item in candidates if item.contact.get("is_pinned") or item.contact.get("engagement_locked")),
        key=lambda item: (_position(item.contact), -item.score),
    )
    for item in locked:
        if len(selected) >= limit:
            break
        selected.append(item)

    role_slots: tuple[tuple[str, ...], ...] = (
        ("procurement",),
        ("commercial",),
        ("business",),
        ("technical",),
        ("product", "operations", "finance_legal", "executive", "other"),
    )
    for groups in role_slots:
        if len(selected) >= limit or any(item.role_group in groups for item in selected):
            continue
        match = _best_candidate(candidates, selected, groups)
        if match:
            selected.append(match)

    while len(selected) < limit:
        match = _best_candidate(candidates, selected, None)
        if not match:
            break
        selected.append(match)

    return [_apply_diversity_penalty(item, selected[:index]) for index, item in enumerate(selected)]


def _best_candidate(
    candidates: list[ScoredContact],
    selected: list[ScoredContact],
    groups: tuple[str, ...] | None,
) -> ScoredContact | None:
    selected_ids = {_contact_id(item.contact) for item in selected}
    available = [
        item for item in candidates
        if _contact_id(item.contact) not in selected_ids and (groups is None or item.role_group in groups)
    ]
    available.sort(key=lambda item: item.score, reverse=True)
    return next((item for item in available if _passes_diversity(item, selected)), None)


def _passes_diversity(candidate: ScoredContact, selected: list[ScoredContact]) -> bool:
    department = _text(candidate.contact.get("department")).casefold()
    if department and sum(_text(item.contact.get("department")).casefold() == department for item in selected) >= 2:
        return False
    normalized_title = _text(candidate.contact.get("title_normalized") or candidate.contact.get("title")).casefold()
    if normalized_title and any(
        _text(item.contact.get("title_normalized") or item.contact.get("title")).casefold() == normalized_title
        and item.seniority_level == candidate.seniority_level
        for item in selected
    ):
        return False
    return True


def _apply_diversity_penalty(candidate: ScoredContact, selected: list[ScoredContact]) -> ScoredContact:
    same_function_level = any(
        item.role_group == candidate.role_group and item.seniority_level == candidate.seniority_level
        for item in selected
    )
    if not same_function_level:
        return candidate
    breakdown = dict(candidate.breakdown)
    breakdown["diversity_deduction"] = 8.0
    return replace(
        candidate,
        score=round(max(0.0, candidate.score - 8.0), 2),
        breakdown=breakdown,
        reasons=(*candidate.reasons, "同职能同级别多样性扣分"),
    )


def _blocked_reason(
    contact: dict[str, Any],
    email_status: str,
    *,
    allow_any_email_status: bool = False,
) -> str | None:
    if not _text(contact.get("primary_email") or contact.get("email")):
        return "联系人缺少邮箱"
    if _text(contact.get("status") or "active").casefold() != "active":
        return "联系人非活跃状态"
    if _text(contact.get("employment_status") or "unknown").casefold() == "departed":
        return "联系人已离职"
    if _text(contact.get("legal_basis_status") or "unknown").casefold() == "blocked":
        return "缺少合法触达依据"
    if contact.get("is_suppressed"):
        return "邮箱已进入全局抑制名单"
    if not allow_any_email_status and email_status in {"invalid", "bounced", "opted_out"}:
        return "邮箱退信、退订或无效"
    return None


def _role_score(title: str) -> tuple[str, float, str]:
    rules = (
        ("procurement", ("cpo", "vp procurement", "采购副总裁"), 98.0, "采购决策人"),
        ("procurement", ("procurement director", "head of procurement", "采购总监", "采购负责人"), 95.0, "采购负责人"),
        ("procurement", ("procurement manager", "purchasing manager", "sourcing manager", "采购经理"), 92.0, "采购经理"),
        ("commercial", ("chief commercial officer", "vp commercial", "vp partnerships"), 90.0, "商务决策人"),
        ("commercial", ("commercial director", "bd director", "head of partnerships", "商务总监", "商务负责人"), 88.0, "商务负责人"),
        ("commercial", ("business manager", "bd manager", "partnerships manager", "商务经理"), 85.0, "商务经理"),
        ("business", ("bu head", "general manager", "vp international", "事业部负责人", "海外业务负责人"), 87.0, "业务负责人"),
        ("technical", ("cto", "cio", "vp engineering", "vp technology", "首席技术官"), 84.0, "技术决策人"),
        ("technical", ("it director", "engineering director", "head of architecture", "技术负责人", "架构负责人"), 80.0, "技术负责人"),
        ("product", ("vp product", "product director", "head of product", "产品负责人"), 80.0, "产品负责人"),
        ("operations", ("operations manager", "operation manager", "运营经理"), 72.0, "运营负责人"),
        ("product", ("product manager", "产品经理"), 72.0, "产品经理"),
        ("finance_legal", ("cfo", "finance director", "legal director", "财务总监", "法务总监"), 68.0, "财务或法务负责人"),
        ("executive", ("ceo", "founder", "president", "首席执行官", "创始人", "总裁"), 82.0, "高层负责人"),
    )
    for group, terms, base, reason in rules:
        if any(_contains_term(title, term) for term in terms):
            return group, base, reason
    if any(_contains_term(title, term) for term in ("vp", "vice president", "副总裁")):
        return "business", 74.0, "待补充职能的VP"
    if any(_contains_term(title, term) for term in ("specialist", "coordinator", "assistant", "专员", "助理")):
        return "other", 45.0, "信息提供者"
    if any(_contains_term(title, term) for term in ("hr", "human resources", "marketing", "administration", "人力", "市场", "行政")):
        return "other", 20.0, "非首轮触达部门"
    return "other", 50.0, "职位待进一步归类"


def _seniority_score(title: str) -> tuple[str, float]:
    if any(_contains_term(title, term) for term in ("chief", "cto", "cio", "cfo", "ceo", "vp", "vice president", "总裁", "首席", "副总裁")):
        return "c_level_vp", 20.0
    if any(_contains_term(title, term) for term in ("director", "head", "总监", "负责人", "部长")):
        return "director_head", 16.0
    if any(_contains_term(title, term) for term in ("manager", "经理", "主管")):
        return "manager", 12.0
    return "other", 6.0


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _position(contact: dict[str, Any]) -> int:
    try:
        return int(contact.get("position") or 99)
    except (TypeError, ValueError):
        return 99


def _contact_id(contact: dict[str, Any]) -> str:
    return _text(contact.get("contact_id"))


def _contains_term(text: str, term: str) -> bool:
    if term.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _has_email(contact: dict[str, Any]) -> bool:
    return bool(_text(contact.get("primary_email") or contact.get("email")))


_SCENE_TERMS = (
    "esim", "e-sim", "telecom", "telecommunications", "通信", "差旅",
    "travel", "cross-border", "跨境", "api", "partnership", "合作",
)

_GENERIC_MAILBOXES = {"info", "sales", "contact", "support", "admin", "hello"}
