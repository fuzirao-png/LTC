#!/usr/bin/env python3
"""Seed local development database with demo users, companies, and sales leads.

Usage:
    # Inside docker container (api service):
    python -m ltc.scripts.seed_dev_data

    # Or directly via docker compose:
    docker compose exec api python -m ltc.scripts.seed_dev_data

Creates:
    - 4 demo users: 2 strategic, 2 sales (different regions/tiers)
    - 12 demo companies with ICP/scale assessments
    - 8 demo sales leads spread across region×tier pools
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg import connect
from psycopg.rows import dict_row

from ltc.modules.iam.infrastructure.passwords import Argon2PasswordVerifier
from ltc.platform.config import get_settings
from ltc.scripts.seed_helpers import (
    promote_grade_a_large_candidates,
    repair_na_large_demo_pool,
    upsert_demo_user,
)

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)

# Users: (username, password, display_name, email, account_type, sales_tier, region_code, capacity_limit)
# Users: (username, password, display_name, email, account_type, sales_tier, region_code, capacity_limit)
# 密码统一使用 123456（与原型一致，仅开发环境使用）
DEFAULT_PASSWORD = "123456"

USERS = (
    ("admin", DEFAULT_PASSWORD, "Alex", "admin@ltc.test", "strategic", None, None, None),
    ("boss.admin", DEFAULT_PASSWORD, "Alex", "boss@ltc.test", "strategic", None, None, None),
    ("strategy.ops", DEFAULT_PASSWORD, "运营总监", "ops@ltc.test", "strategic", None, None, None),
    ("li.ming", DEFAULT_PASSWORD, "李明", "liming@ltc.test", "sales", "MA", "EA", 10),
    ("wang.fang", DEFAULT_PASSWORD, "王芳", "wangfang@ltc.test", "sales", "MA", "NA", 10),
    ("zhao.lei", DEFAULT_PASSWORD, "赵磊", "zhaolei@ltc.test", "sales", "SA", "EA", 15),
    ("chen.jie", DEFAULT_PASSWORD, "陈洁", "chenjie@ltc.test", "sales", "A", "SEA", 20),
)

# Companies: (company_name, website, country_code, region_code, city, industry_code, intro)
COMPANIES = (
    ("Sakura Travel Corp", "https://www.sakuratravel.jp", "JP", "EA", "Tokyo", "TRAVEL_OTA", "Japan's leading travel platform for enterprise travel management"),
    ("Osaka Corporate Services", "https://www.osaka-cs.co.jp", "JP", "EA", "Osaka", "OTHER", "Enterprise travel solutions for mid-market companies"),
    ("Kyoto Business Travel", "https://www.kyoto-bt.jp", "JP", "EA", "Kyoto", "TRAVEL_OTA", "Legacy business travel OTA with government and enterprise clients"),
    ("Pacific TMC Japan", "https://www.pacific-tmc.jp", "JP", "EA", "Tokyo", "TMC", "Japanese corporate TMC with recent positive email reply"),
    ("TechVentures Inc", "https://www.techventures.com", "US", "NA", "San Francisco", "OTHER", "SaaS platform for enterprise procurement"),
    ("GlobalTrade Solutions", "https://www.globaltrade.com", "US", "NA", "New York", "FINTECH", "Cross-border payment and trade finance platform"),
    ("SingTel Connect", "https://www.singtelconnect.sg", "SG", "SEA", "Singapore", "OTHER", "Regional telecom provider expanding into IoT connectivity"),
    ("Bangkok Logistics Hub", "https://www.bangkoklogistics.co.th", "TH", "SEA", "Bangkok", "OTHER", "Southeast Asian logistics network operator"),
    ("Berlin Mobility GmbH", "https://www.berlinmobility.de", "DE", "EU", "Berlin", "OTHER", "EV charging infrastructure and mobility platform"),
    ("Dubai Fintech Partners", "https://www.dubaifintech.ae", "AE", "ME", "Dubai", "FINTECH", "Middle East digital payments and remittance leader"),
    ("Lagos Digital Services", "https://www.lagosdigital.ng", "NG", "OTHER", "Lagos", "OTHER", "West African digital transformation consultancy"),
    ("Mumbai Tech Park", "https://www.mumbaitechpark.in", "IN", "OTHER", "Mumbai", "OTHER", "India technology park operator with 500+ tenant companies"),
)

# Sales leads: (company_name, required_sales_tier, pool_region_code)
LEADS = (
    # EA region
    ("Sakura Travel Corp", "MA", "EA"),
    ("Osaka Corporate Services", "MA", "EA"),
    ("Kyoto Business Travel", "SA", "EA"),
    ("Pacific TMC Japan", "MA", "EA"),
    # NA region
    ("TechVentures Inc", "MA", "NA"),
    ("GlobalTrade Solutions", "SA", "NA"),
    # SEA region
    ("SingTel Connect", "A", "SEA"),
    ("Bangkok Logistics Hub", "A", "SEA"),
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if os.getenv("LTC_ENV", "local") == "production":
        print("ERROR: seed_dev_data is disabled in production", file=sys.stderr)
        sys.exit(1)

    settings = get_settings()
    hasher = Argon2PasswordVerifier()

    with connect(settings.database_dsn) as conn:
        # ---- Clean up old seed data (idempotent re-run) ----
        conn.execute("ALTER TABLE ltc.lead_assignment DISABLE TRIGGER trg_lead_assignment_no_hard_delete")
        conn.execute("ALTER TABLE ltc.lead_stage_transition DISABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
        conn.execute("ALTER TABLE ltc.lead_candidate DISABLE TRIGGER trg_lead_candidate_promotion_fact_immutable")
        conn.execute(
            """UPDATE ltc.lead_candidate
               SET processing_status='scored', promoted_company_id=NULL, promoted_lead_id=NULL,
                   selected_icp_assessment_id=NULL, selected_scale_assessment_id=NULL,
                   promotion_result=NULL, promotion_decision_source=NULL,
                   promotion_override_reason=NULL, promoted_by=NULL, promoted_at=NULL,
                   version=version + 1
               WHERE dedupe_key LIKE 'demo.%'"""
        )
        conn.execute("DELETE FROM ltc.lead_stage_transition WHERE lead_id IN (SELECT lead_id FROM ltc.sales_lead WHERE source_candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%'))")
        conn.execute("DELETE FROM ltc.lead_assignment WHERE lead_id IN (SELECT lead_id FROM ltc.sales_lead WHERE source_candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%'))")
        conn.execute("DELETE FROM ltc.sales_lead WHERE source_candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%')")
        conn.execute("DELETE FROM ltc.customer_scale_assessment WHERE candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%')")
        conn.execute("DELETE FROM ltc.lead_icp_assessment WHERE candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%')")
        conn.execute("DELETE FROM ltc.lead_enrichment_run WHERE candidate_id IN (SELECT candidate_id FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%')")
        conn.execute("DELETE FROM ltc.lead_candidate WHERE dedupe_key LIKE 'demo.%'")
        conn.execute("DELETE FROM ltc.job WHERE job_type = 'seed_demo'")
        conn.execute("ALTER TABLE ltc.lead_candidate ENABLE TRIGGER trg_lead_candidate_promotion_fact_immutable")
        conn.execute("ALTER TABLE ltc.lead_assignment ENABLE TRIGGER trg_lead_assignment_no_hard_delete")
        conn.execute("ALTER TABLE ltc.lead_stage_transition ENABLE TRIGGER trg_lead_stage_transition_no_hard_delete")
        conn.commit()

        # ---- Users ----
        print("=== Creating users ===")
        departed_usernames: list[str] = []
        for user in USERS:
            username = str(user[0])
            account_type = str(user[4])
            if upsert_demo_user(conn, hasher, user):
                print(f"  OK {username} ({account_type})")
            else:
                departed_usernames.append(username)
                print(f"  SKIP {username} ({account_type}): departed accounts are terminal")

        conn.commit()

        # Lookup created users
        user_map = {}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT user_id, username FROM ltc.user_account")
            for row in cur:
                user_map[row["username"]] = row["user_id"]

        # ---- Companies ----
        print("\n=== Creating companies ===")
        company_map: dict[str, UUID] = {}
        for company_name, website, country_code, region_code, city, industry_code, intro in COMPANIES:
            company_id = uuid4()
            conn.execute(
                """INSERT INTO ltc.company
                   (company_id, company_name, normalized_company_name, website, country_code, region_code, region_mapping_version, city, industry_code, company_intro)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (company_id, company_name, company_name.lower(), website, country_code, region_code, "v3.6.0", city, industry_code, intro),
            )
            company_map[company_name] = company_id
            print(f"  ✅ {company_name} ({region_code})")

        conn.commit()

        # Re-fetch company IDs (ON CONFLICT DO NOTHING may have skipped)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT company_id, company_name FROM ltc.company WHERE company_name = ANY(%s)",
                ([c[0] for c in COMPANIES],),
            )
            for row in cur:
                company_map[row["company_name"]] = row["company_id"]

        # ---- Enrichment runs + ICP Assessments + Scale Assessments ----
        print("\n=== Creating enrichment runs, ICP & Scale assessments ===")

        enrichment_ids: dict[str, UUID] = {}  # company_name → enrichment_run_id
        icp_ids: dict[str, UUID] = {}          # company_name → icp_assessment_id
        scale_ids: dict[str, UUID] = {}        # company_name → scale_assessment_id
        candidate_ids: dict[str, UUID] = {}    # company_name → candidate_id
        config_checksum = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"

        # Create one placeholder job for enrichment run FKs
        demo_job_id = uuid4()
        conn.execute(
            """INSERT INTO ltc.job
               (job_id, job_type, queue_name, status, priority, payload, progress_percent, attempt_count, max_attempts, run_after, completed_at, created_at, updated_at, version)
               VALUES (%s,'seed_demo','default','succeeded',0,'{}'::jsonb,100,1,1,%s,%s,%s,%s,0)
               ON CONFLICT DO NOTHING""",
            (demo_job_id, NOW, NOW, NOW, NOW),
        )

        for idx, (company_name, required_sales_tier, pool_region_code) in enumerate(LEADS):
            # --- Lead Candidate ---
            candidate_id = uuid4()
            conn.execute(
                """INSERT INTO ltc.lead_candidate
                   (candidate_id, dedupe_key, company_name, normalized_company_name, website,
                    region_code, region_mapping_version, country_code, city,
                    validation_status, processing_status, first_seen_at, last_seen_at, version)
                   VALUES (%s,%s,%s,%s,'https://example.com',%s,'v3.6.0','JP','Tokyo',
                           'valid','scored',%s,%s,0)
                   ON CONFLICT DO NOTHING""",
                (candidate_id, f"demo.{company_name.lower().replace(' ','.')}", company_name, company_name.lower(), pool_region_code, NOW, NOW),
            )
            candidate_ids[company_name] = candidate_id

            # --- Enrichment Run ---
            enrichment_id = uuid4()
            conn.execute(
                """INSERT INTO ltc.lead_enrichment_run
                   (enrichment_run_id, candidate_id, version_no, status, scene_code, rule_version,
                    prompt_version, config_checksum, current_job_id, is_current, created_at, version)
                   VALUES (%s,%s,1,'completed','S1','v3.6.0','v1',%s,%s,true,%s,0)
                   ON CONFLICT DO NOTHING""",
                (enrichment_id, candidate_id, config_checksum, demo_job_id, NOW),
            )
            enrichment_ids[company_name] = enrichment_id

            # --- ICP Assessment ---
            icp_id = uuid4()
            if required_sales_tier == "MA":
                d1, d2, d3, d4 = 35, 25, 18, 8
                total, grade = 86, "A"
            elif required_sales_tier == "SA":
                d1, d2, d3, d4 = 30, 22, 15, 7
                total, grade = 74, "B"
            else:
                d1, d2, d3, d4 = 25, 18, 12, 5
                total, grade = 60, "C"
            conn.execute(
                """INSERT INTO ltc.lead_icp_assessment
                   (icp_assessment_id, candidate_id, enrichment_run_id, version_no,
                    scene_code, rule_version, rule_snapshot, rule_checksum, prompt_version,
                    d1_score, d2_score, d3_score, d4_score, total_score,
                    grade, hard_gate_passed, score_breakdown, explanations, is_current, scored_at)
                   VALUES (%s,%s,%s,1,'S1','v3.6.0','{"scoring":"v3.6"}'::jsonb,
                           'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2',
                           'v1',%s,%s,%s,%s,%s,%s,true,%s::jsonb,%s::jsonb,true,%s)
                   ON CONFLICT DO NOTHING""",
                (icp_id, candidate_id, enrichment_id, d1, d2, d3, d4, total, grade,
                 json.dumps({"d1": d1, "d2": d2, "d3": d3, "d4": d4}),
                 json.dumps({"summary": f"Auto-scored demo lead: {grade}"}),
                 NOW),
            )
            icp_ids[company_name] = icp_id

            # --- Scale Assessment ---
            scale_id = uuid4()
            tier_scores: dict[str, tuple[int, int, int, int]] = {
                "large": (38, 33, 24, 95),
                "medium": (30, 27, 20, 77),
                "small": (20, 18, 15, 53),
            }
            scale_tier = "large" if required_sales_tier == "MA" else "medium" if required_sales_tier == "SA" else "small"
            sd1, sd2, sd3, stotal = tier_scores[scale_tier]
            conn.execute(
                """INSERT INTO ltc.customer_scale_assessment
                   (scale_assessment_id, candidate_id, source_enrichment_run_id, version_no,
                    rule_version, prompt_version, d1_scale_score, d2_commercial_score,
                    d3_coverage_score, total_score, computed_tier, effective_tier,
                    decision_source, assessment_payload, is_current, assessed_at)
                   VALUES (%s,%s,%s,1,'v3.6.0','v1',%s,%s,%s,%s,%s,%s,
                           'computed',%s::jsonb,true,%s)
                   ON CONFLICT DO NOTHING""",
                (scale_id, candidate_id, enrichment_id, sd1, sd2, sd3, stotal,
                 scale_tier, scale_tier,
                 json.dumps({"details": "Auto-scored demo lead"}),
                 NOW),
            )
            scale_ids[company_name] = scale_id
            print(f"  ✅ {company_name}: ICP={total}/{grade} scale={scale_tier} tier={required_sales_tier}")

        conn.commit()

        # ---- Sales Leads (claimable pool) ----
        print("\n=== Creating Sales Leads ===")
        for idx, (company_name, required_sales_tier, pool_region_code) in enumerate(LEADS):
            company_id = company_map.get(company_name)
            if not company_id:
                print(f"  ❌ Company not found: {company_name}")
                continue

            lead_id = uuid4()
            icp_id = icp_ids.get(company_name)
            scale_id = scale_ids.get(company_name)
            candidate_id = candidate_ids.get(company_name)
            if not icp_id or not scale_id or not candidate_id:
                print(f"  ❌ Missing dependencies for: {company_name}")
                continue

            conn.execute(
                """INSERT INTO ltc.sales_lead
                   (lead_id, company_id, source_candidate_id,
                    adopted_icp_assessment_id, adopted_scale_assessment_id,
                    required_sales_tier, pool_region_code, pool_region_mapping_version,
                    allocation_status, pipeline_stage,
                    dynamic_bonus_points, version, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'v3.6.0','claimable','new',0,0,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (lead_id, company_id, candidate_id, icp_id, scale_id,
                 required_sales_tier, pool_region_code, NOW, NOW),
            )
            print(f"  ✅ Lead: {company_name} tier={required_sales_tier} region={pool_region_code}")

        conn.commit()

        print("\n=== Promoting curated Grade A large candidates ===")
        # Seed scripts must not bypass the Application layer for production
        # code paths, but seed helpers operate directly on the database to
        # create a realistic development environment quickly (PRD §3.9 gate 6
        # validation rules enforced at the SQL layer).  The idempotent delete
        # block above ensures every re-run starts from a known state.
        promoted_pool_companies = promote_grade_a_large_candidates(conn, user_map["boss.admin"])
        for company_name in promoted_pool_companies:
            print(f"  OK {company_name}")
        print("\n=== Repairing curated NA large demo pool ===")
        for company_name in repair_na_large_demo_pool(conn):
            print(f"  OK {company_name}: MA/NA claimable")
        conn.commit()

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("SEED COMPLETE")
    print("=" * 60)
    if departed_usernames:
        print(
            "Skipped terminal departed demo accounts: "
            + ", ".join(departed_usernames)
            + ". Create a replacement sales account if that scope needs an active tester."
        )
    print("""
Accounts (password: 123456):
  boss.admin     → strategic  (IAM admin, 经营视角)
  strategy.ops   → strategic  (IAM admin, 经营视角)
  li.ming        → MA / EA    (东亚 MA 销售)
  wang.fang      → MA / NA    (北美 MA 销售)
  zhao.lei       → SA / EA    (东亚 SA 销售)
  chen.jie       → A  / SEA   (东南亚 A 销售)

Pool distribution:
  li.ming (MA/EA)    → Sakura Travel, Osaka CS, Pacific TMC  (3 MA leads in EA)
  wang.fang (MA/NA)  → TechVentures + curated ICP-A large companies in NA
  zhao.lei (SA/EA)   → Kyoto Business Travel                 (1 SA lead in EA)
  chen.jie (A/SEA)   → SingTel Connect, Bangkok Logistics    (2 A leads in SEA)

Verify: each sales user sees ONLY their region×tier pool.
""")


if __name__ == "__main__":
    main()
