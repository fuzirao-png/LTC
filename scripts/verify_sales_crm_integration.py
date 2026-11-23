#!/usr/bin/env python3
"""Verify the Sales CRM worker against a running PostgreSQL instance."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker" / "src"))

from ltc_worker.postgres_services import AutoReleaseService, EventConsumer, WorkerDatabase


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

    ids = {
        "candidate": uuid4(),
        "job": uuid4(),
        "run": uuid4(),
        "icp": uuid4(),
        "scale": uuid4(),
        "company1": uuid4(),
        "company2": uuid4(),
        "lead1": uuid4(),
        "lead2": uuid4(),
        "assignment1": uuid4(),
        "assignment2": uuid4(),
        "email": uuid4(),
        "event": uuid4(),
    }
    now = datetime.now(timezone.utc)
    # Leave enough margin for host/container clock or timezone differences.
    old_assignment = now - timedelta(days=14)
    database = WorkerDatabase()
    database.open()
    try:
        with database.transaction() as connection:
            strategic_id = scalar(connection, "SELECT user_id FROM ltc.user_account WHERE account_type='strategic' AND status='active' LIMIT 1")
            sales_row = connection.execute(
                """SELECT user_id, sales_tier, region_code FROM ltc.user_account
                   WHERE account_type='sales' AND status='active'
                     AND sales_tier IS NOT NULL AND region_code IS NOT NULL
                   ORDER BY username LIMIT 1""",
            ).fetchone()
            sales_id = sales_row[0] if sales_row else None
            sales_tier = sales_row[1] if sales_row else None
            sales_region = sales_row[2] if sales_row else None
            scale_tier = {"MA": "large", "SA": "medium", "A": "small"}.get(str(sales_tier))
            if not strategic_id or not sales_id:
                raise IntegrationFailure("an active strategic account and an active sales account with region/tier are required")
            if not scale_tier:
                raise IntegrationFailure(f"unsupported sales tier for integration fixture: {sales_tier}")

            connection.execute(
                """INSERT INTO ltc.job (job_id, job_type, queue_name, aggregate_type, aggregate_id, concurrency_key, status, payload)
                   VALUES (%s,'fixture','fixture','lead_enrichment_run',%s,%s,'queued','{}'::jsonb)""",
                (ids["job"], ids["run"], f"fixture:{ids['run']}"),
            )
            connection.execute(
                """INSERT INTO ltc.lead_candidate
                   (candidate_id, dedupe_key, company_name, normalized_company_name, normalized_domain,
                    region_code, country_code, region_mapping_version, validation_status, processing_status,
                    first_seen_at, last_seen_at)
                   VALUES (%s,%s,'CRM Worker Fixture','crm worker fixture',%s,%s,'CN','region-country-v5','valid','eligible',%s,%s)""",
                (ids["candidate"], str(ids["candidate"]), f"crm-worker-{ids['candidate']}.test", sales_region, now, now),
            )
            connection.execute(
                """INSERT INTO ltc.lead_enrichment_run
                   (enrichment_run_id, candidate_id, version_no, status, scene_code, rule_version,
                    prompt_version, config_checksum, current_job_id, is_current, completed_at)
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
            for company_key, name in (("company1", "CRM Worker Fixture 1"), ("company2", "CRM Worker Fixture 2")):
                connection.execute(
                    """INSERT INTO ltc.company
                       (company_id, origin_candidate_id, company_name, normalized_company_name, primary_domain,
                        country_code, region_code, region_mapping_version, created_by)
                       VALUES (%s,%s,%s,%s,%s,'CN',%s,'region-country-v5',%s)""",
                    (ids[company_key], ids["candidate"], name, name.lower(), f"{ids[company_key]}.test", sales_region, strategic_id),
                )
            for lead_key, company_key, assigned_at in (("lead1", "company1", now), ("lead2", "company2", old_assignment)):
                connection.execute(
                    """INSERT INTO ltc.sales_lead
                       (lead_id, company_id, source_candidate_id, adopted_icp_assessment_id, adopted_scale_assessment_id,
                        required_sales_tier, pool_region_code, pool_region_mapping_version, allocation_status,
                        pipeline_stage, current_owner_user_id, current_assignment_started_at, sla_due_at, allocation_rule_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'region-country-v5','claimed','new',%s,%s,%s,'fixture')""",
                    (ids[lead_key], ids[company_key], ids["candidate"], ids["icp"], ids["scale"], sales_tier, sales_region, sales_id, assigned_at, assigned_at + timedelta(days=1)),
                )
            connection.execute(
                """INSERT INTO ltc.lead_assignment
                   (assignment_id, lead_id, assignee_user_id, assigned_by, assignment_type, status, assigned_at, sla_due_at)
                   VALUES (%s,%s,%s,%s,'claim','active',%s,%s),(%s,%s,%s,%s,'claim','active',%s,%s)""",
                (ids["assignment1"], ids["lead1"], sales_id, strategic_id, now, now + timedelta(days=1), ids["assignment2"], ids["lead2"], sales_id, strategic_id, old_assignment, old_assignment + timedelta(days=1)),
            )
            connection.execute(
                """INSERT INTO ltc.email_message
                   (email_id, company_id, lead_id, direction, purpose, status, from_address, intended_to_address, subject)
                   VALUES (%s,%s,%s,'outbound','reply_followup','sent','sales@fixture.test','customer@fixture.test','Interested')""",
                (ids["email"], ids["company1"], ids["lead1"]),
            )
            connection.execute(
                """INSERT INTO ltc.outbox_event
                   (event_id, event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload)
                   VALUES (%s,'engagement.email_replied.v1','fixture','email_message',%s,1,%s::jsonb)""",
                (ids["event"], ids["email"], '{"company_id":"%s","lead_id":"%s","email_id":"%s","intent_level":"interested","replied_at":"%s"}' % (ids["company1"], ids["lead1"], ids["email"], now.isoformat())),
            )

        consumer = EventConsumer(database)
        consumer.process_outbox_event(ids["event"])
        consumer.process_outbox_event(ids["event"])
        with database.transaction() as connection:
            stage, bonus, segment = connection.execute(
                "SELECT pipeline_stage, dynamic_bonus_points, a_segment FROM ltc.sales_lead WHERE lead_id=%s", (ids["lead1"],)
            ).fetchone()
            if (stage, int(bonus), segment) != ("engaged", 10, "A4"):
                raise IntegrationFailure(f"pipeline/dynamic intent mismatch: {(stage, bonus, segment)}")
            dynamic_event = connection.execute(
                "SELECT event_id FROM ltc.outbox_event WHERE event_type='crm.dynamic_intent_bonus_applied.v1' AND causation_id=%s", (ids["event"],)
            ).fetchone()[0]

        consumer.process_outbox_event(dynamic_event)
        consumer.process_outbox_event(dynamic_event)
        with database.transaction() as connection:
            analysis_count = scalar(connection, "SELECT count(*) FROM ltc.analysis_run WHERE lead_id=%s", (ids["lead1"],))
            task_count = scalar(connection, "SELECT count(*) FROM ltc.follow_up_task WHERE lead_id=%s", (ids["lead1"],))
            if (analysis_count, task_count) != (1, 1):
                raise IntegrationFailure(f"A4 follow-up duplication: analysis={analysis_count}, tasks={task_count}")

        released = AutoReleaseService(database).execute()
        if released != 1:
            raise IntegrationFailure(f"expected one overdue release, got {released}")
        if AutoReleaseService(database).execute() != 0:
            raise IntegrationFailure("repeated auto-release was not idempotent")
        with database.transaction() as connection:
            shape = connection.execute(
                "SELECT allocation_status, current_owner_user_id, (SELECT count(*) FROM ltc.lead_assignment WHERE lead_id=%s AND status='active') FROM ltc.sales_lead WHERE lead_id=%s",
                (ids["lead2"], ids["lead2"]),
            ).fetchone()
            event_counts = connection.execute(
                "SELECT count(*) FILTER (WHERE event_type='crm.lead_released.v1'), count(*) FILTER (WHERE event_type='notification.sales_lead_auto_released.v1') FROM ltc.outbox_event WHERE aggregate_id=%s",
                (ids["lead2"],),
            ).fetchone()
            if tuple(shape) != ("claimable", None, 0) or tuple(event_counts) != (1, 1):
                raise IntegrationFailure(f"auto-release shape mismatch: shape={shape}, events={event_counts}")
        print("PASS: Sales CRM Pipeline Consumer and Auto Release integration")
        return 0
    finally:
        lead_ids = [ids["lead1"], ids["lead2"]]
        triggers_disabled = False
        try:
            with database.transaction() as connection:
                connection.execute("ALTER TABLE ltc.lead_stage_transition DISABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
                connection.execute("ALTER TABLE ltc.lead_assignment DISABLE TRIGGER trg_lead_assignment_no_hard_delete")
            triggers_disabled = True

            with database.transaction() as connection:
                connection.execute("DELETE FROM ltc.idempotency_record WHERE scope='outbox_consume' AND principal_id IN (SELECT event_id::text FROM ltc.outbox_event WHERE aggregate_id = ANY(%s) OR event_id=%s)", (lead_ids, ids["event"]))
                connection.execute("DELETE FROM ltc.follow_up_task WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.analysis_run WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.outbox_event WHERE aggregate_id = ANY(%s) OR event_id=%s", (lead_ids, ids["event"]))
                connection.execute("DELETE FROM ltc.crm_dynamic_bonus_application WHERE lead_id = ANY(%s)", (lead_ids,))
                # These fixture rows are disposable; production history remains append-only.
                connection.execute("DELETE FROM ltc.lead_stage_transition WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.email_message WHERE email_id=%s", (ids["email"],))
                connection.execute("DELETE FROM ltc.lead_assignment WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.sales_lead WHERE lead_id = ANY(%s)", (lead_ids,))
                connection.execute("DELETE FROM ltc.lead_icp_assessment WHERE icp_assessment_id=%s", (ids["icp"],))
                connection.execute("DELETE FROM ltc.customer_scale_assessment WHERE scale_assessment_id=%s", (ids["scale"],))
                connection.execute("DELETE FROM ltc.lead_enrichment_run WHERE enrichment_run_id=%s", (ids["run"],))
                connection.execute("DELETE FROM ltc.job WHERE aggregate_id = ANY(%s) OR job_id=%s", (lead_ids, ids["job"]))
                connection.execute("DELETE FROM ltc.company WHERE company_id = ANY(%s)", ([ids["company1"], ids["company2"]],))
                connection.execute("DELETE FROM ltc.lead_candidate WHERE candidate_id=%s", (ids["candidate"],))
        finally:
            if triggers_disabled:
                with database.transaction() as connection:
                    connection.execute("ALTER TABLE ltc.lead_assignment ENABLE TRIGGER trg_lead_assignment_no_hard_delete")
                    connection.execute("ALTER TABLE ltc.lead_stage_transition ENABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
