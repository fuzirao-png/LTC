from __future__ import annotations

import json
import re
from contextlib import closing
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pg8000 import dbapi

from ltc.modules.lead_intelligence.agents.email_outreach_agent.agent import AutoTouchConfig
from ltc.modules.sales_crm.domain.contact_priority import score_contact
from ltc.modules.customer_operation.application.email_analysis import is_automatic_reply
from ltc.platform.config import get_settings


_FAILURE_HINTS = {
    "TRANSLATION_SIGNATURE": "\u5c06 sales_name \u6539\u4e3a\u771f\u4eba\u59d3\u540d",
    "TRANSLATION_INCOMPLETE": "检查翻译结果是否保留 PRD 中的全部段落和关键信息",
    "SMTP_REJECT": "检查收件人地址和 SMTP 服务商的拒收策略",
    "SMTP_CONNECTION": "检查 SMTP 主机、端口、账号配置和网络连接",
    "PROVIDER_ERROR": "检查邮件服务商配置及返回的错误信息",
    "HARD_BOUNCE": "核实收件人邮箱地址是否有效，并移除无效地址",
    "SOFT_BOUNCE": "稍后重试发送，并检查收件箱容量或邮件服务状态",
}


def _failure_code(message: str) -> str:
    text = message.lower()
    if "sales signature" in text:
        return "TRANSLATION_SIGNATURE"
    if "translation" in text and any(word in text for word in ("incomplete", "paragraph", "section")):
        return "TRANSLATION_INCOMPLETE"
    if "recipients refused" in text or "recipient refused" in text or ("smtp" in text and "reject" in text):
        return "SMTP_REJECT"
    if re.search(r"\b5\d\d(?:\s+\d\.\d\.\d+)?\b", text):
        return "SMTP_REJECT"
    if "connection" in text and "smtp" in text:
        return "SMTP_CONNECTION"
    if "provider" in text or "mail service" in text:
        return "PROVIDER_ERROR"
    if "hard bounce" in text:
        return "HARD_BOUNCE"
    if "soft bounce" in text or "bounce" in text:
        return "SOFT_BOUNCE"
    return "UNKNOWN"


def _failure_message(message: str, code: str) -> str:
    text = str(message or "").strip()
    lowered = text.lower()
    if "template translation did not preserve the prd paragraph structure" in lowered:
        return "\u7ffb\u8bd1\u5185\u5bb9\u4e0d\u5b8c\u6574"
    if "template translation did not preserve the contact name" in lowered:
        return "\u7ffb\u8bd1\u672a\u4fdd\u7559\u8054\u7cfb\u4eba\u59d3\u540d"
    if "template translation did not preserve the sales signature" in lowered:
        return "\u7ffb\u8bd1\u672a\u4fdd\u7559\u9500\u552e\u7b7e\u540d"
    if "status code 554 5.4.14" in lowered:
        return "\u786c\u9000\u4fe1\uff1a\u90ae\u4ef6\u8def\u7531\u5f02\u5e38\uff08554 5.4.14\uff09"
    if code == "HARD_BOUNCE":
        return "\u786c\u9000\u4fe1\uff1a\u6536\u4ef6\u5730\u5740\u65e0\u6548\u6216\u88ab\u62d2\u6536"
    if code == "SOFT_BOUNCE":
        return "\u8f6f\u9000\u4fe1\uff1a\u6682\u65f6\u65e0\u6cd5\u6295\u9012\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5"
    if code == "RUN_INTERRUPTED":
        return "本轮运行中断，邮件未完成发送"
    if code == "SMTP_REJECT":
        return "\u90ae\u4ef6\u88ab\u6536\u4ef6\u670d\u52a1\u5668\u62d2\u6536"
    if code == "SMTP_CONNECTION":
        return "\u90ae\u4ef6\u670d\u52a1\u5668\u8fde\u63a5\u5931\u8d25"
    if code == "PROVIDER_ERROR":
        return "\u90ae\u4ef6\u670d\u52a1\u5546\u5904\u7406\u5931\u8d25"
    return "\u53d1\u9001\u5931\u8d25"


