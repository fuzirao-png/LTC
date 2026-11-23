BEGIN;

CREATE SCHEMA IF NOT EXISTS ltc;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
SET search_path TO ltc, public;

-- LTC PostgreSQL target schema v3.6
-- Core tables: 42
-- Read-only views: 3 (not counted in core tables)
-- Scope: sales / strategic accounts, current S1/S2/S3 runtime only.

CREATE OR REPLACE FUNCTION ltc.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.validate_job_attempt_metrics_v1(p_metrics jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    k text;
    status_text text;
    input_tokens integer;
    output_tokens integer;
    cached_input_tokens integer;
    total_tokens integer;
    latency_ms integer;
BEGIN
    IF p_metrics IS NULL OR jsonb_typeof(p_metrics) <> 'object' THEN
        RETURN false;
    END IF;

    IF NOT (p_metrics ?& ARRAY[
        'schema_version',
        'input_tokens',
        'output_tokens',
        'cached_input_tokens',
        'total_tokens',
        'latency_ms',
        'cost_amount',
        'currency',
        'cost_status'
    ]) THEN
        RETURN false;
    END IF;

    FOR k IN SELECT jsonb_object_keys(p_metrics)
    LOOP
        IF k NOT IN (
            'schema_version',
            'input_tokens',
            'output_tokens',
            'cached_input_tokens',
            'total_tokens',
            'latency_ms',
            'cost_amount',
            'currency',
            'cost_status'
        ) THEN
            RETURN false;
        END IF;
    END LOOP;

    IF (p_metrics->>'schema_version')::integer <> 1 THEN
        RETURN false;
    END IF;

    input_tokens := (p_metrics->>'input_tokens')::integer;
    output_tokens := (p_metrics->>'output_tokens')::integer;
    cached_input_tokens := (p_metrics->>'cached_input_tokens')::integer;
    total_tokens := (p_metrics->>'total_tokens')::integer;
    latency_ms := (p_metrics->>'latency_ms')::integer;

    IF input_tokens < 0 OR output_tokens < 0 OR cached_input_tokens < 0 OR total_tokens < 0 OR latency_ms < 0 THEN
        RETURN false;
    END IF;

    IF total_tokens <> input_tokens + output_tokens THEN
        RETURN false;
    END IF;

    status_text := p_metrics->>'cost_status';
    IF status_text NOT IN ('confirmed', 'estimated', 'unknown') THEN
        RETURN false;
    END IF;

    IF status_text IN ('confirmed', 'estimated') THEN
        IF p_metrics->>'cost_amount' IS NULL OR p_metrics->>'currency' IS NULL THEN
            RETURN false;
        END IF;
        IF (p_metrics->>'cost_amount') !~ '^[0-9]+(\.[0-9]{1,6})?$' THEN
            RETURN false;
        END IF;
        IF p_metrics->>'currency' !~ '^[A-Z]{3}$' THEN
            RETURN false;
        END IF;
    ELSE
        IF p_metrics->>'cost_amount' IS NOT NULL OR p_metrics->>'currency' IS NOT NULL THEN
            RETURN false;
        END IF;
    END IF;

    RETURN true;
EXCEPTION
    WHEN others THEN
        RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.validate_meeting_summary_v1(p_summary jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    k text;
    item jsonb;
    array_key text;
BEGIN
    IF p_summary IS NULL OR jsonb_typeof(p_summary) <> 'object' THEN
        RETURN false;
    END IF;

    IF NOT (p_summary ?& ARRAY[
        'customer_needs',
        'pain_points',
        'buying_signals',
        'action_items',
        'decisions',
        'risks',
        'keywords',
        'next_step'
    ]) THEN
        RETURN false;
    END IF;

    FOR k IN SELECT jsonb_object_keys(p_summary)
    LOOP
        IF k NOT IN (
            'customer_needs',
            'pain_points',
            'buying_signals',
            'action_items',
            'decisions',
            'risks',
            'keywords',
            'next_step'
        ) THEN
            RETURN false;
        END IF;
    END LOOP;

    IF jsonb_typeof(p_summary->'customer_needs') <> 'array'
       OR jsonb_typeof(p_summary->'pain_points') <> 'array'
       OR jsonb_typeof(p_summary->'buying_signals') <> 'array'
       OR jsonb_typeof(p_summary->'action_items') <> 'array'
       OR jsonb_typeof(p_summary->'decisions') <> 'array'
       OR jsonb_typeof(p_summary->'risks') <> 'array'
       OR jsonb_typeof(p_summary->'keywords') <> 'array' THEN
        RETURN false;
    END IF;

    IF jsonb_typeof(p_summary->'next_step') NOT IN ('string', 'null') THEN
        RETURN false;
    END IF;

    FOREACH array_key IN ARRAY ARRAY[
        'customer_needs',
        'pain_points',
        'buying_signals',
        'decisions',
        'risks',
        'keywords'
    ]
    LOOP
        FOR item IN SELECT value FROM jsonb_array_elements(p_summary->array_key)
        LOOP
            IF jsonb_typeof(item) <> 'string' THEN
                RETURN false;
            END IF;
        END LOOP;
    END LOOP;

    FOR item IN SELECT value FROM jsonb_array_elements(p_summary->'action_items')
    LOOP
        IF jsonb_typeof(item) <> 'object' THEN
            RETURN false;
        END IF;
        IF NOT (item ? 'task') THEN
            RETURN false;
        END IF;
        FOR k IN SELECT jsonb_object_keys(item)
        LOOP
            IF k NOT IN ('task', 'owner', 'due_at') THEN
                RETURN false;
            END IF;
        END LOOP;
        IF jsonb_typeof(item->'task') <> 'string' OR btrim(item->>'task') = '' THEN
            RETURN false;
        END IF;
        IF item ? 'owner' AND jsonb_typeof(item->'owner') NOT IN ('string', 'null') THEN
            RETURN false;
        END IF;
        IF item ? 'due_at' AND jsonb_typeof(item->'due_at') NOT IN ('string', 'null') THEN
            RETURN false;
        END IF;
        IF item ? 'due_at' AND jsonb_typeof(item->'due_at') = 'string' THEN
            IF item->>'due_at' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$' THEN
                RETURN false;
            END IF;
            PERFORM (item->>'due_at')::timestamptz;
        END IF;
    END LOOP;

    RETURN true;
EXCEPTION
    WHEN others THEN
        RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.prevent_candidate_promotion_fact_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.processing_status = 'promoted' AND (
        NEW.promoted_company_id IS DISTINCT FROM OLD.promoted_company_id OR
        NEW.promoted_lead_id IS DISTINCT FROM OLD.promoted_lead_id OR
        NEW.selected_icp_assessment_id IS DISTINCT FROM OLD.selected_icp_assessment_id OR
        NEW.selected_scale_assessment_id IS DISTINCT FROM OLD.selected_scale_assessment_id OR
        NEW.promotion_result IS DISTINCT FROM OLD.promotion_result OR
        NEW.promotion_decision_source IS DISTINCT FROM OLD.promotion_decision_source OR
        NEW.promotion_override_reason IS DISTINCT FROM OLD.promotion_override_reason OR
        NEW.promoted_by IS DISTINCT FROM OLD.promoted_by OR
        NEW.promoted_at IS DISTINCT FROM OLD.promoted_at
    ) THEN
        RAISE EXCEPTION 'promoted candidate selection facts are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_sales_lead_snapshot_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.data_completion_pool IS NULL AND (
        NEW.adopted_icp_assessment_id IS DISTINCT FROM OLD.adopted_icp_assessment_id OR
        NEW.adopted_scale_assessment_id IS DISTINCT FROM OLD.adopted_scale_assessment_id OR
        NEW.required_sales_tier IS DISTINCT FROM OLD.required_sales_tier OR
        NEW.pool_region_code IS DISTINCT FROM OLD.pool_region_code OR
        NEW.pool_region_mapping_version IS DISTINCT FROM OLD.pool_region_mapping_version OR
        NEW.allocation_rule_version IS DISTINCT FROM OLD.allocation_rule_version
    ) THEN
        RAISE EXCEPTION 'formal pool snapshot fields are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_user_account_status_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'departed' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'departed user account is terminal and cannot be reactivated';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.assert_sales_lead_assignment_consistency(p_lead_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    lead_allocation_status text;
    lead_owner_user_id uuid;
    lead_assignment_started_at timestamptz;
    lead_required_sales_tier text;
    lead_pool_region_code text;
    active_assignment_count bigint;
    matching_assignment_count bigint;
BEGIN
    SELECT
        allocation_status,
        current_owner_user_id,
        current_assignment_started_at,
        required_sales_tier,
        pool_region_code
    INTO
        lead_allocation_status,
        lead_owner_user_id,
        lead_assignment_started_at,
        lead_required_sales_tier,
        lead_pool_region_code
    FROM ltc.sales_lead
    WHERE lead_id = p_lead_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT
        COUNT(*) FILTER (WHERE la.status = 'active'),
        COUNT(*) FILTER (
            WHERE la.status = 'active'
              AND la.assignee_user_id = lead_owner_user_id
              AND la.assigned_at = lead_assignment_started_at
              AND ua.account_type = 'sales'
              AND ua.status IN ('active', 'disabled')
              AND ua.sales_tier = lead_required_sales_tier
              AND ua.region_code = lead_pool_region_code
        )
    INTO active_assignment_count, matching_assignment_count
    FROM ltc.lead_assignment la
    LEFT JOIN ltc.user_account ua
        ON ua.user_id = la.assignee_user_id
    WHERE la.lead_id = p_lead_id;

    IF lead_allocation_status = 'claimed' THEN
        IF active_assignment_count <> 1 OR matching_assignment_count <> 1 THEN
            RAISE EXCEPTION
                'claimed lead % must have exactly one matching active assignment',
                p_lead_id;
        END IF;
    ELSIF active_assignment_count <> 0 THEN
        RAISE EXCEPTION
            'non-claimed lead % cannot have an active assignment',
            p_lead_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_user_assignment_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assigned_lead_id uuid;
BEGIN
    IF NEW.status = 'departed' AND EXISTS (
        SELECT 1
        FROM ltc.lead_assignment
        WHERE assignee_user_id = NEW.user_id
          AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'departed user % cannot retain active assignments', NEW.user_id;
    END IF;

    FOR assigned_lead_id IN
        SELECT lead_id
        FROM ltc.lead_assignment
        WHERE assignee_user_id = NEW.user_id
          AND status = 'active'
    LOOP
        PERFORM ltc.assert_sales_lead_assignment_consistency(assigned_lead_id);
    END LOOP;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_sales_lead_assignment_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'sales_lead' THEN
        IF TG_OP = 'DELETE' THEN
            PERFORM ltc.assert_sales_lead_assignment_consistency(OLD.lead_id);
        ELSE
            PERFORM ltc.assert_sales_lead_assignment_consistency(NEW.lead_id);
        END IF;
    ELSE
        IF TG_OP = 'DELETE' THEN
            PERFORM ltc.assert_sales_lead_assignment_consistency(OLD.lead_id);
        ELSIF TG_OP = 'INSERT' THEN
            PERFORM ltc.assert_sales_lead_assignment_consistency(NEW.lead_id);
        ELSE
            IF OLD.lead_id IS DISTINCT FROM NEW.lead_id THEN
                PERFORM ltc.assert_sales_lead_assignment_consistency(OLD.lead_id);
            END IF;
            PERFORM ltc.assert_sales_lead_assignment_consistency(NEW.lead_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.enforce_analysis_report_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (to_jsonb(NEW) - 'superseded_at') IS DISTINCT FROM (to_jsonb(OLD) - 'superseded_at') THEN
        RAISE EXCEPTION 'analysis report content is immutable; create a new version';
    END IF;
    IF OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS DISTINCT FROM OLD.superseded_at THEN
        RAISE EXCEPTION 'superseded analysis report cannot be reactivated or rescheduled';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION ltc.prevent_history_hard_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'hard delete is forbidden for history table %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END;
$$;

-- ---------------------------------------------------------------------------
-- IAM: 3 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.user_account (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    email text,
    account_type text NOT NULL,
    sales_tier text,
    region_code text,
    capacity_limit integer,
    status text NOT NULL DEFAULT 'active',
    failed_login_attempts smallint NOT NULL DEFAULT 0,
    locked_until timestamptz,
    departed_at timestamptz,
    departed_by uuid REFERENCES ltc.user_account(user_id),
    departure_reason text,
    token_version integer NOT NULL DEFAULT 1,
    last_login_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_user_account_type CHECK (account_type IN ('sales', 'strategic')),
    CONSTRAINT ck_user_account_sales_tier CHECK (sales_tier IS NULL OR sales_tier IN ('MA', 'SA', 'A')),
    CONSTRAINT ck_user_account_region_code CHECK (region_code IS NULL OR region_code IN ('NA', 'EA', 'SEA', 'EU', 'ME', 'OTHER')),
    CONSTRAINT ck_user_account_status CHECK (status IN ('active', 'disabled', 'departed')),
    CONSTRAINT ck_user_account_capacity_limit CHECK (capacity_limit IS NULL OR capacity_limit > 0),
    CONSTRAINT ck_user_account_failed_login_attempts CHECK (failed_login_attempts >= 0),
    CONSTRAINT ck_user_account_token_version CHECK (token_version > 0),
    CONSTRAINT ck_user_account_version CHECK (version >= 0),
    CONSTRAINT ck_user_account_email_normalized CHECK (email IS NULL OR email = lower(btrim(email))),
    CONSTRAINT ck_user_account_sales_shape CHECK (
        (account_type = 'sales' AND sales_tier IS NOT NULL AND region_code IS NOT NULL AND capacity_limit IS NOT NULL)
        OR
        (account_type = 'strategic' AND sales_tier IS NULL AND region_code IS NULL AND capacity_limit IS NULL)
    ),
    CONSTRAINT ck_user_account_departed_shape CHECK (
        (status = 'departed' AND departed_at IS NOT NULL AND departed_by IS NOT NULL AND departure_reason IS NOT NULL)
        OR
        (status <> 'departed' AND departed_at IS NULL AND departed_by IS NULL AND departure_reason IS NULL)
    )
);

CREATE TABLE ltc.auth_session (
    session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES ltc.user_account(user_id) ON DELETE CASCADE,
    refresh_token_hash text NOT NULL,
    issued_token_version integer NOT NULL,
    ip_address inet,
    user_agent text,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoke_reason text,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_auth_session_issued_token_version CHECK (issued_token_version > 0),
    CONSTRAINT ck_auth_session_refresh_token_hash CHECK (btrim(refresh_token_hash) <> ''),
    CONSTRAINT ck_auth_session_revoke_reason CHECK (revoke_reason IS NULL OR revoke_reason IN ('logout', 'disabled', 'departed', 'security')),
    CONSTRAINT ck_auth_session_expires_after_create CHECK (expires_at > created_at),
    CONSTRAINT ck_auth_session_revoke_shape CHECK (
        (revoked_at IS NULL AND revoke_reason IS NULL)
        OR
        (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)
    )
);

CREATE TABLE ltc.ref_region_country (
    country_code text PRIMARY KEY,
    country_name text NOT NULL,
    region_code text NOT NULL,
    subregion text,
    default_timezone text,
    data_version text NOT NULL,
    note text,
    CONSTRAINT ck_ref_region_country_country_code CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_ref_region_country_country_name CHECK (btrim(country_name) <> ''),
    CONSTRAINT ck_ref_region_country_region_code CHECK (region_code IN ('NA', 'EA', 'SEA', 'EU', 'ME', 'OTHER')),
    CONSTRAINT ck_ref_region_country_default_timezone CHECK (
        default_timezone IS NULL OR default_timezone ~ '^[A-Za-z_+-]+/[A-Za-z0-9_+/-]+$'
    ),
    CONSTRAINT ck_ref_region_country_data_version CHECK (btrim(data_version) <> '')
);

-- ---------------------------------------------------------------------------
-- Task Runtime: 8 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.job (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type text NOT NULL,
    queue_name text NOT NULL,
    aggregate_type text,
    aggregate_id uuid,
    concurrency_key text,
    retry_of_job_id uuid REFERENCES ltc.job(job_id),
    status text NOT NULL,
    priority smallint NOT NULL DEFAULT 100,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_summary jsonb,
    progress_percent numeric(5,2) NOT NULL DEFAULT 0,
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    run_after timestamptz NOT NULL DEFAULT clock_timestamp(),
    locked_by text,
    lock_token uuid,
    locked_until timestamptz,
    last_error_code text,
    last_error_message text,
    correlation_id uuid,
    created_by uuid REFERENCES ltc.user_account(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_job_status CHECK (status IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed_final', 'cancelled', 'reconcile_required', 'dead')),
    CONSTRAINT ck_job_priority CHECK (priority BETWEEN 0 AND 1000),
    CONSTRAINT ck_job_progress_percent CHECK (progress_percent >= 0 AND progress_percent <= 100),
    CONSTRAINT ck_job_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_job_max_attempts CHECK (max_attempts > 0),
    CONSTRAINT ck_job_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_job_result_summary_object CHECK (result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'),
    CONSTRAINT ck_job_version CHECK (version >= 0),
    CONSTRAINT ck_job_running_lock_shape CHECK (
        (status = 'running' AND locked_by IS NOT NULL AND lock_token IS NOT NULL AND locked_until IS NOT NULL)
        OR
        (status <> 'running')
    ),
    CONSTRAINT ck_job_terminal_shape CHECK (
        (status IN ('succeeded', 'failed_final', 'cancelled', 'reconcile_required', 'dead') AND completed_at IS NOT NULL AND locked_by IS NULL AND lock_token IS NULL AND locked_until IS NULL)
        OR
        (status NOT IN ('succeeded', 'failed_final', 'cancelled', 'reconcile_required', 'dead'))
    )
);

CREATE TABLE ltc.job_attempt (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES ltc.job(job_id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    worker_id text NOT NULL,
    lock_token uuid NOT NULL,
    status text NOT NULL,
    provider_code text,
    provider_request_id text,
    request_summary jsonb,
    response_summary jsonb,
    metrics jsonb NOT NULL,
    error_code text,
    error_message text,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT ck_job_attempt_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT ck_job_attempt_status CHECK (status IN ('started', 'succeeded', 'failed', 'lease_lost')),
    CONSTRAINT ck_job_attempt_request_summary_object CHECK (request_summary IS NULL OR jsonb_typeof(request_summary) = 'object'),
    CONSTRAINT ck_job_attempt_response_summary_object CHECK (response_summary IS NULL OR jsonb_typeof(response_summary) = 'object'),
    CONSTRAINT ck_job_attempt_metrics_shape CHECK (ltc.validate_job_attempt_metrics_v1(metrics)),
    CONSTRAINT ck_job_attempt_completed_shape CHECK (
        (status = 'started' AND completed_at IS NULL)
        OR
        (status <> 'started' AND completed_at IS NOT NULL)
    ),
    CONSTRAINT uq_job_attempt_attempt_no UNIQUE (job_id, attempt_no)
);

CREATE TABLE ltc.job_progress_event (
    progress_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES ltc.job(job_id) ON DELETE CASCADE,
    sequence_no integer NOT NULL,
    event_type text NOT NULL,
    step_code text,
    progress_percent numeric(5,2),
    message text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_job_progress_event_sequence_no CHECK (sequence_no > 0),
    CONSTRAINT ck_job_progress_event_progress_percent CHECK (progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)),
    CONSTRAINT ck_job_progress_event_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT uq_job_progress_event_sequence_no UNIQUE (job_id, sequence_no)
);

CREATE TABLE ltc.idempotency_record (
    idempotency_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope text NOT NULL,
    principal_type text NOT NULL,
    principal_id text NOT NULL,
    actor_user_id uuid REFERENCES ltc.user_account(user_id),
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    state text NOT NULL,
    resource_type text,
    resource_id uuid,
    response_status integer,
    response_body jsonb,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_idempotency_principal_type CHECK (principal_type IN ('user', 'system', 'event_consumer')),
    CONSTRAINT ck_idempotency_state CHECK (state IN ('in_progress', 'completed', 'failed')),
    CONSTRAINT ck_idempotency_response_status CHECK (response_status IS NULL OR (response_status BETWEEN 100 AND 599)),
    CONSTRAINT ck_idempotency_response_body_shape CHECK (response_body IS NULL OR jsonb_typeof(response_body) IN ('object', 'array')),
    CONSTRAINT ck_idempotency_user_shape CHECK (
        (principal_type = 'user' AND actor_user_id IS NOT NULL AND principal_id = actor_user_id::text)
        OR
        (principal_type IN ('system', 'event_consumer') AND actor_user_id IS NULL)
    ),
    CONSTRAINT ck_idempotency_expires_at CHECK (expires_at > created_at)
);

CREATE TABLE ltc.outbox_event (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type text NOT NULL,
    schema_version smallint NOT NULL DEFAULT 1,
    producer text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_version bigint NOT NULL,
    payload jsonb NOT NULL,
    headers jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending',
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    attempt_count integer NOT NULL DEFAULT 0,
    locked_by text,
    lock_token uuid,
    locked_until timestamptz,
    published_at timestamptz,
    last_error text,
    correlation_id uuid,
    causation_id uuid,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_outbox_event_schema_version CHECK (schema_version > 0),
    CONSTRAINT ck_outbox_event_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_outbox_event_headers_object CHECK (jsonb_typeof(headers) = 'object'),
    CONSTRAINT ck_outbox_event_status CHECK (status IN ('pending', 'processing', 'published', 'dead')),
    CONSTRAINT ck_outbox_event_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_outbox_event_processing_lock_shape CHECK (
        (status = 'processing' AND locked_by IS NOT NULL AND lock_token IS NOT NULL AND locked_until IS NOT NULL)
        OR
        (status <> 'processing')
    ),
    CONSTRAINT ck_outbox_event_published_shape CHECK (
        (status = 'published' AND published_at IS NOT NULL)
        OR
        (status <> 'published')
    ),
    CONSTRAINT uq_outbox_event_aggregate_event UNIQUE (aggregate_type, aggregate_id, aggregate_version, event_type)
);

CREATE TABLE ltc.external_event (
    external_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code text NOT NULL,
    provider_event_id text NOT NULL,
    event_type text NOT NULL,
    payload_hash text NOT NULL,
    payload jsonb NOT NULL,
    signature_valid boolean NOT NULL,
    status text NOT NULL DEFAULT 'received',
    linked_resource_type text,
    linked_resource_id uuid,
    attempt_count integer NOT NULL DEFAULT 0,
    last_error text,
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    processed_at timestamptz,
    CONSTRAINT ck_external_event_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_external_event_status CHECK (status IN ('received', 'processing', 'processed', 'quarantined', 'dead')),
    CONSTRAINT ck_external_event_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_external_event_processed_shape CHECK (
        (status IN ('processed', 'quarantined', 'dead') AND processed_at IS NOT NULL)
        OR
        (status IN ('received', 'processing'))
    ),
    CONSTRAINT uq_external_event_provider_event UNIQUE (provider_code, provider_event_id)
);

CREATE TABLE ltc.audit_log (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id uuid REFERENCES ltc.user_account(user_id),
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid,
    request_id text,
    job_id uuid REFERENCES ltc.job(job_id),
    before_data jsonb,
    after_data jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_audit_log_before_data_object CHECK (before_data IS NULL OR jsonb_typeof(before_data) = 'object'),
    CONSTRAINT ck_audit_log_after_data_object CHECK (after_data IS NULL OR jsonb_typeof(after_data) = 'object'),
    CONSTRAINT ck_audit_log_metadata_object CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE ltc.media_asset (
    media_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid,
    parent_media_asset_id uuid REFERENCES ltc.media_asset(media_asset_id),
    asset_kind text NOT NULL,
    storage_backend text NOT NULL,
    storage_key text NOT NULL,
    original_filename text,
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 text NOT NULL,
    status text NOT NULL,
    validation_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    retention_until timestamptz,
    deleted_at timestamptz,
    created_by uuid REFERENCES ltc.user_account(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_media_asset_kind CHECK (asset_kind IN ('search_content', 'email_attachment', 'meeting_source', 'normalized_audio', 'chunk', 'export')),
    CONSTRAINT ck_media_asset_storage_backend CHECK (storage_backend IN ('local', 'oss', 's3')),
    CONSTRAINT ck_media_asset_size_bytes CHECK (size_bytes >= 0),
    CONSTRAINT ck_media_asset_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_media_asset_status CHECK (status IN ('quarantined', 'ready', 'rejected', 'deleted')),
    CONSTRAINT ck_media_asset_validation_payload_object CHECK (jsonb_typeof(validation_payload) = 'object'),
    CONSTRAINT ck_media_asset_deleted_shape CHECK (
        (status = 'deleted' AND deleted_at IS NOT NULL)
        OR
        (status <> 'deleted')
    ),
    CONSTRAINT uq_media_asset_storage UNIQUE (storage_backend, storage_key)
);

-- ---------------------------------------------------------------------------
-- Lead Intelligence: 12 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.lead_search_run (
    search_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dialogue_session_id text,
    query_text text NOT NULL,
    search_mode text NOT NULL,
    target_count integer NOT NULL,
    scene_code text NOT NULL,
    orchestration_profile text NOT NULL,
    orchestration_profile_version text NOT NULL,
    prompt_version text NOT NULL,
    config_checksum text NOT NULL,
    status text NOT NULL,
    evidence_count integer NOT NULL DEFAULT 0,
    candidate_count integer NOT NULL DEFAULT 0,
    enriched_count integer NOT NULL DEFAULT 0,
    scored_count integer NOT NULL DEFAULT 0,
    duplicate_count integer NOT NULL DEFAULT 0,
    rejected_count integer NOT NULL DEFAULT 0,
    current_job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    last_error_code text,
    last_error_message text,
    requested_by uuid REFERENCES ltc.user_account(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_lead_search_run_search_mode CHECK (search_mode IN ('company_only', 'contact_only', 'both')),
    CONSTRAINT ck_lead_search_run_target_count CHECK (target_count BETWEEN 1 AND 200),
    CONSTRAINT ck_lead_search_run_scene_code CHECK (scene_code IN ('S1', 'S2', 'S3')),
    CONSTRAINT ck_lead_search_run_status CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')),
    CONSTRAINT ck_lead_search_run_counts CHECK (
        evidence_count >= 0 AND candidate_count >= 0 AND enriched_count >= 0
        AND scored_count >= 0 AND duplicate_count >= 0 AND rejected_count >= 0
    ),
    CONSTRAINT ck_lead_search_run_version CHECK (version >= 0),
    CONSTRAINT ck_lead_search_run_completed_shape CHECK (
        (status IN ('completed', 'partial', 'failed', 'cancelled') AND completed_at IS NOT NULL)
        OR
        (status IN ('queued', 'running'))
    )
);

CREATE TABLE ltc.search_provider_execution (
    provider_execution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_run_id uuid NOT NULL REFERENCES ltc.lead_search_run(search_run_id) ON DELETE CASCADE,
    job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    job_attempt_id uuid REFERENCES ltc.job_attempt(attempt_id),
    retry_of_provider_execution_id uuid REFERENCES ltc.search_provider_execution(provider_execution_id),
    provider_code text NOT NULL,
    provider_operation text NOT NULL,
    request_hash text NOT NULL,
    request_payload jsonb NOT NULL,
    status text NOT NULL,
    result_count integer NOT NULL DEFAULT 0,
    latency_ms integer,
    cost_amount numeric(12,6),
    cost_currency text,
    external_request_id text,
    error_code text,
    error_message text,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_search_provider_execution_provider_code CHECK (provider_code IN ('web_search', 'apollo')),
    CONSTRAINT ck_search_provider_execution_provider_operation CHECK (provider_operation IN ('search', 'company_lookup', 'contact_lookup')),
    CONSTRAINT ck_search_provider_execution_request_payload_object CHECK (jsonb_typeof(request_payload) = 'object'),
    CONSTRAINT ck_search_provider_execution_status CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT ck_search_provider_execution_result_count CHECK (result_count >= 0),
    CONSTRAINT ck_search_provider_execution_latency_ms CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT ck_search_provider_execution_cost_amount CHECK (cost_amount IS NULL OR cost_amount >= 0),
    CONSTRAINT ck_search_provider_execution_cost_currency CHECK (cost_currency IS NULL OR cost_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_search_provider_execution_completed_shape CHECK (
        (status = 'running' AND completed_at IS NULL)
        OR
        (status IN ('succeeded', 'failed', 'cancelled') AND completed_at IS NOT NULL)
    ),
    CONSTRAINT uq_search_provider_execution_provider_execution_provider UNIQUE (provider_execution_id, provider_code)
);

CREATE TABLE ltc.search_evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_run_id uuid REFERENCES ltc.lead_search_run(search_run_id) ON DELETE SET NULL,
    provider_execution_id uuid,
    job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    search_phase text NOT NULL,
    attempt_no integer NOT NULL,
    query_text text NOT NULL,
    provider_code text NOT NULL,
    provider_result_id text,
    rank_no integer,
    url text,
    canonical_url text,
    domain text,
    title text,
    snippet text,
    content_asset_id uuid REFERENCES ltc.media_asset(media_asset_id),
    raw_payload jsonb NOT NULL,
    content_hash text NOT NULL,
    fetched_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_search_evidence_phase CHECK (search_phase IN ('collection', 'icp_enrichment', 'scale_assessment')),
    CONSTRAINT ck_search_evidence_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT ck_search_evidence_rank_no CHECK (rank_no IS NULL OR rank_no > 0),
    CONSTRAINT ck_search_evidence_raw_payload_object CHECK (jsonb_typeof(raw_payload) = 'object'),
    CONSTRAINT ck_search_evidence_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE ltc.lead_candidate (
    candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dedupe_key text NOT NULL,
    company_name text NOT NULL,
    normalized_company_name text NOT NULL,
    legal_name text,
    website text,
    normalized_domain text,
    company_intro text,
    industry_code text,
    employee_count integer,
    region_code text,
    country_code text,
    region_mapping_version text,
    city text,
    identity_confidence numeric(5,4),
    validation_status text NOT NULL,
    processing_status text NOT NULL,
    negative_filter_result text,
    assessments_stale boolean NOT NULL DEFAULT false,
    promoted_company_id uuid,
    promoted_lead_id uuid,
    selected_icp_assessment_id uuid,
    selected_scale_assessment_id uuid,
    promotion_result text,
    promotion_decision_source text,
    promotion_override_reason text,
    promoted_by uuid REFERENCES ltc.user_account(user_id),
    promoted_at timestamptz,
    merged_into_candidate_id uuid REFERENCES ltc.lead_candidate(candidate_id),
    merged_at timestamptz,
    reject_reason text,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_lead_candidate_industry_code CHECK (
        industry_code IS NULL OR industry_code IN ('TMC', 'TRAVEL_OTA', 'FINTECH', 'OTHER')
    ),
    CONSTRAINT ck_lead_candidate_employee_count CHECK (employee_count IS NULL OR employee_count >= 0),
    CONSTRAINT ck_lead_candidate_region_code CHECK (region_code IS NULL OR region_code IN ('NA', 'EA', 'SEA', 'EU', 'ME', 'OTHER')),
    CONSTRAINT ck_lead_candidate_identity_confidence CHECK (identity_confidence IS NULL OR (identity_confidence >= 0 AND identity_confidence <= 1)),
    CONSTRAINT ck_lead_candidate_validation_status CHECK (validation_status IN ('valid', 'incomplete', 'review_required', 'rejected')),
    CONSTRAINT ck_lead_candidate_processing_status CHECK (processing_status IN ('collected', 'enriching', 'enriched', 'scored', 'eligible', 'promoted', 'rejected', 'merged', 'archived')),
    CONSTRAINT ck_lead_candidate_negative_filter_result CHECK (negative_filter_result IS NULL OR negative_filter_result IN ('none', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6')),
    CONSTRAINT ck_lead_candidate_version CHECK (version >= 0),
    CONSTRAINT ck_lead_candidate_region_mapping_version CHECK (
        region_code IS NULL OR region_mapping_version IS NOT NULL
    ),
    CONSTRAINT ck_lead_candidate_promoted_shape CHECK (
        (processing_status = 'promoted'
         AND promoted_company_id IS NOT NULL
         AND promoted_lead_id IS NOT NULL
         AND selected_icp_assessment_id IS NOT NULL
         AND selected_scale_assessment_id IS NOT NULL
         AND promotion_result IS NOT NULL
         AND promotion_decision_source IS NOT NULL
         AND promoted_by IS NOT NULL
         AND promoted_at IS NOT NULL)
        OR
        (processing_status <> 'promoted'
         AND promoted_company_id IS NULL
         AND promoted_lead_id IS NULL
         AND selected_icp_assessment_id IS NULL
         AND selected_scale_assessment_id IS NULL
         AND promotion_result IS NULL
         AND promotion_decision_source IS NULL
         AND promoted_by IS NULL
         AND promoted_at IS NULL)
    ),
    CONSTRAINT ck_lead_candidate_promotion_override_shape CHECK (
        (promotion_decision_source = 'strategic_override' AND promotion_override_reason IS NOT NULL)
        OR
        (promotion_decision_source IS DISTINCT FROM 'strategic_override' AND promotion_override_reason IS NULL)
    ),
    CONSTRAINT ck_lead_candidate_merged_shape CHECK (
        (processing_status = 'merged'
         AND merged_into_candidate_id IS NOT NULL
         AND merged_into_candidate_id <> candidate_id
         AND merged_at IS NOT NULL)
        OR
        (processing_status <> 'merged'
         AND merged_into_candidate_id IS NULL
         AND merged_at IS NULL)
    )
);

CREATE TABLE ltc.candidate_observation (
    observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    search_run_id uuid REFERENCES ltc.lead_search_run(search_run_id) ON DELETE SET NULL,
    source_kind text NOT NULL,
    observation_hash text NOT NULL,
    extraction_model text,
    prompt_version text NOT NULL,
    company_snapshot jsonb NOT NULL,
    contact_groups_payload jsonb NOT NULL,
    raw_extraction_payload jsonb NOT NULL,
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_candidate_observation_source_kind CHECK (source_kind IN ('live_extraction', 'legacy_extracted_row')),
    CONSTRAINT ck_candidate_observation_company_snapshot_object CHECK (jsonb_typeof(company_snapshot) = 'object'),
    CONSTRAINT ck_candidate_observation_contact_groups_payload_object CHECK (jsonb_typeof(contact_groups_payload) = 'object'),
    CONSTRAINT ck_candidate_observation_raw_extraction_payload_object CHECK (jsonb_typeof(raw_extraction_payload) = 'object'),
    CONSTRAINT uq_candidate_observation_candidate_run_hash UNIQUE (candidate_id, search_run_id, observation_hash)
);

CREATE TABLE ltc.candidate_evidence (
    candidate_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    evidence_id uuid NOT NULL REFERENCES ltc.search_evidence(evidence_id) ON DELETE CASCADE,
    observation_id uuid,
    relation_type text NOT NULL,
    confidence numeric(5,4),
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_candidate_evidence_relation_type CHECK (relation_type IN ('discovery', 'identity', 'contact', 'validation')),
    CONSTRAINT ck_candidate_evidence_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT uq_candidate_evidence_with_observation UNIQUE (candidate_id, evidence_id, relation_type, observation_id)
);

CREATE TABLE ltc.candidate_contact (
    candidate_contact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    observation_id uuid,
    full_name text NOT NULL,
    normalized_name text NOT NULL,
    title text,
    title_normalized text,
    department text,
    relationship_role text NOT NULL,
    priority text,
    email text,
    normalized_email text,
    email_status text,
    email_type text,
    email_score numeric(6,2),
    email_pattern text,
    phone text,
    linkedin_url text,
    identity_hash text NOT NULL,
    source_payload jsonb NOT NULL,
    status text NOT NULL,
    merged_into_candidate_id uuid,
    merged_into_candidate_contact_id uuid,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_candidate_contact_relationship_role CHECK (relationship_role IN ('decision_maker', 'influencer', 'executor', 'general_employee')),
    CONSTRAINT ck_candidate_contact_priority CHECK (priority IS NULL OR priority IN ('P1', 'P2', 'P3')),
    CONSTRAINT ck_candidate_contact_email_status CHECK (email_status IS NULL OR email_status IN ('unknown', 'valid', 'invalid', 'risky')),
    CONSTRAINT ck_candidate_contact_email_score CHECK (email_score IS NULL OR (email_score >= 0 AND email_score <= 100)),
    CONSTRAINT ck_candidate_contact_source_payload_object CHECK (jsonb_typeof(source_payload) = 'object'),
    CONSTRAINT ck_candidate_contact_status CHECK (status IN ('active', 'rejected', 'promoted', 'merged')),
    CONSTRAINT ck_candidate_contact_merged_shape CHECK (
        (status = 'merged' AND merged_into_candidate_id IS NOT NULL AND merged_into_candidate_contact_id IS NOT NULL)
        OR
        (status <> 'merged' AND merged_into_candidate_id IS NULL AND merged_into_candidate_contact_id IS NULL)
    ),
    CONSTRAINT uq_candidate_contact_identity_hash UNIQUE (candidate_id, identity_hash)
);

CREATE TABLE ltc.lead_enrichment_run (
    enrichment_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    version_no integer NOT NULL,
    status text NOT NULL,
    scene_code text NOT NULL,
    rule_version text NOT NULL,
    prompt_version text NOT NULL,
    config_checksum text NOT NULL,
    model_name text,
    d1_payload jsonb,
    d2_payload jsonb,
    d3_payload jsonb,
    d4_payload jsonb,
    output_hash text,
    current_job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    error_code text,
    error_message text,
    is_current boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    superseded_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_lead_enrichment_run_version_no CHECK (version_no > 0),
    CONSTRAINT ck_lead_enrichment_run_status CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'superseded')),
    CONSTRAINT ck_lead_enrichment_run_scene_code CHECK (scene_code IN ('S1', 'S2', 'S3')),
    CONSTRAINT ck_lead_enrichment_run_payloads CHECK (
        (d1_payload IS NULL OR jsonb_typeof(d1_payload) = 'object') AND
        (d2_payload IS NULL OR jsonb_typeof(d2_payload) = 'object') AND
        (d3_payload IS NULL OR jsonb_typeof(d3_payload) = 'object') AND
        (d4_payload IS NULL OR jsonb_typeof(d4_payload) = 'object')
    ),
    CONSTRAINT ck_lead_enrichment_run_version CHECK (version >= 0),
    CONSTRAINT ck_lead_enrichment_run_current_shape CHECK (
        (is_current = true AND status = 'completed' AND superseded_at IS NULL)
        OR
        (is_current = false)
    ),
    CONSTRAINT uq_lead_enrichment_run_candidate_version UNIQUE (candidate_id, version_no),
    CONSTRAINT uq_lead_enrichment_run_self_candidate UNIQUE (enrichment_run_id, candidate_id)
);

CREATE TABLE ltc.enrichment_evidence (
    enrichment_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    enrichment_run_id uuid NOT NULL REFERENCES ltc.lead_enrichment_run(enrichment_run_id) ON DELETE CASCADE,
    evidence_id uuid NOT NULL REFERENCES ltc.search_evidence(evidence_id) ON DELETE CASCADE,
    dimension_code text NOT NULL,
    evidence_role text NOT NULL,
    is_proxy boolean NOT NULL DEFAULT false,
    confidence numeric(5,4),
    excerpt text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_enrichment_evidence_dimension_code CHECK (dimension_code IN ('D1', 'D2', 'D3', 'D4')),
    CONSTRAINT ck_enrichment_evidence_role CHECK (evidence_role IN ('primary', 'supporting', 'contradictory')),
    CONSTRAINT ck_enrichment_evidence_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT uq_enrichment_evidence UNIQUE (enrichment_run_id, evidence_id, dimension_code, evidence_role)
);

CREATE TABLE ltc.lead_icp_assessment (
    icp_assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    enrichment_run_id uuid NOT NULL REFERENCES ltc.lead_enrichment_run(enrichment_run_id) ON DELETE RESTRICT,
    version_no integer NOT NULL,
    scene_code text NOT NULL,
    rule_version text NOT NULL,
    rule_snapshot jsonb NOT NULL,
    rule_checksum text NOT NULL,
    prompt_version text NOT NULL,
    d1_score numeric(6,2) NOT NULL,
    d2_score numeric(6,2) NOT NULL,
    d3_score numeric(6,2) NOT NULL,
    d4_score numeric(6,2) NOT NULL,
    total_score numeric(6,2) NOT NULL,
    grade text NOT NULL,
    hard_gate_passed boolean NOT NULL,
    confidence numeric(5,4),
    score_breakdown jsonb NOT NULL,
    explanations jsonb NOT NULL,
    evidence_sources jsonb,
    job_id uuid REFERENCES ltc.job(job_id),
    is_current boolean NOT NULL DEFAULT false,
    scored_at timestamptz NOT NULL,
    superseded_at timestamptz,
    CONSTRAINT ck_lead_icp_assessment_version_no CHECK (version_no > 0),
    CONSTRAINT ck_lead_icp_assessment_scene_code CHECK (scene_code IN ('S1', 'S2', 'S3')),
    CONSTRAINT ck_lead_icp_assessment_rule_snapshot_object CHECK (jsonb_typeof(rule_snapshot) = 'object'),
    CONSTRAINT ck_lead_icp_assessment_rule_checksum CHECK (rule_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_lead_icp_assessment_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_lead_icp_assessment_score_breakdown_object CHECK (jsonb_typeof(score_breakdown) = 'object'),
    CONSTRAINT ck_lead_icp_assessment_explanations_object CHECK (jsonb_typeof(explanations) = 'object'),
    CONSTRAINT ck_lead_icp_assessment_evidence_sources_object CHECK (evidence_sources IS NULL OR jsonb_typeof(evidence_sources) = 'object'),
    CONSTRAINT ck_lead_icp_assessment_grade CHECK (grade IN ('A', 'B', 'C', 'D')),
    CONSTRAINT ck_lead_icp_assessment_scores_non_negative CHECK (
        d1_score >= 0 AND d2_score >= 0 AND d3_score >= 0 AND d4_score >= 0 AND total_score >= 0 AND total_score <= 100
    ),
    CONSTRAINT ck_lead_icp_assessment_scene_limits CHECK (
        (
            scene_code = 'S1' AND
            d1_score <= 40 AND d2_score <= 30 AND d3_score <= 20 AND d4_score <= 10
        )
        OR
        (
            scene_code IN ('S2', 'S3') AND
            d1_score <= 35 AND d2_score <= 25 AND d3_score <= 25 AND d4_score <= 15
        )
    ),
    CONSTRAINT ck_lead_icp_assessment_total_score CHECK (total_score = d1_score + d2_score + d3_score + d4_score),
    CONSTRAINT ck_lead_icp_assessment_current_shape CHECK (
        (is_current = true AND superseded_at IS NULL)
        OR
        (is_current = false)
    ),
    CONSTRAINT uq_lead_icp_assessment_candidate_version UNIQUE (candidate_id, version_no),
    CONSTRAINT uq_lead_icp_assessment_self_candidate UNIQUE (icp_assessment_id, candidate_id)
);

CREATE TABLE ltc.customer_scale_assessment (
    scale_assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    source_enrichment_run_id uuid NOT NULL,
    version_no integer NOT NULL,
    rule_version text NOT NULL,
    prompt_version text NOT NULL,
    d1_scale_score numeric(6,2) NOT NULL,
    d2_commercial_score numeric(6,2) NOT NULL,
    d3_coverage_score numeric(6,2) NOT NULL,
    total_score numeric(6,2) NOT NULL,
    computed_tier text NOT NULL,
    effective_tier text NOT NULL,
    required_sales_tier text GENERATED ALWAYS AS (
        CASE effective_tier
            WHEN 'large' THEN 'MA'
            WHEN 'medium' THEN 'SA'
            WHEN 'small' THEN 'A'
            WHEN 'unknown' THEN 'A'
        END
    ) STORED,
    decision_source text NOT NULL,
    override_reason text,
    override_by uuid REFERENCES ltc.user_account(user_id),
    override_at timestamptz,
    assessment_payload jsonb NOT NULL,
    job_id uuid REFERENCES ltc.job(job_id),
    is_current boolean NOT NULL DEFAULT false,
    assessed_at timestamptz NOT NULL,
    superseded_at timestamptz,
    CONSTRAINT ck_customer_scale_assessment_version_no CHECK (version_no > 0),
    CONSTRAINT ck_customer_scale_assessment_scores CHECK (
        d1_scale_score >= 0 AND d1_scale_score <= 40 AND
        d2_commercial_score >= 0 AND d2_commercial_score <= 35 AND
        d3_coverage_score >= 0 AND d3_coverage_score <= 25 AND
        total_score = d1_scale_score + d2_commercial_score + d3_coverage_score
    ),
    CONSTRAINT ck_customer_scale_assessment_tiers CHECK (
        computed_tier IN ('large', 'medium', 'small', 'unknown')
        AND effective_tier IN ('large', 'medium', 'small', 'unknown')
    ),
    CONSTRAINT ck_customer_scale_assessment_decision_source CHECK (decision_source IN ('computed', 'manual_override')),
    CONSTRAINT ck_customer_scale_assessment_override_shape CHECK (
        (decision_source = 'computed' AND override_reason IS NULL AND override_by IS NULL AND override_at IS NULL)
        OR
        (decision_source = 'manual_override' AND override_reason IS NOT NULL AND override_by IS NOT NULL AND override_at IS NOT NULL)
    ),
    CONSTRAINT ck_customer_scale_assessment_assessment_payload_object CHECK (jsonb_typeof(assessment_payload) = 'object'),
    CONSTRAINT ck_customer_scale_assessment_current_shape CHECK (
        (is_current = true AND superseded_at IS NULL)
        OR
        (is_current = false)
    ),
    CONSTRAINT uq_customer_scale_assessment_candidate_version UNIQUE (candidate_id, version_no),
    CONSTRAINT uq_customer_scale_assessment_self_candidate UNIQUE (scale_assessment_id, candidate_id),
    CONSTRAINT uq_customer_scale_assessment_self_candidate_tier UNIQUE (scale_assessment_id, candidate_id, required_sales_tier)
);

CREATE TABLE ltc.lead_negative_filter_result (
    filter_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE CASCADE,
    search_run_id uuid REFERENCES ltc.lead_search_run(search_run_id) ON DELETE SET NULL,
    enrichment_run_id uuid REFERENCES ltc.lead_enrichment_run(enrichment_run_id) ON DELETE SET NULL,
    job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    rule_code text NOT NULL,
    verdict text NOT NULL,
    evidence_summary text,
    payload jsonb NOT NULL,
    rule_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_lead_negative_filter_result_rule_code CHECK (rule_code IN ('none', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6')),
    CONSTRAINT ck_lead_negative_filter_result_verdict CHECK (verdict IN ('pass', 'exclude', 'defer')),
    CONSTRAINT ck_lead_negative_filter_result_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_lead_negative_filter_result_rule_verdict CHECK (
        (rule_code = 'none' AND verdict = 'pass')
        OR
        (rule_code IN ('X1', 'X2', 'X5') AND verdict = 'exclude')
        OR
        (rule_code IN ('X3', 'X4', 'X6') AND verdict = 'defer')
    ),
    CONSTRAINT ck_lead_negative_filter_result_source_shape CHECK (
        search_run_id IS NOT NULL OR enrichment_run_id IS NOT NULL
    )
);

-- ---------------------------------------------------------------------------
-- Sales CRM: 5 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.company (
    company_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_candidate_id uuid REFERENCES ltc.lead_candidate(candidate_id),
    company_name text NOT NULL,
    normalized_company_name text NOT NULL,
    legal_name text,
    primary_domain text,
    website text,
    country_code text,
    region_code text,
    region_mapping_version text,
    city text,
    industry_code text,
    company_intro text,
    employee_count integer,
    lifecycle_status text NOT NULL DEFAULT 'prospect',
    version bigint NOT NULL DEFAULT 0,
    created_by uuid REFERENCES ltc.user_account(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    archived_at timestamptz,
    CONSTRAINT ck_company_region_code CHECK (region_code IS NULL OR region_code IN ('NA', 'EA', 'SEA', 'EU', 'ME', 'OTHER')),
    CONSTRAINT ck_company_industry_code CHECK (
        industry_code IS NULL OR industry_code IN ('TMC', 'TRAVEL_OTA', 'FINTECH', 'OTHER')
    ),
    CONSTRAINT ck_company_employee_count CHECK (employee_count IS NULL OR employee_count >= 0),
    CONSTRAINT ck_company_lifecycle_status CHECK (lifecycle_status IN ('prospect', 'active_customer', 'inactive', 'archived')),
    CONSTRAINT ck_company_version CHECK (version >= 0),
    CONSTRAINT ck_company_region_mapping_version CHECK (
        region_code IS NULL OR region_mapping_version IS NOT NULL
    )
);

CREATE TABLE ltc.contact (
    contact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    source_candidate_contact_id uuid REFERENCES ltc.candidate_contact(candidate_contact_id),
    full_name text NOT NULL,
    normalized_name text NOT NULL,
    title text,
    title_normalized text,
    department text,
    relationship_role text,
    priority text,
    primary_email text,
    normalized_email text,
    email_status text NOT NULL DEFAULT 'unknown',
    email_type text,
    email_score numeric(6,2),
    email_pattern text,
    phone text,
    linkedin_url text,
    source text NOT NULL,
    last_contacted_at timestamptz,
    status text NOT NULL DEFAULT 'active',
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_contact_relationship_role CHECK (relationship_role IS NULL OR relationship_role IN ('decision_maker', 'influencer', 'executor', 'general_employee')),
    CONSTRAINT ck_contact_priority CHECK (priority IS NULL OR priority IN ('P1', 'P2', 'P3')),
    CONSTRAINT ck_contact_email_status CHECK (email_status IN ('unknown', 'valid', 'invalid', 'risky', 'opted_out', 'bounced')),
    CONSTRAINT ck_contact_email_score CHECK (email_score IS NULL OR (email_score >= 0 AND email_score <= 100)),
    CONSTRAINT ck_contact_source CHECK (source IN ('candidate', 'manual', 'operation')),
    CONSTRAINT ck_contact_status CHECK (status IN ('active', 'inactive', 'archived')),
    CONSTRAINT ck_contact_version CHECK (version >= 0),
    CONSTRAINT uq_contact_self_company UNIQUE (contact_id, company_id)
);

CREATE TABLE ltc.sales_lead (
    lead_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    source_candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id) ON DELETE RESTRICT,
    adopted_icp_assessment_id uuid NOT NULL,
    adopted_scale_assessment_id uuid NOT NULL,
    required_sales_tier text NOT NULL,
    pool_region_code text,
    pool_region_mapping_version text,
    allocation_status text NOT NULL,
    pipeline_stage text NOT NULL,
    current_owner_user_id uuid REFERENCES ltc.user_account(user_id),
    current_assignment_started_at timestamptz,
    first_touch_at timestamptz,
    last_activity_at timestamptz,
    sla_due_at timestamptz,
    won_reason_code text,
    lost_reason_code text,
    closed_note text,
    released_reason text,
    closed_at timestamptz,
    data_completion_pool text,
    dynamic_bonus_points integer NOT NULL DEFAULT 0,
    a_segment text,
    allocation_rule_version text,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_sales_lead_required_sales_tier CHECK (required_sales_tier IN ('MA', 'SA', 'A')),
    CONSTRAINT ck_sales_lead_pool_region_code CHECK (pool_region_code IS NULL OR pool_region_code IN ('NA', 'EA', 'SEA', 'EU', 'ME', 'OTHER')),
    CONSTRAINT ck_sales_lead_allocation_status CHECK (allocation_status IN ('claimable', 'claimed', 'archived')),
    CONSTRAINT ck_sales_lead_pipeline_stage CHECK (pipeline_stage IN ('new', 'contacted', 'engaged', 'meeting', 'proposal', 'won', 'lost', 'dormant')),
    CONSTRAINT ck_sales_lead_data_completion_pool CHECK (data_completion_pool IS NULL OR data_completion_pool IN ('scale_unknown', 'region_unknown')),
    CONSTRAINT ck_sales_lead_dynamic_bonus_points CHECK (dynamic_bonus_points >= 0),
    CONSTRAINT ck_sales_lead_a_segment CHECK (a_segment IS NULL OR a_segment IN ('A1', 'A2', 'A3', 'A4')),
    CONSTRAINT ck_sales_lead_version CHECK (version >= 0),
    CONSTRAINT ck_sales_lead_pool_region_mapping_version CHECK (
        pool_region_code IS NULL OR pool_region_mapping_version IS NOT NULL
    ),
    CONSTRAINT ck_sales_lead_claimable_shape CHECK (
        (allocation_status = 'claimable' AND current_owner_user_id IS NULL AND current_assignment_started_at IS NULL AND sla_due_at IS NULL)
        OR
        (allocation_status <> 'claimable')
    ),
    CONSTRAINT ck_sales_lead_claimed_shape CHECK (
        (allocation_status = 'claimed' AND current_owner_user_id IS NOT NULL AND current_assignment_started_at IS NOT NULL)
        OR
        (allocation_status <> 'claimed')
    ),
    CONSTRAINT ck_sales_lead_first_touch_sla CHECK (
        first_touch_at IS NULL OR sla_due_at IS NULL
    ),
    CONSTRAINT ck_sales_lead_region_unknown_shape CHECK (
        data_completion_pool IS DISTINCT FROM 'region_unknown'
        OR
        (pool_region_code IS NULL AND pool_region_mapping_version IS NULL)
    ),
    CONSTRAINT ck_sales_lead_scale_unknown_shape CHECK (
        data_completion_pool IS DISTINCT FROM 'scale_unknown'
        OR
        required_sales_tier = 'A'
    ),
    CONSTRAINT ck_sales_lead_terminal_shape CHECK (
        (pipeline_stage IN ('won', 'lost') AND closed_at IS NOT NULL)
        OR
        (pipeline_stage NOT IN ('won', 'lost'))
    ),
    CONSTRAINT uq_sales_lead_self_company UNIQUE (lead_id, company_id),
    CONSTRAINT uq_sales_lead_self_company_candidate UNIQUE (lead_id, company_id, source_candidate_id),
    CONSTRAINT uq_sales_lead_icp_scale_lineage UNIQUE (
        lead_id,
        company_id,
        source_candidate_id,
        adopted_icp_assessment_id,
        adopted_scale_assessment_id
    )
);

CREATE TABLE ltc.lead_assignment (
    assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES ltc.sales_lead(lead_id) ON DELETE RESTRICT,
    assignee_user_id uuid NOT NULL REFERENCES ltc.user_account(user_id),
    assigned_by uuid REFERENCES ltc.user_account(user_id),
    assignment_type text NOT NULL,
    previous_assignment_id uuid,
    status text NOT NULL,
    reason_code text,
    reason_text text,
    assigned_at timestamptz NOT NULL,
    first_touch_at timestamptz,
    sla_due_at timestamptz,
    ended_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_lead_assignment_assignment_type CHECK (assignment_type IN ('claim', 'manual', 'transfer', 'reclaim', 'system')),
    CONSTRAINT ck_lead_assignment_status CHECK (status IN ('active', 'released', 'transferred', 'revoked', 'expired')),
    CONSTRAINT ck_lead_assignment_version CHECK (version >= 0),
    CONSTRAINT ck_lead_assignment_ended_shape CHECK (
        (status = 'active' AND ended_at IS NULL)
        OR
        (status <> 'active' AND ended_at IS NOT NULL)
    ),
    CONSTRAINT ck_lead_assignment_first_touch_after_assigned CHECK (
        first_touch_at IS NULL OR first_touch_at >= assigned_at
    ),
    CONSTRAINT uq_lead_assignment_self_lead UNIQUE (assignment_id, lead_id)
);

CREATE TABLE ltc.lead_stage_transition (
    transition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL,
    lead_id uuid NOT NULL REFERENCES ltc.sales_lead(lead_id) ON DELETE RESTRICT,
    assignment_id uuid,
    event_type text NOT NULL,
    from_allocation_status text,
    to_allocation_status text,
    from_pipeline_stage text,
    to_pipeline_stage text,
    from_owner_user_id uuid REFERENCES ltc.user_account(user_id),
    to_owner_user_id uuid REFERENCES ltc.user_account(user_id),
    actor_user_id uuid REFERENCES ltc.user_account(user_id),
    source_type text NOT NULL,
    source_email_id uuid,
    source_meeting_id uuid,
    source_task_id uuid,
    source_external_key text,
    reason_code text,
    reason_text text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL,
    CONSTRAINT ck_lead_stage_transition_event_type CHECK (event_type IN ('pool_entry', 'claim', 'assign', 'transfer', 'release', 'first_touch', 'stage_change', 'won', 'lost', 'decay', 'reactivate')),
    CONSTRAINT ck_lead_stage_transition_source_type CHECK (source_type IN ('user', 'email', 'meeting', 'task', 'system', 'migration')),
    CONSTRAINT ck_lead_stage_transition_metadata_object CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT ck_lead_stage_transition_source_count CHECK (
        num_nonnulls(source_email_id, source_meeting_id, source_task_id) <= 1
    )
);

-- ---------------------------------------------------------------------------
-- Customer Analysis: 5 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.customer_profile (
    company_id uuid PRIMARY KEY REFERENCES ltc.company(company_id) ON DELETE CASCADE,
    company_type text,
    region_text text,
    employee_scale text,
    business_model text,
    esim_scenario text,
    coverage text,
    estimated_usage text,
    integration text,
    compliance text,
    budget_text text,
    decision_maker_text text,
    decision_maker_contact_id uuid,
    decision_cycle_text text,
    completeness_score numeric(5,4) NOT NULL DEFAULT 0,
    missing_fields text[] NOT NULL DEFAULT ARRAY[]::text[],
    extra_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    field_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_summary text,
    last_enriched_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    updated_by uuid REFERENCES ltc.user_account(user_id),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_customer_profile_completeness_score CHECK (completeness_score >= 0 AND completeness_score <= 1),
    CONSTRAINT ck_customer_profile_missing_fields_no_null CHECK (array_position(missing_fields, NULL) IS NULL),
    CONSTRAINT ck_customer_profile_extra_payload_object CHECK (jsonb_typeof(extra_payload) = 'object'),
    CONSTRAINT ck_customer_profile_field_provenance_object CHECK (jsonb_typeof(field_provenance) = 'object'),
    CONSTRAINT ck_customer_profile_version CHECK (version >= 0)
);

CREATE TABLE ltc.customer_meddpicc_dimension (
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE CASCADE,
    dimension_code text NOT NULL,
    level text,
    status text NOT NULL,
    summary text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    version bigint NOT NULL DEFAULT 0,
    updated_by uuid REFERENCES ltc.user_account(user_id),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (company_id, dimension_code),
    CONSTRAINT ck_customer_meddpicc_dimension_status CHECK (status IN ('unknown', 'partial', 'confirmed', 'rejected')),
    CONSTRAINT ck_customer_meddpicc_dimension_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_customer_meddpicc_dimension_evidence_refs_array CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CONSTRAINT ck_customer_meddpicc_dimension_version CHECK (version >= 0)
);

CREATE TABLE ltc.analysis_run (
    analysis_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    lead_id uuid NOT NULL,
    source_candidate_id uuid NOT NULL REFERENCES ltc.lead_candidate(candidate_id),
    icp_assessment_id uuid NOT NULL,
    scale_assessment_id uuid NOT NULL,
    current_job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    report_type text NOT NULL,
    trigger_type text NOT NULL,
    status text NOT NULL,
    input_hash text NOT NULL,
    prompt_version text NOT NULL,
    schema_version text NOT NULL,
    model_name text,
    profile_version bigint NOT NULL,
    meddpicc_revision text NOT NULL,
    engagement_cutoff_at timestamptz,
    input_snapshot jsonb NOT NULL,
    token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    cost_amount numeric(14,6),
    cost_currency char(3) NOT NULL DEFAULT 'USD',
    cost_status text NOT NULL,
    error_code text,
    error_message text,
    created_by uuid REFERENCES ltc.user_account(user_id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_analysis_run_trigger_type CHECK (trigger_type IN ('manual', 'pool_entry', 'assignment', 'operation', 'schedule', 'migration')),
    CONSTRAINT ck_analysis_run_status CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT ck_analysis_run_input_snapshot_object CHECK (jsonb_typeof(input_snapshot) = 'object'),
    CONSTRAINT ck_analysis_run_token_usage_object CHECK (jsonb_typeof(token_usage) = 'object'),
    CONSTRAINT ck_analysis_run_profile_version CHECK (profile_version >= 0),
    CONSTRAINT ck_analysis_run_cost_amount CHECK (cost_amount IS NULL OR cost_amount >= 0),
    CONSTRAINT ck_analysis_run_cost_currency CHECK (cost_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_analysis_run_cost_status CHECK (cost_status IN ('confirmed', 'estimated', 'unknown')),
    CONSTRAINT ck_analysis_run_version CHECK (version >= 0),
    CONSTRAINT uq_analysis_run_self_company UNIQUE (analysis_run_id, company_id),
    CONSTRAINT uq_analysis_run_self_company_report_type UNIQUE (analysis_run_id, company_id, report_type)
);

CREATE TABLE ltc.analysis_report (
    report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    analysis_run_id uuid NOT NULL,
    report_type text NOT NULL DEFAULT 'customer_analysis',
    version_no integer NOT NULL,
    schema_version text NOT NULL,
    summary text NOT NULL,
    health_grade text,
    intention_level text,
    confidence numeric(5,4),
    section_confidence jsonb,
    low_confidence_sections text[],
    data_sources jsonb,
    evidence_refs jsonb NOT NULL,
    profile_snapshot jsonb NOT NULL,
    meddpicc_snapshot jsonb NOT NULL,
    icp_snapshot jsonb NOT NULL,
    scale_snapshot jsonb NOT NULL,
    report_payload jsonb NOT NULL,
    sales_guide_payload jsonb NOT NULL,
    generated_by text NOT NULL,
    model_name text,
    content_source text NOT NULL,
    generated_at timestamptz NOT NULL,
    superseded_at timestamptz,
    CONSTRAINT ck_analysis_report_version_no CHECK (version_no > 0),
    CONSTRAINT ck_analysis_report_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_analysis_report_section_confidence_object CHECK (section_confidence IS NULL OR jsonb_typeof(section_confidence) = 'object'),
    CONSTRAINT ck_analysis_report_low_confidence_sections_no_null CHECK (low_confidence_sections IS NULL OR array_position(low_confidence_sections, NULL) IS NULL),
    CONSTRAINT ck_analysis_report_data_sources_array CHECK (data_sources IS NULL OR jsonb_typeof(data_sources) = 'array'),
    CONSTRAINT ck_analysis_report_evidence_refs_array CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CONSTRAINT ck_analysis_report_profile_snapshot_object CHECK (jsonb_typeof(profile_snapshot) = 'object'),
    CONSTRAINT ck_analysis_report_meddpicc_snapshot_object CHECK (jsonb_typeof(meddpicc_snapshot) = 'object'),
    CONSTRAINT ck_analysis_report_icp_snapshot_object CHECK (jsonb_typeof(icp_snapshot) = 'object'),
    CONSTRAINT ck_analysis_report_scale_snapshot_object CHECK (jsonb_typeof(scale_snapshot) = 'object'),
    CONSTRAINT ck_analysis_report_report_payload_object CHECK (jsonb_typeof(report_payload) = 'object'),
    CONSTRAINT ck_analysis_report_sales_guide_payload_object CHECK (jsonb_typeof(sales_guide_payload) = 'object'),
    CONSTRAINT ck_analysis_report_generated_by CHECK (generated_by IN ('agent', 'manual', 'import')),
    CONSTRAINT ck_analysis_report_content_source CHECK (content_source IN ('llm', 'template', 'fallback', 'migration')),
    CONSTRAINT ck_analysis_report_superseded_at CHECK (superseded_at IS NULL OR superseded_at >= generated_at),
    CONSTRAINT uq_analysis_report_company_type_version UNIQUE (company_id, report_type, version_no),
    CONSTRAINT uq_analysis_report_self_company UNIQUE (report_id, company_id)
);

CREATE TABLE ltc.analysis_suggestion (
    suggestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    report_id uuid NOT NULL,
    target_type text NOT NULL,
    dimension_code text,
    target_path text NOT NULL,
    target_version_at_creation bigint NOT NULL,
    current_value_snapshot jsonb,
    proposed_value jsonb NOT NULL,
    evidence_refs jsonb NOT NULL,
    confidence numeric(5,4),
    status text NOT NULL,
    reviewed_by uuid REFERENCES ltc.user_account(user_id),
    reviewed_at timestamptz,
    review_note text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_analysis_suggestion_target_type CHECK (target_type IN ('profile', 'meddpicc')),
    CONSTRAINT ck_analysis_suggestion_target_version CHECK (target_version_at_creation >= 0),
    CONSTRAINT ck_analysis_suggestion_evidence_refs_array CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CONSTRAINT ck_analysis_suggestion_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_analysis_suggestion_status CHECK (status IN ('pending', 'accepted', 'rejected', 'expired')),
    CONSTRAINT uq_analysis_suggestion_report_path UNIQUE (report_id, target_path)
);

-- ---------------------------------------------------------------------------
-- Customer Operation: 9 tables
-- ---------------------------------------------------------------------------

CREATE TABLE ltc.email_message (
    email_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    lead_id uuid,
    contact_id uuid,
    parent_email_id uuid,
    thread_key text,
    direction text NOT NULL,
    purpose text,
    status text NOT NULL,
    from_address text NOT NULL,
    intended_to_address text,
    delivered_to_address text,
    cc_addresses jsonb NOT NULL DEFAULT '[]'::jsonb,
    subject text,
    body_text text,
    body_html text,
    intent_level text,
    intent_payload jsonb,
    next_action text,
    approved_by uuid REFERENCES ltc.user_account(user_id),
    approved_at timestamptz,
    generation_prompt_version text,
    generation_model text,
    provider_code text,
    provider_message_id text,
    provider_request_id text,
    message_id_header text,
    in_reply_to text,
    current_job_id uuid REFERENCES ltc.job(job_id),
    idempotency_key text,
    sent_at timestamptz,
    received_at timestamptz,
    replied_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_email_message_direction CHECK (direction IN ('inbound', 'outbound')),
    CONSTRAINT ck_email_message_status CHECK (
        (direction = 'outbound' AND status IN ('generating', 'draft', 'approved', 'queued', 'sending', 'sent', 'delivered', 'opened', 'clicked', 'replied', 'bounced', 'failed', 'reconcile_required', 'cancelled'))
        OR
        (direction = 'inbound' AND status IN ('received', 'processing', 'processed', 'failed'))
    ),
    CONSTRAINT ck_email_message_purpose CHECK (purpose IS NULL OR purpose IN ('first_touch', 'reply_followup', 'meeting_followup')),
    CONSTRAINT ck_email_message_cc_addresses_array CHECK (jsonb_typeof(cc_addresses) = 'array'),
    CONSTRAINT ck_email_message_intent_level CHECK (intent_level IS NULL OR intent_level IN ('interested', 'pricing', 'product_question', 'not_interested', 'unsubscribe')),
    CONSTRAINT ck_email_message_intent_payload_object CHECK (intent_payload IS NULL OR jsonb_typeof(intent_payload) = 'object'),
    CONSTRAINT ck_email_message_version CHECK (version >= 0),
    CONSTRAINT uq_email_message_self_company UNIQUE (email_id, company_id),
    CONSTRAINT uq_email_message_self_company_lead UNIQUE (email_id, company_id, lead_id)
);

CREATE TABLE ltc.email_attachment (
    email_attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    email_id uuid NOT NULL REFERENCES ltc.email_message(email_id) ON DELETE CASCADE,
    media_asset_id uuid NOT NULL REFERENCES ltc.media_asset(media_asset_id) ON DELETE RESTRICT,
    disposition text NOT NULL,
    content_id text,
    filename text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_email_attachment_disposition CHECK (disposition IN ('attachment', 'inline'))
);

CREATE TABLE ltc.email_delivery_attempt (
    delivery_attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id uuid NOT NULL REFERENCES ltc.email_message(email_id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    provider_code text NOT NULL,
    idempotency_key text NOT NULL,
    provider_request_id text,
    provider_message_id text,
    status text NOT NULL,
    request_payload jsonb NOT NULL,
    response_payload jsonb,
    error_code text,
    error_message text,
    started_at timestamptz NOT NULL,
    accepted_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT ck_email_delivery_attempt_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT ck_email_delivery_attempt_status CHECK (status IN ('started', 'accepted', 'delivered', 'failed', 'uncertain', 'reconciled')),
    CONSTRAINT ck_email_delivery_attempt_request_payload_object CHECK (jsonb_typeof(request_payload) = 'object'),
    CONSTRAINT ck_email_delivery_attempt_response_payload_object CHECK (response_payload IS NULL OR jsonb_typeof(response_payload) = 'object'),
    CONSTRAINT uq_email_delivery_attempt_email_attempt_no UNIQUE (email_id, attempt_no),
    CONSTRAINT uq_email_delivery_attempt_provider_idempotency UNIQUE (provider_code, idempotency_key)
);

CREATE TABLE ltc.email_suppression (
    suppression_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_email text NOT NULL,
    reason text NOT NULL,
    source_email_id uuid REFERENCES ltc.email_message(email_id),
    source_external_event_id uuid REFERENCES ltc.external_event(external_event_id),
    status text NOT NULL,
    suppressed_at timestamptz NOT NULL,
    lifted_at timestamptz,
    lifted_by uuid REFERENCES ltc.user_account(user_id),
    note text,
    CONSTRAINT ck_email_suppression_reason CHECK (reason IN ('unsubscribe', 'hard_bounce', 'complaint', 'manual', 'legal')),
    CONSTRAINT ck_email_suppression_status CHECK (status IN ('active', 'lifted')),
    CONSTRAINT ck_email_suppression_lifted_shape CHECK (
        (status = 'lifted' AND lifted_at IS NOT NULL)
        OR
        (status = 'active' AND lifted_at IS NULL)
    )
);

CREATE TABLE ltc.meeting (
    meeting_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    lead_id uuid,
    primary_contact_id uuid,
    owner_user_id uuid REFERENCES ltc.user_account(user_id),
    source_media_asset_id uuid NOT NULL REFERENCES ltc.media_asset(media_asset_id) ON DELETE RESTRICT,
    normalized_audio_asset_id uuid REFERENCES ltc.media_asset(media_asset_id) ON DELETE RESTRICT,
    current_job_id uuid NOT NULL REFERENCES ltc.job(job_id),
    title text,
    source text NOT NULL,
    meeting_started_at timestamptz,
    duration_seconds numeric(12,2),
    processing_status text NOT NULL,
    transcript_status text NOT NULL,
    transcript_text text,
    transcript_language text,
    transcript_provider text,
    summary_payload jsonb,
    summary_schema_version smallint NOT NULL DEFAULT 1,
    next_step text GENERATED ALWAYS AS (
        CASE
            WHEN summary_payload IS NULL THEN NULL
            ELSE summary_payload->>'next_step'
        END
    ) STORED,
    decisions jsonb GENERATED ALWAYS AS (
        CASE
            WHEN summary_payload IS NULL THEN '[]'::jsonb
            ELSE COALESCE(summary_payload->'decisions', '[]'::jsonb)
        END
    ) STORED,
    risks jsonb GENERATED ALWAYS AS (
        CASE
            WHEN summary_payload IS NULL THEN '[]'::jsonb
            ELSE COALESCE(summary_payload->'risks', '[]'::jsonb)
        END
    ) STORED,
    keywords jsonb GENERATED ALWAYS AS (
        CASE
            WHEN summary_payload IS NULL THEN '[]'::jsonb
            ELSE COALESCE(summary_payload->'keywords', '[]'::jsonb)
        END
    ) STORED,
    summary_prompt_version text,
    summary_model text,
    error_code text,
    error_message text,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deleted_at timestamptz,
    CONSTRAINT ck_meeting_source CHECK (source IN ('upload', 'import')),
    CONSTRAINT ck_meeting_duration_seconds CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    CONSTRAINT ck_meeting_processing_status CHECK (processing_status IN ('uploaded', 'queued', 'extracting', 'transcribing', 'summarizing', 'completed', 'failed', 'cancelled', 'deleted')),
    CONSTRAINT ck_meeting_transcript_status CHECK (transcript_status IN ('pending', 'processing', 'done', 'failed', 'cancelled')),
    CONSTRAINT ck_meeting_summary_schema_version CHECK (summary_schema_version = 1),
    CONSTRAINT ck_meeting_summary_payload_shape CHECK (summary_payload IS NULL OR ltc.validate_meeting_summary_v1(summary_payload)),
    CONSTRAINT ck_meeting_completed_summary_shape CHECK (
        (processing_status = 'completed' AND summary_payload IS NOT NULL)
        OR
        (processing_status <> 'completed')
    ),
    CONSTRAINT ck_meeting_deleted_shape CHECK (
        (processing_status = 'deleted' AND deleted_at IS NOT NULL)
        OR
        (processing_status <> 'deleted')
    ),
    CONSTRAINT ck_meeting_version CHECK (version >= 0),
    CONSTRAINT uq_meeting_self_company UNIQUE (meeting_id, company_id),
    CONSTRAINT uq_meeting_self_company_lead UNIQUE (meeting_id, company_id, lead_id)
);

CREATE TABLE ltc.meeting_segment (
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    meeting_id uuid NOT NULL REFERENCES ltc.meeting(meeting_id) ON DELETE CASCADE,
    sequence_no integer NOT NULL,
    start_seconds numeric(12,2) NOT NULL,
    end_seconds numeric(12,2) NOT NULL,
    speaker_id text,
    speaker_label text,
    speaker_contact_id uuid,
    transcript_text text NOT NULL,
    confidence numeric(5,4),
    PRIMARY KEY (meeting_id, sequence_no),
    CONSTRAINT ck_meeting_segment_sequence_no CHECK (sequence_no > 0),
    CONSTRAINT ck_meeting_segment_start_seconds CHECK (start_seconds >= 0),
    CONSTRAINT ck_meeting_segment_end_seconds CHECK (end_seconds > start_seconds),
    CONSTRAINT ck_meeting_segment_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE ltc.follow_up_task (
    task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    lead_id uuid,
    assignee_user_id uuid REFERENCES ltc.user_account(user_id),
    source_email_id uuid,
    source_meeting_id uuid,
    source_report_id uuid,
    source_job_id uuid REFERENCES ltc.job(job_id),
    task_type text NOT NULL,
    title text NOT NULL,
    description text,
    due_at timestamptz,
    status text NOT NULL,
    priority smallint NOT NULL DEFAULT 100,
    idempotency_key text,
    completed_at timestamptz,
    completion_note text,
    created_by uuid REFERENCES ltc.user_account(user_id),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_follow_up_task_task_type CHECK (task_type IN ('email', 'call', 'meeting', 'proposal', 'data_check', 'other')),
    CONSTRAINT ck_follow_up_task_status CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    CONSTRAINT ck_follow_up_task_priority CHECK (priority BETWEEN 0 AND 1000),
    CONSTRAINT ck_follow_up_task_version CHECK (version >= 0),
    CONSTRAINT ck_follow_up_task_source_count CHECK (
        num_nonnulls(source_email_id, source_meeting_id, source_report_id, source_job_id) <= 1
    )
);

CREATE TABLE ltc.customer_activity (
    activity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    lead_id uuid,
    assignment_id uuid,
    activity_type text NOT NULL,
    direction text,
    subject text,
    body text,
    outcome_code text,
    actor_user_id uuid REFERENCES ltc.user_account(user_id),
    source_type text NOT NULL,
    source_job_id uuid REFERENCES ltc.job(job_id),
    source_external_key text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_customer_activity_activity_type CHECK (activity_type IN ('call', 'note', 'proposal', 'demo', 'system', 'other')),
    CONSTRAINT ck_customer_activity_direction CHECK (direction IS NULL OR direction IN ('inbound', 'outbound', 'internal')),
    CONSTRAINT ck_customer_activity_source_type CHECK (source_type IN ('manual', 'system', 'migration')),
    CONSTRAINT ck_customer_activity_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_customer_activity_assignment_lead_shape CHECK (
        assignment_id IS NULL OR lead_id IS NOT NULL
    )
);

CREATE TABLE ltc.manual_note (
    note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES ltc.company(company_id) ON DELETE RESTRICT,
    sales_id uuid NOT NULL REFERENCES ltc.user_account(user_id),
    raw_text text NOT NULL,
    extracted_fields_json jsonb,
    confirm_status text NOT NULL DEFAULT 'pending',
    current_job_id uuid REFERENCES ltc.job(job_id),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_manual_note_extracted_fields_json CHECK (extracted_fields_json IS NULL OR jsonb_typeof(extracted_fields_json) = 'array'),
    CONSTRAINT ck_manual_note_confirm_status CHECK (confirm_status IN ('pending', 'confirmed', 'discarded')),
    CONSTRAINT ck_manual_note_version CHECK (version >= 0)
);

-- ---------------------------------------------------------------------------
-- Key indexes
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX uq_user_account_username_ci ON ltc.user_account (lower(username));
CREATE UNIQUE INDEX uq_user_account_email_ci ON ltc.user_account (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX ix_user_account_active_pool ON ltc.user_account (status, account_type, sales_tier, region_code) WHERE status = 'active' AND account_type = 'sales';
CREATE INDEX ix_user_account_departed_at ON ltc.user_account (departed_at) WHERE departed_at IS NOT NULL;

CREATE UNIQUE INDEX uq_auth_session_refresh_token_hash ON ltc.auth_session (refresh_token_hash);
CREATE INDEX ix_auth_session_user_id_expires_at ON ltc.auth_session (user_id, expires_at DESC);
CREATE INDEX ix_auth_session_active_expires_at ON ltc.auth_session (expires_at) WHERE revoked_at IS NULL;

CREATE INDEX ix_ref_region_country_region_code ON ltc.ref_region_country (region_code);
CREATE INDEX ix_ref_region_country_data_version ON ltc.ref_region_country (data_version);

CREATE UNIQUE INDEX uq_job_concurrency_active ON ltc.job (concurrency_key)
WHERE concurrency_key IS NOT NULL AND status IN ('queued', 'running', 'retry_wait', 'reconcile_required');
CREATE INDEX ix_job_claim ON ltc.job (queue_name, priority, run_after, created_at)
WHERE status IN ('queued', 'retry_wait');
CREATE INDEX ix_job_expired_lease ON ltc.job (locked_until) WHERE status = 'running';
CREATE INDEX ix_job_aggregate ON ltc.job (aggregate_type, aggregate_id, created_at DESC) WHERE aggregate_id IS NOT NULL;
CREATE INDEX ix_job_created_by ON ltc.job (created_by) WHERE created_by IS NOT NULL;
CREATE INDEX ix_job_retry_of_job_id ON ltc.job (retry_of_job_id) WHERE retry_of_job_id IS NOT NULL;

CREATE INDEX ix_job_attempt_job_id ON ltc.job_attempt (job_id, started_at DESC);
CREATE INDEX ix_job_attempt_provider_request_id ON ltc.job_attempt (provider_request_id) WHERE provider_request_id IS NOT NULL;

CREATE INDEX ix_job_progress_event_job_id_created_at ON ltc.job_progress_event (job_id, created_at);
CREATE INDEX ix_job_progress_event_step_code ON ltc.job_progress_event (step_code) WHERE step_code IS NOT NULL;

CREATE UNIQUE INDEX uq_idempotency_record_scope_principal_key
ON ltc.idempotency_record (scope, principal_type, principal_id, idempotency_key);
CREATE INDEX ix_idempotency_record_expires_at ON ltc.idempotency_record (expires_at);

CREATE INDEX ix_outbox_event_pending ON ltc.outbox_event (available_at, created_at) WHERE status = 'pending';
CREATE INDEX ix_outbox_event_processing ON ltc.outbox_event (locked_until) WHERE status = 'processing';
CREATE INDEX ix_outbox_event_correlation_id ON ltc.outbox_event (correlation_id) WHERE correlation_id IS NOT NULL;

CREATE INDEX ix_external_event_status_received_at ON ltc.external_event (status, received_at);
CREATE INDEX ix_external_event_linked_resource ON ltc.external_event (linked_resource_type, linked_resource_id) WHERE linked_resource_id IS NOT NULL;

CREATE INDEX ix_audit_log_resource ON ltc.audit_log (resource_type, resource_id, occurred_at DESC);
CREATE INDEX ix_audit_log_actor ON ltc.audit_log (actor_user_id, occurred_at DESC) WHERE actor_user_id IS NOT NULL;
CREATE INDEX ix_audit_log_job_id ON ltc.audit_log (job_id, occurred_at DESC) WHERE job_id IS NOT NULL;

CREATE INDEX ix_media_asset_company_id ON ltc.media_asset (company_id) WHERE company_id IS NOT NULL;
CREATE INDEX ix_media_asset_parent_media_asset_id ON ltc.media_asset (parent_media_asset_id) WHERE parent_media_asset_id IS NOT NULL;
CREATE INDEX ix_media_asset_asset_kind_status ON ltc.media_asset (asset_kind, status);
CREATE INDEX ix_media_asset_sha256 ON ltc.media_asset (sha256);

CREATE INDEX ix_lead_search_run_scene_code_status ON ltc.lead_search_run (scene_code, status, created_at DESC);
CREATE INDEX ix_lead_search_run_current_job_id ON ltc.lead_search_run (current_job_id);
CREATE INDEX ix_lead_search_run_requested_by ON ltc.lead_search_run (requested_by) WHERE requested_by IS NOT NULL;

CREATE UNIQUE INDEX uq_search_provider_execution_external_request_id
ON ltc.search_provider_execution (provider_code, external_request_id)
WHERE external_request_id IS NOT NULL;
CREATE INDEX ix_search_provider_execution_search_run_id_started_at ON ltc.search_provider_execution (search_run_id, started_at);
CREATE INDEX ix_search_provider_execution_job_id_status ON ltc.search_provider_execution (job_id, status);
CREATE INDEX ix_search_provider_execution_provider_status_started_at ON ltc.search_provider_execution (provider_code, status, started_at);
CREATE INDEX ix_search_provider_execution_retry_of_id ON ltc.search_provider_execution (retry_of_provider_execution_id) WHERE retry_of_provider_execution_id IS NOT NULL;

CREATE INDEX ix_search_evidence_search_run_id ON ltc.search_evidence (search_run_id) WHERE search_run_id IS NOT NULL;
CREATE INDEX ix_search_evidence_provider_execution_id ON ltc.search_evidence (provider_execution_id) WHERE provider_execution_id IS NOT NULL;
CREATE INDEX ix_search_evidence_job_id ON ltc.search_evidence (job_id);
CREATE INDEX ix_search_evidence_provider_code ON ltc.search_evidence (provider_code);
CREATE INDEX ix_search_evidence_canonical_url ON ltc.search_evidence (canonical_url) WHERE canonical_url IS NOT NULL;
CREATE INDEX ix_search_evidence_domain ON ltc.search_evidence (domain) WHERE domain IS NOT NULL;
CREATE INDEX ix_search_evidence_content_hash ON ltc.search_evidence (content_hash);

CREATE UNIQUE INDEX uq_lead_candidate_dedupe_key ON ltc.lead_candidate (dedupe_key);
CREATE UNIQUE INDEX uq_lead_candidate_normalized_domain_active
ON ltc.lead_candidate (normalized_domain)
WHERE normalized_domain IS NOT NULL AND processing_status NOT IN ('merged', 'archived');
CREATE INDEX ix_lead_candidate_normalized_company_country ON ltc.lead_candidate (normalized_company_name, country_code);
CREATE INDEX ix_lead_candidate_processing_status ON ltc.lead_candidate (processing_status, last_seen_at DESC);
CREATE INDEX ix_lead_candidate_region_code ON ltc.lead_candidate (region_code) WHERE region_code IS NOT NULL;
CREATE INDEX ix_lead_candidate_negative_filter_result ON ltc.lead_candidate (negative_filter_result) WHERE negative_filter_result IS NOT NULL;
CREATE INDEX ix_lead_candidate_selected_ready ON ltc.lead_candidate (assessments_stale, processing_status);

CREATE INDEX ix_candidate_observation_candidate_id ON ltc.candidate_observation (candidate_id, observed_at DESC);
CREATE INDEX ix_candidate_observation_search_run_id ON ltc.candidate_observation (search_run_id) WHERE search_run_id IS NOT NULL;

CREATE UNIQUE INDEX uq_candidate_evidence_without_observation
ON ltc.candidate_evidence (candidate_id, evidence_id, relation_type)
WHERE observation_id IS NULL;
CREATE INDEX ix_candidate_evidence_observation_id ON ltc.candidate_evidence (observation_id) WHERE observation_id IS NOT NULL;
CREATE INDEX ix_candidate_evidence_evidence_id ON ltc.candidate_evidence (evidence_id);

CREATE INDEX ix_candidate_contact_candidate_id ON ltc.candidate_contact (candidate_id, last_seen_at DESC);
CREATE INDEX ix_candidate_contact_observation_id ON ltc.candidate_contact (observation_id) WHERE observation_id IS NOT NULL;
CREATE INDEX ix_candidate_contact_title_normalized ON ltc.candidate_contact (title_normalized) WHERE title_normalized IS NOT NULL;
CREATE INDEX ix_candidate_contact_normalized_email ON ltc.candidate_contact (normalized_email) WHERE normalized_email IS NOT NULL;
CREATE INDEX ix_candidate_contact_linkedin_url ON ltc.candidate_contact (linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX ix_candidate_contact_merged_into_candidate_contact_id ON ltc.candidate_contact (merged_into_candidate_contact_id) WHERE merged_into_candidate_contact_id IS NOT NULL;

CREATE UNIQUE INDEX uq_lead_enrichment_run_current_candidate ON ltc.lead_enrichment_run (candidate_id) WHERE is_current;
CREATE UNIQUE INDEX uq_lead_enrichment_run_active_candidate ON ltc.lead_enrichment_run (candidate_id) WHERE status IN ('queued', 'running');
CREATE INDEX ix_lead_enrichment_run_current_job_id ON ltc.lead_enrichment_run (current_job_id);

CREATE INDEX ix_enrichment_evidence_enrichment_run_id ON ltc.enrichment_evidence (enrichment_run_id);
CREATE INDEX ix_enrichment_evidence_evidence_id ON ltc.enrichment_evidence (evidence_id);

CREATE UNIQUE INDEX uq_lead_icp_assessment_current_candidate ON ltc.lead_icp_assessment (candidate_id) WHERE is_current;
CREATE INDEX ix_lead_icp_assessment_enrichment_run_id ON ltc.lead_icp_assessment (enrichment_run_id);
CREATE INDEX ix_lead_icp_assessment_rule_checksum ON ltc.lead_icp_assessment (rule_checksum);
CREATE INDEX ix_lead_icp_assessment_scene_code_scored_at ON ltc.lead_icp_assessment (scene_code, scored_at DESC);
CREATE INDEX ix_lead_icp_assessment_job_id ON ltc.lead_icp_assessment (job_id) WHERE job_id IS NOT NULL;

CREATE UNIQUE INDEX uq_customer_scale_assessment_current_candidate ON ltc.customer_scale_assessment (candidate_id) WHERE is_current;
CREATE INDEX ix_customer_scale_assessment_source_enrichment_run_id ON ltc.customer_scale_assessment (source_enrichment_run_id);
CREATE INDEX ix_customer_scale_assessment_job_id ON ltc.customer_scale_assessment (job_id) WHERE job_id IS NOT NULL;
CREATE INDEX ix_customer_scale_assessment_assessed_at ON ltc.customer_scale_assessment (assessed_at DESC);

CREATE INDEX ix_lead_negative_filter_result_candidate_id ON ltc.lead_negative_filter_result (candidate_id, created_at DESC);
CREATE INDEX ix_lead_negative_filter_result_search_run_id ON ltc.lead_negative_filter_result (search_run_id) WHERE search_run_id IS NOT NULL;
CREATE INDEX ix_lead_negative_filter_result_enrichment_run_id ON ltc.lead_negative_filter_result (enrichment_run_id) WHERE enrichment_run_id IS NOT NULL;
CREATE INDEX ix_lead_negative_filter_result_job_id ON ltc.lead_negative_filter_result (job_id);

CREATE UNIQUE INDEX uq_company_primary_domain_active
ON ltc.company (primary_domain)
WHERE primary_domain IS NOT NULL AND lifecycle_status <> 'archived';
CREATE INDEX ix_company_normalized_company_name ON ltc.company (normalized_company_name);
CREATE INDEX ix_company_region_code ON ltc.company (region_code) WHERE region_code IS NOT NULL;
CREATE INDEX ix_company_origin_candidate_id ON ltc.company (origin_candidate_id) WHERE origin_candidate_id IS NOT NULL;

CREATE UNIQUE INDEX uq_contact_primary_email_active
ON ltc.contact (company_id, lower(primary_email))
WHERE primary_email IS NOT NULL AND status = 'active';
CREATE INDEX ix_contact_company_id ON ltc.contact (company_id);
CREATE INDEX ix_contact_source_candidate_contact_id ON ltc.contact (source_candidate_contact_id) WHERE source_candidate_contact_id IS NOT NULL;
CREATE INDEX ix_contact_title_normalized ON ltc.contact (title_normalized) WHERE title_normalized IS NOT NULL;
CREATE INDEX ix_contact_normalized_email ON ltc.contact (normalized_email) WHERE normalized_email IS NOT NULL;
CREATE INDEX ix_contact_linkedin_url ON ltc.contact (linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX ix_contact_last_contacted_at ON ltc.contact (last_contacted_at DESC) WHERE last_contacted_at IS NOT NULL;

CREATE UNIQUE INDEX uq_sales_lead_company_open
ON ltc.sales_lead (company_id)
WHERE allocation_status <> 'archived' AND pipeline_stage NOT IN ('won', 'lost');
CREATE INDEX ix_sales_lead_pool ON ltc.sales_lead (allocation_status, required_sales_tier, pool_region_code, created_at)
WHERE allocation_status = 'claimable';
CREATE INDEX ix_sales_lead_current_owner_user_id ON ltc.sales_lead (current_owner_user_id, pipeline_stage) WHERE current_owner_user_id IS NOT NULL;
CREATE INDEX ix_sales_lead_last_activity_at ON ltc.sales_lead (last_activity_at DESC) WHERE last_activity_at IS NOT NULL;
CREATE INDEX ix_sales_lead_sla_due_at ON ltc.sales_lead (sla_due_at) WHERE sla_due_at IS NOT NULL;
CREATE INDEX ix_sales_lead_a_segment ON ltc.sales_lead (a_segment) WHERE a_segment IS NOT NULL;

CREATE UNIQUE INDEX uq_lead_assignment_active ON ltc.lead_assignment (lead_id) WHERE status = 'active';
CREATE INDEX ix_lead_assignment_assignee_user_id_active ON ltc.lead_assignment (assignee_user_id, status, assigned_at DESC);
CREATE INDEX ix_lead_assignment_previous_assignment_id ON ltc.lead_assignment (previous_assignment_id) WHERE previous_assignment_id IS NOT NULL;
CREATE INDEX ix_lead_assignment_sla_due_at ON ltc.lead_assignment (sla_due_at) WHERE sla_due_at IS NOT NULL;

CREATE INDEX ix_lead_stage_transition_lead_id_occurred_at ON ltc.lead_stage_transition (lead_id, occurred_at DESC);
CREATE INDEX ix_lead_stage_transition_company_id_occurred_at ON ltc.lead_stage_transition (company_id, occurred_at DESC);
CREATE INDEX ix_lead_stage_transition_assignment_id ON ltc.lead_stage_transition (assignment_id) WHERE assignment_id IS NOT NULL;
CREATE INDEX ix_lead_stage_transition_actor_user_id ON ltc.lead_stage_transition (actor_user_id) WHERE actor_user_id IS NOT NULL;
CREATE UNIQUE INDEX uq_lead_stage_transition_email_stage
ON ltc.lead_stage_transition (source_email_id, to_pipeline_stage)
WHERE source_type = 'email' AND source_email_id IS NOT NULL;
CREATE UNIQUE INDEX uq_lead_stage_transition_meeting_stage
ON ltc.lead_stage_transition (source_meeting_id, to_pipeline_stage)
WHERE source_type = 'meeting' AND source_meeting_id IS NOT NULL;
CREATE UNIQUE INDEX uq_lead_stage_transition_task_stage
ON ltc.lead_stage_transition (source_task_id, to_pipeline_stage)
WHERE source_type = 'task' AND source_task_id IS NOT NULL;

CREATE INDEX ix_customer_profile_decision_maker_contact_id ON ltc.customer_profile (decision_maker_contact_id) WHERE decision_maker_contact_id IS NOT NULL;
CREATE INDEX ix_customer_meddpicc_dimension_status ON ltc.customer_meddpicc_dimension (status);

CREATE UNIQUE INDEX uq_analysis_run_input_hash_active
ON ltc.analysis_run (company_id, report_type, input_hash)
WHERE status NOT IN ('failed', 'cancelled');
CREATE INDEX ix_analysis_run_company_id ON ltc.analysis_run (company_id, created_at DESC);
CREATE INDEX ix_analysis_run_current_job_id ON ltc.analysis_run (current_job_id);
CREATE INDEX ix_analysis_run_source_candidate_id ON ltc.analysis_run (source_candidate_id);

CREATE UNIQUE INDEX uq_analysis_report_current
ON ltc.analysis_report (company_id, report_type)
WHERE superseded_at IS NULL;
CREATE INDEX ix_analysis_report_generated_at ON ltc.analysis_report (generated_at DESC);
CREATE INDEX ix_analysis_report_run_company_type ON ltc.analysis_report (analysis_run_id, company_id, report_type);
CREATE INDEX ix_analysis_report_company_generated_at ON ltc.analysis_report (company_id, generated_at DESC);

CREATE INDEX ix_analysis_suggestion_company_id ON ltc.analysis_suggestion (company_id);
CREATE INDEX ix_analysis_suggestion_report_id_status ON ltc.analysis_suggestion (report_id, status);

CREATE UNIQUE INDEX uq_email_message_provider_message_id
ON ltc.email_message (provider_code, provider_message_id)
WHERE provider_message_id IS NOT NULL;
CREATE UNIQUE INDEX uq_email_message_idempotency_key
ON ltc.email_message (idempotency_key)
WHERE direction = 'outbound' AND idempotency_key IS NOT NULL;
CREATE INDEX ix_email_message_company_id_created_at ON ltc.email_message (company_id, created_at DESC);
CREATE INDEX ix_email_message_lead_id ON ltc.email_message (lead_id) WHERE lead_id IS NOT NULL;
CREATE INDEX ix_email_message_contact_id ON ltc.email_message (contact_id) WHERE contact_id IS NOT NULL;
CREATE INDEX ix_email_message_thread_key ON ltc.email_message (thread_key, created_at);
CREATE INDEX ix_email_message_provider_request_id ON ltc.email_message (provider_request_id) WHERE provider_request_id IS NOT NULL;
CREATE INDEX ix_email_message_message_id_header ON ltc.email_message (message_id_header) WHERE message_id_header IS NOT NULL;
CREATE INDEX ix_email_message_in_reply_to ON ltc.email_message (in_reply_to) WHERE in_reply_to IS NOT NULL;
CREATE INDEX ix_email_message_parent_company ON ltc.email_message (parent_email_id, company_id) WHERE parent_email_id IS NOT NULL;

CREATE INDEX ix_email_attachment_email_id ON ltc.email_attachment (email_id);
CREATE INDEX ix_email_attachment_media_asset_id ON ltc.email_attachment (media_asset_id);

CREATE UNIQUE INDEX uq_email_delivery_attempt_provider_message_id
ON ltc.email_delivery_attempt (provider_code, provider_message_id)
WHERE provider_message_id IS NOT NULL;
CREATE INDEX ix_email_delivery_attempt_email_id ON ltc.email_delivery_attempt (email_id);
CREATE INDEX ix_email_delivery_attempt_provider_request_id ON ltc.email_delivery_attempt (provider_request_id) WHERE provider_request_id IS NOT NULL;

CREATE UNIQUE INDEX uq_email_suppression_active_normalized_email
ON ltc.email_suppression (normalized_email)
WHERE status = 'active';
CREATE INDEX ix_email_suppression_source_email_id ON ltc.email_suppression (source_email_id) WHERE source_email_id IS NOT NULL;
CREATE INDEX ix_email_suppression_source_external_event_id ON ltc.email_suppression (source_external_event_id) WHERE source_external_event_id IS NOT NULL;

CREATE INDEX ix_meeting_company_id_created_at ON ltc.meeting (company_id, created_at DESC);
CREATE INDEX ix_meeting_lead_id ON ltc.meeting (lead_id) WHERE lead_id IS NOT NULL;
CREATE INDEX ix_meeting_primary_contact_id ON ltc.meeting (primary_contact_id) WHERE primary_contact_id IS NOT NULL;
CREATE INDEX ix_meeting_owner_user_id ON ltc.meeting (owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX ix_meeting_current_job_id ON ltc.meeting (current_job_id);
CREATE INDEX ix_meeting_meeting_started_at ON ltc.meeting (meeting_started_at DESC) WHERE meeting_started_at IS NOT NULL;

CREATE INDEX ix_meeting_segment_company_id ON ltc.meeting_segment (company_id);
CREATE INDEX ix_meeting_segment_speaker_contact_id ON ltc.meeting_segment (speaker_contact_id) WHERE speaker_contact_id IS NOT NULL;

CREATE UNIQUE INDEX uq_follow_up_task_idempotency_key
ON ltc.follow_up_task (idempotency_key)
WHERE idempotency_key IS NOT NULL;
CREATE INDEX ix_follow_up_task_assignee_user_id_status_due_at
ON ltc.follow_up_task (assignee_user_id, status, due_at)
WHERE status IN ('pending', 'in_progress');
CREATE INDEX ix_follow_up_task_company_id_created_at ON ltc.follow_up_task (company_id, created_at DESC);
CREATE INDEX ix_follow_up_task_lead_id ON ltc.follow_up_task (lead_id) WHERE lead_id IS NOT NULL;
CREATE INDEX ix_follow_up_task_source_email_company ON ltc.follow_up_task (source_email_id, company_id) WHERE source_email_id IS NOT NULL;
CREATE INDEX ix_follow_up_task_source_meeting_company ON ltc.follow_up_task (source_meeting_id, company_id) WHERE source_meeting_id IS NOT NULL;
CREATE INDEX ix_follow_up_task_source_report_company ON ltc.follow_up_task (source_report_id, company_id) WHERE source_report_id IS NOT NULL;

CREATE UNIQUE INDEX uq_customer_activity_source_external_key
ON ltc.customer_activity (source_type, company_id, source_external_key)
WHERE source_external_key IS NOT NULL;
CREATE INDEX ix_customer_activity_company_id_occurred_at ON ltc.customer_activity (company_id, occurred_at DESC);
CREATE INDEX ix_customer_activity_lead_id ON ltc.customer_activity (lead_id) WHERE lead_id IS NOT NULL;
CREATE INDEX ix_customer_activity_assignment_id ON ltc.customer_activity (assignment_id) WHERE assignment_id IS NOT NULL;
CREATE INDEX ix_customer_activity_actor_user_id ON ltc.customer_activity (actor_user_id) WHERE actor_user_id IS NOT NULL;

CREATE INDEX ix_manual_note_company_id_created_at ON ltc.manual_note (company_id, created_at DESC);
CREATE INDEX ix_manual_note_sales_id_created_at ON ltc.manual_note (sales_id, created_at DESC);
CREATE INDEX ix_manual_note_current_job_id ON ltc.manual_note (current_job_id) WHERE current_job_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Composite keys and foreign keys
-- ---------------------------------------------------------------------------

ALTER TABLE ltc.candidate_observation
ADD CONSTRAINT uq_candidate_observation_id_candidate UNIQUE (observation_id, candidate_id);

ALTER TABLE ltc.lead_candidate
ADD CONSTRAINT uq_lead_candidate_id_merge_target UNIQUE (candidate_id, merged_into_candidate_id);

ALTER TABLE ltc.candidate_contact
ADD CONSTRAINT uq_candidate_contact_id_candidate UNIQUE (candidate_contact_id, candidate_id);

ALTER TABLE ltc.follow_up_task
ADD CONSTRAINT uq_follow_up_task_id_company_lead UNIQUE (task_id, company_id, lead_id);

ALTER TABLE ltc.search_evidence
ADD CONSTRAINT fk_search_evidence_provider_execution
FOREIGN KEY (provider_execution_id, provider_code)
REFERENCES ltc.search_provider_execution(provider_execution_id, provider_code);

ALTER TABLE ltc.candidate_evidence
ADD CONSTRAINT fk_candidate_evidence_observation
FOREIGN KEY (observation_id, candidate_id)
REFERENCES ltc.candidate_observation(observation_id, candidate_id);

ALTER TABLE ltc.candidate_contact
ADD CONSTRAINT fk_candidate_contact_observation
FOREIGN KEY (observation_id, candidate_id)
REFERENCES ltc.candidate_observation(observation_id, candidate_id);

ALTER TABLE ltc.candidate_contact
ADD CONSTRAINT fk_candidate_contact_candidate_merge_target
FOREIGN KEY (candidate_id, merged_into_candidate_id)
REFERENCES ltc.lead_candidate(candidate_id, merged_into_candidate_id);

ALTER TABLE ltc.candidate_contact
ADD CONSTRAINT fk_candidate_contact_merged_contact
FOREIGN KEY (merged_into_candidate_contact_id, merged_into_candidate_id)
REFERENCES ltc.candidate_contact(candidate_contact_id, candidate_id);

ALTER TABLE ltc.lead_enrichment_run
ADD CONSTRAINT uq_lead_enrichment_run_id_candidate UNIQUE (enrichment_run_id, candidate_id);

ALTER TABLE ltc.lead_icp_assessment
ADD CONSTRAINT fk_lead_icp_assessment_enrichment_candidate
FOREIGN KEY (enrichment_run_id, candidate_id)
REFERENCES ltc.lead_enrichment_run(enrichment_run_id, candidate_id);

ALTER TABLE ltc.customer_scale_assessment
ADD CONSTRAINT fk_customer_scale_assessment_enrichment_candidate
FOREIGN KEY (source_enrichment_run_id, candidate_id)
REFERENCES ltc.lead_enrichment_run(enrichment_run_id, candidate_id);

ALTER TABLE ltc.lead_candidate
ADD CONSTRAINT fk_lead_candidate_selected_icp_assessment
FOREIGN KEY (selected_icp_assessment_id, candidate_id)
REFERENCES ltc.lead_icp_assessment(icp_assessment_id, candidate_id);

ALTER TABLE ltc.lead_candidate
ADD CONSTRAINT fk_lead_candidate_selected_scale_assessment
FOREIGN KEY (selected_scale_assessment_id, candidate_id)
REFERENCES ltc.customer_scale_assessment(scale_assessment_id, candidate_id);

ALTER TABLE ltc.customer_profile
ADD CONSTRAINT fk_customer_profile_decision_maker_contact
FOREIGN KEY (decision_maker_contact_id, company_id)
REFERENCES ltc.contact(contact_id, company_id);

ALTER TABLE ltc.sales_lead
ADD CONSTRAINT fk_sales_lead_adopted_icp_assessment
FOREIGN KEY (adopted_icp_assessment_id, source_candidate_id)
REFERENCES ltc.lead_icp_assessment(icp_assessment_id, candidate_id);

ALTER TABLE ltc.sales_lead
ADD CONSTRAINT fk_sales_lead_adopted_scale_assessment
FOREIGN KEY (adopted_scale_assessment_id, source_candidate_id, required_sales_tier)
REFERENCES ltc.customer_scale_assessment(scale_assessment_id, candidate_id, required_sales_tier);

ALTER TABLE ltc.lead_candidate
ADD CONSTRAINT fk_lead_candidate_promoted_lead
FOREIGN KEY (promoted_lead_id, promoted_company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.lead_assignment
ADD CONSTRAINT fk_lead_assignment_previous_assignment
FOREIGN KEY (previous_assignment_id, lead_id)
REFERENCES ltc.lead_assignment(assignment_id, lead_id);

ALTER TABLE ltc.lead_stage_transition
ADD CONSTRAINT fk_lead_stage_transition_lead
FOREIGN KEY (lead_id, company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.lead_stage_transition
ADD CONSTRAINT fk_lead_stage_transition_assignment
FOREIGN KEY (assignment_id, lead_id)
REFERENCES ltc.lead_assignment(assignment_id, lead_id);

ALTER TABLE ltc.analysis_run
ADD CONSTRAINT fk_analysis_run_lead_candidate
FOREIGN KEY (lead_id, company_id, source_candidate_id)
REFERENCES ltc.sales_lead(lead_id, company_id, source_candidate_id);

ALTER TABLE ltc.analysis_run
ADD CONSTRAINT fk_analysis_run_lead_icp_scale
FOREIGN KEY (lead_id, company_id, source_candidate_id, icp_assessment_id, scale_assessment_id)
REFERENCES ltc.sales_lead(lead_id, company_id, source_candidate_id, adopted_icp_assessment_id, adopted_scale_assessment_id);

ALTER TABLE ltc.analysis_run
ADD CONSTRAINT fk_analysis_run_icp_assessment
FOREIGN KEY (icp_assessment_id, source_candidate_id)
REFERENCES ltc.lead_icp_assessment(icp_assessment_id, candidate_id);

ALTER TABLE ltc.analysis_run
ADD CONSTRAINT fk_analysis_run_scale_assessment
FOREIGN KEY (scale_assessment_id, source_candidate_id)
REFERENCES ltc.customer_scale_assessment(scale_assessment_id, candidate_id);

ALTER TABLE ltc.analysis_report
ADD CONSTRAINT fk_analysis_report_run
FOREIGN KEY (analysis_run_id, company_id, report_type)
REFERENCES ltc.analysis_run(analysis_run_id, company_id, report_type);

ALTER TABLE ltc.analysis_suggestion
ADD CONSTRAINT fk_analysis_suggestion_report
FOREIGN KEY (report_id, company_id)
REFERENCES ltc.analysis_report(report_id, company_id);

ALTER TABLE ltc.email_message
ADD CONSTRAINT fk_email_message_lead
FOREIGN KEY (lead_id, company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.email_message
ADD CONSTRAINT fk_email_message_contact
FOREIGN KEY (contact_id, company_id)
REFERENCES ltc.contact(contact_id, company_id);

ALTER TABLE ltc.email_message
ADD CONSTRAINT fk_email_message_parent
FOREIGN KEY (parent_email_id, company_id)
REFERENCES ltc.email_message(email_id, company_id);

ALTER TABLE ltc.media_asset
ADD CONSTRAINT fk_media_asset_company
FOREIGN KEY (company_id)
REFERENCES ltc.company(company_id);

ALTER TABLE ltc.media_asset
ADD CONSTRAINT uq_media_asset_self_company UNIQUE (media_asset_id, company_id);

ALTER TABLE ltc.media_asset
ADD CONSTRAINT fk_media_asset_parent_same_company
FOREIGN KEY (parent_media_asset_id, company_id)
REFERENCES ltc.media_asset(media_asset_id, company_id);

ALTER TABLE ltc.email_attachment
ADD CONSTRAINT fk_email_attachment_email
FOREIGN KEY (email_id, company_id)
REFERENCES ltc.email_message(email_id, company_id);

ALTER TABLE ltc.email_attachment
ADD CONSTRAINT fk_email_attachment_media_asset
FOREIGN KEY (media_asset_id, company_id)
REFERENCES ltc.media_asset(media_asset_id, company_id);

ALTER TABLE ltc.meeting
ADD CONSTRAINT fk_meeting_lead
FOREIGN KEY (lead_id, company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.meeting
ADD CONSTRAINT fk_meeting_primary_contact
FOREIGN KEY (primary_contact_id, company_id)
REFERENCES ltc.contact(contact_id, company_id);

ALTER TABLE ltc.meeting
ADD CONSTRAINT fk_meeting_source_media_asset
FOREIGN KEY (source_media_asset_id, company_id)
REFERENCES ltc.media_asset(media_asset_id, company_id);

ALTER TABLE ltc.meeting
ADD CONSTRAINT fk_meeting_normalized_audio_asset
FOREIGN KEY (normalized_audio_asset_id, company_id)
REFERENCES ltc.media_asset(media_asset_id, company_id);

ALTER TABLE ltc.meeting_segment
ADD CONSTRAINT fk_meeting_segment_meeting
FOREIGN KEY (meeting_id, company_id)
REFERENCES ltc.meeting(meeting_id, company_id);

ALTER TABLE ltc.meeting_segment
ADD CONSTRAINT fk_meeting_segment_speaker_contact
FOREIGN KEY (speaker_contact_id, company_id)
REFERENCES ltc.contact(contact_id, company_id);

ALTER TABLE ltc.follow_up_task
ADD CONSTRAINT fk_follow_up_task_lead
FOREIGN KEY (lead_id, company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.follow_up_task
ADD CONSTRAINT fk_follow_up_task_source_email
FOREIGN KEY (source_email_id, company_id)
REFERENCES ltc.email_message(email_id, company_id);

ALTER TABLE ltc.follow_up_task
ADD CONSTRAINT fk_follow_up_task_source_meeting
FOREIGN KEY (source_meeting_id, company_id)
REFERENCES ltc.meeting(meeting_id, company_id);

ALTER TABLE ltc.follow_up_task
ADD CONSTRAINT fk_follow_up_task_source_report
FOREIGN KEY (source_report_id, company_id)
REFERENCES ltc.analysis_report(report_id, company_id);

ALTER TABLE ltc.customer_activity
ADD CONSTRAINT fk_customer_activity_lead
FOREIGN KEY (lead_id, company_id)
REFERENCES ltc.sales_lead(lead_id, company_id);

ALTER TABLE ltc.customer_activity
ADD CONSTRAINT fk_customer_activity_assignment
FOREIGN KEY (assignment_id, lead_id)
REFERENCES ltc.lead_assignment(assignment_id, lead_id);

ALTER TABLE ltc.lead_stage_transition
ADD CONSTRAINT fk_lead_stage_transition_source_email
FOREIGN KEY (source_email_id, company_id, lead_id)
REFERENCES ltc.email_message(email_id, company_id, lead_id);

ALTER TABLE ltc.lead_stage_transition
ADD CONSTRAINT fk_lead_stage_transition_source_meeting
FOREIGN KEY (source_meeting_id, company_id, lead_id)
REFERENCES ltc.meeting(meeting_id, company_id, lead_id);

ALTER TABLE ltc.lead_stage_transition
ADD CONSTRAINT fk_lead_stage_transition_source_task
FOREIGN KEY (source_task_id, company_id, lead_id)
REFERENCES ltc.follow_up_task(task_id, company_id, lead_id);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

CREATE TRIGGER trg_user_account_updated_at
BEFORE UPDATE ON ltc.user_account
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_user_account_status_transition
BEFORE UPDATE ON ltc.user_account
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_user_account_status_transition();

CREATE TRIGGER trg_job_updated_at
BEFORE UPDATE ON ltc.job
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_idempotency_record_updated_at
BEFORE UPDATE ON ltc.idempotency_record
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_candidate_contact_updated_at
BEFORE UPDATE ON ltc.candidate_contact
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_lead_candidate_updated_at
BEFORE UPDATE ON ltc.lead_candidate
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_company_updated_at
BEFORE UPDATE ON ltc.company
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_contact_updated_at
BEFORE UPDATE ON ltc.contact
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_sales_lead_updated_at
BEFORE UPDATE ON ltc.sales_lead
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_customer_profile_updated_at
BEFORE UPDATE ON ltc.customer_profile
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_customer_meddpicc_dimension_updated_at
BEFORE UPDATE ON ltc.customer_meddpicc_dimension
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_email_message_updated_at
BEFORE UPDATE ON ltc.email_message
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_meeting_updated_at
BEFORE UPDATE ON ltc.meeting
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_follow_up_task_updated_at
BEFORE UPDATE ON ltc.follow_up_task
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_manual_note_updated_at
BEFORE UPDATE ON ltc.manual_note
FOR EACH ROW EXECUTE FUNCTION ltc.set_updated_at();

CREATE TRIGGER trg_lead_candidate_promotion_fact_immutable
BEFORE UPDATE ON ltc.lead_candidate
FOR EACH ROW EXECUTE FUNCTION ltc.prevent_candidate_promotion_fact_mutation();

CREATE TRIGGER trg_sales_lead_snapshot_immutable
BEFORE UPDATE ON ltc.sales_lead
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_sales_lead_snapshot_immutability();

CREATE TRIGGER trg_analysis_report_immutable
BEFORE UPDATE ON ltc.analysis_report
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_analysis_report_immutability();

CREATE TRIGGER trg_lead_assignment_no_hard_delete
BEFORE DELETE ON ltc.lead_assignment
FOR EACH ROW EXECUTE FUNCTION ltc.prevent_history_hard_delete();

CREATE TRIGGER trg_lead_stage_transition_no_hard_delete
BEFORE DELETE ON ltc.lead_stage_transition
FOR EACH ROW EXECUTE FUNCTION ltc.prevent_history_hard_delete();

CREATE TRIGGER trg_analysis_report_no_hard_delete
BEFORE DELETE ON ltc.analysis_report
FOR EACH ROW EXECUTE FUNCTION ltc.prevent_history_hard_delete();

CREATE CONSTRAINT TRIGGER ct_sales_lead_assignment_consistency_on_lead
AFTER INSERT OR UPDATE OR DELETE ON ltc.sales_lead
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_sales_lead_assignment_consistency();

CREATE CONSTRAINT TRIGGER ct_sales_lead_assignment_consistency_on_assignment
AFTER INSERT OR UPDATE OR DELETE ON ltc.lead_assignment
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_sales_lead_assignment_consistency();

CREATE CONSTRAINT TRIGGER ct_user_assignment_consistency
AFTER INSERT OR UPDATE ON ltc.user_account
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION ltc.enforce_user_assignment_consistency();

-- ---------------------------------------------------------------------------
-- Suggested read-only views (not counted in 42 tables)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW ltc.v_sales_lead_pool AS
SELECT
    sl.lead_id,
    sl.company_id,
    c.company_name,
    sl.source_candidate_id,
    sl.adopted_icp_assessment_id,
    sl.adopted_scale_assessment_id,
    sl.required_sales_tier,
    sl.pool_region_code,
    sl.pool_region_mapping_version,
    sl.data_completion_pool,
    sl.allocation_status,
    sl.pipeline_stage,
    sl.sla_due_at,
    sl.current_owner_user_id,
    sl.current_assignment_started_at
FROM ltc.sales_lead sl
JOIN ltc.company c ON c.company_id = sl.company_id
WHERE sl.pool_region_code IS NOT NULL
  AND sl.allocation_status = 'claimable'
  AND sl.data_completion_pool IS DISTINCT FROM 'region_unknown';

CREATE OR REPLACE VIEW ltc.v_sales_workload AS
WITH active_assignment AS (
    SELECT assignee_user_id, COUNT(*) AS active_assignment_count
    FROM ltc.lead_assignment
    WHERE status = 'active'
    GROUP BY assignee_user_id
), overdue_lead AS (
    SELECT current_owner_user_id, COUNT(*) AS sla_overdue_count
    FROM ltc.sales_lead
    WHERE allocation_status = 'claimed'
      AND first_touch_at IS NULL
      AND sla_due_at < clock_timestamp()
    GROUP BY current_owner_user_id
)
SELECT
    ua.user_id,
    ua.display_name,
    ua.sales_tier,
    ua.region_code,
    ua.capacity_limit,
    COALESCE(aa.active_assignment_count, 0) AS active_assignment_count,
    GREATEST(ua.capacity_limit - COALESCE(aa.active_assignment_count, 0), 0) AS remaining_capacity,
    COALESCE(ol.sla_overdue_count, 0) AS sla_overdue_count
FROM ltc.user_account ua
LEFT JOIN active_assignment aa
    ON aa.assignee_user_id = ua.user_id
LEFT JOIN overdue_lead ol
    ON ol.current_owner_user_id = ua.user_id
WHERE ua.account_type = 'sales';

CREATE OR REPLACE VIEW ltc.v_company_360_summary AS
SELECT
    c.company_id,
    c.company_name,
    sl.lead_id AS current_lead_id,
    sl.current_owner_user_id,
    cp.completeness_score AS profile_completeness_score,
    COUNT(cmd.dimension_code) FILTER (WHERE cmd.status = 'confirmed') AS meddpicc_confirmed_count,
    ar.report_id AS current_report_id,
    ar.generated_at AS current_report_generated_at,
    em.email_id AS last_email_id,
    em.created_at AS last_email_at,
    mt.meeting_id AS last_meeting_id,
    mt.created_at AS last_meeting_at
FROM ltc.company c
LEFT JOIN ltc.sales_lead sl
    ON sl.company_id = c.company_id
   AND sl.allocation_status <> 'archived'
   AND sl.pipeline_stage NOT IN ('won', 'lost')
LEFT JOIN ltc.customer_profile cp
    ON cp.company_id = c.company_id
LEFT JOIN ltc.customer_meddpicc_dimension cmd
    ON cmd.company_id = c.company_id
LEFT JOIN LATERAL (
    SELECT ar1.report_id, ar1.generated_at
    FROM ltc.analysis_report ar1
    WHERE ar1.company_id = c.company_id
      AND ar1.superseded_at IS NULL
    ORDER BY ar1.generated_at DESC
    LIMIT 1
) ar ON true
LEFT JOIN LATERAL (
    SELECT em1.email_id, em1.created_at
    FROM ltc.email_message em1
    WHERE em1.company_id = c.company_id
    ORDER BY em1.created_at DESC
    LIMIT 1
) em ON true
LEFT JOIN LATERAL (
    SELECT mt1.meeting_id, mt1.created_at
    FROM ltc.meeting mt1
    WHERE mt1.company_id = c.company_id
      AND mt1.processing_status <> 'deleted'
    ORDER BY mt1.created_at DESC
    LIMIT 1
) mt ON true
GROUP BY
    c.company_id,
    c.company_name,
    sl.lead_id,
    sl.current_owner_user_id,
    cp.completeness_score,
    ar.report_id,
    ar.generated_at,
    em.email_id,
    em.created_at,
    mt.meeting_id,
    mt.created_at;

COMMIT;
