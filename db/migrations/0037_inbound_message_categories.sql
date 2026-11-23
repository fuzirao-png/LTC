BEGIN;

ALTER TABLE ltc.email_message
    ALTER COLUMN company_id DROP NOT NULL;

ALTER TABLE ltc.email_message
    ADD COLUMN IF NOT EXISTS message_category text NOT NULL DEFAULT 'customer_reply';

ALTER TABLE ltc.email_message
    ADD CONSTRAINT ck_email_message_category
    CHECK (message_category IN ('customer_reply', 'automatic_reply', 'delivery_notification', 'internal_mail'));

UPDATE ltc.email_message
SET message_category = CASE
    WHEN direction = 'inbound' AND (
        lower(from_address) LIKE 'mailer-daemon%'
        OR lower(from_address) LIKE 'postmaster%'
        OR lower(COALESCE(subject, '')) LIKE '%delivery status notification%'
        OR lower(COALESCE(subject, '')) LIKE 'undeliverable:%'
    ) THEN 'delivery_notification'
    WHEN direction = 'inbound' AND (
        lower(COALESCE(subject, '')) LIKE '%automatic reply%'
        OR lower(COALESCE(subject, '')) LIKE '%auto reply%'
        OR lower(COALESCE(subject, '')) LIKE '%out of office%'
        OR lower(COALESCE(subject, '')) LIKE 'ooo:%'
        OR lower(COALESCE(subject, '')) LIKE '%réponse automatique%'
        OR lower(COALESCE(subject, '')) LIKE '%risposta automatica%'
        OR COALESCE(subject, '') LIKE '%自动回复%'
        OR COALESCE(subject, '') LIKE '%自动答复%'
    ) THEN 'automatic_reply'
    ELSE 'customer_reply'
END;

CREATE INDEX IF NOT EXISTS ix_email_message_category_received
    ON ltc.email_message (message_category, received_at DESC);

COMMIT;
