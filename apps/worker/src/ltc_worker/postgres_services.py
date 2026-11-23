from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
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


def _dsn() -> str:
    host = os.getenv("LTC_DB_HOST", "postgres")
    port = os.getenv("LTC_DB_PORT", "5432")
    name = os.getenv("LTC_DB_NAME", "ltc")
    user = os.getenv("LTC_DB_USER", "ltc")
    password = os.getenv("LTC_DB_PASSWORD", "ltc_local_change_me")
    sslmode = os.getenv("LTC_DB_SSLMODE", "disable")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"


class WorkerDatabase:
    def __init__(self) -> None:
        self.pool = ConnectionPool(_dsn(), min_size=1, max_size=5, open=False)

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            with connection.transaction():
                yield connection


class WorkerJobs:
    def __init__(self, database: WorkerDatabase, worker_id: str) -> None:
        self.database = database
        self.worker_id = worker_id

    def ensure_auto_release_job(self) -> None:
        now = datetime.now(timezone.utc)
        with self.database.transaction() as connection:
            connection.execute("""INSERT INTO ltc.job (job_type, queue_name, concurrency_key, status, payload, run_after, max_attempts)
                SELECT 'crm.auto_release_overdue.v1','event','crm:auto-release','queued','{}'::jsonb,%s,3
                WHERE NOT EXISTS (SELECT 1 FROM ltc.job WHERE concurrency_key='crm:auto-release' AND status IN ('queued','running','retry_wait','reconcile_required'))""", (now,))

    def ensure_event_jobs(self) -> None:
        with self.database.transaction() as connection:
            connection.execute("""INSERT INTO ltc.job (job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload, max_attempts)
                SELECT 'platform.process_external_event.v1','event','external_event',external_event_id,
                       'external-event:' || external_event_id::text,'queued',jsonb_build_object('external_event_id', external_event_id),5
                  FROM ltc.external_event
                 WHERE status='received'
                   AND NOT EXISTS (SELECT 1 FROM ltc.job j WHERE j.concurrency_key='external-event:' || ltc.external_event.external_event_id::text AND j.status IN ('queued','running','retry_wait','reconcile_required'))
                 ON CONFLICT (concurrency_key) WHERE concurrency_key IS NOT NULL AND status IN ('queued','running','retry_wait','reconcile_required') DO NOTHING""")
            connection.execute("""INSERT INTO ltc.job (job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload, max_attempts)
                SELECT 'platform.dispatch_outbox.v1','event','outbox_event',event_id,
                       'outbox-event:' || event_id::text,'queued',jsonb_build_object('event_id', event_id),5
                  FROM ltc.outbox_event
                 WHERE status='pending'
                   AND NOT EXISTS (SELECT 1 FROM ltc.job j WHERE j.concurrency_key='outbox-event:' || ltc.outbox_event.event_id::text AND j.status IN ('queued','running','retry_wait','reconcile_required'))
                 ON CONFLICT (concurrency_key) WHERE concurrency_key IS NOT NULL AND status IN ('queued','running','retry_wait','reconcile_required') DO NOTHING""")

    def recover_expired_leases(self) -> int:
        """Return abandoned running jobs to the queue after their fencing lease ends."""
        with self.database.transaction() as connection:
            rows = connection.execute("""UPDATE ltc.job
                SET status='queued', locked_by=NULL, lock_token=NULL, locked_until=NULL,
                    run_after=clock_timestamp(), updated_at=clock_timestamp(), version=version+1
                WHERE status='running' AND locked_until < clock_timestamp()
                RETURNING job_id""").fetchall()
        return len(rows)

    def claim(self) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""WITH next_job AS (
                    SELECT job_id FROM ltc.job
                     WHERE status IN ('queued','retry_wait') AND run_after <= %s
                     ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT 1
                ) UPDATE ltc.job j SET status='running', locked_by=%s, lock_token=gen_random_uuid(), locked_until=%s,
                    attempt_count=attempt_count+1, started_at=COALESCE(started_at,%s), updated_at=%s, version=version+1
                  FROM next_job WHERE j.job_id=next_job.job_id
                RETURNING j.job_id, j.job_type, j.lock_token, j.queue_name, j.payload, j.attempt_count""", (now, self.worker_id, now + timedelta(minutes=5), now, now))
                return cursor.fetchone()

    def finish(self, job_id: UUID, lock_token: UUID, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        with self.database.transaction() as connection:
            connection.execute("""UPDATE ltc.job SET status=%s, result_summary=%s::jsonb, last_error_message=%s,
                run_after=CASE WHEN %s='retry_wait' THEN %s ELSE run_after END,
                completed_at=CASE WHEN %s='retry_wait' THEN NULL ELSE %s END,
                locked_by=NULL, lock_token=NULL, locked_until=NULL, updated_at=%s, version=version+1
                WHERE job_id=%s AND lock_token=%s AND status='running'""", (status, json.dumps(result or {}), error, status, now + timedelta(seconds=30), status, now, now, job_id, lock_token))


class EventConsumer:
    name = "sales_crm.pipeline_consumer.v1"

    def __init__(self, database: WorkerDatabase) -> None:
        self.database = database

    def process_external_event(self, external_event_id: UUID) -> None:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM ltc.external_event WHERE external_event_id=%s FOR UPDATE", (external_event_id,))
                event = cursor.fetchone()
                if not event or event["status"] in {"processed", "quarantined", "dead"}:
                    return
                if not event["signature_valid"]:
                    cursor.execute("UPDATE ltc.external_event SET status='quarantined', processed_at=clock_timestamp(), last_error='invalid_signature' WHERE external_event_id=%s", (external_event_id,))
                    return
                cursor.execute("UPDATE ltc.external_event SET status='processing', attempt_count=attempt_count+1 WHERE external_event_id=%s", (external_event_id,))
                payload = event["payload"]
                kind = str(payload.get("event_type") or event["event_type"]).lower()
                email_id = payload.get("email_id")
                if not email_id:
                    cursor.execute("UPDATE ltc.external_event SET status='quarantined', processed_at=clock_timestamp(), last_error='email_id_missing' WHERE external_event_id=%s", (external_event_id,))
                    return
                try:
                    parsed_email_id = UUID(str(email_id))
                except (TypeError, ValueError):
                    cursor.execute("UPDATE ltc.external_event SET status='quarantined', processed_at=clock_timestamp(), last_error='email_id_invalid' WHERE external_event_id=%s", (external_event_id,))
                    return
                self._apply_webhook(cursor, event, parsed_email_id, kind, payload)
                cursor.execute("UPDATE ltc.external_event SET status='processed', processed_at=clock_timestamp(), last_error=NULL WHERE external_event_id=%s", (external_event_id,))

    def _apply_webhook(self, cursor: Any, event: dict[str, Any], email_id: UUID, kind: str, payload: dict[str, Any]) -> None:
        status_map = {"delivered": "delivered", "opened": "opened", "clicked": "clicked"}
        if kind in status_map:
            cursor.execute("SELECT email_id, company_id, lead_id, contact_id, status, version FROM ltc.email_message WHERE email_id=%s FOR UPDATE", (email_id,))
            email = cursor.fetchone()
            if not email:
                return
            ranks = {"generating": -1, "draft": -1, "approved": -1, "queued": -1, "sending": -1, "sent": 0, "delivered": 1, "opened": 2, "clicked": 3, "replied": 4}
            target_rank = ranks[kind]
            current_rank = ranks.get(str(email["status"]), 99 if email["status"] in {"bounced", "failed"} else -1)
            if target_rank <= current_rank:
                return
            cursor.execute("UPDATE ltc.email_message SET status=%s, received_at=COALESCE(received_at,clock_timestamp()), version=version+1, updated_at=clock_timestamp() WHERE email_id=%s RETURNING email_id, company_id, lead_id, contact_id, version", (status_map[kind], email_id))
            email = cursor.fetchone()
            if email and kind in {"opened", "clicked"}:
                event_type = f"engagement.email_{kind}.v1"
                cursor.execute("""INSERT INTO ltc.outbox_event (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                    VALUES (%s,'worker','email_message',%s,%s,%s::jsonb,%s)
                    ON CONFLICT (aggregate_type, aggregate_id, aggregate_version, event_type) DO NOTHING""", (event_type, email_id, email["version"], json.dumps({"company_id": str(email["company_id"]), "lead_id": str(email["lead_id"]) if email["lead_id"] else None, "email_id": str(email_id), "contact_id": str(email["contact_id"]) if email["contact_id"] else None, "occurred_at": datetime.now(timezone.utc).isoformat(), "external_event_id": str(event["external_event_id"])}), uuid4()))
        elif kind in {"bounced", "complaint", "unsubscribe"}:
            normalized_email = payload.get("normalized_email") or payload.get("email")
            if normalized_email:
                reason = {"bounced": "hard_bounce", "complaint": "complaint", "unsubscribe": "unsubscribe"}[kind]
                cursor.execute("""INSERT INTO ltc.email_suppression (normalized_email, reason, source_email_id, source_external_event_id, status, suppressed_at)
                    VALUES (%s,%s,%s,%s,'active',clock_timestamp()) ON CONFLICT DO NOTHING""", (str(normalized_email).strip().lower(), reason, email_id, event["external_event_id"]))

    def process_outbox_event(self, event_id: UUID) -> None:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM ltc.outbox_event WHERE event_id=%s FOR UPDATE", (event_id,))
                event = cursor.fetchone()
                if not event or event["status"] in {"published", "dead"}:
                    return
                if self._consumer_completed(cursor, event["event_id"]):
                    cursor.execute("UPDATE ltc.outbox_event SET status='published', published_at=clock_timestamp(), locked_by=NULL, lock_token=NULL, locked_until=NULL WHERE event_id=%s", (event_id,))
                    return
                event_type = event["event_type"]
                if event_type in {"engagement.email_sent.v1", "engagement.email_replied.v1", "engagement.meeting_analyzed.v1"}:
                    self._advance_pipeline(cursor, event)
                if event_type in {"engagement.email_opened.v1", "engagement.email_clicked.v1", "engagement.email_replied.v1", "engagement.meeting_analyzed.v1"}:
                    self._apply_dynamic_bonus(cursor, event)
                if event_type == "crm.dynamic_intent_bonus_applied.v1":
                    self._create_a4_follow_ups(cursor, event)
                if event_type in {"notification.sales_lead_auto_released.v1", "notification.user_login_locked.v1"}:
                    self._queue_notification(cursor, event)
                self._mark_consumer_completed(cursor, event["event_id"])
                cursor.execute("UPDATE ltc.outbox_event SET status='published', published_at=clock_timestamp(), locked_by=NULL, lock_token=NULL, locked_until=NULL WHERE event_id=%s", (event_id,))

    def _consumer_completed(self, cursor: Any, event_id: UUID) -> bool:
        cursor.execute("SELECT state FROM ltc.idempotency_record WHERE scope='outbox_consume' AND principal_type='event_consumer' AND principal_id=%s AND idempotency_key=%s FOR UPDATE", (str(event_id), self.name))
        row = cursor.fetchone()
        return bool(row and row["state"] == "completed")

    def _mark_consumer_completed(self, cursor: Any, event_id: UUID) -> None:
        cursor.execute("""INSERT INTO ltc.idempotency_record
            (scope, principal_type, principal_id, idempotency_key, request_hash, state, response_status, response_body, expires_at)
            VALUES ('outbox_consume','event_consumer',%s,%s,%s,'completed',200,'{}'::jsonb,clock_timestamp() + interval '30 days')
            ON CONFLICT (scope, principal_type, principal_id, idempotency_key) DO UPDATE
            SET state='completed', updated_at=clock_timestamp()""", (str(event_id), self.name, hashlib.sha256(f"{event_id}:{self.name}".encode()).hexdigest()))

    @staticmethod
    def _event_occurred_at(payload: dict[str, Any], event_type: str) -> datetime:
        field = {
            "engagement.email_sent.v1": "sent_at",
            "engagement.email_replied.v1": "replied_at",
            "engagement.meeting_analyzed.v1": "completed_at",
            "engagement.email_opened.v1": "opened_at",
            "engagement.email_clicked.v1": "clicked_at",
        }.get(event_type, "occurred_at")
        value = payload.get(field) or payload.get("occurred_at")
        if isinstance(value, datetime):
            return value
        if value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def _event_source_matches(self, cursor: Any, event: dict[str, Any]) -> bool:
        """Reject payloads that do not describe the persisted engagement resource."""
        payload = event["payload"]
        lead_id = payload.get("lead_id")
        company_id = payload.get("company_id")
        if not lead_id or not company_id:
            return False
        if event["event_type"].startswith("engagement.email_"):
            email_id = payload.get("email_id")
            if not email_id:
                return False
            cursor.execute("SELECT company_id, lead_id, contact_id FROM ltc.email_message WHERE email_id=%s", (UUID(str(email_id)),))
            source = cursor.fetchone()
            if not source or source["company_id"] != UUID(str(company_id)) or source["lead_id"] != UUID(str(lead_id)):
                return False
            contact_id = payload.get("contact_id")
            return not contact_id or source["contact_id"] == UUID(str(contact_id))
        if event["event_type"] == "engagement.meeting_analyzed.v1":
            meeting_id = payload.get("meeting_id")
            if not meeting_id:
                return False
            cursor.execute("SELECT company_id, lead_id FROM ltc.meeting WHERE meeting_id=%s", (UUID(str(meeting_id)),))
            source = cursor.fetchone()
            return bool(source and source["company_id"] == UUID(str(company_id)) and source["lead_id"] == UUID(str(lead_id)))
        return False

    def _meeting_has_collaboration_signal(self, cursor: Any, meeting_id: UUID) -> bool:
        cursor.execute("SELECT summary_payload FROM ltc.meeting WHERE meeting_id=%s", (meeting_id,))
        meeting = cursor.fetchone()
        if not meeting or not meeting["summary_payload"]:
            return False
        text = json.dumps(meeting["summary_payload"], ensure_ascii=False).lower()
        return any(marker in text for marker in ("合作", "方案", "报价", "集成", "api", "partnership", "proposal", "pricing"))

    def _advance_pipeline(self, cursor: Any, event: dict[str, Any]) -> None:
        payload = event["payload"]
        lead_id = payload.get("lead_id")
        if not lead_id:
            return
        target = {"engagement.email_sent.v1": "contacted", "engagement.email_replied.v1": "engaged", "engagement.meeting_analyzed.v1": "meeting"}[event["event_type"]]
        source_type = "meeting" if target == "meeting" else "email"
        source_id = payload.get("meeting_id") if source_type == "meeting" else payload.get("email_id")
        source_column = "source_meeting_id" if source_type == "meeting" else "source_email_id"
        if not self._event_source_matches(cursor, event):
            return
        cursor.execute("SELECT * FROM ltc.sales_lead WHERE lead_id=%s FOR UPDATE", (UUID(str(lead_id)),))
        lead = cursor.fetchone()
        if not lead or lead["company_id"] != UUID(str(payload["company_id"])) or lead["allocation_status"] != "claimed":
            return
        ranks = {"new": 0, "contacted": 1, "engaged": 2, "meeting": 3, "proposal": 4, "won": 5, "lost": 5, "dormant": 0}
        if ranks[target] <= ranks[lead["pipeline_stage"]] or not source_id:
            return
        transition_type = "first_touch" if event["event_type"] == "engagement.email_sent.v1" and lead["first_touch_at"] is None else "stage_change"
        occurred_at = self._event_occurred_at(payload, event["event_type"])
        cursor.execute(f"""INSERT INTO ltc.lead_stage_transition (company_id, lead_id, event_type, from_allocation_status, to_allocation_status, from_pipeline_stage, to_pipeline_stage, from_owner_user_id, to_owner_user_id, actor_user_id, source_type, {source_column}, occurred_at, metadata)
            VALUES (%s,%s,%s,'claimed','claimed',%s,%s,%s,%s,NULL,%s,%s,%s,%s::jsonb)
            ON CONFLICT DO NOTHING RETURNING transition_id""", (lead["company_id"], lead["lead_id"], transition_type, lead["pipeline_stage"], target, lead["current_owner_user_id"], lead["current_owner_user_id"], source_type, UUID(str(source_id)), occurred_at, json.dumps({"event_id": str(event["event_id"])})))
        transition = cursor.fetchone()
        if transition is None:
            return
        cursor.execute("""UPDATE ltc.sales_lead SET pipeline_stage=%s,
            first_touch_at=CASE WHEN %s='contacted' THEN COALESCE(first_touch_at, %s) ELSE first_touch_at END,
            sla_due_at=CASE WHEN %s='contacted' THEN NULL ELSE sla_due_at END,
            last_activity_at=GREATEST(COALESCE(last_activity_at, %s), %s),
            version=version+1, updated_at=clock_timestamp() WHERE lead_id=%s RETURNING version""", (target, target, occurred_at, target, occurred_at, occurred_at, lead["lead_id"]))
        version = cursor.fetchone()["version"]
        if transition_type == "first_touch":
            cursor.execute("""UPDATE ltc.lead_assignment
                SET first_touch_at=COALESCE(first_touch_at, %s), version=version+1
                WHERE lead_id=%s AND status='active'""", (occurred_at, lead["lead_id"]))
        cursor.execute("""INSERT INTO ltc.outbox_event
            (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id, causation_id)
            VALUES ('crm.pipeline_changed.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s,%s)""", (
            lead["lead_id"], version,
            json.dumps({"company_id": str(lead["company_id"]), "lead_id": str(lead["lead_id"]), "transition_id": str(transition["transition_id"]), "from_stage": lead["pipeline_stage"], "to_stage": target, "source_type": source_type, "source_resource_id": str(source_id), "occurred_at": occurred_at.isoformat()}),
            event["correlation_id"] or uuid4(), event["event_id"],
        ))

    def _apply_dynamic_bonus(self, cursor: Any, event: dict[str, Any]) -> None:
        payload = event["payload"]
        if not payload.get("lead_id"):
            return
        event_type = event["event_type"]
        source_type = "email" if "email" in event_type else "meeting"
        source_id = payload.get("email_id") if source_type == "email" else payload.get("meeting_id")
        if not source_id:
            return
        if not self._event_source_matches(cursor, event):
            return
        if event_type in {"engagement.email_opened.v1", "engagement.email_clicked.v1"}:
            bonus_type, points = "I1", 2
        elif event_type == "engagement.meeting_analyzed.v1":
            if not self._meeting_has_collaboration_signal(cursor, UUID(str(source_id))):
                return
            bonus_type, points = "I4", 10
        else:
            intent = payload.get("intent_level")
            if intent not in INTENT_BONUS_RULES:
                return
            bonus_type, points = INTENT_BONUS_RULES[str(intent)]
        cursor.execute("""SELECT sl.*, ia.total_score AS icp_score, ia.grade AS icp_grade
            FROM ltc.sales_lead sl JOIN ltc.lead_icp_assessment ia ON ia.icp_assessment_id=sl.adopted_icp_assessment_id
            WHERE sl.lead_id=%s FOR UPDATE""", (UUID(str(payload["lead_id"])),))
        lead = cursor.fetchone()
        if not lead or lead["company_id"] != UUID(str(payload["company_id"])):
            return
        cursor.execute("""INSERT INTO ltc.crm_dynamic_bonus_application
            (lead_id, source_type, source_resource_id, bonus_type, bonus_points, rule_version)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (source_type, source_resource_id, bonus_type) DO NOTHING
            RETURNING bonus_application_id""", (lead["lead_id"], source_type, UUID(str(source_id)), bonus_type, points, DYNAMIC_INTENT_RULE_VERSION))
        if cursor.fetchone() is None:
            return
        new_bonus = min(100, int(lead["dynamic_bonus_points"]) + points)
        upgraded = lead["a_segment"] != "A4" and lead["icp_grade"] == "B" and float(lead["icp_score"]) + new_bonus >= 80
        cursor.execute("UPDATE ltc.sales_lead SET dynamic_bonus_points=%s, a_segment=CASE WHEN %s THEN 'A4' ELSE a_segment END, version=version+1, updated_at=clock_timestamp() WHERE lead_id=%s RETURNING version", (new_bonus, upgraded, lead["lead_id"]))
        version = cursor.fetchone()["version"]
        cursor.execute("""INSERT INTO ltc.outbox_event
            (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id, causation_id)
            VALUES ('crm.dynamic_intent_bonus_applied.v1','sales_crm','sales_lead',%s,%s,%s::jsonb,%s,%s)""", (lead["lead_id"], version, json.dumps({"company_id": str(lead["company_id"]), "lead_id": str(lead["lead_id"]), "bonus_type": bonus_type, "bonus_points": points, "new_total": min(100, float(lead["icp_score"]) + new_bonus), "a_segment_upgraded": upgraded, "source_type": source_type, "source_resource_id": str(source_id), "rule_version": DYNAMIC_INTENT_RULE_VERSION, "applied_at": datetime.now(timezone.utc).isoformat()}), event["correlation_id"] or uuid4(), event["event_id"]))

    def _create_a4_follow_ups(self, cursor: Any, event: dict[str, Any]) -> None:
        payload = event["payload"]
        if not payload.get("a_segment_upgraded") or not payload.get("lead_id"):
            return
        cursor.execute("""SELECT * FROM ltc.sales_lead
            WHERE lead_id=%s AND company_id=%s AND a_segment='A4' FOR UPDATE""", (UUID(str(payload["lead_id"])), UUID(str(payload["company_id"]))))
        lead = cursor.fetchone()
        if not lead:
            return
        cursor.execute("""INSERT INTO ltc.follow_up_task (company_id, lead_id, assignee_user_id, task_type, title, description, due_at, status, priority, idempotency_key)
            VALUES (%s,%s,%s,'call','Follow up on A4 intent upgrade','Dynamic intent reached A4; contact the customer promptly.',clock_timestamp(),'pending',50,%s)
            ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING""", (lead["company_id"], lead["lead_id"], lead["current_owner_user_id"], f"a4:{lead['lead_id']}"))

    def _queue_notification(self, cursor: Any, event: dict[str, Any]) -> None:
        cursor.execute("""INSERT INTO ltc.job (job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload, max_attempts)
            VALUES ('platform.notify.v1','event','outbox_event',%s,%s,'queued',%s::jsonb,3)
            ON CONFLICT (concurrency_key) WHERE concurrency_key IS NOT NULL AND status IN ('queued','running','retry_wait','reconcile_required') DO NOTHING""", (event["event_id"], f"notification:{event['event_id']}", json.dumps({"event_id": str(event["event_id"]), "event_type": event["event_type"], "payload": event["payload"]})))


