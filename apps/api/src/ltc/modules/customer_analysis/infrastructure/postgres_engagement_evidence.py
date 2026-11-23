"""Read-only PostgreSQL adapter for Customer Analysis communication evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable
from uuid import UUID

from ltc.modules.customer_analysis.domain.models import EngagementEvidence


_EMAIL_STATUSES = (
    "received",
    "processing",
    "processed",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "replied",
)
_MAX_ITEM_CHARACTERS = 8_000
_MAX_EMAIL_CHARACTERS = 60_000
_MAX_NOTE_CHARACTERS = 40_000
_MAX_MEETING_CHARACTERS = 80_000
_QUOTE_MARKERS = (
    re.compile(r"^on .+ wrote:$", re.IGNORECASE),
    re.compile(r"^from:\s*", re.IGNORECASE),
    re.compile(r"^sent:\s*", re.IGNORECASE),
    re.compile(r"^发件人\s*[:：]"),
    re.compile(r"^发送时间\s*[:：]"),
    re.compile(r"^-{2,}\s*original message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*原始邮件\s*-{2,}$"),
)


class PostgresEngagementEvidenceReadPort:
    """Selects Customer Operation facts without importing or mutating that module."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def _query(
        self, query: str, params: tuple[Any, ...]
    ) -> list[tuple[Any, ...]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(query, params)
                return list(cursor.fetchall())
            finally:
                cursor.close()
        finally:
            connection.close()

    def list_email_evidence(
        self, company_id: UUID, *, cutoff_at: datetime, limit: int = 50
    ) -> tuple[EngagementEvidence, ...]:
        rows = self._query(
            """
            SELECT email_id, company_id, contact_id, direction, status, subject,
                   body_text, intent_level, intent_payload, next_action,
                   COALESCE(received_at, sent_at, created_at) AS occurred_at,
                   version, thread_key
            FROM ltc.email_message
            WHERE company_id = %s
              AND COALESCE(received_at, sent_at, created_at) <= %s
              AND status = ANY(%s)
              AND (
                    (direction = 'inbound' AND status IN ('received', 'processing', 'processed'))
                    OR
                    (direction = 'outbound' AND status IN ('sent', 'smtp_submitted', 'delivery_confirmed', 'delivered', 'opened', 'clicked', 'replied'))
                  )
            ORDER BY COALESCE(received_at, sent_at, created_at) DESC, email_id DESC
            LIMIT %s
            """,
            (company_id, cutoff_at, list(_EMAIL_STATUSES), max(1, min(limit, 200))),
        )
        evidence: list[EngagementEvidence] = []
        seen_hashes: set[str] = set()
        consumed_characters = 0
        for row in rows:
            text = clean_communication_text(str(row[6] or ""))
            subject = clean_communication_text(str(row[5] or ""), max_characters=500)
            if not text and not subject:
                continue
            content_hash = _content_hash(row[3], subject, text)
            if content_hash in seen_hashes:
                continue
            remaining = _MAX_EMAIL_CHARACTERS - consumed_characters
            if remaining <= 0:
                break
            text = text[:remaining]
            consumed_characters += len(text)
            seen_hashes.add(content_hash)
            occurred_at = _aware_datetime(row[10])
            evidence.append(
                EngagementEvidence(
                    evidence_id=f"internal-email:{row[0]}",
                    source_type="internal_email",
                    source_resource_id=str(row[0]),
                    company_id=UUID(str(row[1])),
                    occurred_at=occurred_at,
                    title=subject or "无主题邮件",
                    text=text or subject,
                    content_hash=content_hash,
                    metadata={
                        "contact_id": str(row[2]) if row[2] else None,
                        "direction": str(row[3]),
                        "status": str(row[4]),
                        "intent_level": row[7],
                        "intent_payload": _safe_dict(row[8]),
                        "next_action": row[9],
                        "message_version": int(row[11] or 0),
                        "thread_key": row[12],
                    },
                )
            )
        return tuple(sorted(evidence, key=lambda item: (item.occurred_at, item.evidence_id)))

    def list_confirmed_manual_note_evidence(
        self, company_id: UUID, *, cutoff_at: datetime, limit: int = 100
    ) -> tuple[EngagementEvidence, ...]:
        rows = self._query(
            """
            SELECT note_id, company_id, sales_id, raw_text, extracted_fields_json,
                   version, created_at, updated_at
            FROM ltc.manual_note
            WHERE company_id = %s
              AND confirm_status = 'confirmed'
              AND created_at <= %s
            ORDER BY created_at DESC, note_id DESC
            LIMIT %s
            """,
            (company_id, cutoff_at, max(1, min(limit, 500))),
        )
        evidence: list[EngagementEvidence] = []
        consumed_characters = 0
        for row in rows:
            raw_text = clean_communication_text(str(row[3] or ""))
            if not raw_text:
                continue
            remaining = _MAX_NOTE_CHARACTERS - consumed_characters
            if remaining <= 0:
                break
            raw_text = raw_text[:remaining]
            consumed_characters += len(raw_text)
            extracted_fields = _safe_list(row[4])
            note_version = int(row[5] or 0)
            content_hash = _content_hash(
                raw_text,
                json.dumps(extracted_fields, ensure_ascii=False, sort_keys=True, default=str),
                note_version,
            )
            evidence.append(
                EngagementEvidence(
                    evidence_id=f"internal-manual-note:{row[0]}",
                    source_type="internal_manual_note",
                    source_resource_id=str(row[0]),
                    company_id=UUID(str(row[1])),
                    occurred_at=_aware_datetime(row[6]),
                    title="销售手工记录",
                    text=raw_text,
                    content_hash=content_hash,
                    metadata={
                        "sales_id": str(row[2]),
                        "extracted_fields": extracted_fields,
                        "note_version": note_version,
                        "updated_at": _aware_datetime(row[7]).isoformat(),
                        "confirm_status": "confirmed",
                    },
                )
            )
        return tuple(sorted(evidence, key=lambda item: (item.occurred_at, item.evidence_id)))

    def list_meeting_evidence(
        self, company_id: UUID, *, cutoff_at: datetime, limit: int = 20
    ) -> tuple[EngagementEvidence, ...]:
        """Expose completed meeting summaries as customer-confirmable evidence."""
        rows = self._query(
            """
            SELECT meeting_id, company_id, title, meeting_started_at, created_at,
                   summary_payload, transcript_text, transcript_provider
            FROM ltc.meeting
            WHERE company_id = %s
              AND deleted_at IS NULL
              AND processing_status = 'completed'
              AND summary_payload IS NOT NULL
              AND COALESCE(meeting_started_at, created_at) <= %s
            ORDER BY COALESCE(meeting_started_at, created_at) DESC, meeting_id DESC
            LIMIT %s
            """,
            (company_id, cutoff_at, max(1, min(limit, 100))),
        )
        evidence: list[EngagementEvidence] = []
        consumed = 0
        for row in rows:
            payload = _safe_dict(row[5])
            sections = (
                ("客户需求", payload.get("customer_needs")),
                ("痛点", payload.get("pain_points")),
                ("购买信号", payload.get("buying_signals")),
                ("决策", payload.get("decisions")),
                ("风险", payload.get("risks")),
                ("下一步", payload.get("next_step")),
            )
            lines = [
                f"{label}: " + "；".join(str(item) for item in value if str(item).strip())
                if isinstance(value, list) else f"{label}: {value}"
                for label, value in sections
                if value
            ]
            text = "\n".join(lines).strip()
            if not text:
                text = clean_communication_text(str(row[6] or ""), max_characters=12_000)
            if not text:
                continue
            remaining = _MAX_MEETING_CHARACTERS - consumed
            if remaining <= 0:
                break
            text = text[:remaining]
            consumed += len(text)
            occurred_at = _aware_datetime(row[3] or row[4])
            evidence.append(
                EngagementEvidence(
                    evidence_id=f"internal-meeting:{row[0]}",
                    source_type="internal_meeting",
                    source_resource_id=str(row[0]),
                    company_id=UUID(str(row[1])),
                    occurred_at=occurred_at,
                    title=str(row[2] or "会议摘要"),
                    text=text,
                    content_hash=_content_hash(row[0], text),
                    metadata={
                        "meeting_id": str(row[0]),
                        "transcript_provider": row[7],
                        "summary_payload": payload,
                    },
                )
            )
        return tuple(sorted(evidence, key=lambda item: (item.occurred_at, item.evidence_id)))


def clean_communication_text(
    value: str, *, max_characters: int = _MAX_ITEM_CHARACTERS
) -> str:
    """Normalize plain text and remove quoted history/signatures from one message."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = re.sub(r"[\t ]+", " ", raw_line).strip()
        if line.startswith(">"):
            continue
        if line in {"--", "-- ", "此致", "敬礼"} and lines:
            break
        if any(pattern.search(line) for pattern in _QUOTE_MARKERS) and lines:
            break
        if line or (lines and lines[-1]):
            lines.append(line)
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_characters]


def _content_hash(*values: Any) -> str:
    canonical = "|".join(str(value or "") for value in values)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_list(value: Any) -> list[dict[str, Any]]:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]
