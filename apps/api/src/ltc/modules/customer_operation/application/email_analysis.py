from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Any

from ltc.modules.customer_operation.application.reply_intent_agent import classify_reply

_AUTOMATIC_REPLY_SUBJECT_PATTERNS = (
    r"^(?:re\s*[:\u003a\u002d]\s*)?(?:automatic reply|auto reply|out of office|ooo|vacation responder|r\u00e9ponse automatique|response automatique|risposta automatica|\u81ea\u52a8\u56de\u590d|\u81ea\u52a8\u7b54\u590d)\b",
    r"^(?:automatic reply|auto reply|out of office|ooo|vacation responder|r\u00e9ponse automatique|response automatique|risposta automatica|\u81ea\u52a8\u56de\u590d|\u81ea\u52a8\u7b54\u590d)\s*[:\u003a\u002d]",
)
_AUTOMATIC_REPLY_BODY_PATTERNS = (
    r"(?:^|\n)\s*(?:automatic reply|auto reply|out of office|ooo|vacation responder|r\u00e9ponse automatique|response automatique|risposta automatica|\u81ea\u52a8\u56de\u590d|\u81ea\u52a8\u7b54\u590d)\s*[:\u003a\u002d]?",
    r"(?:^|\n)\s*(?:i am|i'm|je suis|sono|\u6211\u76ee\u524d|\u672c\u4eba)\s+(?:out of office|away|absent|en cong\u00e9|fuori ufficio)",
)
_AUTOMATIC_REPLY_SENDER_HINTS = ("mailer-daemon", "postmaster", "noreply", "no-reply", "autoreply", "auto-reply")

_DELIVERY_TOKENS = ("mailer-daemon", "postmaster", "delivery status notification", "delivery report", "mail delivery failed", "undeliverable", "final-recipient", "action: failed", "action: delayed", "action: delivered", "邮件被退回", "退信通知", "退信原因", "无法发送到", "被退回邮件")


def _normalize_email(value: str) -> str:
    raw = str(value or "").strip()
    _, address = parseaddr(raw)
    return (address or raw).strip().strip("<>（）()，,；;").lower()


def _attachment_text(attachments: list[Any] | None) -> str:
    parts: list[str] = []
    for attachment in attachments or []:
        content_type = str(getattr(attachment, "content_type", "") or "").lower()
        filename = str(getattr(attachment, "filename", "") or "").lower()
        if content_type != "message/rfc822" and not filename.endswith((".eml", ".msg")):
            continue
        content = getattr(attachment, "content", b"")
        parts.append(content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content or ""))
    return "\n".join(parts)


def combined_email_text(subject: str, body_text: str, attachments: list[Any] | None = None) -> str:
    return "\n".join(part for part in (str(subject or ""), str(body_text or ""), _attachment_text(attachments)) if part)


def is_delivery_notification(subject: str, body_text: str, attachments: list[Any] | None = None) -> bool:
    lowered = combined_email_text(subject, body_text, attachments).casefold()
    return any(token in lowered for token in _DELIVERY_TOKENS)


def is_automatic_reply(*, subject: str, body_text: str, from_email: str = "") -> bool:
    normalized_subject = " ".join(str(subject or "").split()).casefold()
    normalized_body = str(body_text or "").replace("\r", "").casefold()
    sender = _normalize_email(from_email)
    if any(re.search(pattern, normalized_subject, re.IGNORECASE) for pattern in _AUTOMATIC_REPLY_SUBJECT_PATTERNS):
        return True
    if any(re.search(pattern, normalized_body, re.IGNORECASE) for pattern in _AUTOMATIC_REPLY_BODY_PATTERNS):
        return True
    if any(hint in sender for hint in _AUTOMATIC_REPLY_SENDER_HINTS):
        return any(re.search(pattern, normalized_body, re.IGNORECASE) for pattern in _AUTOMATIC_REPLY_BODY_PATTERNS)
    return False


def classify_email_category(*, subject: str, body_text: str, from_email: str = "", attachments: list[Any] | None = None) -> str:
    if is_delivery_notification(subject, body_text, attachments):
        return "delivery_notification"
    if is_automatic_reply(subject=subject, body_text=body_text, from_email=from_email):
        return "automatic_reply"
    return "customer_reply"


