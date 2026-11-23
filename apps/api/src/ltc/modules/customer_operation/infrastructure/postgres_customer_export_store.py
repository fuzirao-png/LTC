from __future__ import annotations

from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings


class PostgresCustomerExportStore:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return all([self.settings.db_host, self.settings.db_name, self.settings.db_user, self.settings.db_password])

    def _connect(self):
        return dbapi.connect(
            user=self.settings.db_user,
            host=self.settings.db_host,
            database=self.settings.db_name,
            port=self.settings.db_port,
            password=self.settings.db_password,
            timeout=30,
        )

    def export_customers(self, *, limit: int = 500, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        if not self.is_configured():
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            owner_filter = ""
            params: list[Any] = []
            if owner_user_id:
                owner_filter = """
                  AND (
                    EXISTS (
                      SELECT 1 FROM ltc.customer_operation_owner coo
                      WHERE coo.company_id = c.company_id
                        AND coo.sales_user_id = %s
                    )
                    OR EXISTS (
                      SELECT 1 FROM ltc.sales_lead owned_sl
                      WHERE owned_sl.company_id = c.company_id
                        AND owned_sl.current_owner_user_id = %s
                        AND owned_sl.allocation_status = 'claimed'
                    )
                  )
                """
                params.extend([owner_user_id, owner_user_id])
            params.append(limit)
            cur.execute(
                f"""
                SELECT
                    c.company_id,
                    c.company_name,
                    c.primary_domain,
                    c.country_code,
                    c.region_code,
                    c.industry_code,
                    c.lifecycle_status,
                    c.created_by,
                    u.display_name AS owner_display_name,
                    count(DISTINCT ct.contact_id) AS contact_count,
                    count(DISTINCT em.email_id) AS email_count,
                    count(DISTINCT m.meeting_id) AS meeting_count,
                    count(DISTINCT t.task_id) AS task_count,
                    count(DISTINCT ca.activity_id) AS activity_count,
                    max(ca.occurred_at) AS last_activity_at,
                    (
                      SELECT ua.display_name
                      FROM ltc.sales_lead owned_sl
                      JOIN ltc.user_account ua ON ua.user_id = owned_sl.current_owner_user_id
                      WHERE owned_sl.company_id = c.company_id
                        AND owned_sl.allocation_status = 'claimed'
                      ORDER BY owned_sl.updated_at DESC
                      LIMIT 1
                    ) AS owner_name
                FROM ltc.company c
                LEFT JOIN ltc.user_account u ON u.user_id = c.created_by
                LEFT JOIN ltc.contact ct ON ct.company_id = c.company_id AND ct.status <> 'archived'
                LEFT JOIN ltc.email_message em ON em.company_id = c.company_id
                LEFT JOIN ltc.meeting m ON m.company_id = c.company_id AND m.deleted_at IS NULL
                LEFT JOIN ltc.follow_up_task t ON t.company_id = c.company_id
                    LEFT JOIN ltc.customer_activity ca ON ca.company_id = c.company_id
                WHERE c.archived_at IS NULL
                  AND lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name)) <> 'exmail.weixin.qq.com'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM ltc.user_mailbox internal_mailbox
                    WHERE lower(split_part(internal_mailbox.email_address, '@', 2)) =
                          lower(COALESCE(NULLIF(c.primary_domain, ''), c.company_name))
                  )
                {owner_filter}
                GROUP BY c.company_id, u.display_name
                ORDER BY max(ca.occurred_at) DESC NULLS LAST, c.created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        return [
            {
                "companyId": str(row[0]),
                "companyName": str(row[1]),
                "primaryDomain": row[2],
                "countryCode": row[3],
                "regionCode": row[4],
                "industryCode": row[5],
                "lifecycleStatus": row[6],
                "createdBy": str(row[7] or ""),
                "ownerName": str(row[15] or row[8] or row[7] or ""),
                "assigned_to": str(row[15] or row[8] or row[7] or ""),
                "contactCount": int(row[9] or 0),
                "emailCount": int(row[10] or 0),
                "meetingCount": int(row[11] or 0),
                "taskCount": int(row[12] or 0),
                "activityCount": int(row[13] or 0),
                "lastActivityAt": row[14].isoformat() if row[14] else None,
            }
            for row in rows
        ]



