from __future__ import annotations

from typing import Any

from ltc.modules.customer_operation.application.email_analysis import analyze_inbound_email


class EmailAnalysisSkill:
    name = "email_analysis"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return analyze_inbound_email(
            subject=str(input_data.get("subject") or input_data.get("currentSubject") or ""),
            body_text=str(input_data.get("body") or input_data.get("currentBody") or ""),
            from_email=str(input_data.get("fromEmail") or input_data.get("from_address") or ""),
            attachments=input_data.get("attachments") or [],
        )
