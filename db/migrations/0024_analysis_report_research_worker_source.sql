BEGIN;

ALTER TABLE ltc.analysis_report
    DROP CONSTRAINT IF EXISTS ck_analysis_report_content_source;

ALTER TABLE ltc.analysis_report
    ADD CONSTRAINT ck_analysis_report_content_source
    CHECK (content_source IN (
        'llm',
        'template',
        'fallback',
        'migration',
        'research_worker'
    ));

COMMIT;
