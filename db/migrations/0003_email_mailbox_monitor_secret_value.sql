BEGIN;

SET search_path TO ltc, public;

ALTER TABLE ltc.mailbox_monitor
ADD COLUMN IF NOT EXISTS secret_value text;

COMMIT;
