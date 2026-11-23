"""Unit tests for the Meeting Analysis module.

Tests domain logic, application service, and file validation using
fake in-memory implementations of the Protocol ports — no database required.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from uuid import UUID, uuid4

from ltc.modules.meeting_analysis.domain.errors import (
    AudioProcessingError,
    FileValidationError,
    InvalidMeetingStateError,
    MeetingError,
    MeetingNotFoundError,
    MeetingVersionConflictError,
    SummaryGenerationError,
)
from ltc.modules.meeting_analysis.domain.models import Meeting, MeetingSegment, MediaAsset
from ltc.modules.meeting_analysis.application.meeting_service import MeetingService, _build_segments, _guess_chunk_duration
from ltc.modules.meeting_analysis.infrastructure.file_handler import (
    is_allowed_media_file,
    is_audio_file,
    is_video_file,
)
from ltc.modules.meeting_analysis.infrastructure.summary_adapter import SummaryAdapter
from ltc.modules.meeting_analysis.infrastructure.text_normalizer import (
    to_simplified_text,
    normalize_to_simplified,
)


# ── Fixtures ──

COMPANY_ID = uuid4()
OWNER_ID = uuid4()
NOW_STR = "2026-07-23T10:00:00+00:00"


def make_meeting(**overrides: object) -> Meeting:
    import datetime
    values: dict[str, object] = {
        "meeting_id": uuid4(),
        "company_id": COMPANY_ID,
        "source_media_asset_id": uuid4(),
        "current_job_id": uuid4(),
        "processing_status": "uploaded",
        "transcript_status": "pending",
        "source": "upload",
        "version": 0,
        "lead_id": None,
        "primary_contact_id": None,
        "owner_user_id": OWNER_ID,
        "title": "Test Meeting",
        "duration_seconds": None,
        "transcript_text": None,
        "summary_payload": None,
        "created_at": datetime.datetime(2026, 7, 23, 10, 0, 0),
        "updated_at": datetime.datetime(2026, 7, 23, 10, 0, 0),
    }
    values.update(overrides)
    return Meeting(**values)


def make_media_asset(**overrides: object) -> MediaAsset:
    values: dict[str, object] = {
        "media_asset_id": uuid4(),
        "company_id": COMPANY_ID,
        "parent_media_asset_id": None,
        "asset_kind": "meeting_source",
        "storage_backend": "local",
        "storage_key": "/tmp/ltc/test.wav",
        "original_filename": "test.wav",
        "mime_type": "audio/wav",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "status": "ready",
    }
    values.update(overrides)
    return MediaAsset(**values)


class SummaryAdapterTests(unittest.TestCase):
    def test_unconfigured_adapter_uses_transcript_as_core_summary(self) -> None:
        adapter = SummaryAdapter(api_key="", base_url="")

        result = adapter.summarize("  First sentence.\n\nSecond sentence.  ")

        self.assertEqual(result["core_summary"], "First sentence. Second sentence.")
        self.assertEqual(result["customer_needs"], [])

    def test_missing_model_core_summary_uses_transcript_fallback(self) -> None:
        result = SummaryAdapter._fill_defaults(
            {"customer_needs": ["Need A"], "core_summary": ""},
            "Transcript fallback",
        )

        self.assertEqual(result["core_summary"], "Transcript fallback")
        self.assertEqual(result["customer_needs"], ["Need A"])


# ── Fake Ports ──

class FakeAudioProcessor:
    """In-memory audio processor — no ffmpeg needed."""
    def __init__(self) -> None:
        self.extract_calls: list[tuple[str, str]] = []
        self.normalize_calls: list[tuple[str, str]] = []
        self.split_calls: list[tuple[str, str, int]] = []
        self.probe_calls: list[str] = []
        self._extracted_path = "/tmp/ltc/fake_extracted.mp3"
        self._normalized_path = "/tmp/ltc/fake_norm.wav"
        self._chunks = ["/tmp/ltc/fake_chunk_0.wav"]
        self._duration = 120.0
        self._fail = False

    def extract_audio_from_video(self, video_path: str, target_dir: str) -> str:
        self.extract_calls.append((video_path, target_dir))
        if self._fail:
            raise AudioProcessingError("ffmpeg extract failed")
        return self._extracted_path

    def normalize_audio(self, source_path: str, target_dir: str) -> str:
        self.normalize_calls.append((source_path, target_dir))
        if self._fail:
            raise AudioProcessingError("ffmpeg normalize failed")
        return self._normalized_path

    def split_audio(self, source_path: str, target_dir: str, chunk_seconds: int = 60) -> list[str]:
        self.split_calls.append((source_path, target_dir, chunk_seconds))
        if self._fail:
            raise AudioProcessingError("ffmpeg split failed")
        return self._chunks

    def probe_duration(self, source_path: str) -> float:
        self.probe_calls.append(source_path)
        return self._duration


class FakeAsrService:
    """Fake ASR that returns canned transcript text."""
    def __init__(self) -> None:
        self.transcribe_calls: list[tuple[str,]] = []
        self.transcript = "会议讨论内容：客户表示对新产品很感兴趣。"
        self._fail = False

    def transcribe(self, file_path: str) -> str:
        self.transcribe_calls.append((file_path,))
        if self._fail:
            from ltc.modules.meeting_analysis.domain.errors import AsrTranscriptionError
            raise AsrTranscriptionError("ASR failed")
        return self.transcript

    def transcribe_many(self, file_paths: list[str]) -> str:
        parts = [self.transcribe(path) for path in file_paths]
        return "\n".join(parts)


class FakeSummaryService:
    """Fake LLM summarizer that returns a valid v1 summary."""
    def __init__(self) -> None:
        self.model_name = "gpt-5.6-terra"
        self.summarize_calls: list[str] = []
        self.summary: dict[str, object] = {
            "customer_needs": ["降低成本", "提高效率"],
            "pain_points": ["现有系统维护成本高"],
            "buying_signals": ["客户询问报价"],
            "action_items": [{"task": "发送报价", "owner": "销售", "due_at": "2026-07-30T00:00:00Z"}],
            "decisions": ["下周进行产品演示"],
            "risks": ["竞争对手也在跟进"],
            "keywords": ["成本", "效率", "报价"],
            "next_step": "安排产品演示并发送报价单",
        }
        self._fail = False

    def summarize(self, transcript: str) -> dict[str, object]:
        self.summarize_calls.append(transcript)
        if self._fail:
            raise SummaryGenerationError("LLM summary failed")
        return self.summary


class FakeMeetingRepository:
    """In-memory repository implementing MeetingRepository protocol."""

    def __init__(self) -> None:
        self.meetings: dict[UUID, Meeting] = {}
        self.assets: dict[UUID, MediaAsset] = {}
        self.segments: dict[UUID, list[MeetingSegment]] = {}
        self.jobs: list[UUID] = []
        self.completed_jobs: list[UUID] = []
        # Counters for assertions
        self.insert_meeting_count = 0
        self.insert_asset_count = 0
        self.insert_job_count = 0

    @property
    def connection(self) -> object:
        return self

    def insert_media_asset(self, company_id, asset_kind, storage_backend, storage_key,
                           original_filename, mime_type, size_bytes, sha256_val, created_by) -> MediaAsset:
        asset = MediaAsset(
            media_asset_id=uuid4(),
            company_id=company_id,
            parent_media_asset_id=None,
            asset_kind=asset_kind,
            storage_backend=storage_backend,
            storage_key=storage_key,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256_val,
            status="ready",
            created_by=created_by,
        )
        self.assets[asset.media_asset_id] = asset
        self.insert_asset_count += 1
        return asset

    def find_media_asset_by_id(self, media_asset_id):
        return self.assets.get(media_asset_id)

    def insert_meeting(self, company_id, source_media_asset_id, current_job_id,
                       owner_user_id, title, source) -> Meeting:
        import datetime
        meeting = Meeting(
            meeting_id=uuid4(),
            company_id=company_id,
            source_media_asset_id=source_media_asset_id,
            current_job_id=current_job_id,
            processing_status="uploaded",
            transcript_status="pending",
            source=source,
            version=0,
            owner_user_id=owner_user_id,
            title=title,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.meetings[meeting.meeting_id] = meeting
        self.insert_meeting_count += 1
        return meeting

    def find_meeting_by_id(self, meeting_id):
        return self.meetings.get(meeting_id)

    def find_meeting_by_id_for_update(self, meeting_id):
        return self.meetings.get(meeting_id)

    def soft_delete_meeting(self, meeting_id, owner_user_id):
        import dataclasses
        import datetime

        meeting = self.meetings.get(meeting_id)
        if meeting is None or meeting.owner_user_id != owner_user_id or meeting.deleted_at is not None:
            return False
        self.meetings[meeting_id] = dataclasses.replace(
            meeting,
            deleted_at=datetime.datetime.now(datetime.timezone.utc),
            version=meeting.version + 1,
        )
        return True

    def update_meeting_transcript(self, meeting_id, expected_version, transcript_text,
                                  transcript_language, transcript_provider, transcript_status,
                                  duration_seconds):
        m = self.meetings.get(meeting_id)
        if m is None or m.version != expected_version:
            return None
        import dataclasses
        self.meetings[meeting_id] = dataclasses.replace(
            m,
            transcript_text=transcript_text,
            transcript_language=transcript_language,
            transcript_provider=transcript_provider,
            transcript_status=transcript_status,
            duration_seconds=duration_seconds or m.duration_seconds,
            processing_status="summarizing" if m.processing_status == "transcribing" else m.processing_status,
            version=m.version + 1,
        )
        return self.meetings[meeting_id]

    def update_meeting_summary(self, meeting_id, expected_version, summary_payload,
                               summary_prompt_version, summary_model):
        m = self.meetings.get(meeting_id)
        if m is None or m.version != expected_version:
            return None
        import dataclasses
        self.meetings[meeting_id] = dataclasses.replace(
            m,
            summary_payload=summary_payload,
            summary_prompt_version=summary_prompt_version,
            summary_model=summary_model,
            processing_status="completed",
            version=m.version + 1,
        )
        return self.meetings[meeting_id]

    def update_meeting_status(self, meeting_id, expected_version, processing_status,
                              error_code, error_message):
        m = self.meetings.get(meeting_id)
        if m is None or m.version != expected_version:
            return None
        import dataclasses
        self.meetings[meeting_id] = dataclasses.replace(
            m,
            processing_status=processing_status,
            error_code=error_code,
            error_message=error_message,
            version=m.version + 1,
        )
        return self.meetings[meeting_id]

    def set_normalized_audio_asset(self, meeting_id, expected_version, normalized_audio_asset_id):
        m = self.meetings.get(meeting_id)
        if m is None or m.version != expected_version:
            return None
        import dataclasses
        self.meetings[meeting_id] = dataclasses.replace(
            m,
            normalized_audio_asset_id=normalized_audio_asset_id,
            version=m.version + 1,
        )
        return self.meetings[meeting_id]

    def list_meetings(self, owner_user_id, company_id, processing_status, cursor, limit):
        result = [
            {
                "meeting_id": m.meeting_id,
                "company_id": m.company_id,
                "company_name": "Test Corp",
                "title": m.title,
                "processing_status": m.processing_status,
                "transcript_status": m.transcript_status,
                "duration_seconds": m.duration_seconds,
                "next_step": None,
                "created_at": m.created_at,
            }
            for m in self.meetings.values()
        ]
        # Apply filters
        if owner_user_id is not None:
            result = [r for m in self.meetings.values() if m.owner_user_id == owner_user_id
                      for r in [next(x for x in result if x["meeting_id"] == m.meeting_id)]]
        if company_id is not None:
            result = [r for r in result if r["company_id"] == company_id]
        return result[:limit]

    def replace_segments(self, meeting_id, company_id, segments):
        self.segments[meeting_id] = segments

    def list_segments(self, meeting_id):
        return self.segments.get(meeting_id, [])

    def insert_job(self, job_type, queue_name, status, priority, payload=None):
        job_id = uuid4()
        self.jobs.append(job_id)
        self.insert_job_count += 1
        return job_id

    def complete_job(self, job_id):
        self.completed_jobs.append(job_id)


class FakeMeetingUnitOfWork:
    def __init__(self, repository: FakeMeetingRepository) -> None:
        self.repository = repository

    @contextmanager
    def transaction(self):
        yield self.repository


# ── Tests ──

class DomainModelsTests(unittest.TestCase):
    """Test domain model logic (properties, status checks, etc.)."""

    def test_meeting_is_terminal_recognises_terminal_states(self) -> None:
        for state in ("completed", "failed", "cancelled", "deleted"):
            m = make_meeting(processing_status=state)
            self.assertTrue(m.is_terminal, f"processing_status={state!r} should be terminal")

    def test_meeting_is_terminal_rejects_active_states(self) -> None:
        for state in ("uploaded", "queued", "extracting", "transcribing", "summarizing"):
            m = make_meeting(processing_status=state)
            self.assertFalse(m.is_terminal, f"processing_status={state!r} should NOT be terminal")

    def test_meeting_next_step_extracts_from_summary_payload(self) -> None:
        m = make_meeting(summary_payload={"next_step": "给客户发邮件"})
        self.assertEqual(m.next_step, "给客户发邮件")

    def test_meeting_next_step_returns_none_when_no_summary(self) -> None:
        m = make_meeting(summary_payload=None)
        self.assertIsNone(m.next_step)

    def test_meeting_decisions_returns_list(self) -> None:
        m = make_meeting(summary_payload={"decisions": ["A", "B"]})
        self.assertEqual(m.decisions, ["A", "B"])

    def test_meeting_risks_empty_default(self) -> None:
        m = make_meeting(summary_payload=None)
        self.assertEqual(m.risks, [])

    def test_meeting_keywords_empty_default(self) -> None:
        m = make_meeting(summary_payload=None)
        self.assertEqual(m.keywords, [])


class FileValidationTests(unittest.TestCase):
    """Test file extension filtering."""

    def test_audio_extensions_accepted(self) -> None:
        for ext in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"):
            with self.subTest(ext=ext):
                self.assertTrue(is_audio_file(f"meeting{ext}"), f"{ext} should be audio")

    def test_video_extensions_accepted(self) -> None:
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            with self.subTest(ext=ext):
                self.assertTrue(is_video_file(f"video{ext}"), f"{ext} should be video")

    def test_media_file_rejects_unknown_types(self) -> None:
        self.assertFalse(is_allowed_media_file("document.pdf"))
        self.assertFalse(is_allowed_media_file("image.png"))
        self.assertFalse(is_allowed_media_file("spreadsheet.xlsx"))

    def test_video_is_not_audio(self) -> None:
        self.assertFalse(is_audio_file("recording.mp4"))


class TextNormalizerTests(unittest.TestCase):
    """Test Traditional → Simplified Chinese conversion."""

    def test_traditional_to_simplified_fallback(self) -> None:
        simplified = to_simplified_text("會議記錄")
        # The fallback table should convert at minimum these common chars
        self.assertIn("会", simplified)
        self.assertIn("记", simplified)
        self.assertIn("录", simplified)

    def test_simplified_already_unchanged(self) -> None:
        original = "会议记录文本"
        result = to_simplified_text(original)
        self.assertEqual(result, original)

    def test_normalize_to_simplified_recursively_converts_dict(self) -> None:
        data = {
            "title": "會議總結",
            "items": ["第一項", "第二項"],
            "nested": {"key": "內容"},
        }
        result = normalize_to_simplified(data)
        self.assertIn("会", result["title"])
        self.assertIn("项", result["items"][0])
        self.assertIn("内", result["nested"]["key"])

    def test_normalize_skips_non_strings(self) -> None:
        self.assertEqual(normalize_to_simplified(42), 42)
        self.assertIsNone(normalize_to_simplified(None))
        self.assertEqual(normalize_to_simplified(3.14), 3.14)


class AudioSegmentTests(unittest.TestCase):
    """Test segment and chunk-duration math."""

    def test_build_segments_skips_empty_transcript_parts(self) -> None:
        parts = ["第一段", "", "第三段"]
        segments = _build_segments(uuid4(), COMPANY_ID, 3, 90.0, parts)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].sequence_no, 1)
        self.assertEqual(segments[1].sequence_no, 3)

    def test_guess_chunk_duration_last_chunk_shorter(self) -> None:
        self.assertAlmostEqual(_guess_chunk_duration(100.0, 0, 3), 33.333, places=1)
        self.assertAlmostEqual(_guess_chunk_duration(100.0, 2, 3), 100.0 - 66.666, places=1)

    def test_build_segments_orders_sequentially(self) -> None:
        parts = ["A", "B", "C"]
        meeting_id = uuid4()
        segments = _build_segments(meeting_id, COMPANY_ID, 3, 120.0, parts)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].sequence_no, 1)
        self.assertEqual(segments[1].sequence_no, 2)
        self.assertEqual(segments[2].sequence_no, 3)
        self.assertEqual(segments[0].meeting_id, meeting_id)


class MeetingServiceTests(unittest.TestCase):
    """Test application service with fake ports."""

    def setUp(self) -> None:
        self.repo = FakeMeetingRepository()
        self.uow = FakeMeetingUnitOfWork(self.repo)
        self.audio = FakeAudioProcessor()
        self.asr = FakeAsrService()
        self.summary = FakeSummaryService()
        self.service = MeetingService(
            audio_processor=self.audio,
            asr_service=self.asr,
            summary_service=self.summary,
        )

    # ── Query tests ──

    def test_get_meeting_returns_meeting(self) -> None:
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        result = self.service.get_meeting(self.repo, m.meeting_id)
        self.assertEqual(result.meeting_id, m.meeting_id)
        self.assertEqual(result.title, "Test Meeting")

    def test_get_meeting_raises_not_found(self) -> None:
        with self.assertRaises(MeetingNotFoundError):
            self.service.get_meeting(self.repo, uuid4())

    def test_get_meeting_with_segments_returns_both(self) -> None:
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        seg = MeetingSegment(
            company_id=COMPANY_ID, meeting_id=m.meeting_id,
            sequence_no=1, start_seconds=0.0, end_seconds=30.0,
            transcript_text="测试文本",
        )
        self.repo.segments[m.meeting_id] = [seg]

        meeting, segments = self.service.get_meeting_with_segments(self.repo, m.meeting_id)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].transcript_text, "测试文本")

    def test_list_meetings_filters_by_owner(self) -> None:
        other_id = uuid4()
        self.repo.meetings[uuid4()] = make_meeting(owner_user_id=OWNER_ID)
        self.repo.meetings[uuid4()] = make_meeting(owner_user_id=other_id)

        rows = self.service.list_meetings(self.repo, owner_user_id=OWNER_ID, limit=10)
        ids = {r["meeting_id"] for r in rows}
        self.assertEqual(len(ids), 1)

    def test_delete_meeting_soft_deletes_owned_meeting(self) -> None:
        meeting = make_meeting(owner_user_id=OWNER_ID)
        self.repo.meetings[meeting.meeting_id] = meeting

        self.service.delete_meeting(self.repo, meeting.meeting_id, OWNER_ID)

        deleted = self.repo.meetings[meeting.meeting_id]
        self.assertIsNotNone(deleted.deleted_at)
        self.assertEqual(deleted.version, meeting.version + 1)

    def test_delete_meeting_hides_other_users_meeting(self) -> None:
        meeting = make_meeting(owner_user_id=uuid4())
        self.repo.meetings[meeting.meeting_id] = meeting

        with self.assertRaises(MeetingNotFoundError):
            self.service.delete_meeting(self.repo, meeting.meeting_id, OWNER_ID)

        self.assertIsNone(self.repo.meetings[meeting.meeting_id].deleted_at)

    def test_delete_meeting_rejects_already_deleted_meeting(self) -> None:
        meeting = make_meeting(owner_user_id=OWNER_ID)
        self.repo.meetings[meeting.meeting_id] = meeting
        self.service.delete_meeting(self.repo, meeting.meeting_id, OWNER_ID)

        with self.assertRaises(MeetingNotFoundError):
            self.service.delete_meeting(self.repo, meeting.meeting_id, OWNER_ID)

    # ── Process pipeline tests ──

    def test_process_meeting_full_pipeline(self) -> None:
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        asset = make_media_asset(media_asset_id=m.source_media_asset_id, storage_key="/fake/test.wav")
        self.repo.assets[asset.media_asset_id] = asset

        result = self.service.process_meeting(self.repo, m.meeting_id)

        self.assertEqual(result.processing_status, "completed")
        self.assertIsNotNone(result.transcript_text)
        self.assertIn("会议讨论", result.transcript_text or "")
        self.assertIsNotNone(result.summary_payload)
        self.assertEqual(result.summary_payload["customer_needs"], ["降低成本", "提高效率"])
        self.assertEqual(result.next_step, "安排产品演示并发送报价单")
        self.assertEqual(result.summary_model, "gpt-5.6-terra")

    def test_process_meeting_saves_segments(self) -> None:
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        asset = make_media_asset(media_asset_id=m.source_media_asset_id, storage_key="/fake/test.wav")
        self.repo.assets[asset.media_asset_id] = asset

        self.service.process_meeting(self.repo, m.meeting_id)
        segments = self.repo.list_segments(m.meeting_id)
        self.assertGreater(len(segments), 0)
        self.assertEqual(segments[0].meeting_id, m.meeting_id)

    def test_process_meeting_rejects_non_uploaded_status(self) -> None:
        m = make_meeting(processing_status="completed")
        self.repo.meetings[m.meeting_id] = m

        with self.assertRaises(InvalidMeetingStateError):
            self.service.process_meeting(self.repo, m.meeting_id)

    def test_process_meeting_version_conflict_detected(self) -> None:
        """Version conflict: if repository methods return None on version mismatch,
        the service should raise MeetingVersionConflictError."""
        # Use a subclass that simulates version conflict on every mutation
        class VersionConflictingRepo(FakeMeetingRepository):
            def update_meeting_status(self, meeting_id, expected_version, *args, **kwargs):
                return None  # Always fails — simulates version mismatch
            def update_meeting_transcript(self, meeting_id, expected_version, *args, **kwargs):
                return None
            def update_meeting_summary(self, meeting_id, expected_version, *args, **kwargs):
                return None

        repo = VersionConflictingRepo()
        m = make_meeting()
        repo.meetings[m.meeting_id] = m
        asset = make_media_asset(media_asset_id=m.source_media_asset_id, storage_key="/fake/test.wav")
        repo.assets[asset.media_asset_id] = asset

        service = MeetingService(
            audio_processor=self.audio,
            asr_service=self.asr,
            summary_service=self.summary,
        )
        with self.assertRaises(MeetingVersionConflictError):
            service.process_meeting(repo, m.meeting_id)

    def test_process_meeting_fails_on_missing_media_asset(self) -> None:
        """Meeting references a media_asset that doesn't exist."""
        m = make_meeting(source_media_asset_id=uuid4())  # nonexistent asset
        self.repo.meetings[m.meeting_id] = m

        with self.assertRaises(MeetingError) as ctx:
            self.service.process_meeting(self.repo, m.meeting_id)
        self.assertIn("Source media asset", str(ctx.exception))

    def test_process_meeting_marks_failed_on_audio_error(self) -> None:
        self.audio._fail = True
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        asset = make_media_asset(media_asset_id=m.source_media_asset_id, storage_key="/fake/test.wav")
        self.repo.assets[asset.media_asset_id] = asset

        with self.assertRaises(AudioProcessingError):
            self.service.process_meeting(self.repo, m.meeting_id)

        # Verify meeting is marked failed
        updated = self.repo.meetings[m.meeting_id]
        self.assertEqual(updated.processing_status, "failed")

    def test_process_meeting_runs_asr_on_all_chunks(self) -> None:
        self.audio._chunks = ["/tmp/c0.wav", "/tmp/c1.wav", "/tmp/c2.wav"]
        m = make_meeting()
        self.repo.meetings[m.meeting_id] = m
        asset = make_media_asset(media_asset_id=m.source_media_asset_id, storage_key="/fake/test.wav")
        self.repo.assets[asset.media_asset_id] = asset

        self.service.process_meeting(self.repo, m.meeting_id)
        self.assertEqual(len(self.asr.transcribe_calls), 3)

    def test_refuses_wrong_file_type(self) -> None:
        self.assertFalse(is_allowed_media_file("invoice.exe"))
        self.assertFalse(is_allowed_media_file("report.docx"))

    # ── Summary property tests ──

    def test_meeting_summary_properties_work(self) -> None:
        m = make_meeting(summary_payload={
            "customer_needs": ["需求A"],
            "pain_points": ["痛点B"],
            "buying_signals": [],
            "action_items": [],
            "decisions": ["决定C"],
            "risks": ["风险D"],
            "keywords": ["KW1", "KW2"],
            "next_step": "follow up",
        })
        self.assertEqual(m.decisions, ["决定C"])
        self.assertEqual(m.risks, ["风险D"])
        self.assertEqual(m.keywords, ["KW1", "KW2"])
        self.assertEqual(m.next_step, "follow up")


