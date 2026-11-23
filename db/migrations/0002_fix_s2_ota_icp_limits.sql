-- S2 is the business-travel OTA scene. Its limits follow the maintained
-- OTA rule sheet: D1=40, D2=30, D3=20, D4=10.
ALTER TABLE ltc.lead_icp_assessment
    DROP CONSTRAINT IF EXISTS ck_lead_icp_assessment_scene_limits;

ALTER TABLE ltc.lead_icp_assessment
    ADD CONSTRAINT ck_lead_icp_assessment_scene_limits CHECK (
        (
            scene_code IN ('S1', 'S2') AND
            d1_score <= 40 AND d2_score <= 30 AND d3_score <= 20 AND d4_score <= 10
        )
        OR
        (
            scene_code = 'S3' AND
            d1_score <= 35 AND d2_score <= 25 AND d3_score <= 25 AND d4_score <= 15
        )
    );
