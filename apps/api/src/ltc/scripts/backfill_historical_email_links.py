from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta
import argparse
from typing import Any

from pg8000 import dbapi

from ltc.modules.customer_operation.infrastructure.mail_store import (
    _looks_like_delivery_notification,
    _message_id_matches,
    _normalize_email,
    _normalize_reply_subject,
)
from ltc.modules.customer_operation.application.email_analysis import parse_delivery_notification
from ltc.platform.config import get_settings


@dataclass
class BackfillPlan:
    matched: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)


def _add_skip(plan: BackfillPlan, reason: str) -> None:
    plan.skipped[reason] = plan.skipped.get(reason, 0) + 1


def _candidate_by_message_id(inbound: dict[str, Any], outbound_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value = str(inbound.get("in_reply_to") or "")
    return [row for row in outbound_rows if (
        _message_id_matches(value, str(row.get("message_id_header") or row.get("provider_message_id") or ""))
        and row.get("company_id") == inbound.get("company_id")
        and row.get("contact_id") == inbound.get("contact_id")
    )]


def _candidate_by_business_fields(inbound: dict[str, Any], outbound_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sender = _normalize_email(str(inbound.get("from_address") or ""))
    subject = _normalize_reply_subject(str(inbound.get("subject") or ""))
    received_at = inbound.get("received_at")
    if not sender or not subject or received_at is None:
        return []
    candidates = []
    for row in outbound_rows:
        sent_at = row.get("sent_at")
        if sent_at is None or sent_at > received_at or received_at - sent_at > timedelta(days=30):
            continue
        if row.get("company_id") != inbound.get("company_id") or row.get("contact_id") != inbound.get("contact_id"):
            continue
        if _normalize_email(str(row.get("intended_to_address") or "")) != sender:
            continue
        if _normalize_reply_subject(str(row.get("subject") or "")) == subject:
            candidates.append(row)
    return candidates


def _candidate_for_delivery_notification(inbound: dict[str, Any], outbound_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    delivery = parse_delivery_notification(str(inbound.get("subject") or ""), str(inbound.get("body_text") or ""))
    message_ids = [str(value) for value in delivery.get("message_ids") or [] if value]
    if message_ids:
        candidates = [row for row in outbound_rows if any(_message_id_matches(value, str(row.get("message_id_header") or row.get("provider_message_id") or "")) for value in message_ids)]
        if candidates:
            return candidates, delivery
    recipient_set = {_normalize_email(value) for value in delivery.get("recipients") or []}
    original_subject = _normalize_reply_subject(str(delivery.get("original_subject") or ""))
    received_at = inbound.get("received_at")
    if not recipient_set or not original_subject or received_at is None:
        return [], delivery
    candidates = []
    for row in outbound_rows:
        sent_at = row.get("sent_at")
        if sent_at is None or sent_at > received_at or received_at - sent_at > timedelta(days=30):
            continue
        if _normalize_email(str(row.get("intended_to_address") or "")) in recipient_set and _normalize_reply_subject(str(row.get("subject") or "")) == original_subject:
            candidates.append(row)
    return candidates, delivery


def _parse_historical_delivery(inbound: dict[str, Any]) -> dict[str, Any] | None:
    parsed = parse_delivery_notification(str(inbound.get("subject") or ""), str(inbound.get("body_text") or ""))
    if _looks_like_delivery_notification(str(inbound.get("subject") or ""), str(inbound.get("body_text") or "")):
        return parsed
    if parsed.get("recipients") and (parsed.get("original_subject") or parsed.get("status") in {"hard_bounce", "soft_bounce", "delivered_confirmed"}):
        return parsed
    return None


def plan_backfill(inbound_rows: list[dict[str, Any]], outbound_rows: list[dict[str, Any]], internal_addresses: set[str]) -> BackfillPlan:
    plan = BackfillPlan()
    for inbound in inbound_rows:
        inbound_id = str(inbound["email_id"])
        if inbound.get("parent_email_id"):
            _add_skip(plan, "already_linked")
            continue
        if _normalize_email(str(inbound.get("from_address") or "")) in internal_addresses:
            _add_skip(plan, "internal_sender")
            continue
        delivery = _parse_historical_delivery(inbound)
        if delivery is not None:
            candidates, delivery = _candidate_for_delivery_notification(inbound, outbound_rows)
            reason = "delivery_notification"
        else:
            candidates = _candidate_by_message_id(inbound, outbound_rows)
            reason = "message_id"
            if not candidates:
                candidates = _candidate_by_business_fields(inbound, outbound_rows)
                reason = "business_fields"
        if len(candidates) == 1:
            item = {"inbound_id": inbound_id, "outbound": candidates[0], "reason": reason}
            if delivery is not None:
                item["delivery"] = delivery
            plan.matched.append(item)
        elif len(candidates) > 1:
            plan.ambiguous.append(inbound_id)
        else:
            plan.unmatched.append(inbound_id)
    return plan


def _connect():
    settings = get_settings()
    return dbapi.connect(user=settings.db_user, host=settings.db_host, database=settings.db_name, port=settings.db_port, password=settings.db_password, timeout=30)


def _load_rows(cur):
    cur.execute("SELECT email_address FROM ltc.user_mailbox WHERE email_address IS NOT NULL")
    internal = {_normalize_email(str(row[0])) for row in cur.fetchall()}
    cur.execute("SELECT email_id, from_address, subject, body_text, in_reply_to, company_id, contact_id, received_at, parent_email_id FROM ltc.email_message WHERE direction = 'inbound' ORDER BY received_at, created_at")
    inbound_columns = ["email_id", "from_address", "subject", "body_text", "in_reply_to", "company_id", "contact_id", "received_at", "parent_email_id"]
    inbound = [dict(zip(inbound_columns, row)) for row in cur.fetchall()]
    cur.execute("SELECT email_id, intended_to_address, subject, message_id_header, provider_message_id, company_id, contact_id, sent_at, thread_key FROM ltc.email_message WHERE direction = 'outbound' AND sent_at IS NOT NULL")
    outbound_columns = ["email_id", "intended_to_address", "subject", "message_id_header", "provider_message_id", "company_id", "contact_id", "sent_at", "thread_key"]
    outbound = [dict(zip(outbound_columns, row)) for row in cur.fetchall()]
    return inbound, outbound, internal


def run_backfill(*, dry_run: bool = False) -> BackfillPlan:
    with closing(_connect()) as conn:
        cur = conn.cursor()
        inbound, outbound, internal = _load_rows(cur)
        plan = plan_backfill(inbound, outbound, internal)
        if dry_run:
            conn.rollback()
            return plan
        for item in plan.matched:
            inbound_id = item["inbound_id"]
            parent = item["outbound"]
            thread_key = parent.get("thread_key") or parent.get("message_id_header")
            if item.get("delivery") is not None:
                cur.execute("UPDATE ltc.email_message SET company_id=%s, contact_id=%s, message_category='delivery_notification', updated_at=clock_timestamp() WHERE email_id=%s AND direction='inbound'", (parent.get("company_id"), parent.get("contact_id"), inbound_id))
            cur.execute("UPDATE ltc.email_message SET parent_email_id = %s, thread_key = COALESCE(thread_key, %s), updated_at = clock_timestamp() WHERE email_id = %s AND direction = 'inbound' AND parent_email_id IS NULL", (parent["email_id"], thread_key, inbound_id))
            delivery = item.get("delivery")
            if delivery is not None:
                if delivery.get("status") in {"hard_bounce", "soft_bounce"}:
                    bounce_type = delivery.get("bounce_type")
                    reason_text = delivery.get("reason") or "Delivery notification reported a bounce."
                    cur.execute("UPDATE ltc.email_message SET status='bounced', updated_at=clock_timestamp() WHERE email_id=%s AND direction='outbound'", (parent["email_id"],))
                    cur.execute("UPDATE ltc.email_delivery_attempt SET status='failed', bounce_type=%s, error_message=%s, completed_at=COALESCE(completed_at, clock_timestamp()), response_payload=COALESCE(response_payload, %s::jsonb) WHERE email_id=%s AND status IN ('accepted','uncertain')", (bounce_type, reason_text, '{"source":"historical_delivery_notification"}', parent["email_id"]))
                    cur.execute("UPDATE ltc.email_automation_touch t SET status='failed', error_message=%s, completed_at=COALESCE(completed_at, clock_timestamp()) FROM ltc.email_message em WHERE em.email_id=%s AND t.provider_message_id=COALESCE(em.provider_message_id, em.message_id_header) AND t.status IN ('reserved','sent')", (reason_text, parent["email_id"]))
                    if bounce_type == "5xx":
                        cur.execute("UPDATE ltc.contact SET email_status='invalid', updated_at=clock_timestamp(), version=version+1 WHERE company_id=%s AND contact_id=%s", (parent.get("company_id"), parent.get("contact_id")))
            else:
                cur.execute("UPDATE ltc.email_message SET replied_at = COALESCE(replied_at, (SELECT received_at FROM ltc.email_message WHERE email_id = %s)), status = CASE WHEN status IN ('sent', 'delivered', 'opened', 'clicked') THEN 'replied' ELSE status END, updated_at = clock_timestamp() WHERE email_id = %s AND direction = 'outbound'", (inbound_id, parent["email_id"]))
        cur.execute("""
            UPDATE ltc.email_message AS outbound
            SET replied_at = COALESCE(outbound.replied_at, inbound.received_at),
                status = CASE WHEN outbound.status IN ('smtp_submitted', 'sent', 'delivered', 'opened', 'clicked') THEN 'replied' ELSE outbound.status END,
                updated_at = clock_timestamp()
            FROM ltc.email_message AS inbound
            WHERE inbound.direction = 'inbound'
              AND inbound.parent_email_id = outbound.email_id
              AND inbound.message_category IN ('customer_reply', 'automatic_reply')
              AND outbound.direction = 'outbound'
        """)
        conn.commit()
        return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely link historical inbound emails to outbound messages.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = run_backfill(dry_run=args.dry_run)
    print({"matched": len(plan.matched), "ambiguous": len(plan.ambiguous), "unmatched": len(plan.unmatched), "skipped": plan.skipped, "dry_run": args.dry_run})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
