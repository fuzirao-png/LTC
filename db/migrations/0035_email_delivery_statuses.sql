-- Distinguish SMTP acceptance from a provider-confirmed delivery.
-- Existing sent/delivered values remain valid for backward compatibility.
ALTER TABLE ltc.email_message
    DROP CONSTRAINT IF EXISTS ck_email_message_status;

ALTER TABLE ltc.email_message
    ADD CONSTRAINT ck_email_message_status CHECK (
        (direction = 'outbound' AND status IN (
            'generating', 'draft', 'approved', 'queued', 'sending', 'sent',
            'smtp_submitted', 'delivery_confirmed', 'delivered', 'opened',
            'clicked', 'replied', 'bounced', 'failed', 'reconcile_required',
            'cancelled'
        ))
        OR
        (direction = 'inbound' AND status IN ('received', 'processing', 'processed', 'failed'))
    );
