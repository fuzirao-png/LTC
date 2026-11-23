from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pg8000 import dbapi

from ltc.platform.config import get_settings


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _summary_payload(result: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("summary_payload")
    if isinstance(payload, dict):
        return payload
    action_items = []
    for item in _as_list(result.get("action_items") or record.get("actionItems")):
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or item.get("text") or "").strip()
        if task:
            action_items.append(
                {
                    "task": task,
                    "owner": item.get("owner") or "sales",
                    "due_at": item.get("due_at"),
                }
            )
    next_step = str(result.get("next_step") or "").strip()
    if not next_step and action_items:
        next_step = str(action_items[0]["task"])
    if not next_step:
        next_step = str(record.get("summary") or "Review meeting summary and define the next step.")
    return {
        "customer_needs": [str(item) for item in _as_list(result.get("customer_needs"))],
        "pain_points": [str(item) for item in _as_list(result.get("pain_points"))],
        "buying_signals": [str(item) for item in _as_list(result.get("buying_signals"))],
        "action_items": action_items,
        "decisions": [str(item) for item in _as_list(result.get("decisions"))],
        "risks": [str(item) for item in _as_list(result.get("risks"))],
        "keywords": [str(item) for item in _as_list(result.get("keywords"))],
        "next_step": next_step,
    }


class PostgresMeetingStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return all([self.settings.db_host, self.settings.db_name, self.settings.db_user, self.settings.db_password])

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    def record_completed_meeting(
        self,
        *,
        job: dict[str, Any],
        record: dict[str, Any],
        result: dict[str, Any],
    ) -> str | None:
        if not self.is_configured():
            return None
        company_id = str(job.get("companyId") or job.get("company_id") or "").strip()
        if not company_id:
            return None

        meeting_id = str(job["recordId"])
        job_id = str(job["id"])
        media_asset_id = str(uuid4())
        file_path = Path(str(job.get("storedFilePath") or ""))
        audio_bytes = file_path.read_bytes() if file_path.exists() else b""
        storage_key = f"meeting-audios/{meeting_id}/{job.get('storedFileName') or file_path.name}"
        now = datetime.now(timezone.utc)
        summary_payload = _summary_payload(result, record)
        transcript = str(record.get("transcript") or "")
        segments = record.get("segments") if isinstance(record.get("segments"), list) else []

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ltc.job (
                    job_id, job_type, queue_name, aggregate_type, aggregate_id,
                    status, priority, payload, result_summary, progress_percent,
                    attempt_count, max_attempts, run_after, completed_at
                )
                VALUES (%s, 'meeting_analysis', 'meeting', 'company', %s,
                        'succeeded', 100, %s, %s, 100, 1, 5, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    result_summary = EXCLUDED.result_summary,
                    progress_percent = EXCLUDED.progress_percent,
                    completed_at = EXCLUDED.completed_at,
                    updated_at = clock_timestamp()
                """,
                (
                    job_id,
                    company_id,
                    json.dumps({"source": job.get("source") or "upload"}),
                    json.dumps({"summary": record.get("summary") or ""}),
                    now,
                    now,
                ),
            )
            cur.execute(
                """
                INSERT INTO ltc.media_asset (
                    media_asset_id, company_id, asset_kind, storage_backend, storage_key,
                    original_filename, mime_type, size_bytes, sha256, status, validation_payload, created_at
                )
                VALUES (%s, %s, 'meeting_source', 'local', %s, %s, %s, %s, %s, 'ready', %s, %s)
                ON CONFLICT (storage_backend, storage_key) DO UPDATE SET
                    status = EXCLUDED.status,
                    validation_payload = EXCLUDED.validation_payload
                RETURNING media_asset_id
                """,
                (
                    media_asset_id,
                    company_id,
                    storage_key,
                    job.get("fileName") or record.get("fileName") or "meeting-audio",
                    job.get("mimeType") or record.get("mimeType") or "application/octet-stream",
                    len(audio_bytes),
                    sha256(audio_bytes).hexdigest(),
                    json.dumps({"record_id": meeting_id, "source": "customer-operation-agent"}),
                    now,
                ),
            )
            media_asset_id = str(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO ltc.meeting (
                    meeting_id, company_id, source_media_asset_id, current_job_id,
                    title, source, meeting_started_at, duration_seconds,
                    processing_status, transcript_status, transcript_text,
                    transcript_language, transcript_provider, summary_payload,
                    summary_prompt_version, summary_model, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'upload', %s, %s,
                        'completed', 'done', %s, 'zh', %s, %s,
                        'customer-operation-v3.7', %s, %s, %s)
                ON CONFLICT (meeting_id) DO UPDATE SET
                    processing_status = EXCLUDED.processing_status,
                    transcript_status = EXCLUDED.transcript_status,
                    transcript_text = EXCLUDED.transcript_text,
                    transcript_provider = EXCLUDED.transcript_provider,
                    summary_payload = EXCLUDED.summary_payload,
                    summary_model = EXCLUDED.summary_model,
                    updated_at = clock_timestamp()
                """,
                (
                    meeting_id,
                    company_id,
                    media_asset_id,
                    job_id,
                    record.get("title") or "Uploaded meeting recording",
                    now,
                    record.get("durationSeconds") or 0,
                    transcript,
                    record.get("transcriptProvider") or result.get("transcript_provider") or "",
                    json.dumps(summary_payload),
                    self.settings.llm_model or result.get("summary_model") or "",
                    now,
                    now,
                ),
            )
            cur.execute("DELETE FROM ltc.meeting_segment WHERE meeting_id = %s", (meeting_id,))
            for index, segment in enumerate(segments, start=1):
                start = float(segment.get("start") or 0)
                end = float(segment.get("end") or start + 0.01)
                if end <= start:
                    end = start + 0.01
                cur.execute(
                    """
                    INSERT INTO ltc.meeting_segment (
                        company_id, meeting_id, sequence_no, start_seconds, end_seconds,
                        speaker_id, speaker_label, transcript_text, confidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    """,
                    (
                        company_id,
                        meeting_id,
                        index,
                        start,
                        end,
                        segment.get("speaker_id") or segment.get("speaker"),
                        segment.get("speaker"),
                        segment.get("text") or "",
                    ),
                )
            for index, item in enumerate(summary_payload["action_items"], start=1):
                cur.execute(
                    """
                    INSERT INTO ltc.follow_up_task (
                        company_id, source_meeting_id, task_type, title, description,
                        status, priority, idempotency_key, created_at, updated_at
                    )
                    VALUES (%s, %s, 'proposal', %s, %s, 'pending', 80, %s, %s, %s)
                    ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        updated_at = clock_timestamp()
                    """,
                    (
                        company_id,
                        meeting_id,
                        str(item.get("task") or "Follow up meeting"),
                        str(item.get("task") or "Follow up meeting"),
                        f"meeting:{meeting_id}:action:{index}",
                        now,
                        now,
                    ),
                )
            cur.execute(
                """
                INSERT INTO ltc.customer_activity (
                    company_id, activity_type, direction, subject, body, source_type,
                    source_external_key, payload, occurred_at
                )
                VALUES (%s, 'system', 'internal', %s, %s, 'system', %s, %s, %s)
                ON CONFLICT (source_type, company_id, source_external_key)
                WHERE source_external_key IS NOT NULL
                DO UPDATE SET
                    subject = EXCLUDED.subject,
                    body = EXCLUDED.body,
                    payload = EXCLUDED.payload,
                    occurred_at = EXCLUDED.occurred_at
                """,
                (
                    company_id,
                    record.get("title") or "Meeting completed",
                    summary_payload["next_step"],
                    f"meeting:{meeting_id}",
                    json.dumps(
                        {
                            "event_type": "meeting_completed",
                            "meeting_id": meeting_id,
                            "next_step": summary_payload["next_step"],
                        }
                    ),
                    now,
                ),
            )
            conn.commit()
        return meeting_id



