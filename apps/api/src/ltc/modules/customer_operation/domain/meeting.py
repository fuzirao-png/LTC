from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


TranscriptStatus = Literal["pending", "transcribing", "transcribed", "failed"]


@dataclass(frozen=True)
class Meeting:
    meeting_id: UUID
    company_id: UUID
    title: str | None
    meeting_time: datetime
    duration_seconds: int
    audio_url: str | None
    transcript_status: TranscriptStatus
    transcript: str | None
    summary: dict[str, Any] | None
    asr_provider: str | None
    summary_model: str | None
    version: int
    created_at: datetime
    updated_at: datetime





