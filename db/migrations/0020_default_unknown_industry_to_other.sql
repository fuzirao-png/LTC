-- Industry is a required display dimension for lead pools. Historical rows
-- may still contain null/blank or legacy pending-confirmation placeholders.
UPDATE ltc.lead_candidate
SET industry_code = 'OTHER', updated_at = clock_timestamp()
WHERE industry_code IS NULL
   OR btrim(industry_code) = ''
   OR lower(btrim(industry_code)) IN ('待确认', '待补齐', '未知', 'unknown', 'n/a', '-');

UPDATE ltc.company
SET industry_code = 'OTHER', updated_at = clock_timestamp()
WHERE industry_code IS NULL
   OR btrim(industry_code) = ''
   OR lower(btrim(industry_code)) IN ('待确认', '待补齐', '未知', 'unknown', 'n/a', '-');

UPDATE ltc.lead_candidate c
SET region_code = rc.region_code, region_mapping_version = rc.data_version,
    updated_at = clock_timestamp()
FROM ltc.ref_region_country rc
WHERE c.region_code IS NULL
  AND c.country_code = rc.country_code;

UPDATE ltc.company c
SET region_code = rc.region_code, updated_at = clock_timestamp()
FROM ltc.ref_region_country rc
WHERE c.region_code IS NULL
  AND c.country_code = rc.country_code;
