BEGIN;

CREATE TABLE IF NOT EXISTS ltc.customer_operation_owner (
    company_id uuid PRIMARY KEY REFERENCES ltc.company(company_id) ON DELETE CASCADE,
    sales_user_id uuid NOT NULL REFERENCES ltc.user_account(user_id),
    ownership_source text NOT NULL DEFAULT 'mailbox',
    assigned_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_customer_operation_owner_source
        CHECK (ownership_source IN ('mailbox', 'sales_lead', 'legacy_backfill', 'manual'))
);

CREATE INDEX IF NOT EXISTS ix_customer_operation_owner_sales_user
    ON ltc.customer_operation_owner(sales_user_id, updated_at DESC);

WITH legacy_owner AS (
    SELECT user_id
    FROM ltc.user_account
    WHERE username = 'li.ming'
), updated AS (
    UPDATE ltc.email_message
    SET sales_user_id = (SELECT user_id FROM legacy_owner)
    WHERE sales_user_id IS NULL
      AND EXISTS (SELECT 1 FROM legacy_owner)
    RETURNING email_id
)
SELECT count(*) FROM updated;

INSERT INTO ltc.customer_operation_owner (
    company_id, sales_user_id, ownership_source, assigned_at, updated_at
)
SELECT DISTINCT ON (em.company_id)
    em.company_id,
    em.sales_user_id,
    'mailbox',
    COALESCE(em.received_at, em.sent_at, em.created_at),
    COALESCE(em.received_at, em.sent_at, em.created_at)
FROM ltc.email_message em
WHERE em.sales_user_id IS NOT NULL
ORDER BY em.company_id, COALESCE(em.received_at, em.sent_at, em.created_at) DESC
ON CONFLICT (company_id) DO UPDATE SET
    sales_user_id = EXCLUDED.sales_user_id,
    ownership_source = EXCLUDED.ownership_source,
    assigned_at = EXCLUDED.assigned_at,
    updated_at = EXCLUDED.updated_at;

INSERT INTO ltc.customer_operation_owner (
    company_id, sales_user_id, ownership_source
)
SELECT c.company_id, u.user_id, 'legacy_backfill'
FROM ltc.company c
JOIN ltc.user_account u ON u.username = 'li.ming'
WHERE c.archived_at IS NULL
ON CONFLICT (company_id) DO NOTHING;

COMMIT;
