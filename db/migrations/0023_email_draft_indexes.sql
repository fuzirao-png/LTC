BEGIN;

CREATE INDEX IF NOT EXISTS ix_email_message_sales_drafts_updated
    ON ltc.email_message (sales_user_id, updated_at DESC)
    WHERE direction = 'outbound' AND status = 'draft' AND sales_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_email_message_company_sales_drafts_updated
    ON ltc.email_message (company_id, sales_user_id, updated_at DESC)
    WHERE direction = 'outbound' AND status = 'draft' AND sales_user_id IS NOT NULL;

COMMIT;
