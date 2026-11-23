ALTER TABLE ltc.email_message
    ADD COLUMN IF NOT EXISTS notification_created_at timestamptz,
    ADD COLUMN IF NOT EXISTS notification_read_at timestamptz,
    ADD COLUMN IF NOT EXISTS notification_dismissed_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_email_message_sales_notification
    ON ltc.email_message (sales_user_id, notification_created_at DESC)
    WHERE notification_created_at IS NOT NULL
      AND notification_dismissed_at IS NULL;
