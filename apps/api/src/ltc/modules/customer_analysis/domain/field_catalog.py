"""Canonical core-field catalog shared by analysis, APIs, and the UI."""

from __future__ import annotations

from typing import Any, Final


CORE_PROFILE_FIELDS: Final[tuple[str, ...]] = (
    "company_type",
    "business_model",
    "employee_scale",
    "region_text",
    "esim_scenario",
    "coverage",
    "estimated_usage",
    "integration",
    "compliance",
    "budget_text",
    "decision_maker_text",
    "decision_maker_contact_id",
    "decision_cycle_text",
)

CORE_MEDDPICC_FIELDS: Final[tuple[str, ...]] = (
    "metrics",
    "economic_buyer",
    "decision_process",
    "identify_pain",
)

FIELD_COLLECTION_GUIDANCE: Final[dict[str, tuple[str, str]]] = {
    "company_type": ("public_or_internal", "可通过官网、工商资料或内部客户资料补齐。"),
    "business_model": ("public_or_internal", "可通过官网产品与商业介绍补齐，仍需销售确认是否适用于当前机会。"),
    "employee_scale": ("public_or_internal", "可通过公开员工数据或内部客户资料补齐；来源冲突时需要人工确认。"),
    "region_text": ("public_or_internal", "可通过官网地址、服务区域或内部客户资料补齐。"),
    "esim_scenario": ("sales_confirmation", "公开信息通常无法证明该客户的真实 eSIM 使用场景，需要销售访谈确认。"),
    "coverage": ("public_or_internal", "可通过官网业务区域推断候选值，实际项目覆盖范围仍需销售确认。"),
    "estimated_usage": ("sales_confirmation", "预估用量属于商机内部信息，需要销售询问用户数、国家和月度峰值。"),
    "integration": ("public_or_internal", "可检索公开集成能力，但本项目的目标系统和接口范围需要技术访谈确认。"),
    "compliance": ("public_or_internal", "可检索公开认证与隐私声明，项目特定合规要求需要客户确认。"),
    "budget_text": ("sales_confirmation", "预算通常不会公开，需要销售向经济决策者或采购负责人确认。"),
    "decision_maker_text": ("sales_confirmation", "公开职位不能证明当前商机决策权，需要销售确认真实决策角色。"),
    "decision_maker_contact_id": ("sales_confirmation", "需要从已核实联系人中指定当前商机的经济决策者。"),
    "decision_cycle_text": ("sales_confirmation", "采购与决策周期属于内部流程，需要销售访谈或 CRM 记录补齐。"),
    "metrics": ("sales_confirmation", "公开指标只能作为参考，当前商机的基线与目标需要销售量化确认。"),
    "economic_buyer": ("sales_confirmation", "经济决策者必须结合当前预算归属和审批权由销售确认。"),
    "decision_process": ("sales_confirmation", "决策步骤、参与人和时间节点需要销售访谈确认。"),
    "identify_pain": ("sales_confirmation", "公开资料只能形成痛点假设，真实痛点、影响和优先级需要客户确认。"),
}

CORE_FIELD_GROUPS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "D1",
        "label": "公司与业务",
        "fields": (
            ("company_type", "公司类型", "profile"),
            ("business_model", "业务模式", "profile"),
            ("employee_scale", "员工规模", "profile"),
            ("region_text", "所属区域", "profile"),
        ),
    },
    {
        "id": "D2",
        "label": "场景与方案",
        "fields": (
            ("esim_scenario", "eSIM 使用场景", "profile"),
            ("coverage", "覆盖区域", "profile"),
            ("estimated_usage", "预估用量", "profile"),
            ("integration", "集成方式", "profile"),
            ("compliance", "合规要求", "profile"),
        ),
    },
    {
        "id": "D3",
        "label": "商务与决策",
        "fields": (
            ("budget_text", "预算信息", "profile"),
            ("decision_maker_text", "决策人描述", "profile"),
            ("decision_maker_contact_id", "决策人联系人", "profile"),
            ("decision_cycle_text", "决策周期", "profile"),
        ),
    },
    {
        "id": "D4",
        "label": "MEDDPICC 高频维度",
        "fields": (
            ("metrics", "量化指标", "meddpicc"),
            ("economic_buyer", "经济决策者", "meddpicc"),
            ("decision_process", "决策流程", "meddpicc"),
            ("identify_pain", "痛点识别", "meddpicc"),
        ),
    },
)


def field_catalog_payload() -> dict[str, Any]:
    return {
        "version": "core-field-catalog-v1",
        "profile_field_count": len(CORE_PROFILE_FIELDS),
        "core_field_count": len(CORE_PROFILE_FIELDS) + len(CORE_MEDDPICC_FIELDS),
        "groups": [
            {
                "id": group["id"],
                "label": group["label"],
                "fields": [
                    {
                        "id": field_id,
                        "label": label,
                        "target_type": target_type,
                        "collection_method": FIELD_COLLECTION_GUIDANCE[field_id][0],
                        "missing_guidance": FIELD_COLLECTION_GUIDANCE[field_id][1],
                    }
                    for field_id, label, target_type in group["fields"]
                ],
            }
            for group in CORE_FIELD_GROUPS
        ],
    }


def catalog_entries() -> list[dict[str, str]]:
    return [
        {
            "group_id": str(group["id"]),
            "group_label": str(group["label"]),
            "field_id": field_id,
            "label": label,
            "target_type": target_type,
            "collection_method": FIELD_COLLECTION_GUIDANCE[field_id][0],
            "missing_guidance": FIELD_COLLECTION_GUIDANCE[field_id][1],
        }
        for group in CORE_FIELD_GROUPS
        for field_id, label, target_type in group["fields"]
    ]
