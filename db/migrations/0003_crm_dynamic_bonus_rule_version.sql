-- Preserve the Config-as-Code version that mapped engagement intent to a bonus.
-- This is separate from 0002 because deployed migrations are immutable.

ALTER TABLE ltc.crm_dynamic_bonus_application
    ADD COLUMN rule_version text NOT NULL DEFAULT 'dynamic-intent-2026-07-v1';
