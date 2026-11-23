\set ON_ERROR_STOP on

BEGIN;

INSERT INTO ltc.user_account (
    user_id, username, password_hash, display_name, account_type, status
) VALUES (
    '00000000-0000-0000-0000-000000000101',
    'strategic.fixture',
    'test-only-hash',
    'Strategic Fixture',
    'strategic',
    'active'
);

INSERT INTO ltc.user_account (
    user_id, username, password_hash, display_name, account_type,
    sales_tier, region_code, capacity_limit, status
) VALUES
    (
        '00000000-0000-0000-0000-000000000102',
        'sales.fixture',
        'test-only-hash',
        'Sales Fixture',
        'sales', 'MA', 'NA', 10, 'active'
    ),
    (
        '00000000-0000-0000-0000-000000000103',
        'depart.fixture',
        'test-only-hash',
        'Depart Fixture',
        'sales', 'MA', 'NA', 10, 'active'
    );

INSERT INTO ltc.job (
    job_id, job_type, queue_name, aggregate_type, concurrency_key, status, payload
) VALUES (
    '00000000-0000-0000-0000-000000000201',
    'lead_enrichment',
    'lead-intelligence',
    'fixture',
    'fixture:enrichment',
    'queued',
    '{}'::jsonb
);

INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    region_code, country_code, region_mapping_version,
    validation_status, processing_status, first_seen_at, last_seen_at
) VALUES
    (
        '00000000-0000-0000-0000-000000000301',
        'fixture-company-1', 'Fixture Company 1', 'fixture company 1',
        'NA', 'US', 'region-country-v5',
        'valid', 'eligible', clock_timestamp(), clock_timestamp()
    ),
    (
        '00000000-0000-0000-0000-000000000302',
        'fixture-company-2', 'Fixture Company 2', 'fixture company 2',
        'NA', 'CA', 'region-country-v5',
        'valid', 'eligible', clock_timestamp(), clock_timestamp()
    );

INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status, scene_code,
    rule_version, prompt_version, config_checksum, current_job_id,
    is_current, completed_at
) VALUES
    (
        '00000000-0000-0000-0000-000000000401',
        '00000000-0000-0000-0000-000000000301',
        1, 'completed', 'S1', 'icp-v1', 'prompt-v1',
        repeat('a', 64), '00000000-0000-0000-0000-000000000201', true, clock_timestamp()
    ),
    (
        '00000000-0000-0000-0000-000000000402',
        '00000000-0000-0000-0000-000000000302',
        1, 'completed', 'S1', 'icp-v1', 'prompt-v1',
        repeat('b', 64), '00000000-0000-0000-0000-000000000201', true, clock_timestamp()
    );

INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, score_breakdown, explanations, is_current, scored_at
) VALUES
    (
        '00000000-0000-0000-0000-000000000501',
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000401',
        1, 'S1', 'icp-v1', '{}'::jsonb, repeat('c', 64), 'prompt-v1',
        30, 25, 15, 10, 80, 'A', true, '{}'::jsonb, '{}'::jsonb, true, clock_timestamp()
    ),
    (
        '00000000-0000-0000-0000-000000000502',
        '00000000-0000-0000-0000-000000000302',
        '00000000-0000-0000-0000-000000000402',
        1, 'S1', 'icp-v1', '{}'::jsonb, repeat('d', 64), 'prompt-v1',
        30, 25, 15, 10, 80, 'A', true, '{}'::jsonb, '{}'::jsonb, true, clock_timestamp()
    );

INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id, version_no,
    rule_version, prompt_version, d1_scale_score, d2_commercial_score,
    d3_coverage_score, total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at
) VALUES
    (
        '00000000-0000-0000-0000-000000000601',
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000401',
        1, 'scale-v1', 'prompt-v1', 40, 30, 20, 90,
        'large', 'large', 'computed', '{}'::jsonb, true, clock_timestamp()
    ),
    (
        '00000000-0000-0000-0000-000000000602',
        '00000000-0000-0000-0000-000000000302',
        '00000000-0000-0000-0000-000000000402',
        1, 'scale-v1', 'prompt-v1', 40, 30, 20, 90,
        'large', 'large', 'computed', '{}'::jsonb, true, clock_timestamp()
    );

