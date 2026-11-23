CREATE TABLE ltc.meeting_asr_checkpoint (
    transcript_ref text PRIMARY KEY,
    meeting_id uuid NOT NULL REFERENCES ltc.meeting(meeting_id) ON DELETE CASCADE,
    segment_index integer NOT NULL CHECK (segment_index >= 0),
    transcript_text text NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_meeting_asr_checkpoint_meeting ON ltc.meeting_asr_checkpoint (meeting_id);

-- Adopt unfinished uploads from the former in-process meeting runner.
UPDATE ltc.job job
SET job_type = 'engagement.process_meeting.v1', queue_name = 'media',
    aggregate_type = 'meeting', aggregate_id = meeting.meeting_id,
    status = 'queued', run_after = clock_timestamp(),
    locked_by = NULL, lock_token = NULL, locked_until = NULL
FROM ltc.meeting meeting
WHERE meeting.current_job_id = job.job_id AND meeting.deleted_at IS NULL
  AND job.job_type = 'meeting_processing' AND job.status = 'queued'
  AND meeting.processing_status IN ('uploaded', 'extracting', 'transcribing', 'summarizing');
