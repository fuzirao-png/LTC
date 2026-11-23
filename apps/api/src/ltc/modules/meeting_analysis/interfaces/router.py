"""Meeting Analysis HTTP interfaces."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.meeting_analysis.application.meeting_service import MeetingService
from ltc.modules.meeting_analysis.domain.errors import (
    InvalidMeetingStateError,
    MeetingError,
    MeetingNotFoundError,
    MeetingVersionConflictError,
)
from ltc.modules.meeting_analysis.domain.models import Meeting, MeetingSegment
from ltc.modules.meeting_analysis.domain.ports import MeetingRepository
from ltc.modules.meeting_analysis.infrastructure.postgres_repository import (
    PostgresMeetingRepository,
    PostgresMeetingUnitOfWork,
)  # noqa: FORBIDDEN_LAYER — wire-up at composition root
from ltc.platform.observability.tracing import trace_context

router = APIRouter(prefix="/meetings", tags=["meeting-analysis"])


# ── Pydantic DTOs ──

class SegmentResponse(BaseModel):
    sequence_no: int
    start_seconds: float
    end_seconds: float
    transcript_text: str
    speaker_id: str | None = None
    speaker_label: str | None = None
    confidence: float | None = None


class MeetingSummaryData(BaseModel):
    customer_needs: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    action_items: list[dict[str, object]] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    next_step: str | None = None


class MeetingResponse(BaseModel):
    meeting_id: UUID
    company_id: UUID
    title: str | None
    source: str
    processing_status: str
    transcript_status: str
    duration_seconds: float | None
    meeting_started_at: datetime | None
    transcript_text: str | None
    summary: MeetingSummaryData | None
    next_step: str | None
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    segments: list[SegmentResponse] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_meeting(
        cls,
        meeting: Meeting,
        segments: list[MeetingSegment] | None = None,
    ) -> "MeetingResponse":
        summary = None
        if meeting.summary_payload:
            summary = MeetingSummaryData(**meeting.summary_payload)
        return cls(
            meeting_id=meeting.meeting_id,
            company_id=meeting.company_id,
            title=meeting.title,
            source=meeting.source,
            processing_status=meeting.processing_status,
            transcript_status=meeting.transcript_status,
            duration_seconds=meeting.duration_seconds,
            meeting_started_at=meeting.meeting_started_at,
            transcript_text=meeting.transcript_text,
            summary=summary,
            next_step=meeting.next_step,
            decisions=meeting.decisions,
            risks=meeting.risks,
            keywords=meeting.keywords,
            segments=[
                SegmentResponse(
                    sequence_no=s.sequence_no,
                    start_seconds=s.start_seconds,
                    end_seconds=s.end_seconds,
                    transcript_text=s.transcript_text,
                    speaker_id=s.speaker_id,
                    speaker_label=s.speaker_label,
                    confidence=s.confidence,
                )
                for s in (segments or [])
            ],
            error_code=meeting.error_code,
            error_message=meeting.error_message,
            version=meeting.version,
            created_at=meeting.created_at or datetime.utcnow(),
            updated_at=meeting.updated_at or datetime.utcnow(),
        )


class MeetingListItem(BaseModel):
    meeting_id: UUID
    company_id: UUID
    company_name: str
    title: str | None
    processing_status: str
    transcript_status: str
    duration_seconds: float | None
    next_step: str | None
    created_at: datetime


class MeetingListResponse(BaseModel):
    request_id: UUID
    data: list[MeetingListItem]
    page: dict[str, Any] = Field(default_factory=lambda: {"next_cursor": None, "has_more": False})


class MeetingEnvelope(BaseModel):
    request_id: UUID
    data: MeetingResponse


class UploadResponse(BaseModel):
    request_id: UUID
    data: dict[str, object]


# ── Service resolution ──

def _service(request: Request) -> MeetingService:
    return request.app.state.meeting_service


def _repository(request: Request) -> PostgresMeetingUnitOfWork:
    return request.app.state.meeting_uow


# ── Endpoints ──

@router.post("/upload", response_model=UploadResponse)
def upload_meeting(
    request: Request,
    file: UploadFile = File(...),
    company_id: UUID = Form(...),
    title: str | None = Form(default=None),
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> UploadResponse:
    """Upload a meeting recording (audio or video) and start async processing."""
    service = _service(request)
    uow = _repository(request)
    trace_metadata: dict[str, str] = {}
    trace_context.inject(trace_metadata)

    try:
        with uow.transaction() as repo:
            meeting = service.create_meeting(
                repository=repo,
                upload_file=file,
                company_id=company_id,
                owner_user_id=context.actor.user_id,
                title=title,
                actor=context.actor,
                trace_metadata=trace_metadata,
            )
    except MeetingError as exc:
        _raise_meeting_error(exc)

    return UploadResponse(
        request_id=uuid4(),
        data={
            "meeting_id": str(meeting.meeting_id),
            "status": meeting.processing_status,
        },
    )


@router.get("/{meeting_id}", response_model=MeetingEnvelope)
def get_meeting(
    meeting_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> MeetingEnvelope:
    """Get meeting details including transcript, summary, and segments."""
    service = _service(request)
    uow = _repository(request)

    try:
        with uow.transaction() as repo:
            meeting, segments = service.get_meeting_with_segments(repo, meeting_id)
    except MeetingError as exc:
        _raise_meeting_error(exc)

    return MeetingEnvelope(
        request_id=uuid4(),
        data=MeetingResponse.from_meeting(meeting, segments),
    )


@router.get("/{meeting_id}/audio", response_class=FileResponse)
def get_meeting_audio(
    meeting_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> FileResponse:
    """Stream the original uploaded meeting media for an authorized user."""
    service = _service(request)
    uow = _repository(request)

    try:
        with uow.transaction() as repo:
            meeting, _ = service.get_meeting_with_segments(repo, meeting_id)
            asset = repo.find_media_asset_by_id(meeting.source_media_asset_id)
    except MeetingError as exc:
        _raise_meeting_error(exc)

    if asset is None or asset.storage_backend != "local":
        raise HTTPException(status_code=404, detail="Meeting media not found")
    media_path = Path(asset.storage_key)
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Meeting media file not found")
    return FileResponse(
        media_path,
        media_type=asset.mime_type,
        filename=asset.original_filename or media_path.name,
        content_disposition_type="inline",
    )


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_meeting(
    meeting_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> Response:
    """Soft-delete a meeting owned by the current user."""
    service = _service(request)
    uow = _repository(request)

    try:
        with uow.transaction() as repo:
            service.delete_meeting(repo, meeting_id, context.actor.user_id)
    except MeetingError as exc:
        _raise_meeting_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    request: Request,
    company_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, alias="processing_status"),
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> MeetingListResponse:
    """List meetings visible to the current user."""
    service = _service(request)
    uow = _repository(request)

    with uow.transaction() as repo:
        rows = service.list_meetings(
            repo,
            owner_user_id=context.actor.user_id,
            company_id=company_id,
            processing_status=status,
            limit=limit + 1,
        )

    has_more = len(rows) > limit
    items = [
        MeetingListItem(
            meeting_id=cast(UUID, row["meeting_id"]) if isinstance(row["meeting_id"], str) else row["meeting_id"],
            company_id=cast(UUID, row["company_id"]) if isinstance(row["company_id"], str) else row["company_id"],
            company_name=str(row.get("company_name", "")),
            title=cast(str | None, row.get("title")),
            processing_status=str(row.get("processing_status", "")),
            transcript_status=str(row.get("transcript_status", "")),
            duration_seconds=cast(float | None, row.get("duration_seconds")),
            next_step=cast(str | None, row.get("next_step")),
            created_at=cast(datetime, row.get("created_at", datetime.utcnow())),
        )
        for row in rows[:limit]
    ]

    return MeetingListResponse(
        request_id=uuid4(),
        data=items,
        page={"next_cursor": None, "has_more": has_more},
    )


# ── Error mapping ──

def _raise_meeting_error(error: MeetingError) -> None:
    if isinstance(error, MeetingNotFoundError):
        raise HTTPException(status_code=404, detail={"code": "MEETING_NOT_FOUND", "message": str(error)}) from error
    if isinstance(error, MeetingVersionConflictError):
        raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT", "message": str(error)}) from error
    if isinstance(error, InvalidMeetingStateError):
        raise HTTPException(status_code=409, detail={"code": "INVALID_MEETING_STATE", "message": str(error)}) from error
    raise HTTPException(status_code=422, detail={"code": "MEETING_ERROR", "message": str(error)}) from error


def _cast(obj: object, cls: type) -> object:
    """Lightweight cast helper for dict row values."""
    return obj
