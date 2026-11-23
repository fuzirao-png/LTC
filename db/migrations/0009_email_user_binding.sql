-- 0009_email_user_binding: per-user mailbox configuration
BEGIN;

-- 1. Add user_id to mailbox_monitor (maps inbox to a specific user)
ALTER TABLE ltc.mailbox_monitor
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES ltc.user_account(user_id);

-- 2. Add per-user SMTP fields to user_account (nullable - defaults to global settings)
ALTER TABLE ltc.user_account
  ADD COLUMN IF NOT EXISTS mail_from     text,
  ADD COLUMN IF NOT EXISTS smtp_username text,
  ADD COLUMN IF NOT EXISTS smtp_password text;

-- 3. Create index for user mailbox lookup
CREATE INDEX IF NOT EXISTS ix_mailbox_monitor_user_id
  ON ltc.mailbox_monitor(user_id) WHERE user_id IS NOT NULL;

COMMIT;