def _extract_reason(text: str) -> str:
    match = re.search(r"退信原因\s*[:：]?\s*(.+?)(?=\n\s*解决方案|\Z)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return " ".join(match.group(1).split())[:2000]
    smtp_match = re.search(r"([^\n]*(?:[45]\d\d\s+[45]\.\d+\.\d+|recipient address rejected|mailbox unavailable|user unknown)[^\n]*)", text, re.IGNORECASE)
    return " ".join(smtp_match.group(1).split())[:2000] if smtp_match else ""


def parse_delivery_notification(subject: str, body_text: str, attachments: list[Any] | None = None) -> dict[str, Any]:
    text = combined_email_text(subject, body_text, attachments)
    lowered = text.casefold()
    message_ids = list(dict.fromkeys(re.findall(r"(?:original[- ]message[- ]id|message-id|in-reply-to)\s*:\s*(<[^>\s]+>)", text, re.IGNORECASE)))
    recipient_candidates = re.findall(r"(?:final-recipient|original-recipient|x-failed-recipient)\s*:\s*(?:rfc822;)?\s*([^\s;<>]+)", text, re.IGNORECASE)
    recipient_candidates.extend(re.findall(r"无法发送到\s+([\w.!#$%&'*+/=?^_`{|}~-]+@[\w.-]+)", text, re.IGNORECASE))
    recipient_candidates.extend(re.findall(r"收件人\s*[（(]\s*([^\s（）()<>]+@[^\s（）()<>]+)\s*[）)]", text, re.IGNORECASE))
    recipients = list(dict.fromkeys(value for value in (_normalize_email(item) for item in recipient_candidates) if "@" in value))
    original_subject_match = re.search(r"(?:被退回邮件\s*)?主\s*题\s*[:：]\s*([^\r\n]+)", text, re.IGNORECASE)
    original_subject = " ".join(original_subject_match.group(1).split()) if original_subject_match else ""
    codes = re.findall(r"\b([45](?:\d\d|\.\d+\.\d+))\b", text)
    hard_tokens = ("user unknown", "mailbox unavailable", "recipient address rejected", "access denied", "拒绝接收", "地址不存在")
    soft_tokens = ("action: delayed", "mailbox full", "greylist", "邮箱已满", "稍后重试")
    if any(code.startswith("5") for code in codes) or any(token in lowered for token in hard_tokens):
        status, bounce_type = "hard_bounce", "5xx"
    elif any(code.startswith("4") for code in codes) or any(token in lowered for token in soft_tokens):
        status, bounce_type = "soft_bounce", "4xx"
    elif "action: delivered" in lowered or "delivery confirmed" in lowered or "投递成功" in lowered:
        status, bounce_type = "delivered_confirmed", None
    else:
        status, bounce_type = "reconcile_required", None
    return {"message_ids": message_ids, "recipients": recipients, "status": status, "bounce_type": bounce_type, "original_subject": original_subject, "reason": _extract_reason(text)}


def analyze_inbound_email(*, subject: str, body_text: str, from_email: str = "", attachments: list[Any] | None = None) -> dict[str, Any]:
    category = classify_email_category(subject=subject, body_text=body_text, from_email=from_email, attachments=attachments)
    base = {"messageCategory": category, "countsAsReply": category in {"customer_reply", "automatic_reply"}, "intentLevel": None, "nextAction": None, "confidence": None, "evidenceQuote": None, "deliveryStatus": None, "bounceType": None, "recipients": [], "messageIds": [], "originalSubject": "", "reason": ""}
    if category == "delivery_notification":
        delivery = parse_delivery_notification(subject, body_text, attachments)
        base.update({"deliveryStatus": delivery["status"], "bounceType": delivery["bounce_type"], "recipients": delivery["recipients"], "messageIds": delivery["message_ids"], "originalSubject": delivery["original_subject"], "reason": delivery["reason"]})
        return base
    if category == "automatic_reply":
        base.update({"intentLevel": "automatic_reply", "nextAction": None, "evidenceQuote": str(body_text or "").strip()[:500] or None})
        return base
    intent = classify_reply(str(body_text or "").strip())
    base.update({"intentLevel": intent.intent_level, "nextAction": intent.next_action, "confidence": intent.confidence, "evidenceQuote": intent.evidence_quote})
    return base

