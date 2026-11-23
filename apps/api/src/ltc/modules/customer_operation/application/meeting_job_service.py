import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ltc.modules.customer_operation.infrastructure.legacy_file_store import LegacyFileStore
from ltc.modules.customer_operation.application.meeting_analysis_client import MeetingAnalysisClient
from ltc.modules.customer_operation.infrastructure.meeting_store import PostgresMeetingStore


def _normalize_base64(value: str) -> str:
    text = str(value or "").strip()
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    return "".join(text.split())


def _extension(file_name: str, mime_type: str) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix:
        return suffix
    mime = (mime_type or "").lower()
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    if "wav" in mime:
        return ".wav"
    if "m4a" in mime or "mp4" in mime:
        return ".m4a"
    if "ogg" in mime:
        return ".ogg"
    return ".webm"


def build_meeting_job_response(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        "id": job.get("id"),
        "customerName": job.get("customerName"),
        "status": job.get("status"),
        "progress": int(job.get("progress") or 0),
        "message": job.get("message") or "",
        "createdAt": job.get("createdAt") or "",
        "startedAt": job.get("startedAt") or "",
        "completedAt": job.get("completedAt") or "",
        "errorMessage": job.get("errorMessage") or "",
        "transcriptProvider": job.get("transcriptProvider") or "",
        "recordId": job.get("recordId") or "",
    }


def get_meeting_job_response(job_id: str) -> dict[str, Any] | None:
    job = LegacyFileStore().get_meeting_job(job_id)
    return build_meeting_job_response(job)


def get_meeting_audio_path(record_id: str) -> Path | None:
    return LegacyFileStore().get_meeting_audio_path(record_id)


def _normalize_meeting_segments(segments: Any) -> list[dict[str, Any]]:
    if not isinstance(segments, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = segment.get("start", 0)
        end = segment.get("end", start)
        speaker = segment.get("speaker") or segment.get("speaker_id") or f"片段 {index + 1}"
        normalized.append(
            {
                "start": start,
                "end": end,
                "speaker": speaker,
                "speaker_id": segment.get("speaker_id"),
                "text": text,
            }
        )
    return normalized


def create_meeting_upload_job(payload: dict[str, Any]) -> dict[str, Any]:
    customer_name = str(payload.get("customerName") or "").strip()
    audio_bytes = payload.get("audioBytes")
    if not isinstance(audio_bytes, bytes):
        audio_base64 = _normalize_base64(str(payload.get("audioBase64") or ""))
        if not audio_base64:
            audio_bytes = b""
        else:
            audio_bytes = base64.b64decode(audio_base64)

    if not customer_name or not audio_bytes:
        raise ValueError("Missing required fields: customerName, audioBase64 or file")
    if not audio_bytes:
        raise ValueError("Audio content is empty.")

    legacy = LegacyFileStore()
    record_id = str(uuid4())
    job_id = str(uuid4())
    file_name = str(payload.get("fileName") or "meeting.webm").strip()
    mime_type = str(payload.get("mimeType") or "audio/webm").strip()
    stored_file_name = f"{record_id}{_extension(file_name, mime_type)}"
    stored_dir = legacy.meeting_audio_dir(customer_name)
    stored_dir.mkdir(parents=True, exist_ok=True)
    stored_file_path = stored_dir / stored_file_name
    stored_file_path.write_bytes(audio_bytes)

    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": job_id,
        "customerName": customer_name,
        "createdAt": now,
        "startedAt": "",
        "completedAt": "",
        "status": "queued",
        "progress": 10,
        "message": "录音已上传，正在排队生成会议纪要",
        "errorMessage": "",
        "recordId": record_id,
        "source": str(payload.get("source") or "upload").strip(),
        "companyId": str(payload.get("companyId") or payload.get("company_id") or "").strip(),
        "contactId": str(payload.get("contactId") or payload.get("contact_id") or "").strip(),
        "fileName": file_name,
        "storedFileName": stored_file_name,
        "mimeType": mime_type,
        "durationSeconds": max(0, float(payload.get("durationSeconds") or 0)),
        "browserTranscript": str(payload.get("transcript") or "").strip(),
        "incomingSegments": payload.get("segments") if isinstance(payload.get("segments"), list) else [],
        "incomingSummary": str(payload.get("summary") or "").strip(),
        "incomingActionItems": payload.get("actionItems") if isinstance(payload.get("actionItems"), list) else [],
        "storedFilePath": str(stored_file_path),
        "transcriptProvider": "",
    }
    legacy.save_meeting_job(job)
    return job


async def process_meeting_job(job_id: str) -> None:
    legacy = LegacyFileStore()
    job = legacy.get_meeting_job(job_id)
    if not job or job.get("status") in {"completed", "error"}:
        return

    job.update(
        {
            "status": "transcribing",
            "progress": 35,
            "startedAt": job.get("startedAt") or datetime.now(timezone.utc).isoformat(),
            "message": "正在转写会议内容",
            "errorMessage": "",
        }
    )
    legacy.save_meeting_job(job)

    try:
        result = await MeetingAnalysisClient().analyze_file(Path(job["storedFilePath"]))
        transcript = str(result.get("transcript") or job.get("browserTranscript") or "").strip()
        summary = str(result.get("summary") or job.get("incomingSummary") or "").strip()
        if not transcript:
            raise RuntimeError("会议分析未返回转写文本。")
        if not summary:
            raise RuntimeError("会议分析未返回会议摘要。")

        action_items = result.get("action_items") or result.get("actionItems") or job.get("incomingActionItems") or []
        segments = _normalize_meeting_segments(result.get("segments")) or _normalize_meeting_segments(
            job.get("incomingSegments")
        )
        record = {
            "id": job["recordId"],
            "customerName": job["customerName"],
            "title": "上传会议录音" if job.get("source") == "upload" else "实时会议录音",
            "source": job.get("source") or "upload",
            "fileName": result.get("file_name") or job.get("fileName"),
            "storedFileName": job.get("storedFileName"),
            "mimeType": job.get("mimeType"),
            "durationSeconds": result.get("duration_seconds") or job.get("durationSeconds") or 0,
            "createdAt": job.get("createdAt"),
            "audioUrl": f"/api/meeting/audio?id={job['recordId']}",
            "storage": "backend-disk",
            "storedFilePath": job.get("storedFilePath"),
            "transcript": transcript,
            "fullTranscript": transcript,
            "transcriptProvider": result.get("transcript_provider") or result.get("provider") or "customer-operation-agent",
            "segments": segments,
            "summary": summary,
            "actionItems": action_items,
            "engineMeta": {
                "service": "customer-operation-agent",
                "asrProvider": result.get("transcript_provider") or result.get("provider") or "",
                "decisions": result.get("decisions") or [],
                "risks": result.get("risks") or [],
                "keywords": result.get("keywords") or [],
            },
        }
        legacy.append_meeting_record(record)
        PostgresMeetingStore().record_completed_meeting(job=job, record=record, result=result)
        job.update(
            {
                "status": "completed",
                "progress": 100,
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "recordId": record["id"],
                "transcriptProvider": record["transcriptProvider"],
                "message": "会议纪要已生成，可在前端查看摘要、逐段对话和待办。",
            }
        )
        legacy.save_meeting_job(job)
    except Exception as exc:
        job.update(
            {
                "status": "error",
                "progress": 100,
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "errorMessage": str(exc),
                "message": "会议录音处理失败，请检查会议分析和模型配置。",
            }
        )
        legacy.save_meeting_job(job)



