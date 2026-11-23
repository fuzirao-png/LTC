from __future__ import annotations

from typing import Any

from ltc.modules.customer_operation.application.email_agent import run_email_agent_for_payload
from ltc.modules.customer_operation.application.email_delivery_service import send_email_for_payload
from ltc.modules.lead_intelligence.agents.email_outreach_agent.agent import (
    AutoTouchConfig,
    choose_template_details,
    run_email_automation_agent,
)
from ltc.modules.lead_intelligence.infrastructure.email_automation_store import EmailAutomationStore


class EmailAutomationService:
    def __init__(self, store: EmailAutomationStore | None = None) -> None:
        self.store = store or EmailAutomationStore()

    @staticmethod
    def as_payload(config: AutoTouchConfig) -> dict[str, Any]:
        return {
            "enabled": config.enabled,
            "intervalMinutes": config.interval_minutes,
            "minScore": config.min_score,
            "regions": list(config.regions),
            "senderUserId": config.sender_user_id,
            "salesName": config.sales_name,
            "templateSubject": config.template_subject,
            "templateBody": config.template_body,
        }

    def get_config(self) -> dict[str, Any]:
        return self.as_payload(self.store.load_config())

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.as_payload(self.store.save_config(payload))

    def preview(self) -> dict[str, Any]:
        config = self.store.load_config()
        candidates = self.store.find_candidates(config)
        items = []
        for item in candidates:
            template, template_reason = choose_template_details(item)
            items.append(
                {
                    "companyId": item.get("company_id"),
                    "companyName": item.get("company_name"),
                    "contactId": item.get("contact_id"),
                    "contactScore": item.get("contact_score", 0),
                    "contactName": item.get("contact_name"),
                    "recipientEmail": item.get("recipient_email"),
                    "region": item.get("region_code"),
                    "industry": item.get("industry_code"),
                    "icpScore": item.get("icp_score"),
                    "template": template,
                    "templateReason": template_reason,
                }
            )
        companies: dict[str, dict[str, Any]] = {}
        for item in items:
            company = companies.setdefault(item["companyId"], {
                "companyId": item["companyId"],
                "companyName": item["companyName"],
                "region": item["region"],
                "industry": item["industry"],
                "icpScore": item["icpScore"],
                "contacts": [],
            })
            company["contacts"].append(item)
        return {
            "enabled": config.enabled,
            "minScore": config.min_score,
            "regions": list(config.regions),
            "companies": list(companies.values()),
            "totalCompanies": len(companies),
            "totalContacts": len(items),
        }

    def build_config(self, payload: dict[str, Any] | None = None) -> AutoTouchConfig:
        config = self.store.load_config()
        payload = payload or {}
        return AutoTouchConfig(
            enabled=bool(payload.get("enabled", config.enabled)),
            interval_minutes=int(payload.get("intervalMinutes", config.interval_minutes)),
            min_score=float(payload.get("minScore", config.min_score)),
            regions=tuple(str(item).upper() for item in payload.get("regions", config.regions)),
            max_per_run=500,
            selected_contact_ids=tuple(str(item) for item in payload.get("selectedContactIds", [])),
            sender_user_id=str(payload.get("senderUserId") or config.sender_user_id),
            sales_name=str(payload.get("salesName") or config.sales_name),
            template_subject=str(payload.get("templateSubject") or config.template_subject),
            template_body=str(payload.get("templateBody") or config.template_body),
        )

    def enqueue(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.build_config(payload)
        if not config.enabled:
            return {"status": "disabled", "sent": 0, "failed": 0, "skipped": 0}
        run_id = self.store.start_run(config)
        if not run_id:
            return {"status": "already_running", "sent": 0, "failed": 0, "skipped": 0}
        return {"status": "queued", "runId": run_id, "selectedContacts": len(config.selected_contact_ids)}

    async def process_run(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.build_config(payload)
        return await run_email_automation_agent(
            config=config,
            store=self.store,
            email_agent=run_email_agent_for_payload,
            sender=send_email_for_payload,
            run_id=run_id,
        )
    async def run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.store.load_config()
        if payload:
            config = AutoTouchConfig(
                enabled=bool(payload.get("enabled", config.enabled)),
                interval_minutes=int(payload.get("intervalMinutes", config.interval_minutes)),
                min_score=float(payload.get("minScore", config.min_score)),
                regions=tuple(str(item).upper() for item in payload.get("regions", config.regions)),
                max_per_run=500,
                selected_contact_ids=tuple(str(item) for item in payload.get("selectedContactIds", [])),
                sender_user_id=str(payload.get("senderUserId") or config.sender_user_id),
                sales_name=str(payload.get("salesName") or config.sales_name),
                template_subject=str(payload.get("templateSubject") or config.template_subject),
                template_body=str(payload.get("templateBody") or config.template_body),
            )
        return await run_email_automation_agent(
            config=config,
            store=self.store,
            email_agent=run_email_agent_for_payload,
            sender=send_email_for_payload,
        )

    def list_runs(self, limit: int) -> dict[str, Any]:
        return {"items": self.store.list_runs(limit)}

    def list_replies(self, run_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        result = self.store.list_replies(run_id, page, page_size)
        if result is None:
            raise KeyError(run_id)
        return result

    def list_failures(self, run_id: str, page: int = 1, page_size: int = 20, code: str | None = None) -> dict[str, Any]:
        result = self.store.list_failures(run_id, page, page_size, code)
        if result is None:
            raise KeyError(run_id)
        return result
