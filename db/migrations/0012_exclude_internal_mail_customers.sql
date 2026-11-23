BEGIN;

DELETE FROM ltc.customer_operation_owner coo
USING ltc.company c
WHERE c.company_id = coo.company_id
  AND (
    lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name)) = 'exmail.weixin.qq.com'
    OR EXISTS (
      SELECT 1
      FROM ltc.user_mailbox um
      WHERE lower(split_part(um.email_address, '@', 2)) =
            lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name))
    )
  );

COMMIT;