def normalize_failure_detail(detail: dict[str, Any]) -> dict[str, Any]:
    message = str(detail.get("message") or detail.get("error") or "发送失败")
    code = str(detail.get("code") or _failure_code(message)).upper()
    phase = str(detail.get("phase") or ("compose" if code.startswith("TRANSLATION_") else "send"))
    raw_hint = str(detail.get("hint") or "").strip()
    hint = _FAILURE_HINTS.get(code, "请查看失败原因并人工确认") if not raw_hint or "?" in raw_hint else raw_hint
    return {
        "phase": phase,
        "code": code,
        "message": _failure_message(message, code),
        "hint": hint,
        "attempts": int(detail.get("attempts") or 0),
        "companyId": detail.get("companyId") or detail.get("company_id"),
        "contactId": detail.get("contactId") or detail.get("contact_id"),
        "companyName": detail.get("companyName") or detail.get("company_name"),
        "contactName": detail.get("contactName") or detail.get("contact_name"),
        "recipientEmail": detail.get("recipientEmail") or detail.get("recipient_email"),
    }


def build_failure_summary(details: list[dict[str, Any]] | None, expected_failed: int = 0) -> dict[str, Any]:
    if details is None or not details:
        return {"total": 0, "byCode": {}, "unavailable": True}
    by_code: dict[str, int] = {}
    for detail in details:
        if str(detail.get("status") or "").lower() != "failed":
            continue
        code = normalize_failure_detail(detail)["code"]
        by_code[code] = by_code.get(code, 0) + 1
    return {"total": sum(by_code.values()), "byCode": by_code, "unavailable": False}


