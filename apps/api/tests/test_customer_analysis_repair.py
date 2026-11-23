from __future__ import annotations

import unittest
from dataclasses import replace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.enrichment import (
    build_deterministic_candidates,
    merge_candidate_sets,
)
from ltc.modules.customer_analysis.domain.field_catalog import (
    CORE_MEDDPICC_FIELDS,
    CORE_PROFILE_FIELDS,
    field_catalog_payload,
)
from ltc.modules.customer_analysis.domain.models import (
    AnalysisContext,
    AnalysisSuggestion,
)
from ltc.modules.customer_analysis.domain.output_schema import (
    CustomerAnalysisLLMOutput,
    _is_chinese_copy,
)
from ltc.modules.customer_analysis.domain.reporting import build_template_report
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    TemplateReportGenerator,
)
from ltc.modules.customer_analysis.interfaces.router import (
    build_customer_analysis_router,
)
from ltc.platform.search import _normalize_search_items


class CoreFieldContractTests(unittest.TestCase):
    def test_catalog_is_exactly_thirteen_profile_plus_four_meddpicc_fields(self) -> None:
        catalog = field_catalog_payload()
        field_ids = [
            field["id"]
            for group in catalog["groups"]
            for field in group["fields"]
        ]
        self.assertEqual(17, len(field_ids))
        self.assertEqual(
            set(CORE_PROFILE_FIELDS + CORE_MEDDPICC_FIELDS), set(field_ids)
        )
        self.assertTrue(all(
            field["collection_method"] in {"public_or_internal", "sales_confirmation"}
            and bool(field["missing_guidance"])
            for group in catalog["groups"]
            for field in group["fields"]
        ))

    def test_provider_schema_requires_every_top_level_contract_member(self) -> None:
        with self.assertRaises(ValidationError):
            CustomerAnalysisLLMOutput.model_validate({"summary": "incomplete"})
        schema = CustomerAnalysisLLMOutput.model_json_schema()
        self.assertEqual(False, schema["additionalProperties"])
        self.assertIn("customer_view", schema["required"])

    def test_customer_facing_copy_requires_chinese_narrative(self) -> None:
        self.assertTrue(_is_chinese_copy("客户需求与下一步建议"))
        self.assertTrue(_is_chinese_copy("TMC", allow_identifier=True))
        self.assertFalse(_is_chinese_copy("English-only customer summary"))


class SearchEvidenceTests(unittest.TestCase):
    def test_search_normalization_preserves_text_highlights_and_hash(self) -> None:
        result = _normalize_search_items(
            [
                {
                    "url": "https://acme.example/about",
                    "title": "Acme About",
                    "text": "Acme provides enterprise eSIM services.",
                    "highlights": ["enterprise eSIM"],
                }
            ]
        )[0]
        self.assertEqual("Acme provides enterprise eSIM services.", result["text"])
        self.assertEqual(["enterprise eSIM"], result["highlights"])
        self.assertTrue(result["evidence_id"].startswith("web:"))
        self.assertTrue(result["content_hash"].startswith("sha256:"))


class EnrichmentAndBatchReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = uuid4()
        self.contexts = InMemoryAnalysisContextPort()
        self.repository = InMemoryCustomerAnalysisRepository()
        self.context = AnalysisContext(
            company_id=self.company_id,
            company={
                "company_name": "Acme Travel",
                "industry": "Travel technology",
                "region_code": "NA",
                "employee_count": 120,
            },
            sales_lead={},
            adopted_icp={"total_score": 88},
            adopted_scale={},
        )
        self.contexts.put_context(self.context)
        self.service = CustomerAnalysisService(
            repository=self.repository,
            context_port=self.contexts,
            report_generator=TemplateReportGenerator(),
            job_port=InlineAnalysisJobPort(),
        )

    def test_deterministic_enrichment_maps_employee_count(self) -> None:
        profile, meddpicc = build_deterministic_candidates(self.context)
        self.assertEqual("51-200 人", profile["employee_scale"]["value"])
        self.assertEqual("Travel technology", profile["company_type"]["value"])
        self.assertEqual(set(CORE_MEDDPICC_FIELDS), set(meddpicc))

    def test_merge_candidates_keeps_complete_deterministic_contract(self) -> None:
        deterministic_profile, deterministic_meddpicc = build_deterministic_candidates(
            self.context
        )

        profile, meddpicc = merge_candidate_sets(
            {}, {}, deterministic_profile, deterministic_meddpicc
        )

        self.assertEqual(set(CORE_PROFILE_FIELDS), set(profile))
        self.assertEqual(set(CORE_MEDDPICC_FIELDS), set(meddpicc))

    def test_batch_accept_updates_multiple_profile_fields_once(self) -> None:
        profile = self.service.get_profile(self.company_id)
        report_id = uuid4()
        suggestions = [
            AnalysisSuggestion(
                suggestion_id=uuid4(),
                company_id=self.company_id,
                report_id=report_id,
                target_type="profile",
                dimension_code=None,
                target_path=field_id,
                target_version_at_creation=profile.version,
                current_value_snapshot=None,
                proposed_value=value,
                confidence=0.9,
            )
            for field_id, value in (
                ("business_model", "B2B SaaS"),
                ("employee_scale", "51-200 人"),
            )
        ]
        for suggestion in suggestions:
            self.repository.save_suggestion(suggestion)

        result = self.service.review_suggestions_batch(
            self.company_id,
            profile_version=profile.version,
            items=[
                {
                    "suggestion_id": suggestion.suggestion_id,
                    "suggestion_version": suggestion.version,
                    "action": "accept",
                }
                for suggestion in suggestions
            ],
        )

        updated = self.service.get_profile(self.company_id)
        self.assertEqual(profile.version + 1, updated.version)
        self.assertEqual("B2B SaaS", updated.business_model)
        self.assertEqual("51-200 人", updated.employee_scale)
        self.assertEqual(2, len(result["suggestions"]))

    def test_catalog_and_core_field_routes_expose_the_shared_contract(self) -> None:
        app = FastAPI()
        app.include_router(build_customer_analysis_router(self.service), prefix="/api/v1")
        client = TestClient(app)

        catalog = client.get("/api/v1/customer-analysis/field-catalog")
        core_fields = client.get(f"/api/v1/companies/{self.company_id}/core-fields")
        customer_list = client.get("/api/v1/api/customers/analysis/list")

        self.assertEqual(200, catalog.status_code)
        self.assertEqual(17, catalog.json()["data"]["core_field_count"])
        self.assertEqual(200, core_fields.status_code)
        self.assertEqual(17, len(core_fields.json()["data"]["fields"]))
        self.assertEqual(200, customer_list.status_code)
        list_item = customer_list.json()["list"][0]
        self.assertEqual(
            core_fields.json()["data"]["candidate_coverage"],
            list_item["reportCoverage"],
        )

    def test_new_report_replaces_stale_pending_candidate_for_same_field(self) -> None:
        profile = self.service.get_profile(self.company_id)
        stale = AnalysisSuggestion(
            suggestion_id=uuid4(),
            company_id=self.company_id,
            report_id=uuid4(),
            target_type="profile",
            dimension_code=None,
            target_path="business_model",
            target_version_at_creation=profile.version,
            current_value_snapshot=None,
            proposed_value="English business model",
            confidence=0.9,
        )
        self.repository.save_suggestion(stale)

        class ChineseCandidateGenerator:
            model_name = None

            @staticmethod
            def generate(context: AnalysisContext):
                content = build_template_report(context)
                candidates = dict(content.profile_candidates)
                candidates["business_model"] = {
                    "value": "企业差旅管理平台",
                    "confidence": 0.9,
                    "evidence_ids": [],
                }
                return replace(content, profile_candidates=candidates)

        job_port = InlineAnalysisJobPort()
        self.service.job_port = job_port
        self.service.report_generator = ChineseCandidateGenerator()
        job_port.bind(self.service.execute_analysis)

        run = self.service.request_analysis(self.company_id, force_refresh=True)
        completed = self.service.get_run(run.run_id)
        pending = self.service.list_suggestions(self.company_id)
        business_model_pending = [
            item for item in pending if item.target_path == "business_model"
        ]

        self.assertEqual("completed", completed.status)
        self.assertEqual(1, len(business_model_pending))
        self.assertEqual(
            "企业差旅管理平台", business_model_pending[0].proposed_value
        )
        self.assertEqual("rejected", self.repository.get_suggestion(stale.suggestion_id).status)


if __name__ == "__main__":
    unittest.main()
