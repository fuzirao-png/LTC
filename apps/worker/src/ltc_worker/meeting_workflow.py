"""Worker activities for the resumable media workflow."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from opentelemetry.trace import Tracer

from ltc.modules.meeting_analysis.domain.models import Meeting, MeetingSegment
from ltc.modules.meeting_analysis.infrastructure import AsrAdapter, PostgresMeetingRepository, SummaryAdapter
from ltc.modules.meeting_analysis.infrastructure import audio_processor as audio
from ltc.modules.meeting_analysis.infrastructure.file_handler import is_video_file

from .crm_services import CrmWorkerDatabase
from .errors import LeaseLost
from .lease import JobLease


class MeetingWorkflow:
    def __init__(
        self, database: CrmWorkerDatabase, asr: AsrAdapter, summary: SummaryAdapter,
        tracer: Tracer, *, model: str, chunk_seconds: int, parallel: int,
    ) -> None:
        self._database = database
        self._asr = asr
        self._summary = summary
        self._tracer = tracer
        self._model = model
        self._chunk_seconds = chunk_seconds
        self._parallel = parallel

    @contextmanager
    def _transaction(self, job: JobLease) -> Iterator[PostgresMeetingRepository]:
        with self._database.transaction() as connection:
            lease = connection.execute(
                """SELECT job_id FROM ltc.job
                    WHERE job_id=%s AND lock_token=%s AND status='running'
                      AND locked_until > clock_timestamp() FOR UPDATE""",
                (job.job_id, job.lock_token),
            ).fetchone()
            if lease is None:
                raise LeaseLost("meeting job lease expired")
            yield PostgresMeetingRepository(connection)

    def run(self, job: JobLease) -> None:
        with self._transaction(job) as repo:
            row = repo.connection.execute(
                "SELECT aggregate_id FROM ltc.job WHERE job_id=%s", (job.job_id,),
            ).fetchone()
            meeting = repo.find_meeting_by_id_for_update(row[0]) if row and row[0] else None
            if meeting is None or meeting.deleted_at or meeting.is_terminal:
                return
            transcript = meeting.transcript_text if meeting.transcript_status == "done" else None
            if transcript is None:
                source = repo.find_media_asset_by_id(meeting.source_media_asset_id)
                if source is None:
                    raise FileNotFoundError("meeting source media record is missing")
                repo.update_meeting_status(meeting.meeting_id, meeting.version, "extracting", None, None)

        if transcript is None:
            with TemporaryDirectory(prefix="ltc-media-") as work_dir:
                with self._tracer.start_as_current_span("meeting.split", record_exception=False):
                    path = source.storage_key
                    if is_video_file(source.original_filename or path):
                        path = audio.extract_audio_from_video(path, work_dir)
                    normalized = audio.normalize_audio(path, work_dir)
                    duration = audio.probe_duration(normalized)
                    chunks = audio.split_audio(normalized, work_dir, self._chunk_seconds)
                    if not chunks:
                        raise ValueError("meeting has no audio segments")
                with self._transaction(job) as repo:
                    current = self._active_meeting(repo, meeting.meeting_id)
                    if current is None:
                        return
                    repo.update_meeting_status(current.meeting_id, current.version, "transcribing", None, None)
                parts = self._transcribe(job, meeting.meeting_id, source.sha256, chunks)
            transcript = "\n".join(parts)
            with self._transaction(job) as repo:
                current = self._active_meeting(repo, meeting.meeting_id)
                if current is None:
                    return
                repo.update_meeting_transcript(
                    current.meeting_id, current.version, transcript, "zh", "openai-asr", "done", duration,
                )
                segments = [
                    MeetingSegment(
                        company_id=meeting.company_id, meeting_id=meeting.meeting_id,
                        sequence_no=index + 1, start_seconds=index * self._chunk_seconds,
                        end_seconds=min(duration, (index + 1) * self._chunk_seconds),
                        transcript_text=text,
                    )
                    for index, text in enumerate(parts) if text.strip()
                ]
                repo.replace_segments(meeting.meeting_id, meeting.company_id, segments)

        with self._tracer.start_as_current_span("meeting.summarize", record_exception=False):
            summary = self._summary.summarize(transcript)
        with self._transaction(job) as repo:
            current = self._active_meeting(repo, meeting.meeting_id)
            if current is not None:
                repo.update_meeting_summary(current.meeting_id, current.version, summary, "v1", self._summary.model_name)

    @staticmethod
    def _active_meeting(repo: PostgresMeetingRepository, meeting_id: UUID) -> Meeting | None:
        meeting = repo.find_meeting_by_id_for_update(meeting_id)
        return meeting if meeting and not meeting.deleted_at and not meeting.is_terminal else None

    def _transcribe(self, job: JobLease, meeting_id: UUID, source_hash: str, chunks: list[str]) -> list[str]:
        with self._transaction(job) as repo:
            saved = dict(repo.connection.execute(
                "SELECT transcript_ref, transcript_text FROM ltc.meeting_asr_checkpoint WHERE meeting_id=%s",
                (meeting_id,),
            ).fetchall())
        refs = [
            sha256(f"v1:{meeting_id}:{source_hash}:{self._model}:{self._chunk_seconds}:{index}".encode()).hexdigest()
            for index in range(len(chunks))
        ]
        if all(ref in saved for ref in refs):
            return [saved[ref] for ref in refs]

        with ThreadPoolExecutor(max_workers=self._parallel) as executor:
            # Submit bounded batches. The remaining chunks stay on disk while the
            # provider is throttled, without an unbounded executor backlog.
            for offset in range(0, len(chunks), self._parallel):
                futures = {
                    refs[index]: executor.submit(
                        copy_context().run, self._transcribe_segment, job, meeting_id, index, chunks[index], refs[index],
                    )
                    for index in range(offset, min(len(chunks), offset + self._parallel)) if refs[index] not in saved
                }
                for ref, future in futures.items():
                    saved[ref] = future.result()
        return [saved[ref] for ref in refs]

    def _transcribe_segment(self, job: JobLease, meeting_id: UUID, index: int, path: str, ref: str) -> str:
        with self._transaction(job) as repo:
            if self._active_meeting(repo, meeting_id) is None:
                raise LeaseLost("meeting is no longer active")
        with self._tracer.start_as_current_span("meeting.transcribe_segment", record_exception=False) as span:
            span.set_attribute("ltc.segment_index", index)
            transcript = self._asr.transcribe_segment(path, ref)
            with self._transaction(job) as repo:
                if self._active_meeting(repo, meeting_id) is None:
                    raise LeaseLost("meeting is no longer active")
                repo.connection.execute(
                    """INSERT INTO ltc.meeting_asr_checkpoint
                           (transcript_ref, meeting_id, segment_index, transcript_text)
                       VALUES (%s,%s,%s,%s) ON CONFLICT (transcript_ref) DO NOTHING""",
                    (ref, meeting_id, index, transcript),
                )
            return transcript

    def close(self) -> None:
        self._asr.close()
