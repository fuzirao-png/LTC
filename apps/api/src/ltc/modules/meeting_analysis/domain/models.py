"""Framework-free Meeting Analysis domain values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID


# ── Status literals ──

ProcessingStatus = Literal[
    "uploaded", "queued", "extracting", "transcribing",
    "summarizing", "completed", "failed", "cancelled", "deleted",
]
TranscriptStatus = Literal["pending", "processing", "done", "failed", "cancelled"]
AssetKind = Literal[
    "search_content", "email_attachment", "meeting_source",
    "normalized_audio", "chunk", "export",
]
StorageBackend = Literal["local", "oss", "s3"]
AssetStatus = Literal["quarantined", "ready", "rejected", "deleted"]
MeetingSource = Literal["upload", "import"]


# ── Domain entities ──

@dataclass(frozen=True)
class MediaAsset:
    media_asset_id: UUID
    company_id: UUID | None
    parent_media_asset_id: UUID | None
    asset_kind: AssetKind
    storage_backend: StorageBackend
    storage_key: str
    original_filename: str | None
    mime_type: str
    size_bytes: int
    sha256: str
    status: AssetStatus
    validation_payload: dict[str, object] = field(default_factory=dict)
    retention_until: datetime | None = None
    deleted_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class MeetingSegment:
    company_id: UUID
    meeting_id: UUID
    sequence_no: int
    start_seconds: float
    end_seconds: float
    transcript_text: str
    speaker_id: str | None = None
    speaker_label: str | None = None
    speaker_contact_id: UUID | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Meeting:
    meeting_id: UUID
    company_id: UUID
    source_media_asset_id: UUID
    current_job_id: UUID
    processing_status: ProcessingStatus
    transcript_status: TranscriptStatus
    source: MeetingSource
    version: int
    lead_id: UUID | None = None
    primary_contact_id: UUID | None = None
    owner_user_id: UUID | None = None
    normalized_audio_asset_id: UUID | None = None
    title: str | None = None
    meeting_started_at: datetime | None = None
    duration_seconds: float | None = None
    transcript_text: str | None = None
    transcript_language: str | None = None
    transcript_provider: str | None = None
    summary_payload: dict[str, object] | None = None
    summary_schema_version: int = 1
    summary_prompt_version: str | None = None
    summary_model: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def next_step(self) -> str | None:
        if self.summary_payload is None:
            return None
        return self.summary_payload.get("next_step")  # type: ignore[return-value]

    @property
    def decisions(self) -> list[str]:
        if self.summary_payload is None:
            return []
        return self.summary_payload.get("decisions", [])  # type: ignore[return-value]

    @property
    def risks(self) -> list[str]:
        if self.summary_payload is None:
            return []
        return self.summary_payload.get("risks", [])  # type: ignore[return-value]

    @property
    def keywords(self) -> list[str]:
        if self.summary_payload is None:
            return []
        return self.summary_payload.get("keywords", [])  # type: ignore[return-value]

    @property
    def is_terminal(self) -> bool:
        return self.processing_status in ("completed", "failed", "cancelled", "deleted")
