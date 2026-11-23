-- CRM event-consumer idempotency for engagement-driven lead scoring.
-- This additive migration is numbered after the v3.3 telemetry migrations.

CREATE TABLE IF NOT EXISTS ltc.crm_dynamic_bonus_application (
    bonus_application_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES ltc.sales_lead(lead_id) ON DELETE RESTRICT,
    source_type text NOT NULL,
    source_resource_id uuid NOT NULL,
    bonus_type text NOT NULL,
    bonus_points integer NOT NULL,
    rule_version text NOT NULL DEFAULT 'dynamic-intent-2026-07-v1',
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_crm_dynamic_bonus_source_type CHECK (source_type IN ('email', 'meeting')),
    CONSTRAINT ck_crm_dynamic_bonus_type CHECK (bonus_type IN ('I1', 'I2', 'I3', 'I4')),
    CONSTRAINT ck_crm_dynamic_bonus_points CHECK (bonus_points > 0),
    CONSTRAINT uq_crm_dynamic_bonus_source UNIQUE (source_type, source_resource_id, bonus_type)
);

CREATE INDEX IF NOT EXISTS ix_crm_dynamic_bonus_lead_id
    ON ltc.crm_dynamic_bonus_application (lead_id, applied_at DESC);
