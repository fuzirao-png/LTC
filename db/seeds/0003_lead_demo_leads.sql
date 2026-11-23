-- LTC lead demo seed v3.2
-- Source: ltc_demo_leads(1).db → enriched_company_validation (144 rows) → 20 curated demo companies
-- Safe to run multiple times (ON CONFLICT DO NOTHING / UPDATE).

BEGIN;

SET search_path TO ltc, public;

INSERT INTO ltc.user_account (user_id, username, password_hash, display_name, account_type, status)
VALUES ('00000000-0000-0000-0000-000000000000', 'seed.import', 'seed-only-not-for-login', 'Seed Import', 'strategic', 'active')
ON CONFLICT (user_id) DO NOTHING;

-- Placeholder job row for FK references from enrichment/assessment tables
INSERT INTO ltc.job (job_id, job_type, queue_name, status, payload, completed_at)
VALUES ('00000000-0000-4000-8000-000000000000', 'seed.import', 'seed', 'succeeded', '{}', clock_timestamp())
ON CONFLICT (job_id) DO NOTHING;

-- Amex GBT (OTHER, OTHER, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('363e7291-94a5-4d1a-b75b-2a83d502a031', 'e5c45cececa06a4b6c11df7aff4f054f', 'Amex GBT', 'amex gbt',
    NULL,
    NULL,
    '', 'OTHER', 'OTHER', 'v3.2-seed',
    NULL,
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('6db69b32-dd95-5c99-acb0-3180ef75b5fe', '363e7291-94a5-4d1a-b75b-2a83d502a031', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":7.5}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('7f6989e5-3111-5c32-89dc-e7147fdcac41', '363e7291-94a5-4d1a-b75b-2a83d502a031', '6db69b32-dd95-5c99-acb0-3180ef75b5fe', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 22.5, 20.0, 7.5, 90.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 22.5, "d3": 20.0, "d4": 7.5}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('18c8fa54-c7a4-5b8c-b282-521b40dbdcb5', '363e7291-94a5-4d1a-b75b-2a83d502a031', '6db69b32-dd95-5c99-acb0-3180ef75b5fe', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- 阿里商旅 (OTHER, OTHER, tier=small)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('7f6ce1dc-50d2-4ea6-a530-4c79883f10c1', 'c785eaa5dc438e25eabe59b86b7019a1', '阿里商旅', '阿里商旅',
    NULL,
    NULL,
    '', 'OTHER', 'OTHER', 'v3.2-seed',
    NULL,
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('d856b5da-a532-526e-85b3-ce60d28f8fe5', '7f6ce1dc-50d2-4ea6-a530-4c79883f10c1', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('a14e030f-8bbc-5b24-955b-ed588c739317', '7f6ce1dc-50d2-4ea6-a530-4c79883f10c1', 'd856b5da-a532-526e-85b3-ce60d28f8fe5', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 0.0, 0.0, 0.0, 0.0, 0.0, 'D',
    true, 0.85, '{"d1": 0.0, "d2": 0.0, "d3": 0.0, "d4": 0.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('421cd65a-8c1b-56b3-b5fe-3db6d83c4b70', '7f6ce1dc-50d2-4ea6-a530-4c79883f10c1', 'd856b5da-a532-526e-85b3-ce60d28f8fe5', 1, 'v3.2-seed', 'v3.2-seed',
    10.0, 10.0, 5.0, 25.0,
    'small', 'small', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 25, "customer_tier_level": "small", "dimensions": [{"dimension": "D1", "score": 10.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 10.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 5.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- 携程商旅 (OTHER, OTHER, tier=small)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('e6627207-e466-4cf9-9605-d61b98b1d51f', '054067711c40cf98838d6278002c48a9', '携程商旅', '携程商旅',
    NULL,
    NULL,
    '', 'OTHER', 'OTHER', 'v3.2-seed',
    NULL,
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('5b5dff31-31b9-5cca-a3f2-50262596cc99', 'e6627207-e466-4cf9-9605-d61b98b1d51f', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('f564c573-91af-58a3-8ff2-123492d8d5ec', 'e6627207-e466-4cf9-9605-d61b98b1d51f', '5b5dff31-31b9-5cca-a3f2-50262596cc99', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 0.0, 0.0, 0.0, 0.0, 0.0, 'D',
    true, 0.85, '{"d1": 0.0, "d2": 0.0, "d3": 0.0, "d4": 0.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('85b47302-7764-50f5-8d40-310a9c0766c2', 'e6627207-e466-4cf9-9605-d61b98b1d51f', '5b5dff31-31b9-5cca-a3f2-50262596cc99', 1, 'v3.2-seed', 'v3.2-seed',
    10.0, 10.0, 5.0, 25.0,
    'small', 'small', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 25, "customer_tier_level": "small", "dimensions": [{"dimension": "D1", "score": 10.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 10.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 5.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Navan (OTHER, OTHER, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('aa68256a-8272-499a-8f97-f59f9f5de642', 'c5c69016499549b7015a6a2075c2e36a', 'Navan', 'navan',
    NULL,
    NULL,
    '', 'OTHER', 'OTHER', 'v3.2-seed',
    NULL,
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('1dab2831-2045-5441-bb8b-e1a3e0d25f31', 'aa68256a-8272-499a-8f97-f59f9f5de642', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('5f3149cb-b8f7-547d-9d93-15a6ba112598', 'aa68256a-8272-499a-8f97-f59f9f5de642', '1dab2831-2045-5441-bb8b-e1a3e0d25f31', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 10.0, 100.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('5e4c2ccc-c665-5845-8880-f05cc3cc7fbc', 'aa68256a-8272-499a-8f97-f59f9f5de642', '1dab2831-2045-5441-bb8b-e1a3e0d25f31', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 93.75, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- SAP Concur (OTHER, OTHER, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('5b40c4dd-0370-48ff-8916-a30cd263f749', '24db75ccbaab552ff5cab2a77573c97d', 'SAP Concur', 'sap concur',
    NULL,
    NULL,
    '', 'OTHER', 'OTHER', 'v3.2-seed',
    NULL,
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('cb768574-db5f-5b15-8f23-c33f6be1b3a9', '5b40c4dd-0370-48ff-8916-a30cd263f749', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('88b4f76a-ba51-57d4-87c8-adf8f9cfc8b4', '5b40c4dd-0370-48ff-8916-a30cd263f749', 'cb768574-db5f-5b15-8f23-c33f6be1b3a9', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 10.0, 100.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('848f184f-057f-5b84-9536-daf441d7de1a', '5b40c4dd-0370-48ff-8916-a30cd263f749', 'cb768574-db5f-5b15-8f23-c33f6be1b3a9', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Perk UK (TMC, EU, tier=medium)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('94b221da-a997-47b3-bc0e-2eb703b4b305', '8cd2d209ccaa8578004eb9902b4812ff', 'Perk UK', 'perk uk',
    'https://travelperk.com/uk',
    'travelperk.com',
    '企业差旅管理平台，支持差旅、费用与政策流程自动化。', 'TMC', 'EU', 'v3.2-seed',
    'GB',
    NULL,
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('26b802d6-4058-5eda-839f-4f10acac2487', '94b221da-a997-47b3-bc0e-2eb703b4b305', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":30.0}'::jsonb, '{"score":15.0}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":5.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('acaedcee-da90-5340-afbe-8a599bb0c388', '94b221da-a997-47b3-bc0e-2eb703b4b305', '26b802d6-4058-5eda-839f-4f10acac2487', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 30.0, 15.0, 15.0, 5.0, 65.0, 'C',
    true, 0.85, '{"d1": 30.0, "d2": 15.0, "d3": 15.0, "d4": 5.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('798f9645-a079-591a-806a-dff0e212ae26', '94b221da-a997-47b3-bc0e-2eb703b4b305', '26b802d6-4058-5eda-839f-4f10acac2487', 1, 'v3.2-seed', 'v3.2-seed',
    25.0, 20.0, 15.0, 60.0,
    'medium', 'medium', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 66.25, "customer_tier_level": "medium", "dimensions": [{"dimension": "D1", "score": 25.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 20.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 15.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- American Express Global Business Travel (TMC, EU, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('2ca57771-954b-4240-b164-e0fdeea4ffad', '52f74a616ffcb31d690481b564f1b654', 'American Express Global Business Travel', 'american express global business travel',
    'https://www.amexglobalbusinesstravel.com/uk/neo/',
    'amexglobalbusinesstravel.com',
    '企业差旅管理解决方案平台，面向英国市场提供差旅管理产品与服务。', 'TMC', 'EU', 'v3.2-seed',
    'GB',
    '伦敦',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('30725202-60ca-5f77-8cdc-a450a6000fc0', '2ca57771-954b-4240-b164-e0fdeea4ffad', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":7.5}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('b4a4e086-afc1-5a7d-bc87-6bd6647d16ec', '2ca57771-954b-4240-b164-e0fdeea4ffad', '30725202-60ca-5f77-8cdc-a450a6000fc0', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 7.5, 97.5, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 7.5}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('a3324999-a13b-538c-bf7d-ba34e8fafc80', '2ca57771-954b-4240-b164-e0fdeea4ffad', '30725202-60ca-5f77-8cdc-a450a6000fc0', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- BCD Travel South Korea (TMC, EA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('bb6b8226-26b8-44f6-9570-e1e3e2d617dc', 'ffc6b6d5d6fa31b51ae9f8a863352e8b', 'BCD Travel South Korea', 'bcd travel south korea',
    'https://www.bcdtravel.com/country/korea/',
    'bcdtravel.com',
    'BCD Travel South Korea 是全球差旅管理公司 BCD Travel 的韩国业务页面，主要为企业客户提供商务旅行管理、差旅预订、合规管理、费用控制及全球差旅服务支持。', 'TMC', 'EA', 'v3.2-seed',
    'KR',
    '首尔',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('6b53d584-7555-5ecc-8990-d0a5f44e9101', 'bb6b8226-26b8-44f6-9570-e1e3e2d617dc', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('b624d567-5139-5f65-b08a-2316bca2bdd3', 'bb6b8226-26b8-44f6-9570-e1e3e2d617dc', '6b53d584-7555-5ecc-8990-d0a5f44e9101', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 10.0, 100.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('e3616f17-a921-5684-b5b6-7270a8450c78', 'bb6b8226-26b8-44f6-9570-e1e3e2d617dc', '6b53d584-7555-5ecc-8990-d0a5f44e9101', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Ramp (FINTECH, NA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('4e61bbb1-7495-44d6-ba29-6e3f0f483135', 'd1fbfd148ea0a004cdaa60bc27e24ea8', 'Ramp', 'ramp',
    'https://ramp.com/',
    'ramp.com',
    'Ramp 是企业金融自动化平台，提供企业卡、费用管理、账单支付、采购、差旅和财务分析工具。', 'FINTECH', 'NA', 'v3.2-seed',
    'US',
    '纽约',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('c33473af-c4f0-5704-86f4-02de2e0d7b8c', '4e61bbb1-7495-44d6-ba29-6e3f0f483135', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":30.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('c84c122a-70ea-5e82-b76d-90b5bf18dcb1', '4e61bbb1-7495-44d6-ba29-6e3f0f483135', 'c33473af-c4f0-5704-86f4-02de2e0d7b8c', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 30.0, 30.0, 15.0, 10.0, 85.0, 'A',
    true, 0.85, '{"d1": 30.0, "d2": 30.0, "d3": 15.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('2cb8b473-3b3e-5315-b7a6-fa3d047c943e', '4e61bbb1-7495-44d6-ba29-6e3f0f483135', 'c33473af-c4f0-5704-86f4-02de2e0d7b8c', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 91, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Brex (FINTECH, NA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('c46a290f-84c1-4547-b1c4-ff7a3f1289d2', '217cf7dafb85470017851c2b717d0bbe', 'Brex', 'brex',
    'https://www.brex.com/',
    'brex.com',
    'Brex 是企业金融科技平台，提供企业卡、费用管理、差旅管理、账单支付和财务自动化服务。', 'FINTECH', 'NA', 'v3.2-seed',
    'US',
    '旧金山',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('c727b590-628f-5269-9f3a-7bc27292caee', 'c46a290f-84c1-4547-b1c4-ff7a3f1289d2', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":30.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('38b83d20-579a-5d2d-ac5a-ed799780b148', 'c46a290f-84c1-4547-b1c4-ff7a3f1289d2', 'c727b590-628f-5269-9f3a-7bc27292caee', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 30.0, 22.5, 15.0, 10.0, 77.5, 'B',
    true, 0.85, '{"d1": 30.0, "d2": 22.5, "d3": 15.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('5464659e-7b9a-59ef-bf89-141ecaf35082', 'c46a290f-84c1-4547-b1c4-ff7a3f1289d2', 'c727b590-628f-5269-9f3a-7bc27292caee', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 93.75, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Rocket Travel by Agoda (TRAVEL_OTA, NA, tier=medium)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('7c3ab548-cf85-467f-9da0-46ca23e2f7f2', '1e01e8744c7f14ed968a5ff3ef167b65', 'Rocket Travel by Agoda', 'rocket travel by agoda',
    'https://www.rockettravel.com',
    'rockettravel.com',
    'Rocket Travel by Agoda 位于美国芝加哥，提供旅行技术和商旅 OTA 服务，为金融机构、忠诚度计划和品牌合作伙伴提供酒店及旅行预订解决方案。', 'TRAVEL_OTA', 'NA', 'v3.2-seed',
    'US',
    '芝加哥',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('47b40537-ff35-56cf-94fb-e6cccd57eb51', '7c3ab548-cf85-467f-9da0-46ca23e2f7f2', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":20.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":5.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('fd480833-3436-543f-a3e7-a73c77727b4f', '7c3ab548-cf85-467f-9da0-46ca23e2f7f2', '47b40537-ff35-56cf-94fb-e6cccd57eb51', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 20.0, 22.5, 15.0, 5.0, 62.5, 'C',
    true, 0.85, '{"d1": 20.0, "d2": 22.5, "d3": 15.0, "d4": 5.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('e6241559-af8a-5156-8391-185afcce5df8', '7c3ab548-cf85-467f-9da0-46ca23e2f7f2', '47b40537-ff35-56cf-94fb-e6cccd57eb51', 1, 'v3.2-seed', 'v3.2-seed',
    25.0, 20.0, 15.0, 60.0,
    'medium', 'medium', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 68.75, "customer_tier_level": "medium", "dimensions": [{"dimension": "D1", "score": 25.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 20.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 15.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Expensify (FINTECH, NA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('d4f87f46-a547-4a08-a23c-69d1c150d9bd', 'f0b9e31d10dc872bded4e185a389b787', 'Expensify', 'expensify',
    'https://www.expensify.com',
    'expensify.com',
    'Expensify 是一家美国费用管理和企业支付平台，提供报销、收据扫描、公司卡、账单支付和差旅费用管理功能，面向中小企业和企业团队。', 'FINTECH', 'NA', 'v3.2-seed',
    'US',
    '波特兰',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('dc94c627-f6dd-5cd6-8cf5-262a90e23905', 'd4f87f46-a547-4a08-a23c-69d1c150d9bd', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":30.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('b1353e49-12b8-5f18-976f-892872f707a4', 'd4f87f46-a547-4a08-a23c-69d1c150d9bd', 'dc94c627-f6dd-5cd6-8cf5-262a90e23905', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 30.0, 22.5, 15.0, 10.0, 77.5, 'B',
    true, 0.85, '{"d1": 30.0, "d2": 22.5, "d3": 15.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('84f91d79-13ba-51a6-a6f7-09fff2389978', 'd4f87f46-a547-4a08-a23c-69d1c150d9bd', 'dc94c627-f6dd-5cd6-8cf5-262a90e23905', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 83.75, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- 日本ツアーサービス株式会社 (TRAVEL_OTA, EA, tier=medium)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('2d2a4146-280c-4eda-9272-e7eac5cf5642', '4b5c818bccca56ad1180352d9c2c6ec6', '日本ツアーサービス株式会社', '日本ツアーサービス株式会社',
    'https://jts-travel.jp/biztabi/',
    'jts-travel.jp',
    '面向法人、团体和展会视察的商务旅行服务商，提供国内外差旅、视察团及各类商务出行安排。', 'TRAVEL_OTA', 'EA', 'v3.2-seed',
    'JP',
    '神户',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('9b113c40-b9a5-5f6f-b907-7a6976177c80', '2d2a4146-280c-4eda-9272-e7eac5cf5642', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":20.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":5.0}'::jsonb, '{"score":2.5}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('d5b8d737-5ce8-5627-8ba8-0d89be9fbaf7', '2d2a4146-280c-4eda-9272-e7eac5cf5642', '9b113c40-b9a5-5f6f-b907-7a6976177c80', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 20.0, 22.5, 5.0, 2.5, 50.0, 'C',
    true, 0.85, '{"d1": 20.0, "d2": 22.5, "d3": 5.0, "d4": 2.5}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('798cde13-981a-53de-a61e-b1eee407d4f0', '2d2a4146-280c-4eda-9272-e7eac5cf5642', '9b113c40-b9a5-5f6f-b907-7a6976177c80', 1, 'v3.2-seed', 'v3.2-seed',
    25.0, 20.0, 15.0, 60.0,
    'medium', 'medium', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 68.75, "customer_tier_level": "medium", "dimensions": [{"dimension": "D1", "score": 25.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 20.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 15.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Trip.Biz (TRAVEL_OTA, EA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('f0e24fef-7ad6-431b-a8da-677ab0de0a52', '5141bfb7e51bbca1c1ceb46e95af9b5e', 'Trip.Biz', 'trip.biz',
    'https://jp.trip.biz/',
    'jp.trip.biz',
    'Trip.Biz 是 Trip.com Group 旗下的一体化数字化商旅管理平台，面向日本及全球商旅市场，提供在线预订、审批、报销、报表分析和支付等一站式出差管理服务。依托本地团队和技术能力，帮助企业提升合规性、降低差旅成本并改善员工出行体验。', 'TRAVEL_OTA', 'EA', 'v3.2-seed',
    'JP',
    '东京',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('4578fd44-4013-51bb-a96d-be06f2cfc23a', 'f0e24fef-7ad6-431b-a8da-677ab0de0a52', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":5.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('2a9a7145-ec13-5e8c-8231-01fa2472e7d1', 'f0e24fef-7ad6-431b-a8da-677ab0de0a52', '4578fd44-4013-51bb-a96d-be06f2cfc23a', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 15.0, 5.0, 90.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 15.0, "d4": 5.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('415ac362-d2dc-57ab-8de4-e14670eafc69', 'f0e24fef-7ad6-431b-a8da-677ab0de0a52', '4578fd44-4013-51bb-a96d-be06f2cfc23a', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- GoCorp by Gojek (TMC, OTHER, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('0bbe9b3f-445e-4f08-9c50-a821c5d826bf', '7f5f246884784dc08b9caa4f1651d64d', 'GoCorp by Gojek', 'gocorp by gojek',
    'https://www.gojek.com/gocorp',
    'gojek.com',
    'GoCorp 是 Gojek 面向企业客户推出的商务费用管理平台，支持企业管理员工交通、餐饮配送和物流支出，并通过实时仪表盘、预算控制和自动化报销流程提升费用透明度，主要覆盖印度尼西亚、新加坡和越南。', 'TMC', 'OTHER', 'v3.2-seed',
    '印度',
    '雅加达',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('1201128a-4584-5df9-a90f-767463bba7ed', '0bbe9b3f-445e-4f08-9c50-a821c5d826bf', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('dba3636e-23f9-5839-8cfe-b9afc5c59b54', '0bbe9b3f-445e-4f08-9c50-a821c5d826bf', '1201128a-4584-5df9-a90f-767463bba7ed', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 0.0, 0.0, 0.0, 0.0, 0.0, 'D',
    true, 0.85, '{"d1": 0.0, "d2": 0.0, "d3": 0.0, "d4": 0.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('dc69904d-d0db-54a4-8115-14abb2257247', '0bbe9b3f-445e-4f08-9c50-a821c5d826bf', '1201128a-4584-5df9-a90f-767463bba7ed', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 85, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- YouTrip (FINTECH, SEA, tier=medium)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('1e6e6f8a-7409-4494-9182-be583f9a9e67', 'db0a895ef8ed1fdf79017d8849029d05', 'YouTrip', 'youtrip',
    'https://www.you.co',
    'you.co',
    'YouTrip 是总部位于新加坡的金融科技公司，提供多币种电子钱包、跨境支付、旅行消费卡和企业支出管理服务，主要服务东南亚个人用户和企业客户。', 'FINTECH', 'SEA', 'v3.2-seed',
    'SG',
    '新加坡',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('ceed2002-e48d-5b4a-93fa-ed8a58b4140d', '1e6e6f8a-7409-4494-9182-be583f9a9e67', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":30.0}'::jsonb, '{"score":22.5}'::jsonb,
    '{"score":15.0}'::jsonb, '{"score":2.5}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('8beb59c4-0889-5479-9503-8218863d7166', '1e6e6f8a-7409-4494-9182-be583f9a9e67', 'ceed2002-e48d-5b4a-93fa-ed8a58b4140d', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 30.0, 22.5, 15.0, 2.5, 70.0, 'B',
    true, 0.85, '{"d1": 30.0, "d2": 22.5, "d3": 15.0, "d4": 2.5}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('6745b6b6-9df5-5bb7-a272-45fce07f6efb', '1e6e6f8a-7409-4494-9182-be583f9a9e67', 'ceed2002-e48d-5b4a-93fa-ed8a58b4140d', 1, 'v3.2-seed', 'v3.2-seed',
    25.0, 20.0, 15.0, 60.0,
    'medium', 'medium', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 75, "customer_tier_level": "medium", "dimensions": [{"dimension": "D1", "score": 25.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 20.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 15.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Travelstop (TMC, SEA, tier=small)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('6aad550c-802b-4b10-afd4-9fbb16d45f48', 'cc065f40411fe08d462c61f521095bc9', 'Travelstop', 'travelstop',
    'https://www.travelstop.com',
    'travelstop.com',
    'Travelstop 是总部位于新加坡的企业差旅和费用管理平台，为中小企业提供商旅预订、差旅政策、审批流程、费用报销和企业支出管理工具。', 'TMC', 'SEA', 'v3.2-seed',
    'SG',
    '新加坡',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('86aaeb20-1f42-5dd4-9f94-5263b3ee6fb8', '6aad550c-802b-4b10-afd4-9fbb16d45f48', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":0.0}'::jsonb, '{"score":0.0}'::jsonb,
    '{"score":5.0}'::jsonb, '{"score":2.5}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('56c13b07-c081-5ec1-ba6c-1ecb5fca470b', '6aad550c-802b-4b10-afd4-9fbb16d45f48', '86aaeb20-1f42-5dd4-9f94-5263b3ee6fb8', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 0.0, 0.0, 5.0, 2.5, 7.5, 'D',
    true, 0.85, '{"d1": 0.0, "d2": 0.0, "d3": 5.0, "d4": 2.5}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('d9f48399-21ed-5cc1-8dde-696e2a09706f', '6aad550c-802b-4b10-afd4-9fbb16d45f48', '86aaeb20-1f42-5dd4-9f94-5263b3ee6fb8', 1, 'v3.2-seed', 'v3.2-seed',
    10.0, 10.0, 5.0, 25.0,
    'small', 'small', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 43.75, "customer_tier_level": "small", "dimensions": [{"dimension": "D1", "score": 10.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 10.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 5.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- Christopherson Business Travel (TMC, NA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('09c434d4-b44d-4355-9052-50b6da99cf3a', 'f018aaaccac7b99c8e4e1cacafb81afa', 'Christopherson Business Travel', 'christopherson business travel',
    'https://www.cbtravel.com',
    'cbtravel.com',
    'Christopherson Business Travel 是美国差旅管理公司，提供企业差旅预订、差旅政策执行、费用与数据管理、旅行者安全和客户支持服务。', 'TMC', 'NA', 'v3.2-seed',
    'US',
    '盐湖城',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('e4b014c7-fe2c-5a7f-9885-a51d4ff50cc8', '09c434d4-b44d-4355-9052-50b6da99cf3a', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":15.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('122aa7a6-aa2f-516b-8b1d-4e09fe58886f', '09c434d4-b44d-4355-9052-50b6da99cf3a', 'e4b014c7-fe2c-5a7f-9885-a51d4ff50cc8', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 15.0, 20.0, 10.0, 85.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 15.0, "d3": 20.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('8afc6b53-0ff8-5d3b-b750-660297ed881b', '09c434d4-b44d-4355-9052-50b6da99cf3a', 'e4b014c7-fe2c-5a7f-9885-a51d4ff50cc8', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 83.75, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- FCM Travel Americas (TMC, NA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('2bc41d42-1067-49c1-9e1c-22f585409ee7', '2bbf8b83b1fd132d2434ad341f069570', 'FCM Travel Americas', 'fcm travel americas',
    'http://www.fcmtravel.com/en-us',
    NULL,
    'FCM Travel Americas 是面向企业客户的商旅管理公司，提供差旅管理、成本控制、供应商谈判、会议活动、咨询服务和自有技术平台，帮助企业优化差旅项目。', 'TMC', 'NA', 'v3.2-seed',
    'US',
    '蒙特维尔',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('ab8f2b5d-7e6c-5fd9-b43c-8f0ab3ef46b9', '2bc41d42-1067-49c1-9e1c-22f585409ee7', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":5.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('1143abac-39f2-5d91-ac1a-7e84367a6eae', '2bc41d42-1067-49c1-9e1c-22f585409ee7', 'ab8f2b5d-7e6c-5fd9-b43c-8f0ab3ef46b9', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 5.0, 95.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 5.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('f7e13988-b41d-53d1-b229-12407840d00c', '2bc41d42-1067-49c1-9e1c-22f585409ee7', 'ab8f2b5d-7e6c-5fd9-b43c-8f0ab3ef46b9', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;


-- 携程集团 (TMC, EA, tier=large)
INSERT INTO ltc.lead_candidate (
    candidate_id, dedupe_key, company_name, normalized_company_name,
    website, normalized_domain, company_intro, industry_code,
    region_code, region_mapping_version, country_code, city,
    validation_status, processing_status, assessments_stale,
    first_seen_at, last_seen_at)
VALUES ('379f716d-7734-44a5-bc64-9c08a55aa10b', '9abac3cc382d2f256b2d57fb682fa214', '携程集团', '携程集团',
    'https://www.trip.com',
    'trip.com',
    '携程集团总部位于上海，是综合在线旅行服务平台，业务涵盖机票、酒店、火车票、度假、商旅管理及目的地服务，为个人与企业客户提供一站式出行预订和差旅服务。', 'TMC', 'EA', 'v3.2-seed',
    'CN',
    '上海',
    'valid', 'scored', false, clock_timestamp(), clock_timestamp())
ON CONFLICT (candidate_id) DO UPDATE SET
    company_name = EXCLUDED.company_name, website = EXCLUDED.website,
    company_intro = EXCLUDED.company_intro, industry_code = EXCLUDED.industry_code,
    region_code = EXCLUDED.region_code, country_code = EXCLUDED.country_code,
    city = EXCLUDED.city, updated_at = clock_timestamp();
INSERT INTO ltc.lead_enrichment_run (
    enrichment_run_id, candidate_id, version_no, status,
    scene_code, rule_version, prompt_version, config_checksum, model_name,
    d1_payload, d2_payload, d3_payload, d4_payload,
    output_hash, current_job_id, is_current, created_at, completed_at)
VALUES ('2e5cade4-8c63-5cb5-8a0e-a07edf4d1682', '379f716d-7734-44a5-bc64-9c08a55aa10b', 1, 'completed', 'S1', 'v3.2-seed', 'v3.2-seed',
    '0000000000000000000000000000000000000000000000000000000000000000', 'gpt-5.5',
    '{"score":40.0}'::jsonb, '{"score":30.0}'::jsonb,
    '{"score":20.0}'::jsonb, '{"score":10.0}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    '00000000-0000-4000-8000-000000000000', true, clock_timestamp(), clock_timestamp())
ON CONFLICT (enrichment_run_id) DO NOTHING;
INSERT INTO ltc.lead_icp_assessment (
    icp_assessment_id, candidate_id, enrichment_run_id, version_no,
    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
    d1_score, d2_score, d3_score, d4_score, total_score, grade,
    hard_gate_passed, confidence, score_breakdown, explanations, evidence_sources,
    is_current, scored_at)
VALUES ('733a0f1f-1378-5b1c-ade5-d1308dac89f1', '379f716d-7734-44a5-bc64-9c08a55aa10b', '2e5cade4-8c63-5cb5-8a0e-a07edf4d1682', 1, 'S1', 'v3.2-seed',
    '{"rule_version": "v3.2-seed", "scene": "S1"}'::jsonb,
    '0000000000000000000000000000000000000000000000000000000000000000',
    'v3.2-seed', 40.0, 30.0, 20.0, 10.0, 100.0, 'A',
    true, 0.85, '{"d1": 40.0, "d2": 30.0, "d3": 20.0, "d4": 10.0}'::jsonb, '{"d1": "seed", "d2": "seed", "d3": "seed", "d4": "seed"}'::jsonb, '{}'::jsonb,
    true, clock_timestamp())
ON CONFLICT (icp_assessment_id) DO NOTHING;
INSERT INTO ltc.customer_scale_assessment (
    scale_assessment_id, candidate_id, source_enrichment_run_id,
    version_no, rule_version, prompt_version,
    d1_scale_score, d2_commercial_score, d3_coverage_score,
    total_score, computed_tier, effective_tier,
    decision_source, assessment_payload, is_current, assessed_at)
VALUES ('fd9326e6-32b1-58ef-b5dc-58c5a4772126', '379f716d-7734-44a5-bc64-9c08a55aa10b', '2e5cade4-8c63-5cb5-8a0e-a07edf4d1682', 1, 'v3.2-seed', 'v3.2-seed',
    40.0, 35.0, 25.0, 100.0,
    'large', 'large', 'computed', '{"rule_name": "\u5ba2\u6237\u4f53\u91cf\u91cf\u5316\u5206\u5c42\u89c4\u5219", "rule_version": "v3.2-seed", "total_score": 100, "customer_tier_level": "large", "dimensions": [{"dimension": "D1", "score": 40.0, "label": "\u89c4\u6a21\u6570\u91cf"}, {"dimension": "D2", "score": 35.0, "label": "\u8425\u6536/\u5546\u4e1a\u4ef7\u503c"}, {"dimension": "D3", "score": 25.0, "label": "\u5168\u7403\u8986\u76d6"}]}'::jsonb, true, clock_timestamp())
ON CONFLICT (scale_assessment_id) DO NOTHING;

COMMIT;
