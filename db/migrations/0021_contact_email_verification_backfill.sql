BEGIN;

WITH verified_contacts AS (
    SELECT
        ct.contact_id,
        ct.company_id,
        max(COALESCE(em.received_at, em.created_at)) AS last_verified_at
    FROM ltc.contact ct
    JOIN ltc.email_message em
      ON em.company_id = ct.company_id
     AND em.contact_id = ct.contact_id
     AND em.direction = 'inbound'
    WHERE ct.status = 'active'
    GROUP BY ct.contact_id, ct.company_id
)
UPDATE ltc.contact ct
SET email_status = 'valid',
    last_verified_at = GREATEST(COALESCE(ct.last_verified_at, verified_contacts.last_verified_at), verified_contacts.last_verified_at),
    updated_at = clock_timestamp(),
    version = ct.version + 1
FROM verified_contacts
WHERE ct.contact_id = verified_contacts.contact_id
  AND ct.company_id = verified_contacts.company_id
  AND ct.status = 'active'
  AND (
      ct.email_status IS DISTINCT FROM 'valid'
      OR ct.last_verified_at IS NULL
      OR ct.last_verified_at < verified_contacts.last_verified_at
  );

COMMIT;
