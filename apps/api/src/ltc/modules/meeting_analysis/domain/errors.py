"""Meeting Analysis bounded-context errors."""

from __future__ import annotations


class MeetingError(RuntimeError):
    """Base error for the Meeting Analysis bounded context."""


class MeetingNotFoundError(MeetingError):
    """The requested meeting does not exist."""


class MediaAssetNotFoundError(MeetingError):
    """The requested media asset does not exist."""


class MeetingVersionConflictError(MeetingError):
    """Optimistic lock failure — meeting version mismatch."""


class InvalidMeetingStateError(MeetingError):
    """The meeting is not in a state that allows this operation."""


class AudioProcessingError(MeetingError):
    """FFmpeg audio processing failed."""


class MediaExtractionError(MeetingError):
    """FFmpeg media extraction failed."""


class AsrTranscriptionError(MeetingError):
    """ASR transcription failed after retries."""


class SummaryGenerationError(MeetingError):
    """LLM summary generation failed."""


class InvalidMediaFileError(MeetingError):
    """Uploaded file is not an allowed media format or exceeds size limits."""


class FileValidationError(MeetingError):
    """File validation failed (corrupt file, wrong format, etc.)."""
