"""Sales CRM implementation of IAM's synchronous departure port."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from ltc.modules.iam.domain.ports import DepartureReleaseResult


class PostgresSalesDeparturePort:
    def release_departed_sales(
        self,
        connection: Connection,
        departed_user_id: UUID,
        departed_by: UUID,
        reason_text: str,
        request_id: str,
        occurred_at: datetime,
    ) -> DepartureReleaseResult:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT la.assignment_id, la.lead_id, sl.company_id, sl.version AS lead_version,
                       sl.allocation_status, sl.pipeline_stage, sl.current_owner_user_id,
                       sl.required_sales_tier, sl.pool_region_code, sl.pool_region_mapping_version,
                       sl.allocation_rule_version
                FROM ltc.lead_assignment la
                JOIN ltc.sales_lead sl ON sl.lead_id = la.lead_id
                WHERE la.assignee_user_id = %s AND la.status = 'active'
                ORDER BY la.lead_id
                FOR UPDATE OF la, sl
                """,
                (departed_user_id,),
            )
            assignments = list(cursor.fetchall())
            for row in assignments:
                if row["allocation_status"] != "claimed" or row["current_owner_user_id"] != departed_user_id:
                    raise RuntimeError("active assignment is inconsistent before departure")
                cursor.execute(
                    """
                    UPDATE ltc.lead_assignment
                    SET handover_pending=true, reason_code='sales_departed', reason_text=%s,
                        version=version + 1
                    WHERE assignment_id=%s AND status='active'
                    """,
                    (reason_text, row["assignment_id"]),
                )

        return DepartureReleaseResult(
            released_lead_count=0,
            returned_pools=tuple(),
            handover_lead_count=len(assignments),
        )
