BEGIN;

SET search_path TO ltc, public;

CREATE TABLE ltc.mailbox_monitor (
    mailbox_monitor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code text NOT NULL,
    host text NOT NULL,
    port integer NOT NULL,
    username text NOT NULL,
    secret_env_var text NOT NULL,
    mailbox_name text NOT NULL DEFAULT 'INBOX',
    enabled boolean NOT NULL DEFAULT true,
    poll_seconds integer NOT NULL DEFAULT 60,
    last_uid text,
    last_polled_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_mailbox_monitor_provider_code CHECK (provider_code IN ('imap')),
    CONSTRAINT ck_mailbox_monitor_port CHECK (port > 0),
    CONSTRAINT ck_mailbox_monitor_poll_seconds CHECK (poll_seconds >= 10),
    CONSTRAINT ck_mailbox_monitor_version CHECK (version >= 0)
);

CREATE UNIQUE INDEX uq_mailbox_monitor_provider_username_mailbox
ON ltc.mailbox_monitor (provider_code, username, mailbox_name);

CREATE INDEX ix_mailbox_monitor_enabled_created_at
ON ltc.mailbox_monitor (enabled, created_at DESC);

CREATE INDEX ix_mailbox_monitor_last_polled_at
ON ltc.mailbox_monitor (last_polled_at DESC)
WHERE last_polled_at IS NOT NULL;

CREATE TRIGGER trg_mailbox_monitor_updated_at
BEFORE UPDATE ON ltc.mailbox_monitor
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

COMMIT;
