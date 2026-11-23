"""Ports used by Meeting Analysis application services."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from ltc.modules.meeting_analysis.domain.models import Meeting, MeetingSegment, MediaAsset


# ── Audio / ASR / Summary ports ──

class AudioProcessorPort(Protocol):
    """FFmpeg-based audio processing."""
    def extract_audio_from_video(self, video_path: str, target_dir: str) -> str: ...
    def normalize_audio(self, source_path: str, target_dir: str) -> str: ...
    def split_audio(self, source_path: str, target_dir: str, chunk_seconds: int) -> list[str]: ...
    def probe_duration(self, source_path: str) -> float: ...


class AsrPort(Protocol):
    """OpenAI-compatible speech-to-text."""
    def transcribe(self, file_path: str) -> str: ...
    def transcribe_many(self, file_paths: list[str]) -> str: ...


class SummaryPort(Protocol):
    """LLM-based meeting summarization."""
    def summarize(self, transcript: str) -> dict[str, object]: ...


# ── Repository port ──

class MeetingRepository(Protocol):
    @property
    def connection(self) -> object: ...

    # Media asset
    def insert_media_asset(
        self,
        company_id: UUID | None,
        asset_kind: str,
        storage_backend: str,
        storage_key: str,
        original_filename: str | None,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        created_by: UUID | None,
    ) -> MediaAsset: ...

    def find_media_asset_by_id(self, media_asset_id: UUID) -> MediaAsset | None: ...

    # Meeting
    def insert_meeting(
        self,
        company_id: UUID,
        source_media_asset_id: UUID,
        current_job_id: UUID,
        owner_user_id: UUID | None,
        title: str | None,
        source: str,
    ) -> Meeting: ...

    def find_meeting_by_id(self, meeting_id: UUID) -> Meeting | None: ...
    def find_meeting_by_id_for_update(self, meeting_id: UUID) -> Meeting | None: ...

    def soft_delete_meeting(self, meeting_id: UUID, owner_user_id: UUID) -> bool: ...

    def update_meeting_transcript(
        self,
        meeting_id: UUID,
        expected_version: int,
        transcript_text: str,
        transcript_language: str | None,
        transcript_provider: str | None,
        transcript_status: str,
        duration_seconds: float | None,
    ) -> Meeting | None: ...

    def update_meeting_summary(
        self,
        meeting_id: UUID,
        expected_version: int,
        summary_payload: dict[str, object],
        summary_prompt_version: str | None,
        summary_model: str | None,
    ) -> Meeting | None: ...

    def update_meeting_status(
        self,
        meeting_id: UUID,
        expected_version: int,
        processing_status: str,
        error_code: str | None,
        error_message: str | None,
    ) -> Meeting | None: ...

    def set_normalized_audio_asset(
        self,
        meeting_id: UUID,
        expected_version: int,
        normalized_audio_asset_id: UUID,
    ) -> Meeting | None: ...

    def list_meetings(
        self,
        owner_user_id: UUID | None,
        company_id: UUID | None,
        processing_status: str | None,
        cursor: tuple[str, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]: ...

    # Meeting segments
    def replace_segments(self, meeting_id: UUID, company_id: UUID, segments: list[MeetingSegment]) -> None: ...

    def list_segments(self, meeting_id: UUID) -> list[MeetingSegment]: ...

    # Job
    def insert_job(
        self,
        job_type: str,
        queue_name: str,
        status: str,
        priority: int,
        payload: dict[str, str] | None = None,
    ) -> UUID: ...

    def complete_job(self, job_id: UUID) -> None: ...


class MeetingUnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[MeetingRepository]: ...
