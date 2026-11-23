"""PostgreSQL-backed Sales CRM automation for the Worker runtime."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import asyncio
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


DYNAMIC_INTENT_RULE_VERSION = "dynamic-intent-2026-07-v1"
INTENT_BONUS_RULES = {
    "product_question": ("I2", 5),
    "pricing": ("I3", 8),
    "interested": ("I4", 10),
}


def database_dsn() -> str:
    host = os.getenv("LTC_DB_HOST", "postgres")
    port = os.getenv("LTC_DB_PORT", "5432")
    name = os.getenv("LTC_DB_NAME", "ltc")
    user = os.getenv("LTC_DB_USER", "ltc")
    password = os.getenv("LTC_DB_PASSWORD", "ltc_local_change_me")
    sslmode = os.getenv("LTC_DB_SSLMODE", "disable")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"


class CrmWorkerDatabase:
    def __init__(self, dsn: str | None = None) -> None:
        self.pool = ConnectionPool(dsn or database_dsn(), min_size=1, max_size=5, open=False)

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            with connection.transaction():
                yield connection


class CrmOutboxConsumer:
    name = "sales_crm.pipeline_consumer.v1"

    def __init__(self, database: CrmWorkerDatabase) -> None:
        self.database = database

    def process(self, event_id: UUID) -> None:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM ltc.outbox_event WHERE event_id=%s FOR UPDATE", (event_id,))
                event = cursor.fetchone()
                if not event or event["status"] in {"published", "dead"}:
                    return
                if self._completed(cursor, event_id):
                    cursor.execute(
                        "UPDATE ltc.outbox_event SET status='published', published_at=clock_timestamp() WHERE event_id=%s",
                        (event_id,),
                    )
                    return
                event_type = event["event_type"]
                if event_type in {
                    "engagement.email_sent.v1",
                    "engagement.email_replied.v1",
                    "engagement.meeting_analyzed.v1",
                }:
                    self._advance_pipeline(cursor, event)
                if event_type in {
                    "engagement.email_opened.v1", "engagement.email_clicked.v1", "engagement.email_replied.v1",
                    "engagement.meeting_analyzed.v1",
                }:
                    self._apply_dynamic_bonus(cursor, event)
                if event_type == "crm.dynamic_intent_bonus_applied.v1":
                    self._create_a4_follow_up(cursor, event)
                self._mark_completed(cursor, event_id)
                cursor.execute(
                    "UPDATE ltc.outbox_event SET status='published', published_at=clock_timestamp() WHERE event_id=%s",
                    (event_id,),
                )

    def process_outbox_event(self, event_id: UUID) -> None:
        """Compatibility name used by the CRM integration harness."""
        self.process(event_id)

    def _completed(self, cursor: Any, event_id: UUID) -> bool:
        cursor.execute(
            """SELECT state FROM ltc.idempotency_record
               WHERE scope='outbox_consume' AND principal_type='event_consumer'
                 AND principal_id=%s AND idempotency_key=%s FOR UPDATE""",
            (str(event_id), self.name),
        )
        row = cursor.fetchone()
        return bool(row and row["state"] == "completed")

    def _mark_completed(self, cursor: Any, event_id: UUID) -> None:
        request_hash = hashlib.sha256(f"{event_id}:{self.name}".encode()).hexdigest()
        cursor.execute(
            """INSERT INTO ltc.idempotency_record
               (scope, principal_type, principal_id, idempotency_key, request_hash,
                state, response_status, response_body, expires_at)
               VALUES ('outbox_consume','event_consumer',%s,%s,%s,'completed',200,'{}'::jsonb,
                       clock_timestamp() + interval '30 days')
               ON CONFLICT (scope, principal_type, principal_id, idempotency_key)
               DO UPDATE SET state='completed', updated_at=clock_timestamp()""",
            (str(event_id), self.name, request_hash),
        )

    def _source(self, cursor: Any, event: dict[str, Any]) -> tuple[UUID, UUID, UUID, str] | None:
        payload = event["payload"]
        try:
            company_id = UUID(str(payload["company_id"]))
            lead_id = UUID(str(payload["lead_id"]))
        except (KeyError, TypeError, ValueError):
            return None
        is_meeting = event["event_type"] == "engagement.meeting_analyzed.v1"
        source_key = "meeting_id" if is_meeting else "email_id"
        try:
            source_id = UUID(str(payload[source_key]))
        except (KeyError, TypeError, ValueError):
            return None
        table = "ltc.meeting" if is_meeting else "ltc.email_message"
        columns = "company_id, lead_id" if is_meeting else "company_id, lead_id, contact_id"
        cursor.execute(f"SELECT {columns} FROM {table} WHERE {source_key}=%s", (source_id,))
        row = cursor.fetchone()
        if not row or row["company_id"] != company_id or row["lead_id"] != lead_id:
            return None
        if not is_meeting:
            contact_id = event["payload"].get("contact_id")
            if contact_id and row["contact_id"] != UUID(str(contact_id)):
                return None
        return company_id, lead_id, source_id, "meeting" if is_meeting else "email"

    @staticmethod
    def _occurred_at(payload: dict[str, Any]) -> datetime:
        value = (
            payload.get("replied_at")
            or payload.get("sent_at")
            or payload.get("completed_at")
            or payload.get("occurred_at")
        )
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _advance_pipeline(self, cursor: Any, event: dict[str, Any]) -> None:
        source = self._source(cursor, event)
        if not source:
            return
        company_id, lead_id, source_id, source_type = source
        target = {
            "engagement.email_replied.v1": "engaged",
            "engagement.meeting_analyzed.v1": "meeting",
        }.get(event["event_type"], "contacted")
        cursor.execute("SELECT * FROM ltc.sales_lead WHERE lead_id=%s FOR UPDATE", (lead_id,))
        lead = cursor.fetchone()
        if not lead or lead["company_id"] != company_id or lead["allocation_status"] != "claimed":
            return
        ranks = {"new": 0, "contacted": 1, "engaged": 2, "meeting": 3, "proposal": 4, "won": 5, "lost": 5, "dormant": 0}
        if ranks[target] <= ranks[lead["pipeline_stage"]]:
            return
        occurred_at = self._occurred_at(event["payload"])
        transition_type = "first_touch" if target == "contacted" and lead["first_touch_at"] is None else "stage_change"
        cursor.execute(
            """INSERT INTO ltc.lead_stage_transition
               (company_id, lead_id, event_type, from_allocation_status, to_allocation_status,
                from_pipeline_stage, to_pipeline_stage, from_owner_user_id, to_owner_user_id,
               source_type, source_email_id, source_meeting_id, occurred_at, metadata)
               VALUES (%s,%s,%s,'claimed','claimed',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT DO NOTHING RETURNING transition_id""",
            (company_id, lead_id, transition_type, lead["pipeline_stage"], target,
             lead["current_owner_user_id"], lead["current_owner_user_id"], source_type,
             source_id if source_type == "email" else None,
             source_id if source_type == "meeting" else None,
             occurred_at, json.dumps({"event_id": str(event["event_id"])})),
        )
        transition = cursor.fetchone()
        if transition is None:
            return
        cursor.execute(
            """UPDATE ltc.sales_lead SET pipeline_stage=%s,
               first_touch_at=CASE WHEN %s='contacted' THEN COALESCE(first_touch_at,%s) ELSE first_touch_at END,
               sla_due_at=CASE WHEN %s='contacted' THEN NULL ELSE sla_due_at END,
               last_activity_at=GREATEST(COALESCE(last_activity_at,%s),%s), version=version+1,
               updated_at=clock_timestamp() WHERE lead_id=%s RETURNING version""",
            (target, target, occurred_at, target, occurred_at, occurred_at, lead_id),
        )
        version = cursor.fetchone()["version"]
        if transition_type == "first_touch":
            cursor.execute(
                "UPDATE ltc.lead_assignment SET first_touch_at=COALESCE(first_touch_at,%s), version=version+1 WHERE lead_id=%s AND status='active'",
                (occurred_at, lead_id),
            )
        cursor.execute(
            """INSERT INTO ltc.outbox_event
               (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id, causation_id)
               VALUES ('crm.pipeline_changed.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s,%s)""",
            (lead_id, version, json.dumps({"company_id": str(company_id), "lead_id": str(lead_id), "transition_id": str(transition["transition_id"]), "from_stage": lead["pipeline_stage"], "to_stage": target, "source_type": source_type, "source_resource_id": str(source_id), "occurred_at": occurred_at.isoformat()}), event.get("correlation_id") or uuid4(), event["event_id"]),
        )

    def _apply_dynamic_bonus(self, cursor: Any, event: dict[str, Any]) -> None:
        source = self._source(cursor, event)
        if not source:
            return
        company_id, lead_id, source_id, source_type = source
        if event["event_type"] in {"engagement.email_opened.v1", "engagement.email_clicked.v1"}:
            bonus_type, points = "I1", 2
        elif event["event_type"] == "engagement.meeting_analyzed.v1":
            cursor.execute("SELECT summary_payload FROM ltc.meeting WHERE meeting_id=%s", (source_id,))
            meeting = cursor.fetchone()
            if not meeting or not meeting["summary_payload"]:
                return
            text = json.dumps(meeting["summary_payload"], ensure_ascii=False).lower()
            if not any(marker in text for marker in ("合作", "方案", "报价", "集成", "api", "partnership", "proposal", "pricing")):
                return
            bonus_type, points = "I4", 10
        else:
            intent = event["payload"].get("intent_level")
            if intent not in INTENT_BONUS_RULES:
                return
            bonus_type, points = INTENT_BONUS_RULES[intent]
        cursor.execute(
            """SELECT sl.*, ia.total_score AS icp_score, ia.grade AS icp_grade
               FROM ltc.sales_lead sl JOIN ltc.lead_icp_assessment ia ON ia.icp_assessment_id=sl.adopted_icp_assessment_id
               WHERE sl.lead_id=%s FOR UPDATE""",
            (lead_id,),
        )
        lead = cursor.fetchone()
        if not lead or lead["company_id"] != company_id:
            return
        cursor.execute(
            """INSERT INTO ltc.crm_dynamic_bonus_application
               (lead_id, source_type, source_resource_id, bonus_type, bonus_points, rule_version)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (source_type, source_resource_id, bonus_type) DO NOTHING
               RETURNING bonus_application_id""",
            (lead_id, source_type, source_id, bonus_type, points, DYNAMIC_INTENT_RULE_VERSION),
        )
        if cursor.fetchone() is None:
            return
        new_bonus = min(100, int(lead["dynamic_bonus_points"]) + points)
        upgraded = lead["a_segment"] != "A4" and lead["icp_grade"] == "B" and float(lead["icp_score"]) + new_bonus >= 80
        cursor.execute(
            "UPDATE ltc.sales_lead SET dynamic_bonus_points=%s, a_segment=CASE WHEN %s THEN 'A4' ELSE a_segment END, version=version+1, updated_at=clock_timestamp() WHERE lead_id=%s RETURNING version",
            (new_bonus, upgraded, lead_id),
        )
        version = cursor.fetchone()["version"]
        cursor.execute(
            """INSERT INTO ltc.outbox_event
               (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id, causation_id)
               VALUES ('crm.dynamic_intent_bonus_applied.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s,%s)""",
            (lead_id, version, json.dumps({"company_id": str(company_id), "lead_id": str(lead_id), "bonus_type": bonus_type, "bonus_points": points, "new_total": new_bonus, "a_segment_upgraded": upgraded, "source_type": source_type, "source_resource_id": str(source_id), "rule_version": DYNAMIC_INTENT_RULE_VERSION}), event.get("correlation_id") or uuid4(), event["event_id"]),
        )

    def _create_a4_follow_up(self, cursor: Any, event: dict[str, Any]) -> None:
        payload = event["payload"]
        if not payload.get("a_segment_upgraded"):
            return
        cursor.execute(
            "SELECT * FROM ltc.sales_lead WHERE lead_id=%s AND company_id=%s AND a_segment='A4' FOR UPDATE",
            (UUID(str(payload["lead_id"])), UUID(str(payload["company_id"]))),
        )
        lead = cursor.fetchone()
        if lead:
            cursor.execute(
                """INSERT INTO ltc.follow_up_task
                   (company_id, lead_id, assignee_user_id, task_type, title, description, due_at, status, priority, idempotency_key)
                   VALUES (%s,%s,%s,'call','Follow up on A4 intent upgrade','Dynamic intent reached A4; contact the customer promptly.',clock_timestamp(),'pending',50,%s)
                   ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING""",
                (lead["company_id"], lead["lead_id"], lead["current_owner_user_id"], f"a4:{lead['lead_id']}"),
            )


class CrmAutoReleaseService:
    def __init__(self, database: CrmWorkerDatabase) -> None:
        self.database = database

    def execute(self) -> int:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT la.lead_id FROM ltc.lead_assignment la JOIN ltc.sales_lead sl ON sl.lead_id=la.lead_id
                       WHERE la.status='active' AND sl.allocation_status='claimed' AND sl.first_touch_at IS NULL
                         AND (SELECT COUNT(*) FROM generate_series((la.assigned_at AT TIME ZONE 'Asia/Shanghai')::date,
                              ((clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date - 1), interval '1 day') d
                              WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5) >= 3""",
                )
                lead_ids = [row["lead_id"] for row in cursor.fetchall()]
        return sum(1 for lead_id in lead_ids if self._release_one(lead_id))

    def _release_one(self, lead_id: UUID) -> bool:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT la.assignment_id, la.assignee_user_id, sl.* FROM ltc.lead_assignment la
                       JOIN ltc.sales_lead sl ON sl.lead_id=la.lead_id
                       WHERE la.lead_id=%s AND la.status='active' AND la.handover_pending=false
                         AND sl.allocation_status='claimed'
                         AND sl.first_touch_at IS NULL FOR UPDATE OF la, sl""",
                    (lead_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                now = datetime.now(timezone.utc)
                cursor.execute("UPDATE ltc.lead_assignment SET status='released', reason_code='auto_release_no_first_touch', ended_at=%s, version=version+1 WHERE assignment_id=%s AND handover_pending=false", (now, row["assignment_id"]))
                cursor.execute("""UPDATE ltc.sales_lead SET allocation_status='claimable', current_owner_user_id=NULL,
                    current_assignment_started_at=NULL, sla_due_at=NULL, released_reason='auto_release_no_first_touch',
                    version=version+1, updated_at=%s WHERE lead_id=%s""", (now, lead_id))
                cursor.execute(
                    """INSERT INTO ltc.lead_stage_transition
                       (company_id, lead_id, assignment_id, event_type,
                        from_allocation_status, to_allocation_status,
                        from_pipeline_stage, to_pipeline_stage,
                        from_owner_user_id, to_owner_user_id, actor_user_id,
                        source_type, reason_code, reason_text, metadata, occurred_at)
                       VALUES (%s,%s,%s,'release','claimed','claimable',%s,%s,
                               %s,NULL,NULL,'system','auto_release_no_first_touch',
                               '3 business days without first touch',%s::jsonb,%s)""",
                    (
                        row["company_id"], lead_id, row["assignment_id"],
                        row["pipeline_stage"], row["pipeline_stage"],
                        row["current_owner_user_id"],
                        json.dumps({"notify_user_id": str(row["assignee_user_id"])}), now,
                    ),
                )
                payload = {"lead_id": str(lead_id), "company_id": str(row["company_id"]), "assignment_id": str(row["assignment_id"]), "notify_user_id": str(row["assignee_user_id"]), "reason_code": "auto_release_no_first_touch", "reason_text": "3 business days without first touch", "released_at": now.isoformat()}
                cursor.execute("""INSERT INTO ltc.outbox_event
                    (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                    VALUES ('crm.lead_released.v1','worker','sales_lead',%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""", (lead_id, int(row["version"]) + 1, json.dumps(payload), uuid4()))
                cursor.execute("""INSERT INTO ltc.outbox_event
                    (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                    VALUES ('notification.sales_lead_auto_released.v1','worker','sales_lead',%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING""", (lead_id, int(row["version"]) + 1, json.dumps(payload), uuid4()))
                return True


class CrmOutboxUseCase:
    def __init__(self, consumer: CrmOutboxConsumer) -> None:
        self.consumer = consumer

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        del lock_token
        event_id = payload.get("event_id")
        if not event_id:
            raise ValueError(f"job {job_id} is missing event_id")
        await asyncio.to_thread(self.consumer.process, UUID(str(event_id)))


class CrmAutoReleaseUseCase:
    def __init__(self, service: CrmAutoReleaseService) -> None:
        self.service = service

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        del job_id, lock_token, payload
        await asyncio.to_thread(self.service.execute)


# Keep the names used by the previous CRM acceptance harness while the Worker
# runtime moves to its versioned JobExecutionUseCase contract.
WorkerDatabase = CrmWorkerDatabase
EventConsumer = CrmOutboxConsumer
AutoReleaseService = CrmAutoReleaseService