INSERT INTO ltc.company (
    company_id, origin_candidate_id, company_name, normalized_company_name,
    country_code, region_code, region_mapping_version, created_by
) VALUES
    (
        '00000000-0000-0000-0000-000000000701',
        '00000000-0000-0000-0000-000000000301',
        'Fixture Company 1', 'fixture company 1', 'US', 'NA', 'region-country-v5',
        '00000000-0000-0000-0000-000000000101'
    ),
    (
        '00000000-0000-0000-0000-000000000702',
        '00000000-0000-0000-0000-000000000302',
        'Fixture Company 2', 'fixture company 2', 'CA', 'NA', 'region-country-v5',
        '00000000-0000-0000-0000-000000000101'
    );

INSERT INTO ltc.sales_lead (
    lead_id, company_id, source_candidate_id,
    adopted_icp_assessment_id, adopted_scale_assessment_id,
    required_sales_tier, pool_region_code, pool_region_mapping_version,
    allocation_status, pipeline_stage, current_owner_user_id,
    current_assignment_started_at, sla_due_at, allocation_rule_version
) VALUES
    (
        '00000000-0000-0000-0000-000000000801',
        '00000000-0000-0000-0000-000000000701',
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000501',
        '00000000-0000-0000-0000-000000000601',
        'MA', 'NA', 'region-country-v5', 'claimed', 'new',
        '00000000-0000-0000-0000-000000000102',
        '2026-07-20T00:00:00Z', '2026-07-19T00:00:00Z', 'allocation-v1'
    ),
    (
        '00000000-0000-0000-0000-000000000802',
        '00000000-0000-0000-0000-000000000702',
        '00000000-0000-0000-0000-000000000302',
        '00000000-0000-0000-0000-000000000502',
        '00000000-0000-0000-0000-000000000602',
        'MA', 'NA', 'region-country-v5', 'claimed', 'new',
        '00000000-0000-0000-0000-000000000102',
        '2026-07-20T00:01:00Z', '2099-01-01T00:00:00Z', 'allocation-v1'
    );

INSERT INTO ltc.lead_assignment (
    assignment_id, lead_id, assignee_user_id, assigned_by,
    assignment_type, status, assigned_at, sla_due_at
) VALUES
    (
        '00000000-0000-0000-0000-000000000901',
        '00000000-0000-0000-0000-000000000801',
        '00000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000101',
        'claim', 'active', '2026-07-20T00:00:00Z', '2026-07-19T00:00:00Z'
    ),
    (
        '00000000-0000-0000-0000-000000000902',
        '00000000-0000-0000-0000-000000000802',
        '00000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000101',
        'claim', 'active', '2026-07-20T00:01:00Z', '2099-01-01T00:00:00Z'
    );

INSERT INTO ltc.analysis_run (
    analysis_run_id, company_id, lead_id, source_candidate_id,
    icp_assessment_id, scale_assessment_id, current_job_id,
    report_type, trigger_type, status, input_hash, prompt_version,
    schema_version, profile_version, meddpicc_revision, input_snapshot,
    token_usage, cost_status, completed_at
) VALUES (
    '00000000-0000-0000-0000-000000000a01',
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000501',
    '00000000-0000-0000-0000-000000000601',
    '00000000-0000-0000-0000-000000000201',
    'customer_analysis', 'manual', 'completed', repeat('e', 64),
    'prompt-v1', 'report-v1', 0, 'fixture-0', '{}'::jsonb,
    '{}'::jsonb, 'unknown', clock_timestamp()
);

INSERT INTO ltc.analysis_report (
    report_id, company_id, analysis_run_id, report_type, version_no,
    schema_version, summary, evidence_refs, profile_snapshot,
    meddpicc_snapshot, icp_snapshot, scale_snapshot, report_payload,
    sales_guide_payload, generated_by, content_source, generated_at
) VALUES (
    '00000000-0000-0000-0000-000000000b01',
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000a01',
    'customer_analysis', 1, 'report-v1', 'immutable fixture report',
    '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    '{}'::jsonb, '{}'::jsonb, 'agent', 'migration', clock_timestamp()
);

COMMIT;

DO $$
DECLARE
    active_count bigint;
    remaining_count bigint;
    overdue_count bigint;
BEGIN
    SELECT active_assignment_count, remaining_capacity, sla_overdue_count
    INTO active_count, remaining_count, overdue_count
    FROM ltc.v_sales_workload
    WHERE user_id = '00000000-0000-0000-0000-000000000102';

    IF active_count <> 2 OR remaining_count <> 8 OR overdue_count <> 1 THEN
        RAISE EXCEPTION
            'v_sales_workload count drift: active=%, remaining=%, overdue=%',
            active_count, remaining_count, overdue_count;
    END IF;
END;
$$;

