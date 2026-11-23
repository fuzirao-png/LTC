"""PostgreSQL adapter: promotion read-port + write-port.

Implements CandidatePromotionPort and SalesLeadWritePort defined by
the lead_intelligence application layer.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from psycopg.rows import dict_row


class PostgresPromotionAdapter:
    """Single adapter that satisfies both CandidatePromotionPort and SalesLeadWritePort.

    The adapter keeps queries self-contained so it can be wired in via
    main.py alongside the existing Sales CRM and Lead Intelligence modules.
    """

    def __init__(self, database) -> None:
        self._db = database

    # ── Read side: CandidatePromotionPort ──────────────────────────

    def fetch_candidate_for_promotion(self, candidate_id: str) -> dict | None:
        with self._db.transaction() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT candidate_id, company_name, normalized_company_name,
                              website, normalized_domain, company_intro, industry_code,
                              employee_count, region_code, region_mapping_version,
                              country_code, city, processing_status, assessments_stale,
                              promoted_company_id, promoted_lead_id, promotion_result, version
                       FROM ltc.lead_candidate
                       WHERE candidate_id = %s
                       FOR UPDATE""",
                    (candidate_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def fetch_current_icp(self, candidate_id: str) -> dict | None:
        with self._db.transaction() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT icp_assessment_id, scene_code, rule_version,
                              d1_score, d2_score, d3_score, d4_score, total_score,
                              grade, hard_gate_passed, confidence, score_breakdown,
                              explanations, evidence_sources
                       FROM ltc.lead_icp_assessment
                       WHERE candidate_id = %s AND is_current = true
                       ORDER BY scored_at DESC LIMIT 1""",
                    (candidate_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def fetch_current_scale(self, candidate_id: str) -> dict | None:
        with self._db.transaction() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT scale_assessment_id, d1_scale_score, d2_commercial_score,
                              d3_coverage_score, total_score, computed_tier,
                              effective_tier
                       FROM ltc.customer_scale_assessment
                       WHERE candidate_id = %s AND is_current = true
                       ORDER BY assessed_at DESC LIMIT 1""",
                    (candidate_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def check_open_sales_lead(self, candidate_id: str) -> dict | None:
        """Check if the candidate's company already has an open (non-terminal) Sales Lead."""
        with self._db.transaction() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT sl.lead_id, sl.company_id, sl.allocation_status,
                              sl.pipeline_stage, sl.version
                       FROM ltc.sales_lead sl
                       WHERE sl.source_candidate_id = %s
                         AND sl.pipeline_stage NOT IN ('won', 'lost')
                         AND sl.allocation_status IN ('claimable', 'claimed')
                       LIMIT 1""",
                    (candidate_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    # ── Write side: SalesLeadWritePort ─────────────────────────────

    def promote_candidate(
        self,
        candidate: dict,
        icp: dict,
        scale: dict,
        actor_id: str,
        override: bool,
        override_reason: str | None,
        request_id: str,
    ) -> dict:
        now = datetime.now(timezone.utc)

        with self._db.transaction() as conn:
            # 1. Check for open reuse lead (within the same tx for atomicity)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT lead_id, company_id, allocation_status, version
                       FROM ltc.sales_lead
                       WHERE source_candidate_id = %s
                         AND pipeline_stage NOT IN ('won', 'lost')
                         AND allocation_status IN ('claimable', 'claimed')
                       LIMIT 1
                       FOR UPDATE""",
                    (candidate["candidate_id"],),
                )
                reuse = cur.fetchone()

            promotion_result = "created_lead"
            lead_id = str(uuid.uuid4())
            company_id = str(uuid.uuid4())

            if reuse:
                # Reuse open lead — do not replace adopted ICP/Scale
                lead_id = str(reuse["lead_id"])
                company_id = str(reuse["company_id"])
                promotion_result = "reused_open_lead"
            else:
                # 2. Create or reuse Company
                company_id = self._upsert_company(conn, candidate, now)

                # 3. Determine data_completion_pool
                effective_tier = str(scale.get("effective_tier") or scale.get("computed_tier") or "")
                region_code = candidate.get("region_code")
                data_completion_pool = None
                if effective_tier == "unknown" and region_code:
                    data_completion_pool = "scale_unknown"
                elif not region_code:
                    data_completion_pool = "region_unknown"

                # Require sales_tier from scale; fallback to A for unknown
                required_sales_tier = self._tier_to_sales_tier(effective_tier)

                # 4. Create Sales Lead
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO ltc.sales_lead
                           (lead_id, company_id, source_candidate_id,
                            adopted_icp_assessment_id, adopted_scale_assessment_id,
                            required_sales_tier, pool_region_code, pool_region_mapping_version,
                            allocation_status, pipeline_stage, data_completion_pool,
                            dynamic_bonus_points, allocation_rule_version, version,
                            created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'claimable','new',%s,0,'v3.6.0',0,%s,%s)""",
                        (lead_id, company_id, candidate["candidate_id"],
                         icp["icp_assessment_id"], scale["scale_assessment_id"],
                         required_sales_tier, region_code,
                         candidate.get("region_mapping_version", "v3.6.0"),
                         data_completion_pool, now, now),
                    )

            # Keep contacts synchronized even when an existing open lead is reused.
            self._promote_contacts(conn, candidate["candidate_id"], company_id, now)

            # 5. Mark candidate as promoted
            decision_source = "strategic_override" if override else "normal_selection"
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE ltc.lead_candidate
                       SET processing_status = 'promoted',
                           promoted_company_id = %s,
                           promoted_lead_id = %s,
                           selected_icp_assessment_id = %s,
                           selected_scale_assessment_id = %s,
                           promotion_result = %s,
                           promotion_decision_source = %s,
                           promotion_override_reason = %s,
                           promoted_by = %s,
                           promoted_at = %s,
                           version = version + 1
                       WHERE candidate_id = %s""",
                    (company_id, lead_id, icp["icp_assessment_id"], scale["scale_assessment_id"],
                     promotion_result, decision_source, override_reason,
                     actor_id, now, candidate["candidate_id"]),
                )

            # 6. Write outbox event
            conn.execute(
                """INSERT INTO ltc.outbox_event
                   (event_type, producer, aggregate_type, aggregate_id, aggregate_version, payload, correlation_id)
                   VALUES ('lead.promoted_to_sales_lead.v1', 'lead_intelligence',
                           'lead_candidate', %s, 1, %s::jsonb, %s)""",
                (candidate["candidate_id"],
                 json.dumps({"candidate_id": str(candidate["candidate_id"]),
                             "company_id": str(company_id), "lead_id": str(lead_id),
                             "promotion_result": promotion_result}),
                 request_id),
            )

        return {
            "company_id": company_id,
            "lead_id": lead_id,
            "icp_assessment_id": str(icp["icp_assessment_id"]),
            "scale_assessment_id": str(scale["scale_assessment_id"]),
            "promotion_result": promotion_result,
            "allocation_status": "claimable",
        }

    # ── Internal helpers ───────────────────────────────────────────

    @staticmethod
    def _upsert_company(conn, candidate: dict, now: datetime) -> str:
        """Create or reuse Company from candidate data."""
        company_name = str(candidate.get("company_name") or "")
        normalized = company_name.casefold()
        website = candidate.get("website") or ""
        # Normalize domain
        domain = None
        if website and "://" not in website:
            website = "https://" + website
        if website:
            from urllib.parse import urlparse
            domain = urlparse(website).netloc.lower().removeprefix("www.") or None

        with conn.cursor() as cur:
            # Try to match existing company by domain or normalized name
            if domain:
                cur.execute(
                    "SELECT company_id FROM ltc.company WHERE primary_domain = %s OR normalized_company_name = %s LIMIT 1",
                    (domain, normalized),
                )
            else:
                cur.execute(
                    "SELECT company_id FROM ltc.company WHERE normalized_company_name = %s LIMIT 1",
                    (normalized,),
                )
            existing = cur.fetchone()
            if existing:
                company_id = str(existing[0])
                # Update stale fields
                cur.execute(
                    """UPDATE ltc.company
                       SET website = COALESCE(NULLIF(website, ''), %s),
                           primary_domain = COALESCE(NULLIF(primary_domain, ''), %s),
                           company_intro = COALESCE(NULLIF(company_intro, ''), %s),
                           industry_code = COALESCE(NULLIF(industry_code, ''), %s),
                           employee_count = COALESCE(NULLIF(employee_count::text, ''), %s)::int,
                           region_code = COALESCE(NULLIF(region_code, ''), %s),
                           region_mapping_version = COALESCE(NULLIF(region_mapping_version, ''), %s),
                           country_code = COALESCE(NULLIF(country_code, ''), %s),
                           city = COALESCE(NULLIF(city, ''), %s),
                           version = version + 1,
                           updated_at = %s
                       WHERE company_id = %s""",
                    (website, domain, candidate.get("company_intro"),
                     candidate.get("industry_code"), candidate.get("employee_count"),
                     candidate.get("region_code"), candidate.get("region_mapping_version", "v3.6.0"),
                     candidate.get("country_code"), candidate.get("city"),
                     now, company_id),
                )
                return company_id

            # Create new company
            company_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO ltc.company
                   (company_id, origin_candidate_id, company_name, normalized_company_name,
                    legal_name, primary_domain, website, country_code, region_code,
                    region_mapping_version, city, industry_code, company_intro,
                    employee_count, lifecycle_status, version, created_by, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'prospect',0,%s,%s,%s)""",
                (company_id, candidate["candidate_id"], company_name, normalized,
                 candidate.get("legal_name"), domain, website,
                 candidate.get("country_code"), candidate.get("region_code"),
                 candidate.get("region_mapping_version", "v3.6.0"),
                 candidate.get("city"), candidate.get("industry_code"),
                 candidate.get("company_intro"), candidate.get("employee_count"),
                 candidate.get("promoted_by") or candidate.get("_actor_id"),
                 now, now),
            )
        return company_id

    @staticmethod
    def _promote_contacts(conn, candidate_id: str, company_id: str, now: datetime) -> None:
        """Copy active candidate contacts → formal contact table."""
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT candidate_contact_id, full_name, normalized_name, title,
                          title_normalized, department, relationship_role, priority,
                          email, normalized_email, email_status, email_type,
                          email_score, email_pattern, phone, linkedin_url,
                          source_payload
                   FROM ltc.candidate_contact
                   WHERE candidate_id = %s AND status = 'active'
                   ORDER BY last_seen_at DESC""",
                (candidate_id,),
            )
            contacts = cur.fetchall()

        for cc in contacts:
            name = str(cc.get("full_name") or "").strip()
            if not name:
                continue
            contact_id = str(uuid.uuid4())
            normalized_name = str(cc.get("normalized_name") or name).casefold()
            normalized_email = str(cc.get("normalized_email") or "").casefold() or None

            with conn.cursor() as cur:
                cur.execute(
                    """SELECT contact_id FROM ltc.contact
                       WHERE company_id = %s
                         AND status <> 'archived'
                         AND (
                           source_candidate_contact_id = %s
                           OR (%s::text IS NOT NULL AND normalized_email = %s)
                           OR normalized_name = %s
                         )
                       ORDER BY
                         (source_candidate_contact_id = %s) DESC,
                         (normalized_email = %s) DESC,
                         created_at DESC
                       LIMIT 1""",
                    (company_id, cc.get("candidate_contact_id"), normalized_email,
                     normalized_email, normalized_name, cc.get("candidate_contact_id"),
                     normalized_email),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE ltc.contact
                           SET source_candidate_contact_id = COALESCE(source_candidate_contact_id, %s),
                               full_name = %s,
                               normalized_name = %s,
                               title = COALESCE(%s, title),
                               title_normalized = COALESCE(%s, title_normalized),
                               department = COALESCE(%s, department),
                               relationship_role = COALESCE(%s, relationship_role),
                               priority = COALESCE(%s, priority),
                               primary_email = COALESCE(%s, primary_email),
                               normalized_email = COALESCE(%s, normalized_email),
                               email_status = COALESCE(%s, email_status),
                               email_type = COALESCE(%s, email_type),
                               email_score = COALESCE(%s, email_score),
                               email_pattern = COALESCE(%s, email_pattern),
                               phone = COALESCE(%s, phone),
                               linkedin_url = COALESCE(%s, linkedin_url),
                               updated_at = %s,
                               version = version + 1
                           WHERE contact_id = %s""",
                        (cc.get("candidate_contact_id"), name, normalized_name,
                         cc.get("title"), cc.get("title_normalized"), cc.get("department"),
                         cc.get("relationship_role"), cc.get("priority"), cc.get("email"),
                         normalized_email, cc.get("email_status"), cc.get("email_type"),
                         cc.get("email_score"), cc.get("email_pattern"), cc.get("phone"),
                         cc.get("linkedin_url"), now, existing[0]),
                    )
                    continue

            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ltc.contact
                       (contact_id, company_id, source_candidate_contact_id,
                        full_name, normalized_name, title, title_normalized,
                        department, relationship_role, priority,
                        primary_email, normalized_email, email_status,
                        email_type, email_score, email_pattern,
                        phone, linkedin_url, source, status, version, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'candidate','active',0,%s,%s)""",
                    (contact_id, company_id, cc.get("candidate_contact_id"),
                     name, normalized_name,
                     cc.get("title"), cc.get("title_normalized"),
                     cc.get("department"), cc.get("relationship_role"),
                     cc.get("priority"), cc.get("email"),
                     cc.get("normalized_email"), cc.get("email_status") or "unknown",
                     cc.get("email_type"), cc.get("email_score"),
                     cc.get("email_pattern"), cc.get("phone"),
                     cc.get("linkedin_url"), now, now),
                )

    @staticmethod
    def _tier_to_sales_tier(effective_tier: str) -> str:
        if effective_tier == "large":
            return "MA"
        if effective_tier == "medium":
            return "SA"
        return "A"

    # ── Enrichment refresh (router delegates to this) ─────────────────

    def prepare_refresh_enrichment(self, candidate_id: str) -> dict:
        """Mark candidate assessments stale, create enrichment run + job.

        Returns the identifiers and pipeline payload so the router can schedule
        the background re-run without touching SQL directly.
        """
        import uuid as _uuid
        job_id = str(_uuid.uuid4())
        enrichment_run_id = str(_uuid.uuid4())
        search_run_id = str(_uuid.uuid4())
        with self._db.transaction() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT company_name, website
                       FROM ltc.lead_candidate
                       WHERE candidate_id = %s
                       FOR UPDATE""",
                    (candidate_id,),
                )
                candidate = cur.fetchone()
            if not candidate:
                raise ValueError(f"Candidate {candidate_id} does not exist")
            company_name = str(candidate["company_name"] or "").strip()
            website = str(candidate["website"] or "").strip()
            query_text = " ".join(part for part in (company_name, website) if part)
            pipeline_payload = {
                "query_text": query_text,
                "search_mode": "both",
                "target_count": 1,
                "scene_code": "S1",
                "search_run_id": search_run_id,
                "candidate_id": candidate_id,
                "refresh": True,
            }
            conn.execute(
                """INSERT INTO ltc.job
                   (job_id, job_type, queue_name, aggregate_type, aggregate_id, status, priority,
                    payload, progress_percent, attempt_count, max_attempts, run_after,
                    created_at, updated_at, version)
                   VALUES (%s,'lead.enrichment_pipeline.v1','lead-search','lead_candidate',%s,
                           'queued',0,%s::jsonb,0,0,3,clock_timestamp(),
                           clock_timestamp(),clock_timestamp(),0)""",
                (job_id, candidate_id, json.dumps(pipeline_payload, ensure_ascii=False)),
            )
            conn.execute(
                """INSERT INTO ltc.lead_search_run
                   (search_run_id, query_text, search_mode, target_count, scene_code,
                    orchestration_profile, orchestration_profile_version, prompt_version,
                    config_checksum, status, current_job_id)
                   VALUES (%s,%s,'both',1,'S1','memory_exa_leadsfinder_exa_linkedin_parallel7',
                           '1','zh-v1',%s,'queued',%s)""",
                (search_run_id, query_text, hashlib.sha256(b"lead-intelligence-v1").hexdigest(), job_id),
            )
            conn.execute(
                "UPDATE ltc.lead_candidate SET assessments_stale=true, version=version+1 WHERE candidate_id=%s",
                (candidate_id,),
            )
            conn.execute(
                """INSERT INTO ltc.lead_enrichment_run
                   (enrichment_run_id, candidate_id, version_no, status, scene_code, rule_version,
                    prompt_version, config_checksum, current_job_id, is_current, created_at, version)
                   SELECT %s,%s,COALESCE(MAX(version_no),0)+1,'queued','S1','v3.6.0','v1',
                           '0000000000000000000000000000000000000000000000000000000000000000',
                           %s,false,clock_timestamp(),0
                   FROM ltc.lead_enrichment_run
                   WHERE candidate_id=%s""",
                (enrichment_run_id, candidate_id, job_id, candidate_id),
            )
        return {
            "enrichment_run_id": enrichment_run_id,
            "job_id": job_id,
            "search_run_id": search_run_id,
            "pipeline_payload": pipeline_payload,
        }
