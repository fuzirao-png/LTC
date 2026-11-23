ALTER TABLE ltc.email_automation_touch
    DROP CONSTRAINT IF EXISTS uq_email_automation_touch_company;

ALTER TABLE ltc.email_automation_touch
    ADD CONSTRAINT uq_email_automation_touch_company_contact UNIQUE (company_id, contact_id);
