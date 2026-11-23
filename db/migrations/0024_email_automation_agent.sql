CREATE TABLE ltc.email_automation_config (
    config_id boolean PRIMARY KEY DEFAULT true,
    enabled boolean NOT NULL DEFAULT false,
    interval_minutes integer NOT NULL DEFAULT 60,
    min_score numeric(6,2) NOT NULL DEFAULT 75,
    regions jsonb NOT NULL DEFAULT '["NA", "EU"]'::jsonb,
    max_per_run integer NOT NULL DEFAULT 10,
    sender_user_id uuid REFERENCES ltc.user_account(user_id),
    sales_name text NOT NULL DEFAULT 'Global Marketing Team',
    template_subject text NOT NULL DEFAULT '',
    template_body text NOT NULL DEFAULT '',
    next_run_at timestamptz,
    last_run_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_email_automation_config_singleton CHECK (config_id),
    CONSTRAINT ck_email_automation_interval CHECK (interval_minutes BETWEEN 1 AND 10080),
    CONSTRAINT ck_email_automation_min_score CHECK (min_score BETWEEN 0 AND 100),
    CONSTRAINT ck_email_automation_regions_array CHECK (jsonb_typeof(regions) = 'array'),
    CONSTRAINT ck_email_automation_max_per_run CHECK (max_per_run BETWEEN 1 AND 500)
);

CREATE TABLE ltc.email_automation_run (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    config_snapshot jsonb NOT NULL,
    candidate_count integer NOT NULL DEFAULT 0,
    sent_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    skipped_count integer NOT NULL DEFAULT 0,
    details jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_message text,
    CONSTRAINT ck_email_automation_run_status CHECK (status IN ('running', 'completed', 'failed')),
    CONSTRAINT ck_email_automation_run_config_object CHECK (jsonb_typeof(config_snapshot) = 'object'),
    CONSTRAINT ck_email_automation_run_details_array CHECK (jsonb_typeof(details) = 'array')
);

CREATE TABLE ltc.email_automation_touch (
    touch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    contact_id uuid NOT NULL REFERENCES ltc.contact(contact_id) ON DELETE RESTRICT,
    run_id uuid NOT NULL REFERENCES ltc.email_automation_run(run_id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'reserved',
    provider_message_id text,
    error_message text,
    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CONSTRAINT ck_email_automation_touch_status CHECK (status IN ('reserved', 'sent', 'failed')),
    CONSTRAINT uq_email_automation_touch_company UNIQUE (company_id)
);

CREATE INDEX ix_email_automation_run_started_at
    ON ltc.email_automation_run (started_at DESC);

CREATE INDEX ix_email_automation_touch_status
    ON ltc.email_automation_touch (status, reserved_at);

INSERT INTO ltc.email_automation_config (config_id)
VALUES (true)
ON CONFLICT (config_id) DO NOTHING;
