-- Migration 0005: telemetry event tables for AI, Tool, and Lead Lifecycle tracking.
-- Supports v3.3 data instrumentation and anomaly strategy.

BEGIN;

SET search_path TO ltc, public;

-- ---------------------------------------------------------------
-- AI Event: one row per LLM/Agent invocation
-- ---------------------------------------------------------------
CREATE TABLE ltc.ai_event (
    ai_event_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name       text NOT NULL,
    prompt_version   text,
    model            text NOT NULL,
    input_token      integer NOT NULL DEFAULT 0,
    output_token     integer NOT NULL DEFAULT 0,
    response_time_ms integer NOT NULL DEFAULT 0,
    confidence       numeric(5,2),
    retry_count      integer NOT NULL DEFAULT 0,
    cost             numeric(10,4) NOT NULL DEFAULT 0,
    success          boolean NOT NULL DEFAULT true,
    input_hash       text,
    output_hash      text,
    company_id       uuid,
    lead_id          uuid,
    triggered_by     text NOT NULL DEFAULT 'system',
    job_id           uuid,
    event_metadata   jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at      timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT ck_ai_event_agent_name CHECK (agent_name ~ '^[A-Za-z][A-Za-z0-9]{2,49}$'),
    CONSTRAINT ck_ai_event_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100)),
    CONSTRAINT ck_ai_event_tokens_non_negative CHECK (input_token >= 0 AND output_token >= 0),
    CONSTRAINT ck_ai_event_cost_non_negative CHECK (cost >= 0),
    CONSTRAINT ck_ai_event_response_time_non_negative CHECK (response_time_ms >= 0),
    CONSTRAINT ck_ai_event_triggered_by CHECK (triggered_by = ANY (ARRAY['system','user','agent']))
);

CREATE INDEX ix_ai_event_agent_name_occurred ON ltc.ai_event (agent_name, occurred_at DESC);
CREATE INDEX ix_ai_event_company_id ON ltc.ai_event (company_id) WHERE company_id IS NOT NULL;
CREATE INDEX ix_ai_event_job_id ON ltc.ai_event (job_id) WHERE job_id IS NOT NULL;
CREATE INDEX ix_ai_event_model ON ltc.ai_event (model, occurred_at DESC);
CREATE INDEX ix_ai_event_success ON ltc.ai_event (success, occurred_at DESC) WHERE success = false;

-- ---------------------------------------------------------------
-- Tool Event: one row per external API / provider call
-- ---------------------------------------------------------------
CREATE TABLE ltc.tool_event (
    tool_event_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name      text NOT NULL,
    provider       text NOT NULL,
    api            text,
    request_id     text,
    response_code  integer,
    duration_ms    integer NOT NULL DEFAULT 0,
    retry          integer NOT NULL DEFAULT 0,
    cost           numeric(10,4) NOT NULL DEFAULT 0,
    cache_hit      boolean NOT NULL DEFAULT false,
    company_id     uuid,
    job_id         uuid,
    error_code     text,
    event_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT ck_tool_event_duration_non_negative CHECK (duration_ms >= 0),
    CONSTRAINT ck_tool_event_retry_non_negative CHECK (retry >= 0),
    CONSTRAINT ck_tool_event_cost_non_negative CHECK (cost >= 0)
);

CREATE INDEX ix_tool_event_tool_name_occurred ON ltc.tool_event (tool_name, occurred_at DESC);
CREATE INDEX ix_tool_event_provider ON ltc.tool_event (provider, occurred_at DESC);
CREATE INDEX ix_tool_event_request_id ON ltc.tool_event (request_id) WHERE request_id IS NOT NULL;
CREATE INDEX ix_tool_event_cache_hit ON ltc.tool_event (cache_hit, occurred_at DESC);

-- ---------------------------------------------------------------
-- Lead Lifecycle Event: one row per state transition
-- ---------------------------------------------------------------
CREATE TABLE ltc.lead_lifecycle_event (
    lifecycle_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id            uuid,
    company_id         uuid,
    event_code         text NOT NULL,
    from_state         text,
    to_state           text,
    triggered_by       text NOT NULL DEFAULT 'system',
    job_id             uuid,
    actor_user_id      uuid,
    event_payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at        timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_lead_lifecycle_event_lead ON ltc.lead_lifecycle_event (lead_id, occurred_at DESC) WHERE lead_id IS NOT NULL;
CREATE INDEX ix_lead_lifecycle_event_company ON ltc.lead_lifecycle_event (company_id, occurred_at DESC) WHERE company_id IS NOT NULL;
CREATE INDEX ix_lead_lifecycle_event_code ON ltc.lead_lifecycle_event (event_code, occurred_at DESC);
CREATE INDEX ix_lead_lifecycle_event_triggered ON ltc.lead_lifecycle_event (triggered_by, occurred_at DESC);

COMMIT;
