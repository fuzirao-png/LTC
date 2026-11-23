BEGIN;

CREATE TEMP TABLE inbound_mailbox_duplicate_map ON COMMIT DROP AS
WITH ranked AS (
    SELECT
        email_id AS duplicate_email_id,
        company_id AS duplicate_company_id,
        lead_id AS duplicate_lead_id,
        first_value(email_id) OVER mailbox_message AS canonical_email_id,
        first_value(company_id) OVER mailbox_message AS canonical_company_id,
        first_value(lead_id) OVER mailbox_message AS canonical_lead_id,
        row_number() OVER mailbox_message AS copy_number
    FROM ltc.email_message
    WHERE direction = 'inbound'
      AND message_id_header IS NOT NULL
      AND NULLIF(trim(intended_to_address), '') IS NOT NULL
    WINDOW mailbox_message AS (
        PARTITION BY lower(trim(intended_to_address)), message_id_header
        ORDER BY created_at DESC, email_id DESC
    )
)
SELECT * FROM ranked WHERE copy_number > 1;

UPDATE ltc.email_message child
SET parent_email_id = CASE
        WHEN child.company_id = duplicates.canonical_company_id
            THEN duplicates.canonical_email_id
        ELSE NULL
    END
FROM inbound_mailbox_duplicate_map duplicates
WHERE child.parent_email_id = duplicates.duplicate_email_id;

UPDATE ltc.email_attachment attachment
SET email_id = duplicates.canonical_email_id
FROM inbound_mailbox_duplicate_map duplicates
WHERE attachment.email_id = duplicates.duplicate_email_id
  AND attachment.company_id = duplicates.canonical_company_id;

UPDATE ltc.email_delivery_attempt attempt
SET email_id = duplicates.canonical_email_id
FROM inbound_mailbox_duplicate_map duplicates
WHERE attempt.email_id = duplicates.duplicate_email_id;

UPDATE ltc.email_suppression suppression
SET source_email_id = duplicates.canonical_email_id
FROM inbound_mailbox_duplicate_map duplicates
WHERE suppression.source_email_id = duplicates.duplicate_email_id;

UPDATE ltc.follow_up_task task
SET source_email_id = CASE
        WHEN task.company_id = duplicates.canonical_company_id
            THEN duplicates.canonical_email_id
        ELSE NULL
    END
FROM inbound_mailbox_duplicate_map duplicates
WHERE task.source_email_id = duplicates.duplicate_email_id;

UPDATE ltc.company_outreach_state outreach
SET source_email_id = CASE
        WHEN outreach.company_id = duplicates.canonical_company_id
            THEN duplicates.canonical_email_id
        ELSE NULL
    END
FROM inbound_mailbox_duplicate_map duplicates
WHERE outreach.source_email_id = duplicates.duplicate_email_id;

UPDATE ltc.lead_stage_transition transition
SET source_email_id = CASE
        WHEN transition.company_id = duplicates.canonical_company_id
             AND transition.lead_id IS NOT DISTINCT FROM duplicates.canonical_lead_id
            THEN duplicates.canonical_email_id
        ELSE NULL
    END
FROM inbound_mailbox_duplicate_map duplicates
WHERE transition.source_email_id = duplicates.duplicate_email_id;

DELETE FROM ltc.email_message email
USING inbound_mailbox_duplicate_map duplicates
WHERE email.email_id = duplicates.duplicate_email_id;

CREATE UNIQUE INDEX uq_email_message_inbound_mailbox_message_id
ON ltc.email_message (
    lower(trim(intended_to_address)),
    message_id_header
)
WHERE direction = 'inbound'
  AND message_id_header IS NOT NULL
  AND NULLIF(trim(intended_to_address), '') IS NOT NULL;

COMMIT;
