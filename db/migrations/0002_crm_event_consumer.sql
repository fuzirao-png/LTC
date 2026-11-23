-- CRM event-consumer idempotency for dynamic intent bonuses.
-- This is a follow-up migration; 0001_v3_6_initial.sql remains immutable.

CREATE TABLE ltc.crm_dynamic_bonus_application (
    bonus_application_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES ltc.sales_lead(lead_id) ON DELETE RESTRICT,
    source_type text NOT NULL,
    source_resource_id uuid NOT NULL,
    bonus_type text NOT NULL,
    bonus_points integer NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_crm_dynamic_bonus_source_type CHECK (source_type IN ('email', 'meeting')),
    CONSTRAINT ck_crm_dynamic_bonus_type CHECK (bonus_type IN ('I1', 'I2', 'I3', 'I4')),
    CONSTRAINT ck_crm_dynamic_bonus_points CHECK (bonus_points > 0),
    CONSTRAINT uq_crm_dynamic_bonus_source UNIQUE (source_type, source_resource_id, bonus_type)
);

CREATE INDEX ix_crm_dynamic_bonus_lead_id ON ltc.crm_dynamic_bonus_application (lead_id, applied_at DESC);
