BEGIN;

ALTER TABLE ltc.email_delivery_attempt
  ADD COLUMN IF NOT EXISTS bounce_type text;

ALTER TABLE ltc.email_automation_run
  ADD COLUMN IF NOT EXISTS delivery_summary jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE ltc.email_delivery_attempt
  DROP CONSTRAINT IF EXISTS ck_email_delivery_attempt_bounce_type;
ALTER TABLE ltc.email_delivery_attempt
  ADD CONSTRAINT ck_email_delivery_attempt_bounce_type
  CHECK (bounce_type IS NULL OR bounce_type IN ('4xx', '5xx'));

COMMIT;
