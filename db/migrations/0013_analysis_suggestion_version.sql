BEGIN;

ALTER TABLE ltc.analysis_suggestion
    ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 0;

ALTER TABLE ltc.analysis_suggestion
    DROP CONSTRAINT IF EXISTS ck_analysis_suggestion_version;

ALTER TABLE ltc.analysis_suggestion
    ADD CONSTRAINT ck_analysis_suggestion_version CHECK (version >= 0);

COMMIT;
