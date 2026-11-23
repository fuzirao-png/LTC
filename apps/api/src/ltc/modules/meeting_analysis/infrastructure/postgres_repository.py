"""PostgreSQL implementations of Meeting Analysis ports."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterator, cast
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ltc.modules.meeting_analysis.domain.errors import (
    MeetingNotFoundError,
    MeetingVersionConflictError,
)
from ltc.modules.meeting_analysis.domain.models import (
    MediaAsset,
    Meeting,
    MeetingSegment,
)
from ltc.modules.meeting_analysis.domain.ports import MeetingRepository
from ltc.platform.db import PostgresDatabase


# ── Column lists ──

MEDIA_ASSET_COLUMNS = """
    media_asset_id, company_id, parent_media_asset_id, asset_kind,
    storage_backend, storage_key, original_filename, mime_type,
    size_bytes, sha256, status, validation_payload,
    retention_until, deleted_at, created_by, created_at
"""

MEETING_COLUMNS = """
    meeting_id, company_id, lead_id, primary_contact_id, owner_user_id,
    source_media_asset_id, normalized_audio_asset_id, current_job_id,
    title, source, meeting_started_at, duration_seconds,
    processing_status, transcript_status, transcript_text,
    transcript_language, transcript_provider,
    summary_payload, summary_schema_version,
    summary_prompt_version, summary_model,
    error_code, error_message, version, created_at, updated_at
"""

MEETING_SEGMENT_COLUMNS = """
    company_id, meeting_id, sequence_no, start_seconds, end_seconds,
    speaker_id, speaker_label, speaker_contact_id,
    transcript_text, confidence