class CreateMeetingValidationTests(unittest.TestCase):
    """Test the validation logic in create_meeting (without full FastAPI)."""

    def setUp(self) -> None:
        self.repo = FakeMeetingRepository()
        self.service = MeetingService(
            audio_processor=FakeAudioProcessor(),
            asr_service=FakeAsrService(),
            summary_service=FakeSummaryService(),
        )

    def test_allowed_media_extensions(self) -> None:
        allowed = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".avi", ".mkv", ".webm"]
        for ext in allowed:
            self.assertTrue(is_allowed_media_file(f"recording{ext}"), f"{ext} should be allowed")

    def test_disallowed_extensions(self) -> None:
        self.assertFalse(is_allowed_media_file("notes.txt"))
        self.assertFalse(is_allowed_media_file("image.jpg"))
        self.assertFalse(is_allowed_media_file("data.json"))

    def test_audio_vs_video_classification(self) -> None:
        self.assertTrue(is_audio_file("meeting.mp3"))
        self.assertTrue(is_video_file("meeting.mp4"))
        self.assertFalse(is_audio_file("meeting.mp4"))
        self.assertFalse(is_video_file("meeting.mp3"))


class RepositoryTests(unittest.TestCase):
    """Smoke-test the FakeMeetingRepository for test correctness."""

    def setUp(self) -> None:
        self.repo = FakeMeetingRepository()

    def test_insert_meeting_creates_record(self) -> None:
        m = self.repo.insert_meeting(COMPANY_ID, uuid4(), uuid4(), OWNER_ID, "Test", "upload")
        self.assertEqual(m.title, "Test")
        self.assertEqual(m.processing_status, "uploaded")
        self.assertEqual(m.version, 0)
        self.assertIn(m.meeting_id, self.repo.meetings)

    def test_inserting_and_finding(self) -> None:
        m = self.repo.insert_meeting(COMPANY_ID, uuid4(), uuid4(), OWNER_ID, "Demo", "upload")
        found = self.repo.find_meeting_by_id(m.meeting_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "Demo")

    def test_find_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.repo.find_meeting_by_id(uuid4()))

    def test_list_meetings_respects_limit(self) -> None:
        for _ in range(5):
            self.repo.insert_meeting(COMPANY_ID, uuid4(), uuid4(), OWNER_ID, "T", "upload")
        rows = self.repo.list_meetings(None, None, None, None, limit=3)
        self.assertEqual(len(rows), 3)

    def test_insert_media_asset_sets_correct_fields(self) -> None:
        asset = self.repo.insert_media_asset(
            COMPANY_ID, "meeting_source", "local", "/tmp/test.mp3",
            "test.mp3", "audio/mpeg", 5000, "b" * 64, OWNER_ID,
        )
        self.assertEqual(asset.asset_kind, "meeting_source")
        self.assertEqual(asset.mime_type, "audio/mpeg")
        self.assertEqual(asset.size_bytes, 5000)

    def test_segment_replace_and_list(self) -> None:
        meeting_id = uuid4()
        segs = [
            MeetingSegment(company_id=COMPANY_ID, meeting_id=meeting_id,
                           sequence_no=1, start_seconds=0.0, end_seconds=30.0,
                           transcript_text="第一段"),
            MeetingSegment(company_id=COMPANY_ID, meeting_id=meeting_id,
                           sequence_no=2, start_seconds=30.0, end_seconds=60.0,
                           transcript_text="第二段"),
        ]
        self.repo.replace_segments(meeting_id, COMPANY_ID, segs)
        result = self.repo.list_segments(meeting_id)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].sequence_no, 1)


if __name__ == "__main__":
    unittest.main()
