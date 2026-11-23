"""PostgreSQL context adapter for customer analysis."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Callable, Iterator
from uuid import UUID, uuid5

from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.platform.db.customer_visibility import (
    clean_customer_company_clause,
    sales_visible_company_clause,
    sales_visible_company_params,
)


class PostgresAnalysisContextPort:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        connection = self._connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _json(value: Any) -> Any:
        try:
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        except ImportError:
            return json.dumps(value, ensure_ascii=False, default=str)

    def _query(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        *,
        all_rows: bool = False,
    ) -> Any:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query, params)
            return cursor.fetchall() if all_rows else cursor.fetchone()

    def load_context(self, company_id: UUID) -> AnalysisContext | None:
        company = self._query(
            """SELECT c.company_id, c.company_name, c.website, c.country_code,
            c.region_code, c.city, c.industry_code, c.company_intro,
            c.employee_count, c.lifecycle_status, rc.default_timezone
            FROM ltc.company c
            LEFT JOIN ltc.ref_region_country rc ON rc.country_code=c.country_code
            WHERE c.company_id=%s""",
            (company_id,),
        )
        if not company:
            return None
        lead = self._query(
            """SELECT lead_id, pipeline_stage, allocation_status,
            current_owner_user_id, first_touch_at, last_activity_at, sla_due_at,
            data_completion_pool, required_sales_tier, adopted_icp_assessment_id,
            adopted_scale_assessment_id FROM ltc.sales_lead WHERE company_id=%s
            ORDER BY updated_at DESC LIMIT 1""",
            (company_id,),
        )
        contacts = self._query(
            """SELECT contact_id, full_name, title, department, relationship_role,
            primary_email, phone, linkedin_url, last_contacted_at FROM ltc.contact
            WHERE company_id=%s AND status='active'
            ORDER BY priority NULLS LAST, updated_at DESC""",
            (company_id,),
            all_rows=True,
        )
        profile = self._query(
            """SELECT company_type, region_text, employee_scale, business_model,
            esim_scenario, coverage, estimated_usage, integration, compliance,
            budget_text, decision_maker_text, decision_cycle_text, extra_payload
            FROM ltc.customer_profile WHERE company_id=%s""",
            (company_id,),
        )
        dimensions = self._query(
            """SELECT dimension_code, level, status, summary, payload, evidence_refs
            FROM ltc.customer_meddpicc_dimension WHERE company_id=%s""",
            (company_id,),
            all_rows=True,
        )
        adopted_icp, adopted_scale = self._assessments(lead)
        company_payload = {
            "company_id": str(company[0]),
            "company_name": company[1],
            "website": company[2],
            "country": company[3],
            "region": company[4],
            "city": company[5],
            "industry": company[6],
            "company_intro": company[7],
            "employee_count": company[8],
            "lifecycle_status": company[9],
            "time_zone": company[10],
        }
        lead_payload = {}
        if lead:
            lead_payload = {
                "lead_id": str(lead[0]),
                "pipeline_stage": lead[1],
                "stage": lead[1],
                "allocation_status": lead[2],
                "owner_id": str(lead[3]) if lead[3] else None,
                "first_touch_at": lead[4].isoformat() if lead[4] else None,
                "last_activity_at": lead[5].isoformat() if lead[5] else None,
                "sla_due_at": lead[6].isoformat() if lead[6] else None,
                "data_completion_pool": lead[7],
                "required_sales_tier": lead[8],
            }
        profile_payload: dict[str, Any] = {}
        if profile:
            names = (
                "company_type", "region_text", "employee_scale", "business_model",
                "esim_scenario", "coverage", "estimated_usage", "integration",
                "compliance", "budget_text", "decision_maker_text",
                "decision_cycle_text", "extra_payload",
            )
            profile_payload = {
                name: profile[index]
                for index, name in enumerate(names)
                if profile[index] is not None
            }
            extra = dict(profile[12] or {})
            profile_payload.update(extra)
            company_payload.update(extra.get("company", {}))
            lead_payload.update(extra.get("sales_lead", {}))
        contact_payload = tuple(
            {
                "contact_id": str(row[0]), "name": row[1], "title": row[2],
                "department": row[3], "relationship_role": row[4],
                "email": row[5], "phone": row[6], "linkedin_url": row[7],
                "last_contacted_at": row[8].isoformat() if row[8] else None,
            }
            for row in contacts
        )
        meddpicc = {
            row[0]: {
                "level": row[1], "status": row[2], "summary": row[3],
                "payload": dict(row[4] or {}), "evidence_refs": list(row[5] or []),
            }
            for row in dimensions
        }
        return AnalysisContext(
            company_id=company_id,
            company=company_payload,
            sales_lead=lead_payload,
            adopted_icp=adopted_icp,
            adopted_scale=adopted_scale,
            contacts=contact_payload,
            engagement=dict(extra.get("engagement", {})) if profile else {},
            profile=profile_payload,
            meddpicc=meddpicc,
        )

    def _assessments(
        self, lead: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not lead:
            return {}, {}
        icp = self._query(
            """SELECT total_score, grade, scene_code, confidence,
            d1_score, d2_score, d3_score, d4_score,
            score_breakdown, explanations FROM ltc.lead_icp_assessment
            WHERE icp_assessment_id=%s""",
            (lead[9],),
        )
        scale = self._query(
            """SELECT total_score, computed_tier, effective_tier,
            required_sales_tier, assessment_payload
            FROM ltc.customer_scale_assessment WHERE scale_assessment_id=%s""",
            (lead[10],),
        )
        icp_payload = {}
        if icp:
            icp_payload = {
                "total_score": float(icp[0]), "grade": icp[1],
                "scene_code": icp[2],
                "confidence": float(icp[3]) if icp[3] is not None else None,
                "dimension_scores": {
                    "D1": float(icp[4]), "D2": float(icp[5]),
                    "D3": float(icp[6]), "D4": float(icp[7]),
                },
                "score_breakdown": dict(icp[8] or {}),
                "explanations": dict(icp[9] or {}),
            }
        scale_payload = {}
        if scale:
            scale_payload = {
                "total_score": float(scale[0]), "computed_tier": scale[1],
                "effective_tier": scale[2], "required_sales_tier": scale[3],
                **dict(scale[4] or {}),
            }
        return icp_payload, scale_payload

    def put_context(self, context: AnalysisContext) -> None:
        """Persist event-driven company/profile/MEDDPICC updates transactionally."""
        with self._connection() as connection:
            cursor = connection.cursor()
            company = context.company
            name = str(
                company.get("company_name") or company.get("name") or context.company_id
            )
            industry = str(
                company.get("industry_code") or company.get("industry") or "OTHER"
            ).upper()
            if industry not in {"TMC", "TRAVEL_OTA", "FINTECH", "OTHER"}:
                industry = "OTHER"
            region = str(company.get("region_code") or company.get("region") or "")
            if region not in {"NA", "EA", "SEA", "EU", "ME", "OTHER"}:
                region = None
            country = str(company.get("country_code") or company.get("country") or "").upper()
            if len(country) != 2:
                country = None
            cursor.execute(
                """INSERT INTO ltc.company (
                company_id, company_name, normalized_company_name, website,
                country_code, region_code, region_mapping_version, city,
                industry_code, company_intro)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_id) DO UPDATE SET
                company_name=EXCLUDED.company_name,
                normalized_company_name=EXCLUDED.normalized_company_name,
                website=EXCLUDED.website, country_code=EXCLUDED.country_code,
                region_code=EXCLUDED.region_code,
                region_mapping_version=EXCLUDED.region_mapping_version,
                city=EXCLUDED.city, industry_code=EXCLUDED.industry_code,
                company_intro=EXCLUDED.company_intro""",
                (
                    context.company_id, name, name.casefold(), company.get("website"),
                    country, region, "region-country-v5" if region else None,
                    company.get("city"), industry,
                    company.get("company_intro") or company.get("industry"),
                ),
            )
            self._ensure_analysis_lineage(cursor, context, name, industry, region, country)
            self._save_profile(cursor, context)
            self._save_meddpicc(cursor, context)
            self._save_contacts(cursor, context)

    def _ensure_analysis_lineage(
        self,
        cursor: Any,
        context: AnalysisContext,
        company_name: str,
        industry: str,
        region: str | None,
        country: str | None,
    ) -> None:
        cursor.execute(
            "SELECT lead_id FROM ltc.sales_lead WHERE company_id=%s LIMIT 1",
            (context.company_id,),
        )
        if cursor.fetchone():
            return
        namespace = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        candidate_id = uuid5(namespace, f"candidate:{context.company_id}")
        enrichment_id = uuid5(namespace, f"enrichment:{context.company_id}")
        enrichment_job_id = uuid5(namespace, f"enrichment-job:{context.company_id}")
        icp_id = uuid5(namespace, f"icp:{context.company_id}")
        scale_id = uuid5(namespace, f"scale:{context.company_id}")
        lead_id = uuid5(namespace, f"lead:{context.company_id}")
        score = max(0.0, min(100.0, float(context.adopted_icp.get("total_score") or 0)))
        d1, d2, d3, d4 = self._icp_components(score, "S1")
        grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 45 else "D"
        scale_score = max(0.0, min(100.0, float(context.adopted_scale.get("total_score") or context.adopted_scale.get("score") or 0)))
        sd1 = min(40.0, scale_score * 0.4)
        sd2 = min(35.0, scale_score * 0.35)
        sd3 = min(25.0, scale_score - sd1 - sd2)
        tier = str(context.adopted_scale.get("effective_tier") or context.adopted_scale.get("scale_code") or "unknown")
        if tier not in {"large", "medium", "small", "unknown"}:
            tier = "large" if scale_score >= 80 else "medium" if scale_score >= 50 else "small"
        sales_tier = {"large": "MA", "medium": "SA", "small": "A", "unknown": "A"}[tier]
        cursor.execute(
            """INSERT INTO ltc.job (job_id, job_type, queue_name, aggregate_type,
            aggregate_id, status, payload, result_summary, progress_percent, completed_at)
            VALUES (%s,'lead_enrichment','lead-intelligence','company',%s,'succeeded',
            '{}'::jsonb,'{}'::jsonb,100,clock_timestamp()) ON CONFLICT (job_id) DO NOTHING""",
            (enrichment_job_id, context.company_id),
        )
        cursor.execute(
            """INSERT INTO ltc.lead_candidate (candidate_id, dedupe_key, company_name,
            normalized_company_name, website, industry_code, region_code, country_code,
            region_mapping_version, city, validation_status, processing_status,
            first_seen_at, last_seen_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            'valid','eligible',clock_timestamp(),clock_timestamp())
            ON CONFLICT (candidate_id) DO NOTHING""",
            (candidate_id, f"customer-analysis:{context.company_id}", company_name,
             company_name.casefold(), context.company.get("website"), industry, region,
             country, "region-country-v5" if region else None, context.company.get("city")),
        )
        cursor.execute(
            """INSERT INTO ltc.lead_enrichment_run (enrichment_run_id, candidate_id,
            version_no, status, scene_code, rule_version, prompt_version, config_checksum,
            current_job_id, is_current, completed_at) VALUES (%s,%s,1,'completed','S1',
            'customer-analysis-migration','customer-analysis-v3.6',repeat('a',64),%s,true,
            clock_timestamp()) ON CONFLICT (enrichment_run_id) DO NOTHING""",
            (enrichment_id, candidate_id, enrichment_job_id),
        )
        cursor.execute(
            """INSERT INTO ltc.lead_icp_assessment (icp_assessment_id, candidate_id,
            enrichment_run_id, version_no, scene_code, rule_version, rule_snapshot,
            rule_checksum, prompt_version, d1_score, d2_score, d3_score, d4_score,
            total_score, grade, hard_gate_passed, score_breakdown, explanations,
            is_current, scored_at) VALUES (%s,%s,%s,1,'S1','customer-analysis-migration',
            '{}'::jsonb,repeat('b',64),'customer-analysis-v3.6',%s,%s,%s,%s,%s,%s,true,
            %s,'{}'::jsonb,true,clock_timestamp()) ON CONFLICT (icp_assessment_id) DO NOTHING""",
            (icp_id, candidate_id, enrichment_id, d1, d2, d3, d4, score, grade,
             self._json(context.adopted_icp.get("dimension_scores", {}))),
        )
        cursor.execute(
            """INSERT INTO ltc.customer_scale_assessment (scale_assessment_id,
            candidate_id, source_enrichment_run_id, version_no, rule_version,
            prompt_version, d1_scale_score, d2_commercial_score, d3_coverage_score,
            total_score, computed_tier, effective_tier, decision_source,
            assessment_payload, is_current, assessed_at) VALUES (%s,%s,%s,1,
            'customer-analysis-migration','customer-analysis-v3.6',%s,%s,%s,%s,%s,%s,
            'computed',%s,true,clock_timestamp()) ON CONFLICT (scale_assessment_id) DO NOTHING""",
            (scale_id, candidate_id, enrichment_id, sd1, sd2, sd3, scale_score, tier, tier,
             self._json(context.adopted_scale)),
        )
        cursor.execute(
            """INSERT INTO ltc.sales_lead (lead_id, company_id, source_candidate_id,
            adopted_icp_assessment_id, adopted_scale_assessment_id, required_sales_tier,
            pool_region_code, pool_region_mapping_version, allocation_status, pipeline_stage,
            data_completion_pool, allocation_rule_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
            'claimable',%s,%s,'customer-analysis-migration') ON CONFLICT (lead_id) DO NOTHING""",
            (lead_id, context.company_id, candidate_id, icp_id, scale_id, sales_tier,
             region, "region-country-v5" if region else None,
             self._pipeline_stage(context.sales_lead.get("pipeline_stage") or context.sales_lead.get("stage")),
             "region_unknown" if region is None else None),
        )
    @staticmethod
    def _pipeline_stage(value: Any) -> str:
        normalized = str(value or "new").lower()
        aliases = {"assigned": "new", "qualified": "engaged", "replied": "engaged", "emailed": "contacted"}
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in {"new", "contacted", "engaged", "meeting", "proposal", "won", "lost", "dormant"} else "new"

    def _save_contacts(self, cursor: Any, context: AnalysisContext) -> None:
        namespace = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        for index, contact in enumerate(context.contacts):
            name = str(contact.get("name") or contact.get("full_name") or "Unknown Contact")
            raw_id = contact.get("contact_id") or contact.get("contactId")
            try:
                contact_id = UUID(str(raw_id))
            except (TypeError, ValueError):
                contact_id = uuid5(namespace, f"contact:{context.company_id}:{raw_id or index}:{name}")
            role = str(contact.get("relationship_role") or "general_employee")
            if role not in {"decision_maker", "influencer", "executor", "general_employee"}:
                role = "general_employee"
            cursor.execute(
                """INSERT INTO ltc.contact (contact_id, company_id, full_name,
                normalized_name, title, department, relationship_role, primary_email,
                normalized_email, phone, linkedin_url, source) VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'operation')
                ON CONFLICT (contact_id) DO UPDATE SET full_name=EXCLUDED.full_name,
                normalized_name=EXCLUDED.normalized_name, title=EXCLUDED.title,
                department=EXCLUDED.department, relationship_role=EXCLUDED.relationship_role,
                primary_email=EXCLUDED.primary_email, normalized_email=EXCLUDED.normalized_email,
                phone=EXCLUDED.phone, linkedin_url=EXCLUDED.linkedin_url""",
                (contact_id, context.company_id, name, name.casefold(), contact.get("title"),
                 contact.get("department"), role, contact.get("email"),
                 str(contact.get("email") or "").casefold() or None, contact.get("phone"),
                 contact.get("linkedin_url")),
            )
    @staticmethod
    def _icp_components(score: float, scene_code: str) -> tuple[float, float, float, float]:
        weights = (0.4, 0.3, 0.2, 0.1) if scene_code == "S1" else (0.35, 0.25, 0.25, 0.15)
        first = round(score * weights[0], 2)
        second = round(score * weights[1], 2)
        third = round(score * weights[2], 2)
        fourth = round(score - first - second - third, 2)
        return first, second, third, fourth

    def _save_profile(self, cursor: Any, context: AnalysisContext) -> None:
        profile = context.profile
        if not profile:
            return
        fields = (
            "company_type", "region_text", "employee_scale", "business_model",
            "esim_scenario", "coverage", "estimated_usage", "integration",
            "compliance", "budget_text", "decision_maker_text",
            "decision_cycle_text",
        )
        cursor.execute(
            """INSERT INTO ltc.customer_profile (
            company_id, company_type, region_text, employee_scale, business_model,
            esim_scenario, coverage, estimated_usage, integration, compliance,
            budget_text, decision_maker_text, decision_cycle_text, extra_payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_id) DO UPDATE SET
            company_type=EXCLUDED.company_type, region_text=EXCLUDED.region_text,
            employee_scale=EXCLUDED.employee_scale,
            business_model=EXCLUDED.business_model,
            esim_scenario=EXCLUDED.esim_scenario, coverage=EXCLUDED.coverage,
            estimated_usage=EXCLUDED.estimated_usage,
            integration=EXCLUDED.integration, compliance=EXCLUDED.compliance,
            budget_text=EXCLUDED.budget_text,
            decision_maker_text=EXCLUDED.decision_maker_text,
            decision_cycle_text=EXCLUDED.decision_cycle_text,
            extra_payload=EXCLUDED.extra_payload""",
            (
                context.company_id,
                *(profile.get(field) for field in fields),
                self._json({
                    **dict(profile.get("extra_payload", {})),
                    "company": context.company,
                    "sales_lead": context.sales_lead,
                    "engagement": context.engagement,
                }),
            ),
        )

    def _save_meddpicc(self, cursor: Any, context: AnalysisContext) -> None:
        for code, raw in context.meddpicc.items():
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "unknown")
            if status not in {"unknown", "partial", "confirmed", "rejected"}:
                status = "partial"
            payload = raw.get("payload")
            if not isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in raw.items()
                    if key not in {"level", "status", "summary", "desc", "evidence_refs"}
                }
            cursor.execute(
                """INSERT INTO ltc.customer_meddpicc_dimension (
                company_id, dimension_code, level, status, summary, payload,
                evidence_refs) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_id, dimension_code) DO UPDATE SET
                level=EXCLUDED.level, status=EXCLUDED.status,
                summary=EXCLUDED.summary, payload=EXCLUDED.payload,
                evidence_refs=EXCLUDED.evidence_refs""",
                (
                    context.company_id, code, raw.get("level"), status,
                    raw.get("summary") or raw.get("desc"), self._json(payload),
                    self._json(raw.get("evidence_refs", [])),
                ),
            )

    def list_contexts(self, *, owner_user_id: str | None = None) -> list[AnalysisContext]:
        owner_filter = sales_visible_company_clause() if owner_user_id else ""
        clean_filter = clean_customer_company_clause()
        params = sales_visible_company_params(owner_user_id) if owner_user_id else ()
        rows = self._query(
            f"""SELECT c.company_id FROM ltc.company c WHERE c.archived_at IS NULL
            {clean_filter}
            {owner_filter}
            ORDER BY c.company_name""",
            params,
            all_rows=True,
        )
        return [
            context
            for row in rows
            if (context := self.load_context(row[0])) is not None
        ]
