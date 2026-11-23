BEGIN;

ALTER TABLE ltc.analysis_run
    ADD COLUMN IF NOT EXISTS triggered_at timestamptz,
    ADD COLUMN IF NOT EXISTS trigger_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS superseded_by_run_id uuid;

UPDATE ltc.analysis_run
SET triggered_at = COALESCE(triggered_at, created_at),
    trigger_context = COALESCE(trigger_context, '{}'::jsonb);

ALTER TABLE ltc.analysis_run
    ALTER COLUMN triggered_at SET DEFAULT clock_timestamp(),
    ALTER COLUMN triggered_at SET NOT NULL;

ALTER TABLE ltc.analysis_run
    DROP CONSTRAINT IF EXISTS fk_analysis_run_superseded_by_run;

ALTER TABLE ltc.analysis_run
    ADD CONSTRAINT fk_analysis_run_superseded_by_run
        FOREIGN KEY (superseded_by_run_id)
        REFERENCES ltc.analysis_run(analysis_run_id)
        ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_analysis_run_company_type_triggered_at
    ON ltc.analysis_run (company_id, report_type, triggered_at DESC);

COMMIT;