def rebuild_failure_details(
    existing_details: list[dict[str, Any]],
    failed_touch_rows: list[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    result = list(existing_details)
    existing_contacts = {
        (str(item.get("companyId") or ""), str(item.get("contactId") or ""))
        for item in result
    }
    for row in failed_touch_rows:
        contact_key = (str(row[0]), str(row[2]))
        if contact_key in existing_contacts:
            continue
        is_reserved = len(row) > 6 and str(row[6] or "").lower() == "reserved"
        result.append(normalize_failure_detail({
            "status": "failed",
            "code": "RUN_INTERRUPTED" if is_reserved else None,
            "error": "本轮运行中断，邮件未完成发送" if is_reserved else (row[5] or "发送失败"),
            "companyId": str(row[0]),
            "companyName": row[1],
            "contactId": str(row[2]),
            "contactName": row[3],
            "recipientEmail": row[4],
        }))
        existing_contacts.add(contact_key)
    return result


def effective_run_status(status: str, error_message: Any) -> str:
    normalized_status = str(status or "")
    error_text = str(error_message or "")
    if normalized_status == "failed" and "ck_sales_lead_first_touch_sla" in error_text:
        return "completed"
    return normalized_status


def effective_touch_count(stored_count: int, key: str, touch_summary: dict[str, Any] | None) -> int:
    stored = int(stored_count or 0)
    if stored > 0:
        return stored
    return int((touch_summary or {}).get(key) or 0)


def effective_candidate_count(stored_candidates: int, details: list[dict[str, Any]] | None) -> int:
    """Use processed detail rows when older runs persisted candidate_count as zero."""
    stored = int(stored_candidates or 0)
    if stored > 0:
        return stored
    return sum(
        1
        for detail in details or []
        if str(detail.get("status") or "").lower() in {"sent", "failed", "skipped"}
    )


def effective_failed_count(send_failed: int, delivery_summary: dict[str, Any] | None) -> int:
    summary = delivery_summary or {}
    return int(send_failed or 0) + int(summary.get("hard_bounce") or 0) + int(summary.get("soft_bounce") or 0) + int(summary.get("reserved_count") or 0)


def effective_sent_count(send_sent: int, delivery_summary: dict[str, Any] | None) -> int:
    summary = delivery_summary or {}
    later_failures = int(summary.get("hard_bounce") or 0) + int(summary.get("soft_bounce") or 0)
    return max(0, int(send_sent or 0) - later_failures)


def normalize_reply_detail(detail: dict[str, Any]) -> dict[str, Any]:
    intent_payload = detail.get("intentPayload") or detail.get("intent_payload") or {}
    if isinstance(intent_payload, str):
        try:
            intent_payload = json.loads(intent_payload)
        except json.JSONDecodeError:
            intent_payload = {}
    message_category = str(detail.get("messageCategory") or detail.get("message_category") or "").strip()
    intent_level = detail.get("intentLevel") or detail.get("intent_level")
    subject = detail.get("subject") or ""
    content = detail.get("content") or detail.get("bodyText") or detail.get("body_text") or ""
    sender = detail.get("emailAddress") or detail.get("fromAddress") or detail.get("from_address") or ""
    if message_category == "automatic_reply" or is_automatic_reply(subject=subject, body_text=content, from_email=sender):
        message_category = "automatic_reply"
        intent_level = "automatic_reply"
    automatic_reply = message_category == "automatic_reply"
    next_action = None if automatic_reply else (detail.get("nextAction") or detail.get("next_action"))
    confidence = None if automatic_reply else intent_payload.get("confidence")
    return {
        "emailId": detail.get("emailId") or detail.get("email_id"),
        "messageCategory": message_category or None,
        "companyId": detail.get("companyId") or detail.get("company_id"),
        "companyName": detail.get("companyName") or detail.get("company_name"),
        "contactId": detail.get("contactId") or detail.get("contact_id"),
        "contactName": detail.get("contactName") or detail.get("contact_name"),
        "emailAddress": detail.get("emailAddress") or detail.get("fromAddress") or detail.get("from_address"),
        "recipientEmail": detail.get("recipientEmail") or detail.get("toAddress") or detail.get("to_address"),
        "subject": detail.get("subject") or "",
        "content": detail.get("content") or detail.get("bodyText") or detail.get("body_text") or "",
        "receivedAt": detail.get("receivedAt") or detail.get("received_at"),
        "analysis": {
            "intentLevel": intent_level,
            "nextAction": next_action,
            "confidence": confidence,
            "evidenceQuote": intent_payload.get("evidence_quote"),
        },
    }


def build_reply_summary(details: list[dict[str, Any]] | None) -> dict[str, Any]:
    items = [item for item in details or [] if str(item.get("messageCategory") or item.get("message_category") or "") in {"customer_reply", "automatic_reply"}]
    return {"total": len(items)}
def failure_summary_for_run(
    details: list[dict[str, Any]] | None,
    expected_failed: int,
    delivery_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = build_failure_summary(details, expected_failed)
    if summary["unavailable"] and delivery_summary and delivery_summary.get("candidate_count") is not None:
        failed_count = int(delivery_summary.get("failed_count") or expected_failed or 0)
        reserved_count = int(delivery_summary.get("reserved_count") or 0)
        hard_bounce = int(delivery_summary.get("hard_bounce") or 0)
        soft_bounce = int(delivery_summary.get("soft_bounce") or 0)
        summary["total"] = failed_count + reserved_count + hard_bounce + soft_bounce
        summary["byCode"] = {}
        if failed_count:
            summary["byCode"]["SMTP_REJECT"] = failed_count
        if reserved_count:
            summary["byCode"]["RUN_INTERRUPTED"] = reserved_count
        if hard_bounce:
            summary["byCode"]["HARD_BOUNCE"] = hard_bounce
        if soft_bounce:
            summary["byCode"]["SOFT_BOUNCE"] = soft_bounce
        summary["unavailable"] = False
    return summary

class EmailAutomationStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    @staticmethod
    def _config_payload(config: AutoTouchConfig) -> dict[str, Any]:
        return {
            "enabled": config.enabled,
            "intervalMinutes": config.interval_minutes,
            "minScore": config.min_score,
            "regions": list(config.regions),
            "senderUserId": config.sender_user_id,
            "salesName": config.sales_name,
        }

    def load_config(self) -> AutoTouchConfig:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT enabled, interval_minutes, min_score, regions, max_per_run, sender_user_id,
                       sales_name, template_subject, template_body
                FROM ltc.email_automation_config WHERE config_id=true
                """
            )
            row = cur.fetchone()
            cur.close()
        if not row:
            return AutoTouchConfig()
        regions = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
        return AutoTouchConfig(
            enabled=bool(row[0]),
            interval_minutes=int(row[1]),
            min_score=float(row[2]),
            regions=tuple(str(item).upper() for item in regions),
            max_per_run=500,
            sender_user_id=str(row[5] or ""),
            sales_name=str(row[6] or "Global Marketing Team"),
            template_subject=str(row[7] or ""),
            template_body=str(row[8] or ""),
        )

    def save_config(self, payload: dict[str, Any]) -> AutoTouchConfig:
        config = AutoTouchConfig(
            enabled=bool(payload.get("enabled", False)),
            interval_minutes=max(1, min(10080, int(payload.get("intervalMinutes", 60)))),
            min_score=max(0, min(100, float(payload.get("minScore", 75)))),
            regions=tuple(str(item).upper() for item in payload.get("regions", ["NA", "EU"])),
            max_per_run=500,
            sender_user_id=str(payload.get("senderUserId") or ""),
            sales_name=str(payload.get("salesName") or "Global Marketing Team").strip(),
            template_subject=str(payload.get("templateSubject") or ""),
            template_body=str(payload.get("templateBody") or ""),
        )
        sender_user_id = UUID(config.sender_user_id) if config.sender_user_id else None
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_automation_config
                SET enabled=%s, interval_minutes=%s, min_score=%s, regions=%s, max_per_run=%s,
                    sender_user_id=%s, sales_name=%s, template_subject=%s,
                    template_body=%s, version=version+1, updated_at=clock_timestamp()
                WHERE config_id=true
                """,
                (
                    config.enabled,
                    config.interval_minutes,
                    config.min_score,
                    json.dumps(list(config.regions)),
                    config.max_per_run,
                    sender_user_id,
                    config.sales_name,
                    config.template_subject,
                    config.template_body,
                ),
            )
            conn.commit()
            cur.close()
        return config

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT run_id, started_at, completed_at,
                       CASE WHEN status = 'failed' AND error_message::text LIKE '%ck_sales_lead_first_touch_sla%' THEN 'completed' ELSE status END AS status,
                       candidate_count,
                       sent_count, failed_count, skipped_count, details,
                       COALESCE((
                           SELECT jsonb_build_object(
                               'replied', COUNT(DISTINCT em.email_id) FILTER (WHERE EXISTS (
                                   SELECT 1
                                   FROM ltc.email_message ri
                                   LEFT JOIN ltc.user_mailbox mb ON lower(mb.email_address) = lower(ri.from_address)
                                   WHERE ri.parent_email_id = em.email_id
                                     AND ri.direction = 'inbound'
                                      AND ri.message_category IN ('customer_reply', 'automatic_reply')
                               )),
                               'hard_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '5xx' AND (t.status <> 'failed' OR email_automation_run.candidate_count > 0 OR email_automation_run.sent_count > 0 OR email_automation_run.failed_count > 0)),
                               'soft_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '4xx' AND (t.status <> 'failed' OR email_automation_run.candidate_count > 0 OR email_automation_run.sent_count > 0 OR email_automation_run.failed_count > 0)),
                               'delivered_confirmed', COUNT(*) FILTER (WHERE em.status = 'delivered' OR da.status = 'delivered'),
                               'candidate_count', COUNT(*),
                               'sent_count', COUNT(*) FILTER (WHERE t.status = 'sent'),
                               'failed_count', COUNT(*) FILTER (WHERE t.status = 'failed'),
                               'reserved_count', COUNT(*) FILTER (WHERE t.status = 'reserved')
                           )
                           FROM ltc.email_automation_touch t
                           LEFT JOIN ltc.email_message em ON em.provider_message_id = t.provider_message_id
                           LEFT JOIN LATERAL (
                               SELECT a.status, a.bounce_type
                               FROM ltc.email_delivery_attempt a
                               WHERE a.email_id = em.email_id
                               ORDER BY a.attempt_no DESC
                               LIMIT 1
                           ) da ON TRUE
                           WHERE t.run_id = email_automation_run.run_id
                             AND (em.email_id IS NULL OR COALESCE(em.sent_at, em.created_at) >= email_automation_run.started_at)
                       ), '{}'::jsonb) AS delivery_summary
                FROM ltc.email_automation_run
                ORDER BY started_at DESC LIMIT %s
                """,
                (max(1, min(100, limit)),),
            )
            rows = cur.fetchall() or []
            cur.close()
        result = []
        for row in rows:
            details = row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]")
            result.append({
                "runId": str(row[0]),
                "startedAt": row[1].isoformat() if row[1] else None,
                "completedAt": row[2].isoformat() if row[2] else None,
                "status": str(row[3]),
                "candidates": effective_touch_count(int(row[4]), "candidate_count", row[9] or {}) or effective_candidate_count(int(row[4]), details),
                "sent": effective_sent_count(effective_touch_count(int(row[5]), "sent_count", row[9] or {}), row[9] or {}),
                "failed": effective_failed_count(effective_touch_count(int(row[6]), "failed_count", row[9] or {}), row[9] or {}),
                "skipped": int(row[7]),
                "details": details,
                "failureSummary": failure_summary_for_run(details, int(row[6]), row[9] or {}),
                "deliverySummary": row[9] or {},
            })
        return result

    def mark_run_running(self, run_id: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE ltc.email_automation_run SET status='running' WHERE run_id=%s", (run_id,))
            conn.commit()
            cur.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT run_id, started_at, completed_at,
                       CASE WHEN status = 'failed' AND error_message::text LIKE '%ck_sales_lead_first_touch_sla%' THEN 'completed' ELSE status END AS status,
                       candidate_count,
                       sent_count, failed_count, skipped_count, details,
                       COALESCE((
                           SELECT jsonb_build_object(
                               'replied', COUNT(DISTINCT em.email_id) FILTER (WHERE EXISTS (
                                   SELECT 1
                                   FROM ltc.email_message ri
                                   LEFT JOIN ltc.user_mailbox mb ON lower(mb.email_address) = lower(ri.from_address)
                                   WHERE ri.parent_email_id = em.email_id
                                     AND ri.direction = 'inbound'
                                      AND ri.message_category IN ('customer_reply', 'automatic_reply')
                               )),
                               'hard_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '5xx' AND (t.status <> 'failed' OR email_automation_run.candidate_count > 0 OR email_automation_run.sent_count > 0 OR email_automation_run.failed_count > 0)),
                               'soft_bounce', COUNT(*) FILTER (WHERE da.bounce_type = '4xx' AND (t.status <> 'failed' OR email_automation_run.candidate_count > 0 OR email_automation_run.sent_count > 0 OR email_automation_run.failed_count > 0)),
                               'delivered_confirmed', COUNT(*) FILTER (WHERE em.status = 'delivered' OR da.status = 'delivered'),
                               'candidate_count', COUNT(*),
                               'sent_count', COUNT(*) FILTER (WHERE t.status = 'sent'),
                               'failed_count', COUNT(*) FILTER (WHERE t.status = 'failed'),
                               'reserved_count', COUNT(*) FILTER (WHERE t.status = 'reserved')
                           )
                           FROM ltc.email_automation_touch t
                           LEFT JOIN ltc.email_message em ON em.provider_message_id = t.provider_message_id
                           LEFT JOIN LATERAL (
                               SELECT a.status, a.bounce_type
                               FROM ltc.email_delivery_attempt a
                               WHERE a.email_id = em.email_id
                               ORDER BY a.attempt_no DESC
                               LIMIT 1
                           ) da ON TRUE
                           WHERE t.run_id = email_automation_run.run_id
                             AND (em.email_id IS NULL OR COALESCE(em.sent_at, em.created_at) >= email_automation_run.started_at)
                       ), '{}'::jsonb) AS delivery_summary
                FROM ltc.email_automation_run WHERE run_id=%s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return {
            "runId": str(row[0]),
            "startedAt": row[1].isoformat() if row[1] else None,
            "completedAt": row[2].isoformat() if row[2] else None,
            "status": str(row[3]),
            "candidates": effective_touch_count(int(row[4]), "candidate_count", row[9] or {}) or effective_candidate_count(int(row[4]), row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]")),
            "sent": effective_sent_count(effective_touch_count(int(row[5]), "sent_count", row[9] or {}), row[9] or {}),
            "failed": effective_failed_count(effective_touch_count(int(row[6]), "failed_count", row[9] or {}), row[9] or {}),
            "skipped": int(row[7]),
            "details": row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]"),
            "failureSummary": failure_summary_for_run(row[8] if isinstance(row[8], list) else json.loads(row[8] or "[]"), int(row[6]), row[9] or {}),
            "deliverySummary": row[9] or {},
        }
    def list_failures(self, run_id: str, page: int = 1, page_size: int = 20, code: str | None = None) -> dict[str, Any] | None:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT details, failed_count FROM ltc.email_automation_run WHERE run_id=%s", (run_id,))
            run_row = cur.fetchone()
            if not run_row:
                cur.close()
                return None
            raw_details = run_row[0] if isinstance(run_row[0], list) else json.loads(run_row[0] or "[]")
            expected_failed = int(run_row[1] or 0)
            failed_details = [normalize_failure_detail(item) for item in raw_details if str(item.get("status") or "").lower() == "failed"]
            summary = build_failure_summary(raw_details, expected_failed)
            cur.execute("SELECT t.company_id, c.company_name, t.contact_id, ct.full_name, ct.primary_email, t.error_message, t.status FROM ltc.email_automation_touch t JOIN ltc.company c ON c.company_id=t.company_id JOIN ltc.contact ct ON ct.contact_id=t.contact_id WHERE t.run_id=%s AND t.status IN ('failed', 'reserved') ORDER BY t.completed_at NULLS LAST, t.touch_id", (run_id,))
            contact_rows = cur.fetchall() or []
            failed_details = rebuild_failure_details(failed_details, contact_rows)
            cur.execute(
                """
                SELECT t.company_id, c.company_name, t.contact_id, ct.full_name, ct.primary_email,
                       em.status, da.bounce_type, da.error_message, em.email_id
                FROM ltc.email_automation_touch t
                JOIN ltc.company c ON c.company_id = t.company_id
                JOIN ltc.contact ct ON ct.contact_id = t.contact_id
                JOIN ltc.email_message em ON em.provider_message_id = t.provider_message_id
                JOIN LATERAL (
                    SELECT a.status, a.bounce_type, a.error_message
                    FROM ltc.email_delivery_attempt a
                    WHERE a.email_id = em.email_id
                    ORDER BY a.attempt_no DESC LIMIT 1
                ) da ON TRUE
                WHERE t.run_id = %s
                  AND da.bounce_type IN ('5xx', '4xx')
                  AND t.status <> 'failed'
                """,
                (run_id,),
            )
            for row in cur.fetchall() or []:
                bounce_code = 'HARD_BOUNCE' if row[6] == '5xx' else 'SOFT_BOUNCE'
                failed_details.append({
                    'phase': 'delivery',
                    'code': bounce_code,
                    'message': _failure_message(row[7] or ('邮件硬退' if row[6] == '5xx' else '邮件软退'), bounce_code),
                    'hint': '请更换联系人邮箱' if row[6] == '5xx' else '稍后重试或确认收件箱状态',
                    'companyId': str(row[0]), 'companyName': row[1],
                    'contactId': str(row[2]), 'contactName': row[3],
                    'recipientEmail': row[4], 'emailId': str(row[8]),
                })
            cur.close()
        summary_by_code: dict[str, int] = {}
        for item in failed_details:
            item_code = str(item.get("code") or "UNKNOWN")
            summary_by_code[item_code] = summary_by_code.get(item_code, 0) + 1
        if code:
            failed_details = [item for item in failed_details if item["code"] == code.upper()]
        contacts = {(str(row[0]), str(row[2])): row for row in contact_rows}
        company_ids = {str(item.get("companyId")) for item in failed_details if item.get("companyId")}
        company_names = {}
        contacts_by_company = {}
        if company_ids:
            with closing(self._connect()) as conn:
                cur = conn.cursor()
                placeholders = ",".join(["%s"] * len(company_ids))
                cur.execute(f"SELECT company_id, company_name FROM ltc.company WHERE company_id IN ({placeholders})", tuple(company_ids))
                company_names = {str(row[0]): row[1] for row in (cur.fetchall() or [])}
                cur.execute(
                    f"SELECT ct.company_id, c.company_name, ct.contact_id, ct.full_name, ct.primary_email FROM ltc.contact ct JOIN ltc.company c ON c.company_id = ct.company_id WHERE ct.company_id IN ({placeholders}) AND ct.status='active' AND NULLIF(ct.primary_email, '') IS NOT NULL ORDER BY ct.company_id, ct.contact_id",
                    tuple(company_ids),
                )
                for row in cur.fetchall() or []:
                    contacts_by_company.setdefault(str(row[0]), []).append(row)
                cur.close()
        company_occurrences = {}
        for item in failed_details:
            company_id = str(item.get("companyId") or "")
            row = contacts.get((company_id, str(item.get("contactId"))))
            if row is None:
                candidates = contacts_by_company.get(company_id, [])
                occurrence = company_occurrences.get(company_id, 0)
                row = candidates[min(occurrence, len(candidates) - 1)] if candidates else None
                company_occurrences[company_id] = occurrence + 1
            if row:
                item.update({"companyId": str(row[0]), "companyName": row[1], "contactId": str(row[2]), "contactName": row[3], "recipientEmail": row[4]})
            elif company_id in company_names:
                item["companyName"] = company_names[company_id]
        offset = (page - 1) * page_size
        return {"items": failed_details[offset:offset + page_size], "page": page, "pageSize": page_size, "total": len(failed_details), "byCode": summary_by_code, "unavailable": not bool(failed_details)}

    def list_replies(self, run_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any] | None:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM ltc.email_automation_run WHERE run_id=%s", (run_id,))
            if cur.fetchone() is None:
                cur.close()
                return None
            cur.execute(
                """
                SELECT ri.email_id, ri.company_id, c.company_name, ri.contact_id,
                       ct.full_name, ri.from_address, ri.intended_to_address,
                       ri.subject, ri.body_text, ri.intent_level, ri.intent_payload,
                       ri.next_action, ri.received_at, ri.created_at,
                       COUNT(*) OVER () AS total_count
                FROM ltc.email_automation_touch t
                JOIN ltc.email_message outbound
                  ON outbound.provider_message_id = t.provider_message_id
                JOIN ltc.email_message ri
                  ON ri.parent_email_id = outbound.email_id
                 AND ri.direction = 'inbound'
                 AND ri.message_category IN ('customer_reply', 'automatic_reply')
                LEFT JOIN ltc.company c ON c.company_id = ri.company_id
                LEFT JOIN ltc.contact ct ON ct.contact_id = ri.contact_id
                WHERE t.run_id = %s
                ORDER BY COALESCE(ri.received_at, ri.created_at) DESC, ri.email_id DESC
                LIMIT %s OFFSET %s
                """,
                (run_id, page_size, offset),
            )
            rows = cur.fetchall() or []
            cur.close()
        items = []
        for row in rows:
            items.append(normalize_reply_detail({
                "emailId": str(row[0]), "companyId": str(row[1]) if row[1] else None,
                "companyName": row[2], "contactId": str(row[3]) if row[3] else None,
                "contactName": row[4], "fromAddress": row[5], "toAddress": row[6],
                "subject": row[7], "bodyText": row[8], "intentLevel": row[9],
                "intentPayload": row[10], "nextAction": row[11],
                "receivedAt": row[12] or row[13],
            }))
        total = int(rows[0][14]) if rows else 0
        return {"items": items, "page": page, "pageSize": page_size, "total": total}
    def start_run(self, config: AutoTouchConfig) -> str | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT config_id FROM ltc.email_automation_config WHERE config_id=true FOR UPDATE"
            )
            if cur.fetchone() is None:
                raise RuntimeError("Email automation config is missing")
            cur.execute(
                "SELECT run_id FROM ltc.email_automation_run WHERE status='running' LIMIT 1"
            )
            if cur.fetchone() is not None:
                conn.rollback()
                cur.close()
                return None
            cur.execute(
                """
                INSERT INTO ltc.email_automation_run (config_snapshot)
                VALUES (%s) RETURNING run_id
                """,
                (json.dumps(self._config_payload(config)),),
            )
            run_id = str(cur.fetchone()[0])
            conn.commit()
            cur.close()
        return run_id

    def find_candidates(self, config: AutoTouchConfig) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT sl.lead_id, sl.company_id, sl.pool_region_code, c.company_name,
                       c.company_intro, c.industry_code, c.country_code, ct.contact_id, ct.full_name,
                       ct.title, ct.department, ct.relationship_role, ct.email_status,
                       ct.primary_email, r.position, r.is_pinned, r.engagement_locked,
                       COALESCE(r.priority_score, 0), ia.total_score
                FROM ltc.sales_lead sl
                JOIN ltc.company c ON c.company_id = sl.company_id
                JOIN ltc.contact ct ON ct.company_id = c.company_id
                LEFT JOIN ltc.company_contact_roster r
                  ON r.company_id = c.company_id AND r.contact_id = ct.contact_id
                JOIN ltc.lead_icp_assessment ia
                  ON ia.candidate_id = sl.source_candidate_id AND ia.is_current=true
                WHERE ia.total_score >= %s
                  AND sl.pool_region_code = ANY(%s)
                  AND sl.first_touch_at IS NULL
                  AND sl.allocation_status <> 'archived'
                  AND c.lifecycle_status <> 'archived'
                  AND ct.status = 'active'
                  AND NULLIF(ct.primary_email, '') IS NOT NULL
                  AND (r.roster_status = 'active' OR r.roster_status IS NULL)
                  AND NOT EXISTS (
                      SELECT 1 FROM ltc.email_suppression es
                      WHERE es.normalized_email = lower(trim(ct.primary_email))
                        AND es.status = 'active'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM ltc.email_message em
                      WHERE em.company_id = sl.company_id
                        AND em.direction = 'outbound'
                        AND em.purpose = 'first_touch'
                        AND em.status IN (
                            'sending', 'sent', 'smtp_submitted', 'delivery_confirmed',
                            'delivered', 'opened', 'clicked', 'replied'
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM ltc.email_automation_touch eat
                      WHERE eat.company_id = sl.company_id
                        AND eat.contact_id = ct.contact_id
                        AND eat.status IN ('reserved', 'sent')
                  )
                ORDER BY ia.total_score DESC, sl.created_at ASC
                """,
                (config.min_score, list(config.regions)),
            )
            rows = cur.fetchall() or []
            cur.close()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            contact = {
                "contact_id": str(row[7]),
                "full_name": str(row[8] or "there"),
                "title": row[9],
                "department": row[10],
                "relationship_role": row[11],
                "email_status": row[12],
                "primary_email": row[13],
                "position": row[14],
                "is_pinned": row[15],
                "engagement_locked": row[16],
            }
            item = {
                "lead_id": str(row[0]),
                "company_id": str(row[1]),
                "region_code": str(row[2] or ""),
                "company_name": str(row[3] or ""),
                "company_intro": str(row[4] or ""),
                "industry_code": str(row[5] or ""),
                "country_code": str(row[6] or ""),
                "contact_id": str(row[7]),
                "contact_name": str(row[8] or "there"),
                "recipient_email": str(row[13]),
                "icp_score": float(row[18]),
                "contact_score": float(row[17] or 0),
            }
            scored = score_contact(
        contact,
        scene_text=f"{row[4] or ''} {row[5] or ''}",
        allow_any_email_status=True,
    )
            if scored.eligible:
                item["contact_score"] = scored.score
                grouped.setdefault(item["company_id"], []).append(item)
        selected: list[dict[str, Any]] = []
        for company_items in grouped.values():
            selected.extend(sorted(company_items, key=lambda item: (-float(item["contact_score"]), item["contact_name"]))[:3])
        if config.selected_contact_ids:
            allowed = set(config.selected_contact_ids)
            selected = [item for item in selected if item["contact_id"] in allowed]
        return selected

    def claim_candidate(self, *, run_id: str, company_id: str, contact_id: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ltc.email_automation_touch (company_id, contact_id, run_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (company_id, contact_id) DO UPDATE
                SET contact_id=EXCLUDED.contact_id,
                    run_id=EXCLUDED.run_id,
                    status='reserved',
                    provider_message_id=NULL,
                    error_message=NULL,
                    reserved_at=clock_timestamp(),
                    completed_at=NULL
                WHERE ltc.email_automation_touch.status='failed'
                   OR (
                       ltc.email_automation_touch.status='reserved'
                       AND ltc.email_automation_touch.reserved_at < clock_timestamp() - INTERVAL '10 minutes'
                   )
                RETURNING touch_id
                """,
                (company_id, contact_id, run_id),
            )
            claimed = cur.fetchone() is not None
            conn.commit()
            cur.close()
        return claimed

    def find_existing_delivery(self, *, company_id: str, contact_id: str) -> str | None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(provider_message_id, message_id_header)
                FROM ltc.email_message
                WHERE company_id=%s
                  AND contact_id=%s
                  AND direction='outbound'
                  AND purpose='first_touch'
                  AND status IN (
                      'sending', 'sent', 'smtp_submitted', 'delivery_confirmed',
                      'delivered', 'opened', 'clicked', 'replied'
                  )
                ORDER BY sent_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                (company_id, contact_id),
            )
            row = cur.fetchone()
            cur.close()
        return str(row[0]) if row and row[0] else None

    def mark_success(self, *, run_id: str, company_id: str, contact_id: str, message_id: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            now = datetime.now(timezone.utc)
            cur.execute(
                """
                UPDATE ltc.email_automation_touch
                SET status='sent', provider_message_id=%s, completed_at=%s
                WHERE run_id=%s AND company_id=%s AND contact_id=%s
                """,
                (message_id or None, now, run_id, company_id, contact_id),
            )
            cur.execute(
                """
                UPDATE ltc.sales_lead
                SET first_touch_at=COALESCE(first_touch_at, %s),
                    pipeline_stage=CASE WHEN pipeline_stage='new' THEN 'contacted' ELSE pipeline_stage END,
                    last_activity_at=%s, version=version+1, updated_at=clock_timestamp()
                WHERE company_id=%s AND first_touch_at IS NULL
                """,
                (now, now, company_id),
            )
            conn.commit()
            cur.close()

    def mark_failure(self, *, run_id: str, company_id: str, contact_id: str, error: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_automation_touch
                SET status='failed', error_message=%s, completed_at=clock_timestamp()
                WHERE run_id=%s AND company_id=%s AND contact_id=%s
                """,
                (error[:2000], run_id, company_id, contact_id),
            )
            conn.commit()
            cur.close()

    def fail_run(self, *, run_id: str, error: str) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_automation_run
                SET status='failed', completed_at=clock_timestamp(), error_message=%s
                WHERE run_id=%s AND status='running'
                """,
                (error[:2000], run_id),
            )
            conn.commit()
            cur.close()

    def finish_run(self, *, run_id: str, summary: dict[str, Any]) -> None:
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE ltc.email_automation_run
                SET status='completed', completed_at=clock_timestamp(),
                    candidate_count=%s, sent_count=%s, failed_count=%s,
                    skipped_count=%s, details=%s
                WHERE run_id=%s
                """,
                (
                    int(summary.get("candidates", 0)),
                    int(summary.get("sent", 0)),
                    int(summary.get("failed", 0)),
                    int(summary.get("skipped", 0)),
                    json.dumps(summary.get("details", [])),
                    run_id,
                ),
            )
            conn.commit()
            cur.close()