class AutoReleaseService:
    def __init__(self, database: WorkerDatabase) -> None:
        self.database = database

    def execute(self) -> int:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""SELECT la.lead_id
                    FROM ltc.lead_assignment la JOIN ltc.sales_lead sl ON sl.lead_id=la.lead_id
                   WHERE la.status='active' AND sl.allocation_status='claimed' AND sl.first_touch_at IS NULL
                     AND (SELECT COUNT(*) FROM generate_series(
                         (la.assigned_at AT TIME ZONE 'Asia/Shanghai')::date,
                         ((clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date - 1), interval '1 day'
                     ) d WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5) >= 3
                   ORDER BY la.lead_id""")
                lead_ids = [row["lead_id"] for row in cursor.fetchall()]
        return sum(1 for lead_id in lead_ids if self._release_one(lead_id))

    def _release_one(self, lead_id: UUID) -> bool:
        with self.database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""SELECT la.assignment_id, la.lead_id, la.assignee_user_id, sl.company_id, sl.version, sl.pipeline_stage, sl.current_owner_user_id
                    FROM ltc.lead_assignment la JOIN ltc.sales_lead sl ON sl.lead_id=la.lead_id
                   WHERE la.lead_id=%s AND la.status='active' AND sl.allocation_status='claimed' AND sl.first_touch_at IS NULL
                     AND (SELECT COUNT(*) FROM generate_series(
                         (la.assigned_at AT TIME ZONE 'Asia/Shanghai')::date,
                         ((clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date - 1), interval '1 day'
                     ) d WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5) >= 3
                   FOR UPDATE OF la, sl""", (lead_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                cursor.execute("UPDATE ltc.lead_assignment SET status='released', reason_code='auto_release_no_first_touch', ended_at=clock_timestamp(), version=version+1 WHERE assignment_id=%s AND status='active'", (row["assignment_id"],))
                cursor.execute("UPDATE ltc.sales_lead SET allocation_status='claimable', current_owner_user_id=NULL, current_assignment_started_at=NULL, sla_due_at=NULL, released_reason='auto_release_no_first_touch', version=version+1, updated_at=clock_timestamp() WHERE lead_id=%s AND allocation_status='claimed'", (row["lead_id"],))
                payload = {"lead_id": str(row["lead_id"]), "company_id": str(row["company_id"]), "assignment_id": str(row["assignment_id"]), "released_by": "system", "reason_code": "auto_release_no_first_touch", "reason_text": "3 business days without first touch", "notify_user_id": str(row["assignee_user_id"]), "released_at": datetime.now(timezone.utc).isoformat()}
                cursor.execute("INSERT INTO ltc.lead_stage_transition (company_id, lead_id, assignment_id, event_type, from_allocation_status, to_allocation_status, from_pipeline_stage, to_pipeline_stage, from_owner_user_id, actor_user_id, source_type, reason_code, reason_text, metadata, occurred_at) VALUES (%s,%s,%s,'release','claimed','claimable',%s,%s,%s,NULL,'system','auto_release_no_first_touch','3 business days without first touch',%s::jsonb,clock_timestamp())", (row["company_id"], row["lead_id"], row["assignment_id"], row["pipeline_stage"], row["pipeline_stage"], row["current_owner_user_id"], json.dumps({"notify_user_id": str(row["assignee_user_id"])})))
                cursor.execute("INSERT INTO ltc.outbox_event (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id) VALUES ('crm.lead_released.v1','worker','sales_lead',%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING", (row["lead_id"], int(row["version"])+1, json.dumps(payload), uuid4()))
                cursor.execute("INSERT INTO ltc.outbox_event (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id) VALUES ('notification.sales_lead_auto_released.v1','worker','sales_lead',%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING", (row["lead_id"], int(row["version"])+1, json.dumps(payload), uuid4()))
                return True


class NotificationService:
    """Notification port placeholder with a durable audit trail for local delivery."""

    def __init__(self, database: WorkerDatabase) -> None:
        self.database = database

    def send(self, payload: dict[str, Any]) -> None:
        event_payload = payload.get("payload") or {}
        lead_id = event_payload.get("lead_id")
        user_id = event_payload.get("user_id")
        resource_id = lead_id or user_id
        resource_type = "sales_lead" if lead_id else "user_account" if user_id else "notification"
        with self.database.transaction() as connection:
            connection.execute("""INSERT INTO ltc.audit_log
                (action, resource_type, resource_id, metadata)
                VALUES ('notification_dispatched',%s,%s,%s::jsonb)""", (
                resource_type,
                UUID(str(resource_id)) if resource_id else None,
                json.dumps({"event_id": payload.get("event_id"), "event_type": payload.get("event_type"), "notify_user_id": event_payload.get("notify_user_id")}),
            ))
