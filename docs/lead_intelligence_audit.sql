-- Read-only audit for the latest lead-intelligence search run.
-- Run the whole file in a PostgreSQL query window.

-- 1. All lead-intelligence tables and their current row counts.
SELECT 'lead_search_run' AS table_name, COUNT(*) AS row_count FROM ltc.lead_search_run
UNION ALL SELECT 'search_provider_execution', COUNT(*) FROM ltc.search_provider_execution
UNION ALL SELECT 'search_evidence', COUNT(*) FROM ltc.search_evidence
UNION ALL SELECT 'lead_candidate', COUNT(*) FROM ltc.lead_candidate
UNION ALL SELECT 'candidate_observation', COUNT(*) FROM ltc.candidate_observation
UNION ALL SELECT 'candidate_evidence', COUNT(*) FROM ltc.candidate_evidence
UNION ALL SELECT 'candidate_contact', COUNT(*) FROM ltc.candidate_contact
UNION ALL SELECT 'lead_enrichment_run', COUNT(*) FROM ltc.lead_enrichment_run
UNION ALL SELECT 'enrichment_evidence', COUNT(*) FROM ltc.enrichment_evidence
UNION ALL SELECT 'lead_icp_assessment', COUNT(*) FROM ltc.lead_icp_assessment
UNION ALL SELECT 'customer_scale_assessment', COUNT(*) FROM ltc.customer_scale_assessment
UNION ALL SELECT 'lead_negative_filter_result', COUNT(*) FROM ltc.lead_negative_filter_result
ORDER BY table_name;

-- 2. Lifecycle and counters for the latest run.
SELECT
    r.search_run_id,
    r.query_text,
    r.status,
    r.target_count,
    r.evidence_count,
    r.candidate_count,
    r.enriched_count,
    r.scored_count,
    r.last_error_message,
    r.started_at,
    r.completed_at
FROM ltc.lead_search_run r
ORDER BY r.created_at DESC
LIMIT 1;

-- 3. Provider calls, including success/error state and result counts.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
)
SELECT
    p.provider_code,
    p.provider_operation,
    p.status,
    p.result_count,
    p.error_message,
    p.request_payload,
    p.started_at,
    p.completed_at
FROM ltc.search_provider_execution p
JOIN target t ON t.search_run_id = p.search_run_id
ORDER BY p.started_at;

-- 4. Every Exa/search evidence row retained for the latest run.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
)
SELECT
    e.evidence_id,
    e.search_phase,
    e.provider_code,
    e.query_text,
    e.title,
    e.url,
    e.snippet,
    e.raw_payload,
    e.fetched_at
FROM ltc.search_evidence e
JOIN target t ON t.search_run_id = e.search_run_id
ORDER BY e.fetched_at, e.evidence_id;

-- 5. Canonical company fields alongside all raw AI/provider fields.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
)
SELECT
    c.candidate_id,
    c.company_name,
    c.legal_name,
    c.website,
    c.company_intro,
    c.industry_code,
    c.employee_count,
    c.region_code,
    c.country_code,
    c.city,
    c.validation_status,
    c.processing_status,
    o.company_snapshot,
    o.raw_extraction_payload,
    o.contact_groups_payload,
    o.observed_at
FROM ltc.candidate_observation o
JOIN target t ON t.search_run_id = o.search_run_id
JOIN ltc.lead_candidate c ON c.candidate_id = o.candidate_id
ORDER BY o.observed_at;

-- 6. Field completeness in the canonical candidate table for this run.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
), candidates AS (
    SELECT DISTINCT c.*
    FROM ltc.lead_candidate c
    JOIN ltc.candidate_observation o ON o.candidate_id = c.candidate_id
    JOIN target t ON t.search_run_id = o.search_run_id
)
SELECT
    COUNT(*) AS candidate_count,
    COUNT(*) FILTER (WHERE NULLIF(company_name, '') IS NOT NULL) AS company_name_present,
    COUNT(*) FILTER (WHERE NULLIF(legal_name, '') IS NOT NULL) AS legal_name_present,
    COUNT(*) FILTER (WHERE NULLIF(website, '') IS NOT NULL) AS website_present,
    COUNT(*) FILTER (WHERE NULLIF(company_intro, '') IS NOT NULL) AS company_intro_present,
    COUNT(*) FILTER (WHERE industry_code IS NOT NULL) AS industry_code_present,
    COUNT(*) FILTER (WHERE employee_count IS NOT NULL) AS employee_count_present,
    COUNT(*) FILTER (WHERE region_code IS NOT NULL) AS region_code_present,
    COUNT(*) FILTER (WHERE country_code IS NOT NULL) AS country_code_present,
    COUNT(*) FILTER (WHERE NULLIF(city, '') IS NOT NULL) AS city_present
FROM candidates;

-- 7. Contacts written from the LinkedIn/Apify result and their raw source data.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
)
SELECT
    c.company_name,
    cc.full_name,
    cc.title,
    cc.department,
    cc.relationship_role,
    cc.priority,
    cc.email,
    cc.phone,
    cc.linkedin_url,
    cc.source_payload,
    cc.status
FROM ltc.candidate_contact cc
JOIN ltc.lead_candidate c ON c.candidate_id = cc.candidate_id
JOIN ltc.candidate_observation o ON o.observation_id = cc.observation_id
JOIN target t ON t.search_run_id = o.search_run_id
ORDER BY c.company_name, cc.last_seen_at DESC;

-- 8. Enrichment, ICP scoring, scale scoring, negative filters, and evidence links.
WITH target AS (
    SELECT search_run_id FROM ltc.lead_search_run ORDER BY created_at DESC LIMIT 1
)
SELECT
    c.company_name,
    er.enrichment_run_id,
    er.status AS enrichment_status,
    er.d1_payload,
    er.d2_payload,
    er.d3_payload,
    er.d4_payload,
    ia.d1_score,
    ia.d2_score,
    ia.d3_score,
    ia.d4_score,
    ia.total_score AS icp_total_score,
    ia.grade AS icp_grade,
    ia.explanations AS icp_explanations,
    sa.d1_scale_score,
    sa.d2_commercial_score,
    sa.d3_coverage_score,
    sa.total_score AS scale_total_score,
    sa.effective_tier,
    nf.verdict AS negative_filter_verdict,
    nf.payload AS negative_filter_payload,
    (SELECT COUNT(*) FROM ltc.enrichment_evidence ee WHERE ee.enrichment_run_id = er.enrichment_run_id) AS linked_evidence_count
FROM ltc.lead_enrichment_run er
JOIN ltc.lead_candidate c ON c.candidate_id = er.candidate_id
JOIN ltc.candidate_observation o ON o.candidate_id = c.candidate_id
JOIN target t ON t.search_run_id = o.search_run_id
LEFT JOIN ltc.lead_icp_assessment ia ON ia.enrichment_run_id = er.enrichment_run_id AND ia.is_current
LEFT JOIN ltc.customer_scale_assessment sa ON sa.source_enrichment_run_id = er.enrichment_run_id AND sa.is_current
LEFT JOIN ltc.lead_negative_filter_result nf ON nf.enrichment_run_id = er.enrichment_run_id
WHERE er.is_current
ORDER BY er.completed_at DESC;
