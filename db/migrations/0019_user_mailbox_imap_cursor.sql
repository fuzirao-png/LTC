BEGIN;

ALTER TABLE ltc.user_mailbox
    ADD COLUMN IF NOT EXISTS imap_uid_validity bigint,
    ADD COLUMN IF NOT EXISTS last_processed_uid bigint,
    ADD COLUMN IF NOT EXISTS sync_initialized_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_poll_error text;

ALTER TABLE ltc.user_mailbox
    DROP CONSTRAINT IF EXISTS ck_user_mailbox_imap_uid_validity,
    DROP CONSTRAINT IF EXISTS ck_user_mailbox_last_processed_uid;

ALTER TABLE ltc.user_mailbox
    ADD CONSTRAINT ck_user_mailbox_imap_uid_validity
        CHECK (imap_uid_validity IS NULL OR imap_uid_validity > 0),
    ADD CONSTRAINT ck_user_mailbox_last_processed_uid
        CHECK (last_processed_uid IS NULL OR last_processed_uid >= 0);

COMMIT;