DO $$
BEGIN
    BEGIN
        UPDATE ltc.user_account
        SET status = 'departed',
            departed_at = clock_timestamp(),
            departed_by = '00000000-0000-0000-0000-000000000101',
            departure_reason = 'must release active assignments first'
        WHERE user_id = '00000000-0000-0000-0000-000000000102';
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'expected departed user / active assignment failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected departed user / active assignment failure' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        UPDATE ltc.user_account
        SET region_code = 'EA'
        WHERE user_id = '00000000-0000-0000-0000-000000000102';
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'expected assignee region mismatch failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected assignee region mismatch failure' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        UPDATE ltc.lead_assignment
        SET status = 'released', ended_at = clock_timestamp()
        WHERE assignment_id = '00000000-0000-0000-0000-000000000901';
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'expected claimed lead / assignment consistency failure';
    EXCEPTION
        WHEN integrity_constraint_violation THEN NULL;
        WHEN raise_exception THEN
            IF SQLERRM = 'expected claimed lead / assignment consistency failure' THEN
                RAISE;
            END IF;
    END;
END;
$$;

UPDATE ltc.analysis_report
SET superseded_at = clock_timestamp()
WHERE report_id = '00000000-0000-0000-0000-000000000b01';

DO $$
BEGIN
    BEGIN
        UPDATE ltc.analysis_report
        SET summary = 'illegal in-place rewrite'
        WHERE report_id = '00000000-0000-0000-0000-000000000b01';
        RAISE EXCEPTION 'expected immutable report-content failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected immutable report-content failure' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        UPDATE ltc.analysis_report
        SET superseded_at = NULL
        WHERE report_id = '00000000-0000-0000-0000-000000000b01';
        RAISE EXCEPTION 'expected report-reactivation failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected report-reactivation failure' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        DELETE FROM ltc.analysis_report
        WHERE report_id = '00000000-0000-0000-0000-000000000b01';
        RAISE EXCEPTION 'expected report hard-delete failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected report hard-delete failure' THEN
                RAISE;
            END IF;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        DELETE FROM ltc.lead_assignment
        WHERE assignment_id = '00000000-0000-0000-0000-000000000901';
        RAISE EXCEPTION 'expected assignment hard-delete failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected assignment hard-delete failure' THEN
                RAISE;
            END IF;
    END;
END;
$$;

UPDATE ltc.user_account
SET status = 'departed',
    departed_at = clock_timestamp(),
    departed_by = '00000000-0000-0000-0000-000000000101',
    departure_reason = 'fixture'
WHERE user_id = '00000000-0000-0000-0000-000000000103';

DO $$
BEGIN
    BEGIN
        UPDATE ltc.user_account
        SET status = 'active',
            departed_at = NULL,
            departed_by = NULL,
            departure_reason = NULL
        WHERE user_id = '00000000-0000-0000-0000-000000000103';
        RAISE EXCEPTION 'expected departed terminal-state failure';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM = 'expected departed terminal-state failure' THEN
                RAISE;
            END IF;
    END;
END;
$$;

DO $$
BEGIN
    IF NOT ltc.validate_meeting_summary_v1(
        '{
          "customer_needs":["coverage"],
          "pain_points":["cost"],
          "buying_signals":["quote"],
          "action_items":[{"task":"send proposal","owner":null,"due_at":"2026-07-20T08:00:00Z"}],
          "decisions":["pilot"],
          "risks":["budget"],
          "keywords":["eSIM"],
          "next_step":"send proposal"
        }'::jsonb
    ) THEN
        RAISE EXCEPTION 'valid meeting summary rejected';
    END IF;

    IF ltc.validate_meeting_summary_v1(
        '{
          "customer_needs":[42],
          "pain_points":[],
          "buying_signals":[],
          "action_items":[{"task":"send proposal","unexpected":true}],
          "decisions":[],
          "risks":[],
          "keywords":[],
          "next_step":null
        }'::jsonb
    ) THEN
        RAISE EXCEPTION 'invalid meeting summary accepted';
    END IF;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO ltc.lead_candidate (
            candidate_id, dedupe_key, company_name, normalized_company_name,
            validation_status, processing_status, first_seen_at, last_seen_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000399',
            'invalid-merged-fixture', 'Invalid Merge', 'invalid merge',
            'valid', 'merged', clock_timestamp(), clock_timestamp()
        );
        RAISE EXCEPTION 'expected merged-shape failure';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END;
$$;

SELECT 'core invariants passed' AS result;