"""


# ── Row → entity mappers ──

def _media_asset_from_row(row: dict[str, object]) -> MediaAsset:
    return MediaAsset(
        media_asset_id=cast(UUID, row["media_asset_id"]),
        company_id=cast(UUID | None, row.get("company_id")),
        parent_media_asset_id=cast(UUID | None, row.get("parent_media_asset_id")),
        asset_kind=cast(str, row["asset_kind"]),
        storage_backend=cast(str, row["storage_backend"]),
        storage_key=cast(str, row["storage_key"]),
        original_filename=cast(str | None, row.get("original_filename")),
        mime_type=cast(str, row["mime_type"]),
        size_bytes=cast(int, row["size_bytes"]),
        sha256=cast(str, row["sha256"]),
        status=cast(str, row["status"]),
        validation_payload=cast(dict[str, object], row["validation_payload"]),
        retention_until=cast(datetime | None, row.get("retention_until")),
        deleted_at=cast(datetime | None, row.get("deleted_at")),
        created_by=cast(UUID | None, row.get("created_by")),
        created_at=cast(datetime, row["created_at"]),
    )


def _meeting_from_row(row: dict[str, object]) -> Meeting:
    return Meeting(
        meeting_id=cast(UUID, row["meeting_id"]),
        company_id=cast(UUID, row["company_id"]),
        source_media_asset_id=cast(UUID, row["source_media_asset_id"]),
        current_job_id=cast(UUID, row["current_job_id"]),
        processing_status=cast(str, row["processing_status"]),
        transcript_status=cast(str, row["transcript_status"]),
        source=cast(str, row["source"]),
        version=cast(int, row["version"]),
        lead_id=cast(UUID | None, row.get("lead_id")),
        primary_contact_id=cast(UUID | None, row.get("primary_contact_id")),
        owner_user_id=cast(UUID | None, row.get("owner_user_id")),
        normalized_audio_asset_id=cast(UUID | None, row.get("normalized_audio_asset_id")),
        title=cast(str | None, row.get("title")),
        meeting_started_at=cast(datetime | None, row.get("meeting_started_at")),
        duration_seconds=cast(float | None, row.get("duration_seconds")),
        transcript_text=cast(str | None, row.get("transcript_text")),
        transcript_language=cast(str | None, row.get("transcript_language")),
        transcript_provider=cast(str | None, row.get("transcript_provider")),
        summary_payload=cast(dict[str, object] | None, row.get("summary_payload")),
        summary_schema_version=cast(int, row.get("summary_schema_version", 1)),
        summary_prompt_version=cast(str | None, row.get("summary_prompt_version")),
        summary_model=cast(str | None, row.get("summary_model")),
        error_code=cast(str | None, row.get("error_code")),
        error_message=cast(str | None, row.get("error_message")),
        created_at=cast(datetime, row["created_at"]),
        updated_at=cast(datetime, row["updated_at"]),
        deleted_at=cast(datetime | None, row.get("deleted_at")),
    )


def _segment_from_row(row: dict[str, object]) -> MeetingSegment:
    return MeetingSegment(
        company_id=cast(UUID, row["company_id"]),
        meeting_id=cast(UUID, row["meeting_id"]),
        sequence_no=cast(int, row["sequence_no"]),
        start_seconds=cast(float, row["start_seconds"]),
        end_seconds=cast(float, row["end_seconds"]),
        transcript_text=cast(str, row["transcript_text"]),
        speaker_id=cast(str | None, row.get("speaker_id")),
        speaker_label=cast(str | None, row.get("speaker_label")),
        speaker_contact_id=cast(UUID | None, row.get("speaker_contact_id")),
        confidence=cast(float | None, row.get("confidence")),
    )


# ── Repository ──

class PostgresMeetingRepository(MeetingRepository):
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    @property
    def connection(self) -> Connection:
        return self._connection

    # ── Media asset ──

    def insert_media_asset(
        self,
        company_id: UUID | None,
        asset_kind: str,
        storage_backend: str,
        storage_key: str,
        original_filename: str | None,
        mime_type: str,
        size_bytes: int,
        sha256_val: str,
        created_by: UUID | None,
    ) -> MediaAsset:
        asset_id = uuid4()
        now = datetime.now(timezone.utc)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                INSERT INTO ltc.media_asset
                    (media_asset_id, company_id, asset_kind, storage_backend,
                     storage_key, original_filename, mime_type, size_bytes, sha256,
                     status, validation_payload, created_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'ready','{{}}'::jsonb,%s,%s)
                RETURNING {MEDIA_ASSET_COLUMNS}
                """,
                (asset_id, company_id, asset_kind, storage_backend,
                 storage_key, original_filename, mime_type, size_bytes, sha256_val,
                 created_by, now),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("INSERT media_asset returned no row")
        return _media_asset_from_row(row)

    def find_media_asset_by_id(self, media_asset_id: UUID) -> MediaAsset | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"SELECT {MEDIA_ASSET_COLUMNS} FROM ltc.media_asset WHERE media_asset_id = %s",
                (media_asset_id,),
            )
            row = cursor.fetchone()
        return _media_asset_from_row(row) if row else None

    # ── Meeting ──

    def insert_meeting(
        self,
        company_id: UUID,
        source_media_asset_id: UUID,
        current_job_id: UUID,
        owner_user_id: UUID | None,
        title: str | None,
        source: str,
    ) -> Meeting:
        meeting_id = uuid4()
        now = datetime.now(timezone.utc)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                INSERT INTO ltc.meeting
                    (meeting_id, company_id, source_media_asset_id, current_job_id,
                     owner_user_id, title, source, processing_status, transcript_status,
                     version, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'uploaded','pending',0,%s,%s)
                RETURNING {MEETING_COLUMNS}
                """,
                (meeting_id, company_id, source_media_asset_id, current_job_id,
                 owner_user_id, title, source, now, now),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("INSERT meeting returned no row")
            cursor.execute(
                "UPDATE ltc.job SET aggregate_type='meeting', aggregate_id=%s WHERE job_id=%s",
                (meeting_id, current_job_id),
            )
        return _meeting_from_row(row)

    def find_meeting_by_id(self, meeting_id: UUID) -> Meeting | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"SELECT {MEETING_COLUMNS} FROM ltc.meeting WHERE meeting_id = %s",
                (meeting_id,),
            )
            row = cursor.fetchone()
        return _meeting_from_row(row) if row else None

    def find_meeting_by_id_for_update(self, meeting_id: UUID) -> Meeting | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"SELECT {MEETING_COLUMNS} FROM ltc.meeting WHERE meeting_id = %s FOR UPDATE",
                (meeting_id,),
            )
            row = cursor.fetchone()
        return _meeting_from_row(row) if row else None

    def soft_delete_meeting(self, meeting_id: UUID, owner_user_id: UUID) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ltc.meeting
                SET deleted_at = clock_timestamp(),
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE meeting_id = %s
                  AND owner_user_id = %s
                  AND deleted_at IS NULL
                RETURNING meeting_id
                """,
                (meeting_id, owner_user_id),
            )
            return cursor.fetchone() is not None

    def update_meeting_transcript(
        self,
        meeting_id: UUID,
        expected_version: int,
        transcript_text: str,
        transcript_language: str | None,
        transcript_provider: str | None,
        transcript_status: str,
        duration_seconds: float | None,
    ) -> Meeting | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.meeting
                SET transcript_text = %s,
                    transcript_language = %s,
                    transcript_provider = %s,
                    transcript_status = %s,
                    duration_seconds = COALESCE(%s, duration_seconds),
                    processing_status = CASE
                        WHEN processing_status = 'transcribing' THEN 'summarizing'
                        ELSE processing_status
                    END,
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE meeting_id = %s AND version = %s
                RETURNING {MEETING_COLUMNS}
                """,
                (transcript_text, transcript_language, transcript_provider,
                 transcript_status, duration_seconds,
                 meeting_id, expected_version),
            )
            row = cursor.fetchone()
            if row is None:
                return None  # version conflict
        return _meeting_from_row(row)

    def update_meeting_summary(
        self,
        meeting_id: UUID,
        expected_version: int,
        summary_payload: dict[str, object],
        summary_prompt_version: str | None,
        summary_model: str | None,
    ) -> Meeting | None:
        import json as _json
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.meeting
                SET summary_payload = %s::jsonb,
                    summary_prompt_version = %s,
                    summary_model = %s,
                    processing_status = 'completed',
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE meeting_id = %s AND version = %s
                RETURNING {MEETING_COLUMNS}
                """,
                (_json.dumps(summary_payload, ensure_ascii=False),
                 summary_prompt_version, summary_model,
                 meeting_id, expected_version),
            )
            row = cursor.fetchone()
            if row is None:
                return None
        return _meeting_from_row(row)

    def update_meeting_status(
        self,
        meeting_id: UUID,
        expected_version: int,
        processing_status: str,
        error_code: str | None,
        error_message: str | None,
    ) -> Meeting | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.meeting
                SET processing_status = %s,
                    error_code = %s,
                    error_message = %s,
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE meeting_id = %s AND version = %s
                RETURNING {MEETING_COLUMNS}
                """,
                (processing_status, error_code, error_message, meeting_id, expected_version),
            )
            row = cursor.fetchone()
            if row is None:
                return None
        return _meeting_from_row(row)

    def set_normalized_audio_asset(
        self,
        meeting_id: UUID,
        expected_version: int,
        normalized_audio_asset_id: UUID,
    ) -> Meeting | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE ltc.meeting
                SET normalized_audio_asset_id = %s,
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE meeting_id = %s AND version = %s
                RETURNING {MEETING_COLUMNS}
                """,
                (normalized_audio_asset_id, meeting_id, expected_version),
            )
            row = cursor.fetchone()
            if row is None:
                return None
        return _meeting_from_row(row)

    def list_meetings(
        self,
        owner_user_id: UUID | None,
        company_id: UUID | None,
        processing_status: str | None,
        cursor: tuple[str, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        predicates = ["m.deleted_at IS NULL"]
        params: list[object] = []

        if owner_user_id is not None:
            predicates.append("m.owner_user_id = %s")
            params.append(owner_user_id)
        if company_id is not None:
            predicates.append("m.company_id = %s")
            params.append(company_id)
        if processing_status is not None:
            predicates.append("m.processing_status = %s")
            params.append(processing_status)
        if cursor is not None:
            predicates.append("(m.created_at, m.meeting_id) < (%s, %s)")
            params.extend(cursor)

        params.append(limit)

        with self._connection.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT m.meeting_id, m.company_id, m.title, m.source,
                       m.processing_status, m.transcript_status,
                       m.duration_seconds, m.meeting_started_at,
                       m.owner_user_id, m.version,
                       m.summary_payload,
                       m.next_step, m.decisions, m.risks, m.keywords,
                       m.error_code, m.error_message,
                       m.created_at, m.updated_at,
                       c.company_name
                FROM ltc.meeting m
                JOIN ltc.company c ON c.company_id = m.company_id
                WHERE {' AND '.join(predicates)}
                ORDER BY m.created_at DESC, m.meeting_id DESC
                LIMIT %s
                """,
                params,
            )
            return list(cur.fetchall())

    # ── Meeting segments ──

    def replace_segments(self, meeting_id: UUID, company_id: UUID, segments: list[MeetingSegment]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM ltc.meeting_segment WHERE meeting_id = %s",
                (meeting_id,),
            )
        with self._connection.cursor() as cursor:
            for seg in segments:
                cursor.execute(
                    """
                    INSERT INTO ltc.meeting_segment
                        (company_id, meeting_id, sequence_no, start_seconds, end_seconds,
                         speaker_id, speaker_label, speaker_contact_id,
                         transcript_text, confidence)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (company_id, meeting_id, seg.sequence_no, seg.start_seconds, seg.end_seconds,
                     seg.speaker_id, seg.speaker_label, seg.speaker_contact_id,
                     seg.transcript_text, seg.confidence),
                )

    def list_segments(self, meeting_id: UUID) -> list[MeetingSegment]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                SELECT {MEETING_SEGMENT_COLUMNS}
                FROM ltc.meeting_segment
                WHERE meeting_id = %s
                ORDER BY sequence_no
                """,
                (meeting_id,),
            )
            return [_segment_from_row(row) for row in cursor.fetchall()]

    # ── Job ──

    def insert_job(
        self,
        job_type: str,
        queue_name: str,
        status: str,
        priority: int,
        payload: dict[str, str] | None = None,
    ) -> UUID:
        job_id = uuid4()
        now = datetime.now(timezone.utc)
        # Use 'queued' status (not 'running') — the job table CHECK constraint
        # requires locked_by/lock_token/locked_until when status='running',
        # and 'queued' is the correct initial status for later worker pickup.
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO ltc.job
                    (job_id, job_type, queue_name, status, priority,
                     payload, progress_percent, attempt_count, max_attempts,
                     run_after, created_at, updated_at, version)
                VALUES (%s,%s,%s,%s,%s,%s,0,0,3,%s,%s,%s,0)
                RETURNING job_id
                """,
                (job_id, job_type, queue_name, status, priority, Jsonb(payload or {}), now, now, now),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("INSERT job returned no row")
        return cast(UUID, row["job_id"])

    def complete_job(self, job_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE ltc.job
                SET status = 'succeeded',
                    progress_percent = 100,
                    completed_at = %s,
                    updated_at = %s,
                    version = version + 1
                WHERE job_id = %s
                """,
                (now, now, job_id),
            )


# ── Unit of Work ──

class PostgresMeetingUnitOfWork:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    @contextmanager
    def transaction(self) -> Iterator[PostgresMeetingRepository]:
        with self._database.transaction() as connection:
            yield PostgresMeetingRepository(connection)
