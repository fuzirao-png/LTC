"""PostgreSQL repository for the lead-intelligence write boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, urlsplit, urlunsplit

from ..domain.field_mapping import normalize_company_intro, normalize_industry
from ..domain.icp_rules import ICP_SCORE_RULES, hard_gate_passed, normalize_scene_code
from ltc.platform.config import get_settings
from ltc.platform.contact_ordering import merge_contacts, sort_contacts


class PostgresLeadRepository:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL") or os.getenv("LTC_DATABASE_URL") or self._dsn_from_settings()

    @staticmethod
    def _dsn_from_settings() -> str | None:
        host = os.getenv("LTC_DB_HOST")
        if not host:
            try:
                return get_settings().database_dsn
            except Exception:
                return None
        port = os.getenv("LTC_DB_PORT", "5432")
        name = os.getenv("LTC_DB_NAME", "ltc")
        user = os.getenv("LTC_DB_USER", "ltc")
        password = os.getenv("LTC_DB_PASSWORD", "")
        sslmode = os.getenv("LTC_DB_SSLMODE", "disable")
        return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"

    def _connect(self):
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is required for lead intelligence")
        import psycopg
        conn = psycopg.connect(self.dsn)
        conn.execute("SET client_encoding TO 'UTF8'")
        return conn

    def create_search_run(self, request):
        job_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO ltc.job(job_id,job_type,queue_name,aggregate_type,aggregate_id,status,payload) VALUES (%s,%s,%s,%s,%s,'queued',%s)", (job_id, "lead.search_pipeline.v1", "lead-search", "lead_search_run", run_id, json.dumps({"query_text": request.query_text, "search_mode": request.search_mode, "target_count": request.target_count, "scene_code": request.scene_code, "search_run_id": run_id})))
                cur.execute("INSERT INTO ltc.lead_search_run(search_run_id,dialogue_session_id,query_text,search_mode,target_count,scene_code,orchestration_profile,orchestration_profile_version,prompt_version,config_checksum,status,current_job_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s)", (run_id, getattr(request, "dialogue_session_id", None), request.query_text, request.search_mode, request.target_count, request.scene_code, "memory_exa_leadsfinder_exa_linkedin_parallel7", "1", "zh-v1", hashlib.sha256(b"lead-intelligence-v1").hexdigest(), job_id))
        return run_id, job_id

    def start_search_run(self, search_run_id):
        self._execute("UPDATE ltc.lead_search_run SET status='running',started_at=clock_timestamp() WHERE search_run_id=%s", (search_run_id,))
        self._execute("""UPDATE ltc.job
            SET status='running', started_at=clock_timestamp(), progress_percent=5,
                locked_by='api-background', lock_token=gen_random_uuid(),
                locked_until=clock_timestamp() + interval '10 minutes'
            WHERE job_id=(SELECT current_job_id FROM ltc.lead_search_run WHERE search_run_id=%s)""", (search_run_id,))

    def _execute(self, sql, params=()):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def record_provider(self, **kwargs):
        # Keep provider audit writes in the same transaction boundary as the
        # module repository. The request payload is intentionally normalized.
        import time
        started = datetime.now(timezone.utc)
        payload = kwargs.get("payload") or {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO ltc.search_provider_execution(search_run_id,job_id,provider_code,provider_operation,request_hash,request_payload,status,result_count,error_message,started_at,completed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (kwargs["search_run_id"], kwargs["job_id"], kwargs["provider_code"], kwargs["operation"], hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), _jsonb(payload), kwargs.get("status", "succeeded"), kwargs.get("result_count", 0), kwargs.get("error"), started, started))

    def record_progress(self, *, job_id, event_type, step_code, message, payload=None, progress_percent=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(job_id),))
                cur.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM ltc.job_progress_event WHERE job_id=%s", (job_id,))
                sequence_no = cur.fetchone()[0]
                cur.execute("""INSERT INTO ltc.job_progress_event(job_id,sequence_no,event_type,step_code,progress_percent,message,payload) VALUES (%s,%s,%s,%s,%s,%s,%s)""", (job_id, sequence_no, event_type, step_code, progress_percent, _db_text(message), _jsonb(payload or {})))

    def update_search_run_progress(self, search_run_id, job_id, *, candidate_count, enriched_count, scored_count, progress_percent):
        self._execute(
            """UPDATE ltc.lead_search_run
                  SET candidate_count=GREATEST(candidate_count,%s),
                      enriched_count=GREATEST(enriched_count,%s),
                      scored_count=GREATEST(scored_count,%s)
                WHERE search_run_id=%s AND status='running'""",
            (candidate_count, enriched_count, scored_count, search_run_id),
        )
        self._execute(
            """UPDATE ltc.job
                  SET progress_percent=GREATEST(progress_percent,%s),updated_at=clock_timestamp()
                WHERE job_id=%s AND status='running'""",
            (progress_percent, job_id),
        )

    def record_evidence(self, **kwargs):
        item = kwargs.get("item") or {}
        raw = item if isinstance(item, dict) else {"value": str(item)}
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        url = _db_text(item.get("url"))
        provider_raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        provider_result_id = item.get("provider_result_id") or provider_raw.get("id") or provider_raw.get("result_id")
        rank_no = item.get("_rank_no")
        rank_no = rank_no if isinstance(rank_no, int) and rank_no > 0 else None
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO ltc.search_evidence(search_run_id,job_id,search_phase,attempt_no,query_text,provider_code,provider_result_id,rank_no,url,canonical_url,domain,title,snippet,raw_payload,content_hash,fetched_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) RETURNING evidence_id""", (kwargs["search_run_id"], kwargs["job_id"], kwargs["phase"], kwargs.get("attempt_no", 1), _db_text(kwargs["query"]), _db_text(kwargs["provider_code"]), _db_text(provider_result_id), rank_no, url, _canonical_url(url), _domain(url), _db_text(item.get("title")), _db_text(item.get("snippet")), _jsonb(raw), hashlib.sha256(encoded.encode()).hexdigest()))
                evidence_id = str(cur.fetchone()[0])
                cur.execute("UPDATE ltc.lead_search_run SET evidence_count=evidence_count+1 WHERE search_run_id=%s", (kwargs["search_run_id"],))
                return evidence_id

    def upsert_candidate(self, *, search_run_id, candidate):
        with self._connect() as conn:
            with conn.cursor() as cur:
                now = datetime.now(timezone.utc)
                cid = candidate.candidate_id
                domain = _domain(candidate.website)
                cur.execute("SELECT 1 FROM ltc.lead_candidate WHERE candidate_id=%s", (cid,))
                candidate_already_exists = cur.fetchone() is not None
                if domain and not candidate_already_exists:
                    cur.execute("SELECT candidate_id::text FROM ltc.lead_candidate WHERE normalized_domain=%s AND processing_status NOT IN ('merged','archived') LIMIT 1", (domain,))
                    existing = cur.fetchone()
                    if existing:
                        cid = existing[0]
                        candidate.candidate_id = cid
                cur.execute("""INSERT INTO ltc.lead_candidate(candidate_id,dedupe_key,company_name,normalized_company_name,legal_name,website,normalized_domain,company_intro,industry_code,employee_count,region_code,region_mapping_version,country_code,city,validation_status,processing_status,first_seen_at,last_seen_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'valid','enriched',%s,%s) ON CONFLICT (candidate_id) DO UPDATE SET company_name=EXCLUDED.company_name,legal_name=COALESCE(EXCLUDED.legal_name,ltc.lead_candidate.legal_name),website=COALESCE(EXCLUDED.website,ltc.lead_candidate.website),normalized_domain=COALESCE(EXCLUDED.normalized_domain,ltc.lead_candidate.normalized_domain),company_intro=COALESCE(EXCLUDED.company_intro,ltc.lead_candidate.company_intro),industry_code=COALESCE(EXCLUDED.industry_code,ltc.lead_candidate.industry_code),employee_count=COALESCE(EXCLUDED.employee_count,ltc.lead_candidate.employee_count),region_code=COALESCE(EXCLUDED.region_code,ltc.lead_candidate.region_code),region_mapping_version=COALESCE(EXCLUDED.region_mapping_version,ltc.lead_candidate.region_mapping_version),country_code=COALESCE(EXCLUDED.country_code,ltc.lead_candidate.country_code),city=COALESCE(EXCLUDED.city,ltc.lead_candidate.city),processing_status=CASE WHEN ltc.lead_candidate.processing_status IN ('promoted','eligible','rejected') THEN ltc.lead_candidate.processing_status ELSE 'enriched' END,updated_at=clock_timestamp(),last_seen_at=EXCLUDED.last_seen_at""", (cid, candidate.company_name.casefold(), candidate.company_name, candidate.company_name.casefold(), candidate.legal_name, candidate.website, domain, candidate.company_intro, candidate.industry_code, candidate.employee_count, candidate.region_code, "v1" if candidate.region_code else None, candidate.country_code, candidate.city, now, now))
                snapshot = {"company_name": candidate.company_name, "legal_name": candidate.legal_name, "website": candidate.website, "company_intro": candidate.company_intro, "industry_code": candidate.industry_code, "employee_count": candidate.employee_count, "country_code": candidate.country_code, "region_code": candidate.region_code, "city": candidate.city, "linkedin_company_url": candidate.linkedin_company_url}
                raw_payload = {"raw_ai_output": candidate.raw_ai_output, "extra_fields": candidate.extra_fields, "mapping_status": "best_effort"}
                observation_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                cur.execute("""INSERT INTO ltc.candidate_observation(candidate_id,search_run_id,source_kind,observation_hash,prompt_version,company_snapshot,contact_groups_payload,raw_extraction_payload,observed_at) VALUES (%s,%s,'live_extraction',%s,'zh-v1',%s,%s,%s,%s) ON CONFLICT (candidate_id,search_run_id,observation_hash) DO NOTHING""", (cid, search_run_id, observation_hash, _jsonb(snapshot), _jsonb({"contacts": candidate.contacts}), _jsonb(raw_payload), now))
                for contact in candidate.contacts:
                    name = str(contact.get("full_name") or contact.get("name") or "").strip()
                    if not name:
                        continue
                    identity = hashlib.sha256(name.casefold().encode()).hexdigest()
                    title = _contact_value(contact, "headline", "job_title", "jobTitle", "position", "title")
                    department = _contact_value(contact, "department", "department_name")
                    role = _contact_value(contact, "relationship_role") or "general_employee"
                    role = role if role in {"decision_maker", "influencer", "executor", "general_employee"} else "general_employee"
                    priority = _contact_value(contact, "priority")
                    priority = priority if priority in {"P1", "P2", "P3"} else None
                    email = _contact_value(contact, "email")
                    phone = _contact_value(contact, "phone", "phone_number")
                    linkedin_url = _contact_value(contact, "linkedin_url", "linkedinUrl", "url")
                    email_status = _contact_email_status(contact)
                    email_type = _contact_value(contact, "email_type", "emailType")
                    email_score = _contact_score(_contact_value(contact, "email_score", "emailScore"))
                    email_pattern = _contact_value(contact, "email_pattern", "emailPattern")
                    cur.execute("""INSERT INTO ltc.candidate_contact(candidate_id,observation_id,full_name,normalized_name,title,title_normalized,department,relationship_role,priority,email,normalized_email,email_status,email_type,email_score,email_pattern,phone,linkedin_url,identity_hash,source_payload,status,first_seen_at,last_seen_at) VALUES (%s,(SELECT observation_id FROM ltc.candidate_observation WHERE candidate_id=%s AND search_run_id=%s ORDER BY observed_at DESC LIMIT 1),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s) ON CONFLICT (candidate_id,identity_hash) DO UPDATE SET title=COALESCE(EXCLUDED.title,ltc.candidate_contact.title),title_normalized=COALESCE(EXCLUDED.title_normalized,ltc.candidate_contact.title_normalized),department=COALESCE(EXCLUDED.department,ltc.candidate_contact.department),priority=COALESCE(EXCLUDED.priority,ltc.candidate_contact.priority),email=COALESCE(EXCLUDED.email,ltc.candidate_contact.email),normalized_email=COALESCE(EXCLUDED.normalized_email,ltc.candidate_contact.normalized_email),email_status=COALESCE(EXCLUDED.email_status,ltc.candidate_contact.email_status),email_type=COALESCE(EXCLUDED.email_type,ltc.candidate_contact.email_type),email_score=COALESCE(EXCLUDED.email_score,ltc.candidate_contact.email_score),email_pattern=COALESCE(EXCLUDED.email_pattern,ltc.candidate_contact.email_pattern),phone=COALESCE(EXCLUDED.phone,ltc.candidate_contact.phone),linkedin_url=COALESCE(EXCLUDED.linkedin_url,ltc.candidate_contact.linkedin_url),source_payload=EXCLUDED.source_payload,last_seen_at=EXCLUDED.last_seen_at""", (cid, cid, search_run_id, name, name.casefold(), title, _normalized_text(title), department, role, priority, email, _normalized_email(email), email_status, email_type, email_score, email_pattern, phone, linkedin_url, identity, _jsonb(contact), now, now))

                cur.execute("SELECT observation_id FROM ltc.candidate_observation WHERE candidate_id=%s AND search_run_id=%s ORDER BY observed_at DESC LIMIT 1", (cid, search_run_id))
                observation_row = cur.fetchone()
                observation_id = observation_row[0] if observation_row else None
                for evidence in candidate.evidence:
                    evidence_id = evidence.get("_evidence_id")
                    if evidence_id:
                        cur.execute("""INSERT INTO ltc.candidate_evidence(candidate_id,evidence_id,observation_id,relation_type,confidence,is_primary) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", (cid, evidence_id, observation_id, "discovery" if evidence.get("_phase", "collection") == "collection" else "validation", None, evidence.get("_phase", "collection") == "collection"))

    def record_enrichment(self, *, search_run_id, job_id, candidate, scores, scale_scores, scene_code="S1"):
        scene_code = normalize_scene_code(scene_code)
        cid = candidate.candidate_id
        now = datetime.now(timezone.utc)
        icp = {item.dimension_code: item.score for item in scores}
        scale = {item.dimension_code: item.score for item in scale_scores}
        total = sum(icp.get(k, 0) for k in ("D1", "D2", "D3", "D4"))
        gate_passed = hard_gate_passed(icp)
        rule_snapshot = {"version": "icp-v1.0", "scene_code": scene_code, "dimensions": ICP_SCORE_RULES[scene_code]}
        rule_checksum = hashlib.sha256(json.dumps(rule_snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        evidence_ids = [str(item["_evidence_id"]) for item in candidate.evidence if item.get("_evidence_id")]
        evidence_sources = {"evidence_ids": evidence_ids} if evidence_ids else {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT enrichment_run_id::text, version_no
                       FROM ltc.lead_enrichment_run
                       WHERE candidate_id=%s AND current_job_id=%s
                         AND status IN ('queued','running')
                       FOR UPDATE""",
                    (cid, job_id),
                )
                pending_run = cur.fetchone()
                cur.execute(
                    "SELECT explanations FROM ltc.lead_icp_assessment WHERE candidate_id=%s AND is_current=true ORDER BY scored_at DESC LIMIT 1",
                    (cid,),
                )
                previous_row = cur.fetchone()
                previous_explanations = (previous_row[0] or {}) if previous_row else {}
                for dimension in scores:
                    previous = str(previous_explanations.get(dimension.dimension_code) or "")
                    if previous and len(previous) > len(dimension.explanation or "") and (
                        dimension.provider_status == "fallback" or len(dimension.explanation or "") < 80
                    ):
                        dimension.explanation = previous
                if pending_run:
                    enrichment_id, version = pending_run
                else:
                    enrichment_id = str(uuid.uuid4())
                    cur.execute("SELECT COALESCE(MAX(version_no),0)+1 FROM ltc.lead_enrichment_run WHERE candidate_id=%s", (cid,))
                    version = cur.fetchone()[0]
                cur.execute("UPDATE ltc.lead_enrichment_run SET is_current=false,status=CASE WHEN status='completed' THEN 'superseded' ELSE status END,superseded_at=clock_timestamp() WHERE candidate_id=%s AND is_current=true", (cid,))
                cur.execute("UPDATE ltc.lead_icp_assessment SET is_current=false,superseded_at=clock_timestamp() WHERE candidate_id=%s AND is_current=true", (cid,))
                cur.execute("UPDATE ltc.customer_scale_assessment SET is_current=false,superseded_at=clock_timestamp() WHERE candidate_id=%s AND is_current=true", (cid,))
                payloads = [_jsonb({"dimension_code": item.dimension_code, "score": item.score, "explanation": item.explanation, "provider_status": item.provider_status, "error_message": item.error_message}) for item in scores]
                if pending_run:
                    cur.execute(
                        """UPDATE ltc.lead_enrichment_run
                           SET status='completed', scene_code=%s, rule_version='parallel-7-v1',
                               prompt_version='zh-v1', config_checksum=%s,
                               d1_payload=%s, d2_payload=%s, d3_payload=%s, d4_payload=%s,
                               error_code=NULL, error_message=NULL, is_current=true,
                               started_at=COALESCE(started_at,%s), completed_at=%s,
                               superseded_at=NULL, version=version+1
                           WHERE enrichment_run_id=%s""",
                        (scene_code, hashlib.sha256(b"parallel-7-v1").hexdigest(), *payloads, now, now, enrichment_id),
                    )
                else:
                    cur.execute("INSERT INTO ltc.lead_enrichment_run(enrichment_run_id,candidate_id,version_no,status,scene_code,rule_version,prompt_version,config_checksum,d1_payload,d2_payload,d3_payload,d4_payload,current_job_id,is_current,started_at,completed_at) VALUES (%s,%s,%s,'completed',%s,'parallel-7-v1','zh-v1',%s,%s,%s,%s,%s,%s,true,%s,%s)", (enrichment_id, cid, version, scene_code, hashlib.sha256(b"parallel-7-v1").hexdigest(), *payloads, job_id, now, now))
                cur.execute("INSERT INTO ltc.lead_icp_assessment(candidate_id,enrichment_run_id,version_no,scene_code,rule_version,rule_snapshot,rule_checksum,prompt_version,d1_score,d2_score,d3_score,d4_score,total_score,grade,hard_gate_passed,confidence,score_breakdown,explanations,evidence_sources,job_id,is_current,scored_at) VALUES (%s,%s,%s,%s,'icp-v1.0',%s,%s,'zh-v1.0',%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,true,%s)", (cid, enrichment_id, version, scene_code, _jsonb(rule_snapshot), rule_checksum, icp.get("D1",0), icp.get("D2",0), icp.get("D3",0), icp.get("D4",0), total, _grade(total), gate_passed, _jsonb(icp), _jsonb({item.dimension_code: item.explanation for item in scores}), _jsonb(evidence_sources), job_id, now))
                scale_payload = {
                    "scores": {item.dimension_code: item.score for item in scale_scores},
                    "explanations": {item.dimension_code: item.explanation for item in scale_scores},
                    "provider_status": {item.dimension_code: item.provider_status for item in scale_scores},
                    "errors": {item.dimension_code: item.error_message for item in scale_scores if item.error_message},
                    "evidence_ids": evidence_ids,
                }
                cur.execute("INSERT INTO ltc.customer_scale_assessment(candidate_id,source_enrichment_run_id,version_no,rule_version,prompt_version,d1_scale_score,d2_commercial_score,d3_coverage_score,total_score,computed_tier,effective_tier,decision_source,assessment_payload,job_id,is_current,assessed_at) VALUES (%s,%s,%s,'parallel-7-v1','zh-v1',%s,%s,%s,%s,%s,%s,'computed',%s,%s,true,%s)", (cid, enrichment_id, version, scale.get("D1_SCALE",0), scale.get("D2_COMMERCIAL",0), scale.get("D3_COVERAGE",0), sum(scale.values()), _tier(sum(scale.values())), _tier(sum(scale.values())), _jsonb(scale_payload), job_id, now))
                cur.execute("UPDATE ltc.lead_candidate SET processing_status=CASE WHEN processing_status IN ('promoted','eligible','rejected') THEN processing_status ELSE 'scored' END,assessments_stale=false,negative_filter_result='none' WHERE candidate_id=%s", (cid,))
                cur.execute("""INSERT INTO ltc.lead_negative_filter_result(candidate_id,search_run_id,enrichment_run_id,job_id,rule_code,verdict,evidence_summary,payload,rule_version) VALUES (%s,%s,%s,%s,'none','pass',%s,%s,'negative-filter-v1')""", (cid, search_run_id, enrichment_id, job_id, "未命中负向筛选规则", _jsonb({"reason": "未命中负向筛选规则"})))
                for dimension in scores:
                    for evidence_id in evidence_ids:
                        cur.execute("""INSERT INTO ltc.enrichment_evidence(enrichment_run_id,evidence_id,dimension_code,evidence_role,confidence,excerpt) VALUES (%s,%s,%s,'supporting',NULL,%s) ON CONFLICT DO NOTHING""", (enrichment_id, evidence_id, dimension.dimension_code, dimension.explanation))
                for dimension in scale_scores:
                    for evidence_id in evidence_ids:
                        # Scale dimensions are persisted in the same evidence
                        # table; map them to the closest allowed D1-D4 code.
                        mapped = {"D1_SCALE": "D1", "D2_COMMERCIAL": "D2", "D3_COVERAGE": "D3"}.get(dimension.dimension_code, "D4")
                        cur.execute("""INSERT INTO ltc.enrichment_evidence(enrichment_run_id,evidence_id,dimension_code,evidence_role,confidence,excerpt) VALUES (%s,%s,%s,'supporting',NULL,%s) ON CONFLICT DO NOTHING""", (enrichment_id, evidence_id, mapped, dimension.explanation))

    def finish_search_run(self, search_run_id, job_id, *, status, counts, error=None):
        target = "completed" if status == "completed" else status
        job_status = (
            "cancelled" if target == "cancelled"
            else "failed_final" if target == "failed"
            else "succeeded"
        )
        self._execute("UPDATE ltc.lead_search_run SET status=%s,candidate_count=%s,enriched_count=%s,scored_count=%s,last_error_message=%s,completed_at=clock_timestamp() WHERE search_run_id=%s", (target, counts.get("candidate_count",0), counts.get("enriched_count",0), counts.get("scored_count",0), error, search_run_id))
        self._execute("""UPDATE ltc.job
            SET status=%s, progress_percent=100, completed_at=clock_timestamp(),
                last_error_message=%s, result_summary=%s,
                locked_by=NULL, lock_token=NULL, locked_until=NULL
            WHERE job_id=%s""", (job_status, error, _jsonb(counts), job_id))
        self._execute(
            """UPDATE ltc.lead_enrichment_run
                  SET status='failed', error_code='refresh_pipeline_incomplete',
                      error_message=COALESCE(%s,'Refresh pipeline did not produce the requested candidate'),
                      is_current=false, completed_at=clock_timestamp(), version=version+1
                WHERE current_job_id=%s AND status IN ('queued','running')""",
            (error, job_id),
        )

    def get_search_run(self, search_run_id):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT r.search_run_id::text,r.query_text,r.search_mode,r.target_count,
                    r.scene_code,r.status,r.current_job_id::text,r.candidate_count,r.enriched_count,
                    r.scored_count,r.last_error_message,r.created_at,r.started_at,r.completed_at,
                    j.progress_percent,
                    (SELECT e.message FROM ltc.job_progress_event e
                     WHERE e.job_id=r.current_job_id ORDER BY e.sequence_no DESC LIMIT 1)
                    FROM ltc.lead_search_run r
                    LEFT JOIN ltc.job j ON j.job_id=r.current_job_id
                    WHERE r.search_run_id=%s""", (search_run_id,))
                row = cur.fetchone()
        if not row: return None
        keys = ("search_run_id","query_text","search_mode","target_count","scene_code","status","current_job_id","candidate_count","enriched_count","scored_count","error_message","created_at","started_at","completed_at","progress_percent","progress_message")
        return dict(zip(keys,row))

    def is_search_run_cancelled(self, search_run_id):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status='cancelled' FROM ltc.lead_search_run WHERE search_run_id=%s", (search_run_id,))
                row = cur.fetchone()
        return bool(row and row[0])

    def get_run_trace(self, search_run_id):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_job_id::text FROM ltc.lead_search_run WHERE search_run_id=%s", (search_run_id,))
                row = cur.fetchone()
                if not row:
                    return None
                job_id = row[0]
                cur.execute("SELECT sequence_no,event_type,step_code,progress_percent,message,payload,created_at FROM ltc.job_progress_event WHERE job_id=%s ORDER BY sequence_no", (job_id,))
                progress = cur.fetchall()
                cur.execute("SELECT provider_code,provider_operation,status,result_count,error_message,request_payload,started_at,completed_at FROM ltc.search_provider_execution WHERE search_run_id=%s ORDER BY started_at", (search_run_id,))
                providers = cur.fetchall()
                cur.execute("SELECT e.search_phase,e.query_text,e.provider_code,e.url,e.title,e.snippet,e.raw_payload,e.fetched_at FROM ltc.search_evidence e WHERE e.search_run_id=%s ORDER BY e.fetched_at,e.evidence_id", (search_run_id,))
                evidence = cur.fetchall()
        return {
            "job_id": job_id,
            "progress": [{"sequence_no": r[0], "event_type": r[1], "step_code": r[2], "progress_percent": r[3], "message": r[4], "payload": r[5], "created_at": r[6]} for r in progress],
            "providers": [{"provider_code": r[0], "operation": r[1], "status": r[2], "result_count": r[3], "error_message": r[4], "request_payload": r[5], "started_at": r[6], "completed_at": r[7]} for r in providers],
            "evidence": [{"phase": r[0], "query": r[1], "provider_code": r[2], "url": r[3], "title": r[4], "snippet": r[5], "raw_payload": r[6], "fetched_at": r[7]} for r in evidence],
        }

    def list_candidates(self, *, search_run_id=None, limit=50, analysis_pool=False):
        sql = """
            SELECT c.candidate_id::text,c.company_name,c.legal_name,
                   COALESCE(co.website,c.website),COALESCE(src.translated_intro,co.company_intro,c.company_intro),
                   COALESCE(co.industry_code,c.industry_code),COALESCE(co.city,c.city),
                   c.processing_status,COALESCE(co.country_code,c.country_code),
                   COALESCE(co.region_code,c.region_code,(
                       SELECT rc.region_code FROM ltc.ref_region_country rc
                       WHERE rc.country_code=COALESCE(co.country_code,c.country_code)
                       LIMIT 1
                   )),COALESCE(co.employee_count,c.employee_count),
                   ia.d1_score,ia.d2_score,ia.d3_score,ia.d4_score,ia.total_score,ia.grade,
                   sa.d1_scale_score,sa.d2_commercial_score,sa.d3_coverage_score,sa.total_score,
                   sa.effective_tier,
                   COALESCE(NULLIF((SELECT COALESCE(jsonb_agg(jsonb_build_object(
                       'candidate_contact_id',cc.candidate_contact_id,
                       'full_name',cc.full_name,'title',cc.title,
                       'department',cc.department,'relationship_role',cc.relationship_role,
                       'priority',cc.priority,'email',cc.email,
                       'email_status',cc.email_status,'email_type',cc.email_type,
                       'email_score',cc.email_score,'phone',cc.phone,
                       'linkedin_url',cc.linkedin_url
                   ) ORDER BY cc.priority NULLS LAST,cc.last_seen_at DESC),'[]'::jsonb)
                    FROM ltc.candidate_contact cc
                    WHERE cc.candidate_id=c.candidate_id AND cc.status='active'), '[]'::jsonb),
                    src.observed_contacts, '[]'::jsonb) AS contacts,
                   COALESCE(src.source_channel,'legacy'),c.version,
                   CASE
                     WHEN sa.effective_tier='large' THEN 'A'
                     WHEN sa.effective_tier='medium' THEN 'B'
                     WHEN sa.effective_tier='small' THEN 'C'
                     WHEN COALESCE(co.employee_count,c.employee_count) >= 500 THEN 'A'
                     WHEN COALESCE(co.employee_count,c.employee_count) >= 100 THEN 'B'
                     WHEN COALESCE(co.employee_count,c.employee_count) IS NOT NULL THEN 'C'
                     ELSE 'C'
                   END AS customer_size_grade,
                   ia.explanations,c.promoted_company_id::text,c.promoted_lead_id::text
            FROM ltc.lead_candidate c
            LEFT JOIN LATERAL (
                SELECT company.website,company.company_intro,company.industry_code,company.city,
                       company.country_code,company.region_code,company.employee_count
                FROM ltc.company company
                WHERE company.normalized_company_name=c.normalized_company_name
                ORDER BY company.updated_at DESC LIMIT 1
            ) co ON true
            LEFT JOIN LATERAL (
                SELECT CASE
                    WHEN o.raw_extraction_payload #>> '{raw_ai_output,source}'='manual_upload'
                      OR r.query_text LIKE 'manual upload:%%' THEN 'manual_upload'
                    ELSE 'web_search'
                END AS source_channel,
                CASE
                    WHEN jsonb_typeof(o.contact_groups_payload -> 'contacts')='array'
                    THEN o.contact_groups_payload -> 'contacts'
                    ELSE '[]'::jsonb
                END AS observed_contacts,
                CASE
                    WHEN o.raw_extraction_payload #>> '{raw_ai_output,summary,company_intro}' ~ '[一-龥]'
                    THEN o.raw_extraction_payload #>> '{raw_ai_output,summary,company_intro}'
                END AS translated_intro
                FROM ltc.candidate_observation o
                LEFT JOIN ltc.lead_search_run r ON r.search_run_id=o.search_run_id
                WHERE o.candidate_id=c.candidate_id
                ORDER BY o.observed_at DESC LIMIT 1
            ) src ON true
            LEFT JOIN ltc.lead_icp_assessment ia
              ON ia.candidate_id=c.candidate_id AND ia.is_current=true
            LEFT JOIN ltc.customer_scale_assessment sa
              ON sa.candidate_id=c.candidate_id AND sa.is_current=true
        """
        predicates = [
            "c.validation_status='valid'",
            "btrim(c.company_name) <> ''",
            "lower(btrim(c.company_name)) NOT IN ('待确认','待补齐','未知','unknown','n/a','-')",
            "c.processing_status NOT IN ('merged','archived','rejected')",
        ]
        params = []
        if search_run_id:
            predicates.append("EXISTS (SELECT 1 FROM ltc.candidate_observation o WHERE o.candidate_id=c.candidate_id AND o.search_run_id=%s)")
            params.append(search_run_id)
        if analysis_pool:
            predicates.extend([
                "c.processing_status='promoted'",
                "EXISTS (SELECT 1 FROM ltc.sales_lead sl WHERE sl.source_candidate_id=c.candidate_id AND sl.allocation_status='claimable')",
            ])
        else:
            predicates.append("c.processing_status <> 'promoted'")
        sql += " WHERE " + " AND ".join(predicates)
        sql += " ORDER BY c.updated_at DESC LIMIT %s"
        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [{"candidate_id": row[0], "company_name": row[1], "legal_name": row[2], "website": row[3], "company_intro": normalize_company_intro(row[4]), "industry_code": normalize_industry(row[5], normalize_company_intro(row[4]) or "", row[1]) or row[5], "city": row[6], "status": row[7], "country_code": row[8], "region_code": row[9], "employee_count": row[10], "icp_score": {"D1": row[11], "D2": row[12], "D3": row[13], "D4": row[14], "total": row[15], "grade": row[16], "explanations": row[26]} if row[15] is not None else None, "scale_score": {"D1_SCALE": row[17], "D2_COMMERCIAL": row[18], "D3_COVERAGE": row[19], "total": row[20], "effective_tier": row[21]} if row[20] is not None else None, "contacts": [_public_contact(contact) for contact in sort_contacts(row[22] or [])], "source_channel": row[23], "version": row[24], "customer_size_grade": row[25], "promoted_company_id": row[27], "promoted_lead_id": row[28]} for row in rows]

    def count_candidates(self, *, search_run_id=None, analysis_pool=False):
        predicates = [
            "c.validation_status='valid'",
            "btrim(c.company_name) <> ''",
            "lower(btrim(c.company_name)) NOT IN ('待确认','待补齐','未知','unknown','n/a','-')",
            "c.processing_status NOT IN ('merged','archived','rejected')",
        ]
        params = []
        if search_run_id:
            predicates.append("EXISTS (SELECT 1 FROM ltc.candidate_observation o WHERE o.candidate_id=c.candidate_id AND o.search_run_id=%s)")
            params.append(search_run_id)
        if analysis_pool:
            predicates.extend([
                "c.processing_status='promoted'",
                "EXISTS (SELECT 1 FROM ltc.sales_lead sl WHERE sl.source_candidate_id=c.candidate_id AND sl.allocation_status='claimable')",
            ])
        else:
            predicates.append("c.processing_status <> 'promoted'")
        sql = "SELECT COUNT(*) FROM ltc.lead_candidate c WHERE " + " AND ".join(predicates)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        return int(row[0] or 0)

    def get_candidate(self, candidate_id):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT c.candidate_id::text,c.company_name,c.legal_name,c.website,c.company_intro,c.industry_code,c.city,c.processing_status,c.country_code,
                                      COALESCE(c.region_code,(
                                          SELECT rc.region_code FROM ltc.ref_region_country rc
                                          WHERE rc.country_code=c.country_code LIMIT 1
                                      )),c.employee_count
                               FROM ltc.lead_candidate c WHERE c.candidate_id=%s""", (candidate_id,))
                row = cur.fetchone()
                cur.execute("SELECT d1_score,d2_score,d3_score,d4_score,total_score,grade,confidence,explanations,evidence_sources FROM ltc.lead_icp_assessment WHERE candidate_id=%s AND is_current=true ORDER BY scored_at DESC LIMIT 1", (candidate_id,))
                icp = cur.fetchone()
                cur.execute("SELECT d1_scale_score,d2_commercial_score,d3_coverage_score,total_score,computed_tier,effective_tier,assessment_payload FROM ltc.customer_scale_assessment WHERE candidate_id=%s AND is_current=true ORDER BY assessed_at DESC LIMIT 1", (candidate_id,))
                scale = cur.fetchone()
                cur.execute("SELECT company_snapshot,contact_groups_payload,raw_extraction_payload,observed_at FROM ltc.candidate_observation WHERE candidate_id=%s ORDER BY observed_at DESC LIMIT 1", (candidate_id,))
                observation = cur.fetchone()
                cur.execute("SELECT candidate_contact_id::text,full_name,title,department,relationship_role,priority,email,phone,linkedin_url,email_status,email_type,email_score,source_payload FROM ltc.candidate_contact WHERE candidate_id=%s AND status='active' ORDER BY last_seen_at DESC", (candidate_id,))
                contacts = cur.fetchall()
        if not row:
            return None
        translated_intro = _translated_intro_from_observation(observation)
        company_intro = normalize_company_intro(translated_intro or row[4])
        result = {"candidate_id": row[0], "company_name": row[1], "legal_name": row[2], "website": row[3], "company_intro": company_intro, "industry_code": normalize_industry(row[5], company_intro or "", row[1]) or row[5], "city": row[6], "status": row[7], "country_code": row[8], "region_code": row[9], "employee_count": row[10]}
        if icp:
            result["icp_score"] = {"D1": icp[0], "D2": icp[1], "D3": icp[2], "D4": icp[3], "total": icp[4], "grade": icp[5], "confidence": icp[6], "explanations": icp[7], "evidence_sources": icp[8]}
        else:
            result["icp_score"] = None
        if scale:
            result["scale_score"] = {"D1_SCALE": scale[0], "D2_COMMERCIAL": scale[1], "D3_COVERAGE": scale[2], "total": scale[3], "computed_tier": scale[4], "effective_tier": scale[5], "payload": scale[6]}
        else:
            result["scale_score"] = None
        result["observation"] = {"company_snapshot": observation[0], "contact_groups_payload": observation[1], "raw_extraction_payload": observation[2], "observed_at": observation[3]} if observation else None
        persisted_contacts = [{"candidate_contact_id": r[0], "full_name": r[1], "title": r[2], "department": r[3], "relationship_role": r[4], "priority": r[5], "email": r[6], "phone": r[7], "linkedin_url": r[8], "email_status": r[9], "email_type": r[10], "email_score": r[11], "source_payload": r[12]} for r in contacts]
        observed_contacts = []
        if observation and isinstance(observation[1], dict) and isinstance(observation[1].get("contacts"), list):
            observed_contacts = observation[1]["contacts"]
        result["contacts"] = [_public_contact(contact) for contact in merge_contacts(persisted_contacts, observed_contacts)]
        return result


