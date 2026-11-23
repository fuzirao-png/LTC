BEGIN;

ALTER TABLE ltc.lead_search_run
    DROP CONSTRAINT IF EXISTS ck_lead_search_run_target_count;

ALTER TABLE ltc.lead_search_run
    ADD CONSTRAINT ck_lead_search_run_target_count
    CHECK (target_count BETWEEN 1 AND 2000);

COMMIT;
