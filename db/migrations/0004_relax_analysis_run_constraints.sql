-- Migration 0004: relax analysis_run NOT NULL + FK constraints for inline job port.
-- The InlineAnalysisJobPort fires run generation synchronously (no job table entry),
-- so columns that reference ltc.job must be nullable.

BEGIN;

ALTER TABLE ltc.analysis_run ALTER COLUMN lead_id DROP NOT NULL;
ALTER TABLE ltc.analysis_run ALTER COLUMN source_candidate_id DROP NOT NULL;
ALTER TABLE ltc.analysis_run ALTER COLUMN icp_assessment_id DROP NOT NULL;
ALTER TABLE ltc.analysis_run ALTER COLUMN scale_assessment_id DROP NOT NULL;
ALTER TABLE ltc.analysis_run ALTER COLUMN current_job_id DROP NOT NULL;

-- Drop foreign keys that the inline job port does not satisfy
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS analysis_run_current_job_id_fkey;
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS analysis_run_source_candidate_id_fkey;
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS fk_analysis_run_icp_assessment;
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS fk_analysis_run_lead_candidate;
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS fk_analysis_run_lead_icp_scale;
ALTER TABLE ltc.analysis_run DROP CONSTRAINT IF EXISTS fk_analysis_run_scale_assessment;

-- Keep analysis_run_company_id_fkey and analysis_run_created_by_fkey

COMMIT;
