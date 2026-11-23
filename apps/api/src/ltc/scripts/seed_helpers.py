from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from datetime import datetime, timezone


NA_LARGE_DEMO_COMPANIES = (
    "TechVentures Inc",
    "Engine",
    "Navan",
    "FCM Travel Americas",
    "Christopherson Business Travel",
    "Ramp",
)


class QueryResult(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...


class SeedConnection(Protocol):
    def execute(self, query: str, params: tuple[object, ...]) -> QueryResult: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...


def promote_grade_a_large_candidates(connection: SeedConnection, actor_id: UUID) -> list[str]:
    """Promote eligible Grade A/large candidates into the regional MA pool."""
    now = datetime.now(timezone.utc)
    candidates = connection.execute(
        """SELECT lc.candidate_id, lc.company_name, lc.normalized_company_name,
                  lc.website, lc.country_code, lc.region_code, lc.region_mapping_version,
                  lc.city, lc.industry_code, lc.company_intro, lc.employee_count,
                  icp.icp_assessment_id, scale.scale_assessment_id
           FROM ltc.lead_candidate lc
           JOIN LATERAL (
               SELECT ia.icp_assessment_id, ia.grade, ia.hard_gate_passed
               FROM ltc.lead_icp_assessment ia
               WHERE ia.candidate_id = lc.candidate_id AND ia.is_current = true
               ORDER BY ia.scored_at DESC LIMIT 1
           ) icp ON true
           JOIN LATERAL (
               SELECT sa.scale_assessment_id, sa.effective_tier, sa.computed_tier
               FROM ltc.customer_scale_assessment sa
               WHERE sa.candidate_id = lc.candidate_id AND sa.is_current = true
               ORDER BY sa.assessed_at DESC LIMIT 1
           ) scale ON true
           WHERE (
                 lc.processing_status IN ('scored', 'eligible')
                 OR (
                   lc.processing_status = 'promoted'
                   AND EXISTS (
                     SELECT 1 FROM ltc.sales_lead old_sl
                     WHERE old_sl.source_candidate_id = lc.candidate_id
                       AND (
                         old_sl.required_sales_tier <> 'MA'
                         OR old_sl.pool_region_code IS DISTINCT FROM lc.region_code
                         OR old_sl.data_completion_pool IS NOT NULL
                       )
                   )
                 )
               )
             AND lc.validation_status = 'valid'
             AND lc.assessments_stale = false
             AND lc.region_code IS NOT NULL
             AND icp.grade = 'A'
             AND icp.hard_gate_passed = true
             AND COALESCE(scale.effective_tier, scale.computed_tier) = 'large'
           ORDER BY lower(lc.company_name), lc.candidate_id"""
    ).fetchall()
    promoted_names: list[str] = []

    for candidate in candidates:
        (
            candidate_id, company_name, normalized_company_name, website,
            country_code, region_code, region_mapping_version, city,
            industry_code, company_intro, employee_count,
            icp_assessment_id, scale_assessment_id,
        ) = candidate

        existing_lead = connection.execute(
            """SELECT lead_id, company_id, required_sales_tier, pool_region_code,
                      data_completion_pool
               FROM ltc.sales_lead
               WHERE source_candidate_id = %s
                 AND allocation_status IN ('claimable', 'claimed')
                 AND pipeline_stage NOT IN ('won', 'lost') LIMIT 1""",
            (candidate_id,),
        ).fetchone()
        promotion_result = "reused_open_lead"
        if existing_lead is not None:
            lead_id, company_id, existing_tier, existing_region, existing_completion_pool = existing_lead
            if (existing_tier, existing_region, existing_completion_pool) != ("MA", region_code, None):
                connection.execute(
                    """UPDATE ltc.sales_lead
                       SET adopted_icp_assessment_id=%s, adopted_scale_assessment_id=%s,
                           required_sales_tier='MA', pool_region_code=%s,
                           pool_region_mapping_version=%s, data_completion_pool=NULL,
                           allocation_rule_version='v3.6.0', version=version + 1,
                           updated_at=%s
                       WHERE lead_id=%s""",
                    (icp_assessment_id, scale_assessment_id, region_code,
                     region_mapping_version, now, lead_id),
                )
        else:
            company_row = connection.execute(
                """SELECT company_id FROM ltc.company
                   WHERE origin_candidate_id = %s OR normalized_company_name = %s
                   ORDER BY (origin_candidate_id = %s) DESC, created_at LIMIT 1""",
                (candidate_id, normalized_company_name, candidate_id),
            ).fetchone()
            if company_row is None:
                company_id = uuid4()
                connection.execute(
                    """INSERT INTO ltc.company
                       (company_id, origin_candidate_id, company_name, normalized_company_name,
                        website, country_code, region_code, region_mapping_version, city,
                        industry_code, company_intro, employee_count, lifecycle_status, created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'prospect',%s)""",
                    (company_id, candidate_id, company_name, normalized_company_name,
                     website, country_code, region_code, region_mapping_version, city,
                     industry_code, company_intro, employee_count, actor_id),
                )
            else:
                company_id = company_row[0]

            connection.execute(
                """UPDATE ltc.company
                   SET region_code=COALESCE(region_code, %s),
                       region_mapping_version=COALESCE(region_mapping_version, %s),
                       updated_at=%s
                   WHERE company_id=%s""",
                (region_code, region_mapping_version, now, company_id),
            )

            company_lead = connection.execute(
                """SELECT lead_id FROM ltc.sales_lead WHERE company_id = %s
                   AND allocation_status IN ('claimable', 'claimed')
                   AND pipeline_stage NOT IN ('won', 'lost') LIMIT 1""",
                (company_id,),
            ).fetchone()
            if company_lead is not None:
                lead_id = company_lead[0]
                promotion_result = "reused_open_lead"
                connection.execute(
                    """UPDATE ltc.sales_lead
                       SET adopted_icp_assessment_id=%s, adopted_scale_assessment_id=%s,
                           required_sales_tier='MA', pool_region_code=%s,
                           pool_region_mapping_version=%s, data_completion_pool=NULL,
                           allocation_rule_version='v3.6.0', version=version + 1,
                           updated_at=%s
                       WHERE lead_id=%s""",
                    (icp_assessment_id, scale_assessment_id, region_code,
                     region_mapping_version, now, lead_id),
                )
            else:
                lead_id = uuid4()
                promotion_result = "created_lead"
                connection.execute(
                    """INSERT INTO ltc.sales_lead
                       (lead_id, company_id, source_candidate_id,
                        adopted_icp_assessment_id, adopted_scale_assessment_id,
                        required_sales_tier, pool_region_code, pool_region_mapping_version,
                        allocation_status, pipeline_stage, dynamic_bonus_points,
                        allocation_rule_version, version, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,'MA',%s,%s,'claimable','new',0,'v3.6.0',0,%s,%s)""",
                    (lead_id, company_id, candidate_id, icp_assessment_id,
                     scale_assessment_id, region_code, region_mapping_version, now, now),
                )

        connection.execute(
            """UPDATE ltc.lead_candidate
               SET processing_status='promoted', promoted_company_id=%s, promoted_lead_id=%s,
                   selected_icp_assessment_id=%s, selected_scale_assessment_id=%s,
                   promotion_result=%s, promotion_decision_source='strategic_override',
                   promotion_override_reason='development seed: ICP A and large customer',
                   promoted_by=%s, promoted_at=%s, version=version + 1, updated_at=%s
               WHERE candidate_id=%s""",
            (company_id, lead_id, icp_assessment_id, scale_assessment_id,
             promotion_result, actor_id, now, now, candidate_id),
        )
        promoted_names.append(str(company_name))

    return promoted_names


def repair_na_large_demo_pool(connection: SeedConnection) -> list[str]:
    """Normalize the six curated NA large demo companies to one claimable lead each."""
    repaired: list[str] = []
    now = datetime.now(timezone.utc)
    for company_name in NA_LARGE_DEMO_COMPANIES:
        company_rows = connection.execute(
            """SELECT company_id FROM ltc.company
               WHERE lower(company_name) = lower(%s)
               ORDER BY created_at, company_id""",
            (company_name,),
        ).fetchall()
        if not company_rows:
            continue
        company_ids = [row[0] for row in company_rows]
        lineage = connection.execute(
            """SELECT lc.candidate_id, icp.icp_assessment_id, scale.scale_assessment_id
               FROM ltc.lead_candidate lc
               JOIN LATERAL (
                 SELECT ia.icp_assessment_id
                 FROM ltc.lead_icp_assessment ia
                 WHERE ia.candidate_id = lc.candidate_id AND ia.is_current = true
                 ORDER BY ia.scored_at DESC LIMIT 1
               ) icp ON true
               JOIN LATERAL (
                 SELECT sa.scale_assessment_id
                 FROM ltc.customer_scale_assessment sa
                 WHERE sa.candidate_id = lc.candidate_id
                   AND sa.is_current = true
                   AND sa.required_sales_tier = 'MA'
                 ORDER BY sa.assessed_at DESC LIMIT 1
               ) scale ON true
               WHERE lower(lc.company_name) = lower(%s)
                 AND lc.validation_status = 'valid'
               ORDER BY lc.last_seen_at DESC, lc.candidate_id LIMIT 1""",
            (company_name,),
        ).fetchone()
        if lineage is None:
            continue

        candidate_id, icp_id, scale_id = lineage
        canonical = connection.execute(
            """SELECT lead_id, company_id, required_sales_tier, pool_region_code,
                      data_completion_pool
               FROM ltc.sales_lead
               WHERE company_id = ANY(%s) AND allocation_status IN ('claimable', 'claimed')
               ORDER BY created_at, lead_id LIMIT 1""",
            (company_ids,),
        ).fetchone()

        if canonical is None:
            canonical_company_id = company_ids[0]
            connection.execute(
                """UPDATE ltc.company
                   SET region_code='NA', region_mapping_version=COALESCE(region_mapping_version, 'v3.6.0'),
                       updated_at=%s WHERE company_id=%s""",
                (now, canonical_company_id),
            )
            canonical_lead_id = uuid4()
            connection.execute(
                """INSERT INTO ltc.sales_lead
                   (lead_id, company_id, source_candidate_id,
                    adopted_icp_assessment_id, adopted_scale_assessment_id,
                    required_sales_tier, pool_region_code, pool_region_mapping_version,
                    allocation_status, pipeline_stage, dynamic_bonus_points,
                    allocation_rule_version, version, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,'MA','NA','v3.6.0','claimable','new',0,'v3.6.0',0,%s,%s)""",
                (canonical_lead_id, canonical_company_id, candidate_id, icp_id, scale_id, now, now),
            )
            canonical = (canonical_lead_id, canonical_company_id, None, None, None)
        canonical_lead_id, canonical_company_id, existing_tier, existing_region, existing_pool = canonical

        if (existing_tier, existing_region, existing_pool) != ('MA', 'NA', None):
            connection.execute(
                """UPDATE ltc.sales_lead
                   SET source_candidate_id=%s,
                       adopted_icp_assessment_id=%s, adopted_scale_assessment_id=%s,
                       required_sales_tier='MA', pool_region_code='NA',
                       pool_region_mapping_version='v3.6.0', data_completion_pool=NULL,
                       allocation_rule_version='v3.6.0', version=version + 1,
                       updated_at=%s
                   WHERE lead_id=%s""",
                (candidate_id, icp_id, scale_id, now, canonical_lead_id),
            )

        connection.execute(
            """UPDATE ltc.company
               SET region_code='NA', region_mapping_version=COALESCE(region_mapping_version, 'v3.6.0'),
                   updated_at=%s WHERE lower(company_name)=lower(%s)""",
            (now, company_name),
        )
        connection.execute(
            """UPDATE ltc.sales_lead
               SET allocation_status='archived', released_reason='development seed: duplicate legacy pool row',
                   updated_at=%s
               WHERE company_id = ANY(%s) AND lead_id <> %s
                 AND allocation_status IN ('claimable', 'claimed')""",
            (now, company_ids, canonical_lead_id),
        )
        repaired.append(company_name)
    return repaired


def upsert_demo_user(
    connection: SeedConnection,
    hasher: PasswordHasher,
    user: tuple[object, ...],
) -> bool:
    username, password, display_name, email, account_type, sales_tier, region_code, capacity_limit = user
    existing = connection.execute(
        "SELECT status FROM ltc.user_account WHERE lower(username) = lower(%s)",
        (username,),
    ).fetchone()
    if existing is not None and existing[0] == "departed":
        return False

    connection.execute(
        """INSERT INTO ltc.user_account
           (username, password_hash, display_name, email, account_type, sales_tier, region_code, capacity_limit)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (lower(username)) DO UPDATE SET
             password_hash=EXCLUDED.password_hash,
             display_name=EXCLUDED.display_name,
             status='active',
             failed_login_attempts=0,
             locked_until=NULL,
             token_version=GREATEST(ltc.user_account.token_version + 1, 1)""",
        (username, hasher.hash(str(password)), display_name, email, account_type, sales_tier, region_code, capacity_limit),
    )
    return True
