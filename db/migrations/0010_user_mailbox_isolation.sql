BEGIN;

CREATE TABLE IF NOT EXISTS ltc.user_mailbox (
    user_mailbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES ltc.user_account(user_id) ON DELETE CASCADE,
    email_address text NOT NULL,
    smtp_host text NOT NULL,
    smtp_port integer NOT NULL DEFAULT 465,
    smtp_use_ssl boolean NOT NULL DEFAULT true,
    imap_host text NOT NULL,
    imap_port integer NOT NULL DEFAULT 993,
    imap_use_ssl boolean NOT NULL DEFAULT true,
    mailbox_name text NOT NULL DEFAULT 'INBOX',
    encrypted_password text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    poll_seconds integer NOT NULL DEFAULT 60,
    last_polled_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_mailbox_user UNIQUE (user_id),
    CONSTRAINT uq_user_mailbox_email UNIQUE (email_address),
    CONSTRAINT ck_user_mailbox_smtp_port CHECK (smtp_port BETWEEN 1 AND 65535),
    CONSTRAINT ck_user_mailbox_imap_port CHECK (imap_port BETWEEN 1 AND 65535),
    CONSTRAINT ck_user_mailbox_poll_seconds CHECK (poll_seconds >= 10)
);

CREATE INDEX IF NOT EXISTS ix_user_mailbox_enabled ON ltc.user_mailbox(enabled) WHERE enabled;

ALTER TABLE ltc.email_message
    ADD COLUMN IF NOT EXISTS sales_user_id uuid REFERENCES ltc.user_account(user_id);

CREATE INDEX IF NOT EXISTS ix_email_message_sales_user_created_at
    ON ltc.email_message(sales_user_id, created_at DESC)
    WHERE sales_user_id IS NOT NULL;

COMMIT;
