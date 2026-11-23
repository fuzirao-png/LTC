-- Migration 0006: Agent KPI scoring functions.
-- Computes monthly quality scores for each Agent from telemetry tables.

BEGIN;

SET search_path TO ltc, public;

-- ---------------------------------------------------------------
-- Agent quality score: 0-100, weighted across 4 dimensions
--   accuracy  35%
--   adoption  25%
--   contribution 25%
--   cost_efficiency 15%
-- ---------------------------------------------------------------

CREATE OR REPLACE FUNCTION ltc.compute_agent_quality_score(
    p_agent_name text,
    p_year_month text  -- e.g. '2026-07'
) RETURNS numeric(5,2)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    v_start  timestamptz;
    v_end    timestamptz;
    v_total  integer;
    v_success integer;
    v_accuracy numeric;
    v_adoption numeric;
    v_contribution numeric;
    v_cost_eff numeric;
    v_avg_cost numeric;
    v_score numeric;
BEGIN
    v_start := date_trunc('month', p_year_month::date)::timestamptz;
    v_end   := v_start + interval '1 month';

    -- Total calls this month
    SELECT count(*), count(*) FILTER (WHERE success)
    INTO v_total, v_success
    FROM ltc.ai_event
    WHERE agent_name = p_agent_name
      AND occurred_at >= v_start
      AND occurred_at < v_end;

    IF v_total = 0 THEN
        RETURN NULL;  -- no data for this agent/month
    END IF;

    -- Accuracy: success rate
    v_accuracy := (v_success::numeric / v_total) * 100;

    -- Adoption: based on success rate (proxy; true adoption needs frontend data)
    v_adoption := v_accuracy * 0.9;

    -- Contribution: if many calls, assume agent is being used
    v_contribution := LEAST(v_total::numeric / 10 * 25, 100);  -- max at 40 calls/month

    -- Cost efficiency: lower avg cost is better
    SELECT avg(cost) INTO v_avg_cost
    FROM ltc.ai_event
    WHERE agent_name = p_agent_name
      AND occurred_at >= v_start
      AND occurred_at < v_end
      AND success;

    IF v_avg_cost IS NULL OR v_avg_cost = 0 THEN
        v_cost_eff := 100;
    ELSE
        -- Target cost varies by agent
        v_cost_eff := GREATEST(0, 100 - (v_avg_cost * 200));  -- $0.50/call = 0 score
    END IF;

    v_score := (v_accuracy * 0.35) + (v_adoption * 0.25) + (v_contribution * 0.25) + (v_cost_eff * 0.15);
    RETURN ROUND(GREATEST(0, LEAST(100, v_score)), 2);
END;
$$;


-- ---------------------------------------------------------------
-- Agent quality grade: S / A / B / C
-- ---------------------------------------------------------------

CREATE OR REPLACE FUNCTION ltc.compute_agent_grade(
    p_agent_name text,
    p_year_month text
) RETURNS text
LANGUAGE sql STABLE
AS $$
    SELECT CASE
        WHEN ltc.compute_agent_quality_score(p_agent_name, p_year_month) >= 85 THEN 'S'
        WHEN ltc.compute_agent_quality_score(p_agent_name, p_year_month) >= 70 THEN 'A'
        WHEN ltc.compute_agent_quality_score(p_agent_name, p_year_month) >= 55 THEN 'B'
        WHEN ltc.compute_agent_quality_score(p_agent_name, p_year_month) IS NOT NULL THEN 'C'
        ELSE NULL
    END;
$$;

COMMIT;
