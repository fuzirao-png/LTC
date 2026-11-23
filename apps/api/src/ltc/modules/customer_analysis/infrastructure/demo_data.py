"""Small, local demo dataset used by the compatibility API.

The dataset is intentionally owned by the migrated module.  It is not loaded
from the legacy service and can be replaced by a CRM/context port in runtime.
"""

from __future__ import annotations

from uuid import UUID, uuid5

from ltc.modules.customer_analysis.domain.models import AnalysisContext


DEMO_CLIENTS = (
    ("e533d9c4-8750-4fb8-92ed-24fc7284f050", "2SkyMobile", 88.25, "interested"),
    ("d945ea9d-c560-4ca0-99af-89c2da60d41b", "AGrandTech Limited", 75.75, "product_question"),
    ("103e233f-14af-40be-821e-c757e9a1af74", "Asmote Technology", 55.0, "unknown"),
)

_SHORT_CLIENTS = (
    ("globallink", "GlobalLink Travel", 84.0, "interested"),
    ("pacific", "Pacific TMC Japan", 73.0, "product_question"),
    ("sakura", "Sakura Travel Corp", 79.0, "interested"),
    ("nagoya", "Nagoya Business Travel", 58.0, "unknown"),
    ("techtravel", "TechTravel Inc.", 68.0, "product_question"),
)


def client_uuid(client_id: str) -> UUID:
    try:
        return UUID(client_id)
    except ValueError:
        return uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), client_id)


def _context(client_id: str, name: str, score: float, intent: str) -> AnalysisContext:
    is_high = score >= 85
    is_mid = score >= 70
    profile = {
        "company_type": "全球电信基础设施 / eSIM批发平台" if is_high else "通信技术与企业连接方案提供商" if is_mid else "无线技术与行业专网厂商",
        "region_text": "全球业务覆盖，重点面向跨境连接与国际流量分发" if is_high else "亚太与国际技术合作场景" if is_mid else "以国内行业项目为主，区域信息有限",
        "employee_scale": "500-2000" if is_high else "200-500" if is_mid else "100-500",
        "business_model": "全球 eSIM 基础设施、批发移动数据、白标商店和移动数据 API" if is_high else "5GC、MEC 与企业连接技术解决方案" if is_mid else "无线技术与行业专网终端能力",
        "esim_scenario": "跨境企业连接、白标通信能力嵌入和渠道分销" if is_high else "企业专网连接、边缘通信能力集成" if is_mid else "企业连接场景仍待确认",
        "coverage": "全球多国家覆盖" if is_high else "亚太及国际展会合作场景" if is_mid else "国内行业场景",
        "estimated_usage": "中高频批量开通与统一管理" if is_high else "中频项目制交付" if is_mid else "低到中频项目机会待确认",
        "integration": "移动数据 API、Web/App 商店和白标接入" if is_high else "平台级技术对接和行业方案集成" if is_mid else "集成要求待确认",
        "compliance": "跨境数据留存、API 审计和账户权限隔离" if is_high else "日志留存、网络安全和交付边界" if is_mid else "基础交付合规与资料留痕",
        "budget_text": "$12,000/年" if is_high else "预算方向已确认，金额待审批" if is_mid else "待确认",
        "decision_maker_text": "Mila Hart" if is_high else "Jason Lee" if is_mid else "待确认",
        "decision_cycle_text": "2-3周" if is_high else "4-6周" if is_mid else "待确认",
    }
    pain = (
        "批发和白标业务增长较快，缺少统一的企业级管理与接入能力"
        if is_high else "需要更完整的通信技术方案提升市场竞争力"
        if is_mid else "尚未形成清晰的业务痛点和采购闭环"
    )
    company_id = client_uuid(client_id)
    return AnalysisContext(
        company_id=company_id,
        company={
            "company_id": client_id,
            "company_name": name,
            "industry": profile["company_type"],
            "city": "待确认" if client_id in {item[0] for item in DEMO_CLIENTS} else "Tokyo",
            "country": "未知" if client_id in {item[0] for item in DEMO_CLIENTS} else "Japan",
            "website": f"https://{client_id}.example.com",
        },
        sales_lead={"stage": "qualified" if score >= 70 else "new", "status": "active", "signals": {"has_reply": score >= 70, "has_contact": True, "follow_up_count": 4 if is_high else 2, "last_interaction_days": 2 if is_high else 8}},
        adopted_icp={"total_score": score, "grade": "A" if is_high else "B" if is_mid else "C"},
        adopted_scale={"scale_code": "enterprise" if score >= 70 else "mid_market", "score": score},
        contacts=(
            {"contact_id": f"{client_id}-buyer", "name": profile["decision_maker_text"], "title": "Decision owner"},
            {"contact_id": f"{client_id}-technical", "name": f"{name} Technical", "title": "Technical evaluator"},
        ) if client_id in {"globallink", "e533d9c4-8750-4fb8-92ed-24fc7284f050"} else (
            {"contact_id": f"{client_id}-buyer", "name": profile["decision_maker_text"], "title": "Decision owner"},
        ),
        engagement={"intent_level": intent, "latest_summary": f"{name} 最近沟通聚焦试点范围、集成方式与采购路径。"},
        profile=profile,
        meddpicc={
            "metrics": {"status": "confirmed" if is_high else "partial", "summary": "需求规模和 ROI 需要继续量化"},
            "economic_buyer": {"status": "partial", "summary": f"预算负责人：{profile['decision_maker_text']}"},
            "decision_criteria": {"status": "confirmed" if is_high else "partial", "summary": "覆盖、集成复杂度、稳定性和交付成本"},
            "decision_process": {"status": "partial", "summary": "技术评估后进入商务和法务确认"},
            "paper_process": {"status": "unknown", "summary": "合同与 SLA 条款待确认"},
            "identify_pain": {"status": "confirmed" if is_high else "partial", "summary": pain},
            "champion": {"status": "partial", "summary": "技术联系人已识别，业务 Champion 待建立"},
            "competition": {"status": "partial", "summary": "区域连接供应商、运营商批发方案和内部建设"},
        },
        evidence_refs=({"url": f"https://{client_id}.example.com/source", "title": f"{name} source"},),
    )


def demo_contexts() -> tuple[AnalysisContext, ...]:
    rows = (*DEMO_CLIENTS, *_SHORT_CLIENTS)
    return tuple(_context(*row) for row in rows)

