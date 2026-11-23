-- Customer Analysis previously recomputed a separate six-dimension compatibility
-- score, overwrote the adopted four-dimension ICP assessment, and redistributed
-- the new total by scene weights. Restore only rows whose current dimensions
-- match that exact corruption pattern and whose original enrichment payloads
-- still contain a complete, valid D1-D4 result.
WITH recoverable AS (
    SELECT
        assessment.icp_assessment_id,
        (enrichment.d1_payload ->> 'score')::numeric AS d1_score,
        (enrichment.d2_payload ->> 'score')::numeric AS d2_score,
        (enrichment.d3_payload ->> 'score')::numeric AS d3_score,
        (enrichment.d4_payload ->> 'score')::numeric AS d4_score
    FROM ltc.lead_icp_assessment assessment
    JOIN ltc.lead_enrichment_run enrichment
      ON enrichment.enrichment_run_id = assessment.enrichment_run_id
    WHERE jsonb_typeof(enrichment.d1_payload -> 'score') = 'number'
      AND jsonb_typeof(enrichment.d2_payload -> 'score') = 'number'
      AND jsonb_typeof(enrichment.d3_payload -> 'score') = 'number'
      AND jsonb_typeof(enrichment.d4_payload -> 'score') = 'number'
      AND abs(assessment.d1_score - round(assessment.total_score * CASE WHEN assessment.scene_code = 'S1' THEN 0.40 ELSE 0.35 END, 2)) <= 0.01
      AND abs(assessment.d2_score - round(assessment.total_score * CASE WHEN assessment.scene_code = 'S1' THEN 0.30 ELSE 0.25 END, 2)) <= 0.01
      AND abs(assessment.d3_score - round(assessment.total_score * CASE WHEN assessment.scene_code = 'S1' THEN 0.20 ELSE 0.25 END, 2)) <= 0.01
      AND abs(assessment.d4_score - (assessment.total_score - assessment.d1_score - assessment.d2_score - assessment.d3_score)) <= 0.01
      AND (
          assessment.score_breakdown ?& ARRAY['industry','scale','scenario','budget','decision_chain','behavior']
          OR assessment.d1_score IS DISTINCT FROM (enrichment.d1_payload ->> 'score')::numeric
          OR assessment.d2_score IS DISTINCT FROM (enrichment.d2_payload ->> 'score')::numeric
          OR assessment.d3_score IS DISTINCT FROM (enrichment.d3_payload ->> 'score')::numeric
          OR assessment.d4_score IS DISTINCT FROM (enrichment.d4_payload ->> 'score')::numeric
      )
), valid_recovery AS (
    SELECT *
    FROM recoverable
    WHERE d1_score >= 0 AND d2_score >= 0 AND d3_score >= 0 AND d4_score >= 0
      AND d1_score + d2_score + d3_score + d4_score <= 100
      AND (
          EXISTS (
              SELECT 1 FROM ltc.lead_icp_assessment current_assessment
              WHERE current_assessment.icp_assessment_id = recoverable.icp_assessment_id
                AND current_assessment.scene_code IN ('S1', 'S2')
                AND recoverable.d1_score <= 40 AND recoverable.d2_score <= 30
                AND recoverable.d3_score <= 20 AND recoverable.d4_score <= 10
          )
          OR EXISTS (
              SELECT 1 FROM ltc.lead_icp_assessment current_assessment
              WHERE current_assessment.icp_assessment_id = recoverable.icp_assessment_id
                AND current_assessment.scene_code = 'S3'
                AND recoverable.d1_score <= 35 AND recoverable.d2_score <= 25
                AND recoverable.d3_score <= 25 AND recoverable.d4_score <= 15
          )
      )
)
UPDATE ltc.lead_icp_assessment assessment
SET d1_score = recovery.d1_score,
    d2_score = recovery.d2_score,
    d3_score = recovery.d3_score,
    d4_score = recovery.d4_score,
    total_score = recovery.d1_score + recovery.d2_score + recovery.d3_score + recovery.d4_score,
    grade = CASE
        WHEN recovery.d1_score + recovery.d2_score + recovery.d3_score + recovery.d4_score >= 80 THEN 'A'
        WHEN recovery.d1_score + recovery.d2_score + recovery.d3_score + recovery.d4_score >= 60 THEN 'B'
        WHEN recovery.d1_score + recovery.d2_score + recovery.d3_score + recovery.d4_score >= 40 THEN 'C'
        ELSE 'D'
    END,
    score_breakdown = jsonb_build_object(
        'D1', recovery.d1_score,
        'D2', recovery.d2_score,
        'D3', recovery.d3_score,
        'D4', recovery.d4_score
    )
FROM valid_recovery recovery
WHERE assessment.icp_assessment_id = recovery.icp_assessment_id;

-- Adopted ICP is an immutable scoring snapshot. Customer Analysis and Customer
-- Operation may read it, but any new score must be published as a new version.
CREATE OR REPLACE FUNCTION ltc.reject_lead_icp_business_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (to_jsonb(NEW) - ARRAY['is_current', 'superseded_at'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['is_current', 'superseded_at']) THEN
        RAISE EXCEPTION 'lead ICP assessment is immutable; publish a new version';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_lead_icp_assessment_immutable
    ON ltc.lead_icp_assessment;

CREATE TRIGGER trg_lead_icp_assessment_immutable
BEFORE UPDATE ON ltc.lead_icp_assessment
FOR EACH ROW
EXECUTE FUNCTION ltc.reject_lead_icp_business_update();
