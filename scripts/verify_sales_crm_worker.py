#!/usr/bin/env python3
"""Exercise the Sales CRM Worker consumer against PostgreSQL.

The script creates isolated fixtures, verifies the dynamic-intent and
auto-release workflows, and removes the fixtures before returning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker" / "src"))

from ltc_worker.crm_services import AutoReleaseService, EventConsumer, WorkerDatabase


class IntegrationFailure(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("LTC_DB_HOST", "localhost"))
    parser.add_argument("--port", default=os.getenv("LTC_DB_PORT", "55432"))
    parser.add_argument("--database", default=os.getenv("LTC_DB_NAME", "ltc"))
    parser.add_argument("--user", default=os.getenv("LTC_DB_USER", "ltc"))
    parser.add_argument("--password", default=os.getenv("LTC_DB_PASSWORD", "ltc_local_change_me"))
    return parser.parse_args()


def scalar(connection, sql: str, params: tuple[object, ...] = ()) -> object:
    row = connection.execute(sql, params).fetchone()
    return row[0] if row else None


def add_event(connection, *, event_id: UUID, event_type: str, email_id: UUID, company_id: UUID, lead_id: UUID, occurred_at: datetime, intent: str | None = None) -> None:
    payload = {
        "company_id": str(company_id),
        "lead_id": str(lead_id),
        "email_id": str(email_id),
        "occurred_at": occurred_at.isoformat(),
    }
    if intent:
        payload["intent_level"] = intent
        payload["replied_at"] = occurred_at.isoformat()
    connection.execute(
        """INSERT INTO ltc.outbox_event
           (event_id, event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload)
           VALUES (%s,%s,'crm-worker-integration','email_message',%s,1,%s::jsonb)""",
        (event_id, event_type, email_id, json.dumps(payload)),
    )


def main() -> int:
    args = parse_args()
    os.environ.update(
        LTC_DB_HOST=args.host,
        LTC_DB_PORT=str(args.port),
        LTC_DB_NAME=args.database,
        LTC_DB_USER=args.user,
        LTC_DB_PASSWORD=args.password,
        LTC_DB_SSLMODE="disable",
    )
    ids = {name: uuid4() for name in (
        "candidate", "job", "run", "icp", "scale", "company_active", "company_overdue",
        "lead_active", "lead_overdue", "assignment_active", "assignment_overdue", "email",
        "opened_event", "replied_event",
    )}
    now = datetime.now(timezone.utc)
    overdue_at = now - timedelta(days=14)
    database = WorkerDatabase()
    database.open()
    try:
        with database.transaction() as connection:
            strategic_id = scalar(connection, "SELECT user_id FROM ltc.user_account WHERE account_type='strategic' AND status='active' ORDER BY username LIMIT 1")
            sales = connection.execute(
                """SELECT user_id, sales_tier, region_code FROM ltc.user_account
                   WHERE account_type='sales' AND status='active'
                     AND sales_tier IS NOT NULL AND region_code IS NOT NULL
                   ORDER BY username LIMIT 1"""
            ).fetchone()
            if not strategic_id or not sales:
                raise IntegrationFailure("an active strategic account and active regional sales account are required")
            sales_id, sales_tier, sales_region = sales
            scale_tier = {"MA": "large", "SA": "medium", "A": "small"}.get(str(sales_tier))
            if not scale_tier:
                raise IntegrationFailure(f"unsupported sales tier: {sales_tier}")

            connection.execute(
                """INSERT INTO ltc.job
                   (job_id, job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload)
                   VALUES (%s,'crm.worker.fixture','fixture','lead_enrichment_run',%s,%s,'queued','{}'::jsonb)""",
                (ids["job"], ids["run"], f"crm-fixture:{ids['run']}"),
            )
            connection.execute(
                """INSERT INTO ltc.lead_candidate
                   (candidate_id, dedupe_key, company_name, normalized_company_name, normalized_domain,
                    region_code, country_code, region_mapping_version, validation_status, processing_status,
                    first_seen_at, last_seen_at)
                   VALUES (%s,%s,'CRM Worker Fixture','crm worker fixture',%s,%s,'CN','region-country-v5','valid','eligible',%s,%s)""",
                (ids["candidate"], str(ids["candidate"]), f"crm-{ids['candidate']}.test", sales_region, now, now),
            )
            connection.execute(
                """INSERT INTO ltc.lead_enrichment_run
                   (enrichment_run_id, candidate_id, version_no, status, scene_code, rule_version, prompt_version,
                    config_checksum, current_job_id, is_current, completed_at)
                   VALUES (%s,%s,1,'completed','S1','fixture','fixture',repeat('a',64),%s,true,%s)""",
                (ids["run"], ids["candidate"], ids["job"], now),
            )
            connection.execute(
                """INSERT INTO ltc.lead_icp_assessment
                   (icp_assessment_id, candidate_id, enrichment_run_id, version_no, scene_code, rule_version,
                    rule_snapshot, rule_checksum, prompt_version, d1_score, d2_score, d3_score, d4_score,
                    total_score, grade, hard_gate_passed, score_breakdown, explanations, is_current, scored_at)
                   VALUES (%s,%s,%s,1,'S1','fixture','{}'::jsonb,repeat('b',64),'fixture',30,20,12,8,70,'B',true,'{}'::jsonb,'{}'::jsonb,true,%s)""",
                (ids["icp"], ids["candidate"], ids["run"], now),
            )
            connection.execute(
                """INSERT INTO ltc.customer_scale_assessment
                   (scale_assessment_id, candidate_id, source_enrichment_run_id, version_no, rule_version,
                    prompt_version, d1_scale_score, d2_commercial_score, d3_coverage_score, total_score,
                    computed_tier, effective_tier, decision_source, assessment_payload, is_current, assessed_at)
                   VALUES (%s,%s,%s,1,'fixture','fixture',40,30,20,90,%s,%s,'computed','{}'::jsonb,true,%s)""",
                (ids["scale"], ids["candidate"], ids["run"], scale_tier, scale_tier, now),
            )
            for company_key, lead_key, assignment_key, assigned_at in (
                ("company_active", "lead_active", "assignment_active", now),
                ("company_overdue", "lead_overdue", "assignment_overdue", overdue_at),
            ):
                company_id, lead_id, assignment_id = ids[company_key], ids[lead_key], ids[assignment_key]
                name = f"CRM Worker {company_key} {company_id}"
                connection.execute(
                    """INSERT INTO ltc.company
                       (company_id, origin_candidate_id, company_name, normalized_company_name, primary_domain,
                        country_code, region_code, region_mapping_version, created_by)
                       VALUES (%s,%s,%s,%s,%s,'CN',%s,'region-country-v5',%s)""",
                    (company_id, ids["candidate"], name, name.lower(), f"{company_id}.test", sales_region, strategic_id),
                )
                connection.execute(
                    """INSERT INTO ltc.sales_lead
                       (lead_id, company_id, source_candidate_id, adopted_icp_assessment_id, adopted_scale_assessment_id,
                        required_sales_tier, pool_region_code, pool_region_mapping_version, allocation_status,
                        pipeline_stage, current_owner_user_id, current_assignment_started_at, sla_due_at, allocation_rule_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'region-country-v5','claimed','new',%s,%s,%s,'fixture')""",
                    (lead_id, company_id, ids["candidate"], ids["icp"], ids["scale"], sales_tier, sales_region, sales_id, assigned_at, assigned_at + timedelta(days=1)),
                )
                connection.execute(
                    """INSERT INTO ltc.lead_assignment
                       (assignment_id, lead_id, assignee_user_id, assigned_by, assignment_type, status, assigned_at, sla_due_at)
                       VALUES (%s,%s,%s,%s,'claim','active',%s,%s)""",
                    (assignment_id, lead_id, sales_id, strategic_id, assigned_at, assigned_at + timedelta(days=1)),
                )
            connection.execute(
                """INSERT INTO ltc.email_message
                   (email_id, company_id, lead_id, direction, purpose, status, from_address, intended_to_address, subject)
                   VALUES (%s,%s,%s,'outbound','reply_followup','sent','sales@fixture.test','customer@fixture.test','Interested')""",
                (ids["email"], ids["company_active"], ids["lead_active"]),
            )
            add_event(connection, event_id=ids["opened_event"], event_type="engagement.email_opened.v1", email_id=ids["email"], company_id=ids["company_active"], lead_id=ids["lead_active"], occurred_at=now)
            add_event(connection, event_id=ids["replied_event"], event_type="engagement.email_replied.v1", email_id=ids["email"], company_id=ids["company_active"], lead_id=ids["lead_active"], occurred_at=now, intent="interested")

        consumer = EventConsumer(database)
        for event_id in (ids["opened_event"], ids["opened_event"], ids["replied_event"], ids["replied_event"]):
            consumer.process_outbox_event(event_id)
        with database.transaction() as connection:
            stage, bonus, segment = connection.execute(
                "SELECT pipeline_stage, dynamic_bonus_points, a_segment FROM ltc.sales_lead WHERE lead_id=%s", (ids["lead_active"],)
            ).fetchone()
            if (stage, int(bonus), segment) != ("engaged", 12, "A4"):
                raise IntegrationFailure(f"expected 70 + 2 + 10 = 82 and A4, got {(stage, bonus, segment)}")
            dynamic_event = scalar(
                connection,
                "SELECT event_id FROM ltc.outbox_event WHERE event_type='crm.dynamic_intent_bonus_applied.v1' AND causation_id=%s",
                (ids["replied_event"],),
            )
        if not dynamic_event:
            raise IntegrationFailure("interested reply did not emit a dynamic-bonus event")
        consumer.process_outbox_event(UUID(str(dynamic_event)))
        consumer.process_outbox_event(UUID(str(dynamic_event)))
        with database.transaction() as connection:
            task_count = scalar(connection, "SELECT count(*) FROM ltc.follow_up_task WHERE lead_id=%s", (ids["lead_active"],))
            if task_count != 1:
                raise IntegrationFailure(f"expected one idempotent A4 follow-up task, got {task_count}")

        released = AutoReleaseService(database).execute()
        if released != 1 or AutoReleaseService(database).execute() != 0:
            raise IntegrationFailure(f"expected exactly one idempotent overdue release, got {released}")
        with database.transaction() as connection:
            status, owner, active_assignments = connection.execute(
                """SELECT allocation_status, current_owner_user_id,
                          (SELECT count(*) FROM ltc.lead_assignment WHERE lead_id=%s AND status='active')
                   FROM ltc.sales_lead WHERE lead_id=%s""",
                (ids["lead_overdue"], ids["lead_overdue"]),
            ).fetchone()
            event_counts = connection.execute(
                """SELECT count(*) FILTER (WHERE event_type='crm.lead_released.v1'),
                          count(*) FILTER (WHERE event_type='notification.sales_lead_auto_released.v1')
                   FROM ltc.outbox_event WHERE aggregate_id=%s""",
                (ids["lead_overdue"],),
            ).fetchone()
            transition_count = scalar(
                connection,
                """SELECT count(*) FROM ltc.lead_stage_transition
                   WHERE lead_id=%s AND event_type='release'
                     AND reason_code='auto_release_no_first_touch'""",
                (ids["lead_overdue"],),
            )
            if (status, owner, active_assignments) != ("claimable", None, 0) or tuple(event_counts) != (1, 1) or transition_count != 1:
                raise IntegrationFailure(f"auto-release result mismatch: {(status, owner, active_assignments, event_counts, transition_count)}")
        print("PASS: Sales CRM Worker dynamic intent and auto-release integration")
        return 0
    finally:
        try:
            with database.transaction() as connection:
                connection.execute("ALTER TABLE ltc.lead_stage_transition DISABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
                connection.execute("ALTER TABLE ltc.lead_assignment DISABLE TRIGGER trg_lead_assignment_no_hard_delete")
            with database.transaction() as connection:
                lead_ids = [ids["lead_active"], ids["lead_overdue"]]
                event_ids = [ids["opened_event"], ids["replied_event"]]
                connection.execute(
                    """DELETE FROM ltc.idempotency_record
                       WHERE scope='outbox_consume' AND principal_type='event_consumer'
                         AND principal_id IN (
                             SELECT event_id::text FROM ltc.outbox_event
                              WHERE aggregate_id = ANY(%s) OR event_id = ANY(%s)
                         )""",
                    (lead_ids, event_ids),
                )
                connection.execute("DELETE FROM ltc.follow_up_task WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.crm_dynamic_bonus_application WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.lead_stage_transition WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.outbox_event WHERE aggregate_id = ANY(%s) OR causation_id = ANY(%s) OR event_id = ANY(%s)", (lead_ids, event_ids, event_ids))
                connection.execute("DELETE FROM ltc.email_message WHERE email_id=%s", (ids["email"],))
                connection.execute("DELETE FROM ltc.lead_assignment WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.sales_lead WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.lead_icp_assessment WHERE icp_assessment_id=%s", (ids["icp"],))
                connection.execute("DELETE FROM ltc.customer_scale_assessment WHERE scale_assessment_id=%s", (ids["scale"],))
                connection.execute("DELETE FROM ltc.lead_enrichment_run WHERE enrichment_run_id=%s", (ids["run"],))
                connection.execute("DELETE FROM ltc.job WHERE job_id=%s", (ids["job"],))
                connection.execute("DELETE FROM ltc.company WHERE company_id = ANY(%s)", ([ids["company_active"], ids["company_overdue"]],))
                connection.execute("DELETE FROM ltc.lead_candidate WHERE candidate_id=%s", (ids["candidate"],))
        finally:
            try:
                with database.transaction() as connection:
                    connection.execute("ALTER TABLE ltc.lead_assignment ENABLE TRIGGER trg_lead_assignment_no_hard_delete")
                    connection.execute("ALTER TABLE ltc.lead_stage_transition ENABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
            finally:
                database.close()


if __name__ == "__main__":
    raise SystemExit(main())