def _translated_intro_from_observation(observation):
    if not observation or not isinstance(observation[2], dict):
        return None
    raw_ai_output = observation[2].get("raw_ai_output")
    if not isinstance(raw_ai_output, dict):
        return None
    summary = raw_ai_output.get("summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get("company_intro")
    text = str(value or "").strip()
    return text if re.search(r"[\u3400-\u9fff]", text) else None


def _domain(value):
    if not value: return None
    text = _db_text(value)
    if "://" not in text: text = "https://" + text
    return urlparse(text).netloc.lower().removeprefix("www.") or None


def _canonical_url(value):
    if not value:
        return None
    text = _db_text(value).strip()
    if "://" not in text:
        text = "https://" + text
    parsed = urlsplit(text)
    if not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme.lower() or "https", parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def _contact_value(contact, *keys):
    raw = contact.get("raw") if isinstance(contact.get("raw"), dict) else {}
    for source in (raw, contact):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return str(value).replace("\x00", "").strip()
    return None


def _normalized_text(value):
    return " ".join(str(value or "").casefold().split()) or None


def _normalized_email(value):
    return str(value or "").strip().casefold() or None


def _contact_email_status(contact):
    value = _contact_value(contact, "email_status", "emailStatus")
    normalized = str(value or "").strip().casefold()
    aliases = {
        "verified": "valid",
        "valid": "valid",
        "unverified": "unknown",
        "unknown": "unknown",
        "invalid": "invalid",
        "risky": "risky",
        "catch_all": "risky",
    }
    if normalized in aliases:
        return aliases[normalized]
    raw = contact.get("raw") if isinstance(contact.get("raw"), dict) else {}
    valid = raw.get("email_valid")
    if valid is True:
        return "valid"
    if valid is False:
        return "invalid"
    return None


def _contact_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 100 else None


def _public_contact(contact):
    return {
        "candidate_contact_id": contact.get("candidate_contact_id"),
        "full_name": contact.get("full_name"),
        "title": contact.get("title"),
        "department": contact.get("department"),
        "relationship_role": contact.get("relationship_role"),
        "priority": contact.get("priority"),
        "email": contact.get("email"),
        "email_status": contact.get("email_status"),
        "email_type": contact.get("email_type"),
        "email_score": contact.get("email_score"),
        "phone": contact.get("phone"),
        "linkedin_url": contact.get("linkedin_url"),
    }


def _jsonb(value):
    # PostgreSQL jsonb rejects NUL (\u0000), which can appear in provider
    # page text. Remove only that storage-invalid control character while
    # preserving the rest of the raw provider response.
    value = _json_safe(value)
    try:
        from psycopg.types.json import Jsonb
        return Jsonb(value)
    except ImportError:
        return json.dumps(value, ensure_ascii=False)


def _json_safe(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_json_safe(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _db_text(value):
    return str(value or "").replace("\x00", "")


def _grade(score):
    return "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"


def _tier(score):
    return "large" if score >= 70 else "medium" if score >= 40 else "small"
