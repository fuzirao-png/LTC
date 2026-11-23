"""Read-only Sales CRM queries for the claimable pool."""

from __future__ import annotations

from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


class PostgresSalesPoolRepository:
    def list_claimable_for_sales(
        self,
        connection: Connection,
        user_id: UUID,
        region_code: str,
        sales_tier: str,
        lead_cursor: UUID | None,
        limit: int,
    ) -> list[dict[str, object]]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT pool.lead_id, pool.company_id, pool.company_name,
                       company.website, company.company_intro, company.industry_code,
                       company.country_code, company.city,
                       icp.total_score AS icp_score, icp.grade AS icp_grade,
                       pool.required_sales_tier, pool.pool_region_code,
                       pool.allocation_status, pool.pipeline_stage,
                       pool.sla_due_at, pool.current_owner_user_id, sl.updated_at, sl.version
                FROM ltc.v_sales_lead_pool pool
                JOIN ltc.sales_lead sl ON sl.lead_id = pool.lead_id
                JOIN ltc.company company ON company.company_id = pool.company_id
                LEFT JOIN ltc.lead_icp_assessment icp
                  ON icp.icp_assessment_id = pool.adopted_icp_assessment_id
                JOIN ltc.user_account actor ON actor.user_id = %s
                WHERE actor.status = 'active'
                  AND actor.account_type = 'sales'
                  AND actor.region_code = %s
                  AND actor.sales_tier = %s
                  AND pool.pool_region_code = actor.region_code
                  AND pool.required_sales_tier = actor.sales_tier
                  AND btrim(company.company_name) <> ''
                  AND lower(btrim(company.company_name)) NOT IN
                      ('待确认','待补齐','未知','unknown','n/a','-')
                  AND (
                      actor.capacity_limit IS NULL
                      OR (
                          SELECT COUNT(*)
                          FROM ltc.lead_assignment active_assignment
                          WHERE active_assignment.assignee_user_id = actor.user_id
                            AND active_assignment.status = 'active'
                      ) < actor.capacity_limit
                  )
                  AND (%s::uuid IS NULL OR pool.lead_id > %s::uuid)
                ORDER BY pool.lead_id
                LIMIT %s
                """,
                (user_id, region_code, sales_tier, lead_cursor, lead_cursor, limit),
            )
            return list(cursor.fetchall())
