-- Once a candidate has a country, the promoted company and sales-lead pool
-- must use the same country/region snapshot instead of showing confirmation.
-- Keep this additive and idempotent because deployed migrations are immutable.

UPDATE ltc.company c
SET country_code = COALESCE(NULLIF(c.country_code, ''), lc.country_code),
    region_code = COALESCE(NULLIF(c.region_code, ''), lc.region_code, rc.region_code),
    region_mapping_version = COALESCE(
        NULLIF(c.region_mapping_version, ''),
        NULLIF(lc.region_mapping_version, ''),
        rc.data_version,
        'v3.6.0'
    ),
    updated_at = clock_timestamp()
FROM ltc.sales_lead sl
JOIN ltc.lead_candidate lc ON lc.candidate_id = sl.source_candidate_id
LEFT JOIN ltc.ref_region_country rc ON rc.country_code = lc.country_code
WHERE c.company_id = sl.company_id
  AND (
      (NULLIF(c.country_code, '') IS NULL AND NULLIF(lc.country_code, '') IS NOT NULL)
      OR (NULLIF(c.region_code, '') IS NULL AND COALESCE(NULLIF(lc.region_code, ''), rc.region_code) IS NOT NULL)
  );

UPDATE ltc.sales_lead sl
SET pool_region_code = COALESCE(
        NULLIF(sl.pool_region_code, ''),
        NULLIF(c.region_code, ''),
        NULLIF(lc.region_code, ''),
        (SELECT rc.region_code
         FROM ltc.ref_region_country rc
         WHERE rc.country_code = COALESCE(NULLIF(c.country_code, ''), lc.country_code)
         LIMIT 1)
    ),
    pool_region_mapping_version = COALESCE(
        NULLIF(sl.pool_region_mapping_version, ''),
        NULLIF(lc.region_mapping_version, ''),
        (SELECT rc.data_version
         FROM ltc.ref_region_country rc
         WHERE rc.country_code = COALESCE(NULLIF(c.country_code, ''), lc.country_code)
         LIMIT 1),
        'v3.6.0'
    ),
    data_completion_pool = CASE
        WHEN sl.data_completion_pool = 'region_unknown'
             AND COALESCE(
                 NULLIF(c.region_code, ''),
                 NULLIF(lc.region_code, ''),
                 (SELECT rc.region_code
                  FROM ltc.ref_region_country rc
                  WHERE rc.country_code = COALESCE(NULLIF(c.country_code, ''), lc.country_code)
                  LIMIT 1)
             ) IS NOT NULL
          THEN NULL
        ELSE sl.data_completion_pool
    END,
    updated_at = clock_timestamp()
FROM ltc.company c, ltc.lead_candidate lc
WHERE c.company_id = sl.company_id
  AND lc.candidate_id = sl.source_candidate_id
  AND NULLIF(sl.pool_region_code, '') IS NULL
  AND COALESCE(
      NULLIF(c.region_code, ''),
      NULLIF(lc.region_code, ''),
      (SELECT rc.region_code
       FROM ltc.ref_region_country rc
       WHERE rc.country_code = COALESCE(NULLIF(c.country_code, ''), lc.country_code)
       LIMIT 1)
  ) IS NOT NULL;
