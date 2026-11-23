"""Auto-release overdue claimed leads (PRD §6.18).

Scheduled job: crm.auto_release_overdue.v1 (hourly scan)

For each claimed lead where first_touch_at IS NULL and the active assignment's
assigned_at exceeds 3 business days, release the lead back to claimable pool
and end the assignment with reason_code=auto_release_no_first_touch.

Each lead is processed in an independent short transaction; failure of one
does not affect others.
"""

from __future__ import annotations

import logging
import json as _json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from ltc.platform.db import PostgresDatabase

_logger = logging.getLogger(__name__)
_SCOPE = "crm_auto_release_overdue"
TZ = ZoneInfo("Asia/Shanghai")


def _business_days_ago(days: int, now: datetime) -> datetime:
    """Return the cutoff timestamp: `days` business days before `now` in Asia/Shanghai."""
    local = now.astimezone(TZ)
    remaining = days
    while remaining:
        local -= timedelta(days=1)
        if local.weekday() < 5:  # Mon=0 .. Fri=4
            remaining -= 1
    return local.astimezone(timezone.utc)


def _is_business_hour(dt: datetime) -> bool:
    """Avoid scanning at midnight when no leads would be overdue yet."""
    local = dt.astimezone(TZ)
    return local.weekday() < 5 and 8 <= local.hour < 22


def run_auto_release(database: PostgresDatabase, dry_run: bool = False) -> dict:
    """Scan and release overdue leads. Returns summary counts.

    Called by an external scheduler (cron, APScheduler, or a standalone
    worker process). In development, this can also be invoked via an admin
    CLI or a FastAPI background-task endpoint.
    """
    now = datetime.now(timezone.utc)
    cutoff = _business_days_ago(3, now)
    released: list[str] = []
    failures: list[str] = []

    with database.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT sl.lead_id, sl.company_id, sl.current_owner_user_id,
                          sl.version, sl.pipeline_stage,
                          la.assignment_id, la.assigned_at
                   FROM ltc.sales_lead sl
                   JOIN ltc.lead_assignment la
                     ON la.lead_id = sl.lead_id AND la.status = 'active'
                   WHERE sl.allocation_status = 'claimed'
                     AND sl.first_touch_at IS NULL
                     AND la.handover_pending = false
                     AND la.assigned_at <= %s
                   ORDER BY sl.lead_id""",
                (cutoff,),
            )
            overdue = cur.fetchall()

    if not overdue:
        return {"released": [], "failed": [], "scanned": 0}

    for lead in overdue:
        if dry_run:
            released.append(str(lead["lead_id"]))
            continue
        try:
            _release_one(database, lead, now)
            released.append(str(lead["lead_id"]))
        except Exception as exc:
            _logger.warning("auto_release failed for lead %s: %s", lead["lead_id"], exc)
            failures.append(str(lead["lead_id"]))

    return {"released": released, "failed": failures, "scanned": len(overdue)}


def _release_one(database: PostgresDatabase, lead: dict, now: datetime) -> None:
    """Release a single overdue lead in its own transaction."""
    lead_id = lead["lead_id"]
    assignment_id = lead["assignment_id"]
    company_id = lead["company_id"]
    owner_id = lead["current_owner_user_id"]
    new_version = int(lead["version"]) + 1

    with database.transaction() as conn:
        # End the active assignment
        conn.execute(
            """UPDATE ltc.lead_assignment
               SET status = 'released',
                   reason_code = 'auto_release_no_first_touch',
                   ended_at = %s,
                   version = version + 1
               WHERE assignment_id = %s AND handover_pending = false""",
            (now, assignment_id),
        )

        # Return lead to claimable pool
        conn.execute(
            """UPDATE ltc.sales_lead
               SET allocation_status = 'claimable',
                   current_owner_user_id = NULL,
                   current_assignment_started_at = NULL,
                   sla_due_at = NULL,
                   released_reason = 'auto_release_no_first_touch',
                   version = %s,
                   updated_at = %s
               WHERE lead_id = %s""",
            (new_version, now, lead_id),
        )

        # Stage transition (system source)
        conn.execute(
            """INSERT INTO ltc.lead_stage_transition
               (company_id, lead_id, assignment_id, event_type,
                from_allocation_status, to_allocation_status,
                from_pipeline_stage, to_pipeline_stage,
                from_owner_user_id, to_owner_user_id, actor_user_id,
                source_type, reason_code, metadata, occurred_at)
               VALUES (%s,%s,%s,'release','claimed','claimable',%s,%s,
                       %s,NULL,%s,'system','auto_release_no_first_touch',
                       '{}'::jsonb,%s)""",
            (company_id, lead_id, assignment_id,
             lead["pipeline_stage"], lead["pipeline_stage"],
             owner_id, owner_id, now),
        )

        # Outbox event
        conn.execute(
            """INSERT INTO ltc.outbox_event
               (event_type, producer, aggregate_type, aggregate_id,
                aggregate_version, payload, correlation_id)
               VALUES ('crm.lead_released.v1', 'sales_crm', 'sales_lead',
                       %s, %s, %s::jsonb, %s)""",
            (lead_id, new_version,
             _json.dumps({
                 "company_id": str(company_id),
                 "lead_id": str(lead_id),
                 "assignment_id": str(assignment_id),
                 "released_by": None,
                 "reason_code": "auto_release_no_first_touch",
                 "reason_text": "Auto-release: no first touch within 3 business days",
                 "released_at": now.isoformat(),
             }),
             str(uuid4())),
        )
