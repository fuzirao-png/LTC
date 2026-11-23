\set ON_ERROR_STOP on

BEGIN;

INSERT INTO ltc.job (
    job_id, job_type, queue_name, aggregate_type, aggregate_id, status,
    payload, result_summary, progress_percent, completed_at, version
) VALUES (
    '00000000-0000-0000-0000-000000000c01',
    'customer_analysis', 'customer-analysis', 'company',
    '00000000-0000-0000-0000-000000000701', 'succeeded',
    '{"analysis_run_id":"00000000-0000-0000-0000-000000000d01"}'::jsonb,
    '{"report_id":"00000000-0000-0000-0000-000000000e01"}'::jsonb,
    100, clock_timestamp(), 2
);

INSERT INTO ltc.customer_profile (
    company_id, company_type, region_text, employee_scale, business_model,
    esim_scenario, coverage, estimated_usage, integration, compliance,
    budget_text, decision_maker_text, decision_cycle_text, completeness_score,
    missing_fields, extra_payload, field_provenance, version
) VALUES (
    '00000000-0000-0000-0000-000000000701', 'TMC', 'North America',
    '500-1000', 'B2B subscription', 'enterprise travel', 'Global', '10000',
    'REST API', 'SOC2', '$50k', 'Fixture Buyer', '30 days', 1, ARRAY[]::text[],
    '{"source":"customer-analysis-acceptance"}'::jsonb,
    '{"business_model":{"source":"manual"}}'::jsonb, 1
) ON CONFLICT (company_id) DO UPDATE SET
    business_model=EXCLUDED.business_model, version=EXCLUDED.version;

INSERT INTO ltc.customer_meddpicc_dimension (
    company_id, dimension_code, level, status, summary, payload,
    evidence_refs, version
) VALUES (
    '00000000-0000-0000-0000-000000000701', 'metrics', 'strong',
    'confirmed', '10000 annual activations', '{"value":10000}'::jsonb,
    '[{"url":"https://example.com/evidence"}]'::jsonb, 1
) ON CONFLICT (company_id, dimension_code) DO UPDATE SET
    status=EXCLUDED.status, payload=EXCLUDED.payload, version=EXCLUDED.version;

INSERT INTO ltc.analysis_run (
    analysis_run_id, company_id, lead_id, source_candidate_id,
    icp_assessment_id, scale_assessment_id, current_job_id, report_type,
    trigger_type, status, input_hash, prompt_version, schema_version,
    profile_version, meddpicc_revision, input_snapshot, token_usage,
    cost_status, completed_at, version
) VALUES (
    '00000000-0000-0000-0000-000000000d01',
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000501',
    '00000000-0000-0000-0000-000000000601',
    '00000000-0000-0000-0000-000000000c01',
    'customer_analysis', 'manual', 'completed', repeat('f', 64),
    'customer-analysis-v3.6-p1', 'customer-analysis-report-v3.6', 1,
    repeat('a', 64), '{"company":{"company_name":"Fixture Company 1"}}'::jsonb,
    '{}'::jsonb, 'unknown', clock_timestamp(), 2
);

INSERT INTO ltc.analysis_report (
    report_id, company_id, analysis_run_id, report_type, version_no,
    schema_version, summary, health_grade, intention_level, confidence,
    section_confidence, low_confidence_sections, data_sources, evidence_refs,
    profile_snapshot, meddpicc_snapshot, icp_snapshot, scale_snapshot,
    report_payload, sales_guide_payload, generated_by, content_source,
    generated_at
) VALUES (
    '00000000-0000-0000-0000-000000000e01',
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000d01', 'customer_analysis', 2,
    'customer-analysis-report-v3.6', 'Customer analysis persistence accepted',
    'A-', 'high', 0.9, '{"market":0.9}'::jsonb, ARRAY[]::text[],
    '["https://example.com/evidence"]'::jsonb,
    '[{"url":"https://example.com/evidence"}]'::jsonb,
    '{"profile_version":1}'::jsonb, '{"metrics":{"status":"confirmed"}}'::jsonb,
    '{"total_score":80}'::jsonb, '{"effective_tier":"large"}'::jsonb,
    '{"market":{"sections":[{"subtitle":"coverage","content":"global"}]}}'::jsonb,
    '{"customer_need":{"actions":["pilot"]}}'::jsonb,
    'agent', 'template', clock_timestamp()
);

INSERT INTO ltc.analysis_suggestion (
    suggestion_id, company_id, report_id, target_type, target_path,
    target_version_at_creation, current_value_snapshot, proposed_value,
    evidence_refs, confidence, status
) VALUES (
    '00000000-0000-0000-0000-000000000f01',
    '00000000-0000-0000-0000-000000000701',
    '00000000-0000-0000-0000-000000000e01', 'profile', 'budget_text', 1,
    '"$50k"'::jsonb, '"$60k"'::jsonb,
    '[{"url":"https://example.com/evidence"}]'::jsonb, 0.9, 'pending'
);

COMMIT;

DO $$
DECLARE
    persisted_shape text;
    restart_read_shape text;
BEGIN
    SELECT cp.version || ':' || cmd.status || ':' || ar.status || ':' ||
           rep.version_no || ':' || sug.status || ':' || job.status
    INTO persisted_shape
    FROM ltc.customer_profile cp
    JOIN ltc.customer_meddpicc_dimension cmd USING (company_id)
    JOIN ltc.analysis_run ar USING (company_id)
    JOIN ltc.analysis_report rep ON rep.analysis_run_id=ar.analysis_run_id
    JOIN ltc.analysis_suggestion sug ON sug.report_id=rep.report_id
    JOIN ltc.job job ON job.job_id=ar.current_job_id
    WHERE ar.analysis_run_id='00000000-0000-0000-0000-000000000d01'
      AND cmd.dimension_code='metrics';

    IF persisted_shape <> '1:confirmed:completed:2:pending:succeeded' THEN
        RAISE EXCEPTION 'customer-analysis persistence shape invalid: %', persisted_shape;
    END IF;

    SELECT ar.input_hash || ':' || rep.summary || ':' ||
           (rep.report_payload #>> '{market,sections,0,content}')
    INTO restart_read_shape
    FROM ltc.analysis_report rep
    JOIN ltc.analysis_run ar ON ar.analysis_run_id=rep.analysis_run_id
    WHERE rep.report_id='00000000-0000-0000-0000-000000000e01';

    IF restart_read_shape <> repeat('f', 64) || ':Customer analysis persistence accepted:global' THEN
        RAISE EXCEPTION 'customer-analysis restart read invalid: %', restart_read_shape;
    END IF;
END;
$$;

SELECT 'customer analysis persistence flow passed' AS result;
