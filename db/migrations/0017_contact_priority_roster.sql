ALTER TABLE ltc.contact
    ADD COLUMN employment_status text NOT NULL DEFAULT 'unknown',
    ADD COLUMN legal_basis_status text NOT NULL DEFAULT 'unknown',
    ADD COLUMN last_verified_at timestamptz;

ALTER TABLE ltc.contact
    ADD CONSTRAINT ck_contact_employment_status
    CHECK (employment_status IN ('unknown', 'active', 'departed')),
    ADD CONSTRAINT ck_contact_legal_basis_status
    CHECK (legal_basis_status IN ('unknown', 'allowed', 'blocked'));

CREATE TABLE ltc.company_contact_roster (
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE CASCADE,
    contact_id uuid NOT NULL,
    roster_status text NOT NULL,
    position smallint,
    role_group text NOT NULL,
    priority_score numeric(6,2) NOT NULL,
    score_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
    recommendation_reason text NOT NULL,
    ranking_version text NOT NULL,
    is_pinned boolean NOT NULL DEFAULT false,
    engagement_locked boolean NOT NULL DEFAULT false,
    outreach_status text NOT NULL DEFAULT 'not_contacted',
    last_engagement_at timestamptz,
    override_reason text,
    selected_by uuid REFERENCES ltc.user_account(user_id),
    selected_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (company_id, contact_id),
    FOREIGN KEY (contact_id, company_id)
        REFERENCES ltc.contact(contact_id, company_id) ON DELETE CASCADE,
    CONSTRAINT ck_company_contact_roster_status
        CHECK (roster_status IN ('active', 'backup')),
    CONSTRAINT ck_company_contact_roster_position
        CHECK (
            (roster_status = 'active' AND position BETWEEN 1 AND 5)
            OR (roster_status = 'backup' AND position IS NULL)
        ),
    CONSTRAINT ck_company_contact_roster_role_group
        CHECK (role_group IN (
            'procurement', 'commercial', 'business', 'technical',
            'product', 'operations', 'finance_legal', 'executive', 'other'
        )),
    CONSTRAINT ck_company_contact_roster_score
        CHECK (priority_score BETWEEN 0 AND 100),
    CONSTRAINT ck_company_contact_roster_breakdown
        CHECK (jsonb_typeof(score_breakdown) = 'object'),
    CONSTRAINT ck_company_contact_roster_outreach_status
        CHECK (outreach_status IN (
            'not_contacted', 'scheduled', 'sent', 'replied',
            'meeting', 'bounced', 'opted_out'
        )),
    CONSTRAINT ck_company_contact_roster_version CHECK (version >= 0)
);

CREATE UNIQUE INDEX uq_company_contact_roster_active_position
    ON ltc.company_contact_roster (company_id, position)
    WHERE roster_status = 'active';

CREATE INDEX ix_company_contact_roster_company_score
    ON ltc.company_contact_roster (company_id, roster_status, priority_score DESC);

CREATE TABLE ltc.company_outreach_state (
    company_id uuid PRIMARY KEY REFERENCES ltc.company(company_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active',
    pause_reason text,
    paused_contact_id uuid,
    source_email_id uuid,
    paused_at timestamptz,
    resumed_at timestamptz,
    resumed_by uuid REFERENCES ltc.user_account(user_id),
    resume_reason text,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (paused_contact_id, company_id)
        REFERENCES ltc.contact(contact_id, company_id),
    FOREIGN KEY (source_email_id, company_id)
        REFERENCES ltc.email_message(email_id, company_id),
    CONSTRAINT ck_company_outreach_state_status
        CHECK (status IN ('active', 'paused')),
    CONSTRAINT ck_company_outreach_state_pause_shape
        CHECK (
            (status = 'active')
            OR (status = 'paused' AND pause_reason IS NOT NULL AND paused_at IS NOT NULL)
        ),
    CONSTRAINT ck_company_outreach_state_version CHECK (version >= 0)
);
