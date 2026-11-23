from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.customer_analysis.application.service import (
    _normalize_external_evidence,
    _research_mode_for_trigger,
)
from ltc.modules.customer_analysis.domain.models import (
    AnalysisContext,
    AnalysisRun,
    GeneratedReportContent,
)
from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    _llm_context_snapshot,
    _normalize_provider_shape,
    QueuedAnalysisJobPort,
    TemplateReportGenerator,
    OpenAICompatibleReportGenerator,
)
from ltc.modules.customer_analysis.interfaces.router import build_customer_analysis_router
from ltc.modules.customer_analysis.domain.output_schema import (
    CustomerAnalysisLLMOutput,
    ReportModuleOutput,
)
from ltc.modules.customer_analysis.domain.quality import evaluate_report_quality


class CustomerAnalysisResearchPolicyTests(unittest.TestCase):
    def test_llm_context_compacts_evidence_without_mutating_saved_sources(self) -> None:
        long_text = "A" * 5000
        evidence = ({
            "evidence_id": "exa:large",
            "source_type": "exa",
            "title": "Large source",
            "url": "https://source.test/large",
            "text": long_text,
            "highlights": ["B" * 900, "C" * 900, "D" * 900],
            "provider_debug_payload": long_text,
        },)
        context = AnalysisContext(
            company_id=UUID(int=22),
            company={"company_name": "Acme"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=evidence,
        )

        compact = _llm_context_snapshot(context)["evidence_refs"][0]

        self.assertLessEqual(len(compact["text"]), 1000)
        self.assertEqual(2, len(compact["highlights"]))
        self.assertNotIn("provider_debug_payload", compact)
        self.assertEqual(long_text, context.evidence_refs[0]["text"])

    def test_llm_context_reserves_space_for_internal_knowledge_and_web_evidence(self) -> None:
        evidence = tuple(
            {
                "evidence_id": f"{source}:{index}",
                "source_type": source,
                "text": f"source {source} {index}",
            }
            for source, count in (("internal_meeting", 6), ("weknora", 4), ("exa", 12))
            for index in range(count)
        )
        context = AnalysisContext(
            company_id=UUID(int=23),
            company={"company_name": "Acme"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=evidence,
        )

        selected = _llm_context_snapshot(context)["evidence_refs"]
        source_counts = {
            source: sum(item["source_type"] == source for item in selected)
            for source in ("internal_meeting", "weknora", "exa")
        }

        self.assertEqual(14, len(selected))
        self.assertEqual(
            {"internal_meeting": 3, "weknora": 3, "exa": 8},
            source_counts,
        )
        self.assertEqual("exa:0", selected[6]["evidence_id"])
        self.assertEqual("exa:11", selected[-1]["evidence_id"])

    def test_completion_stream_is_combined_into_one_json_document(self) -> None:
        class Delta:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.delta = Delta(content)

        class Chunk:
            def __init__(self, content: str, usage: dict | None = None) -> None:
                self.choices = [Choice(content)] if content else []
                self._usage = usage

            def model_dump(self):
                return {"usage": self._usage} if self._usage else {}

        content, raw = OpenAICompatibleReportGenerator._consume_completion_stream(
            [Chunk('{"ok":'), Chunk("true}"), Chunk("", {"completion_tokens": 2})]
        )

        self.assertEqual('{"ok":true}', content)
        self.assertTrue(raw["streamed"])
        self.assertEqual(2, raw["usage"]["completion_tokens"])

    def test_template_report_uses_distinct_external_sources_for_claims(self) -> None:
        evidence = tuple(
            {
                "evidence_id": f"exa:{index}",
                "source_type": "exa",
                "title": title,
                "text": text,
                "url": f"https://source-{index}.test/article",
            }
            for index, (title, text) in enumerate(
                (
                    ("Market forecast", "Market growth and industry trend"),
                    ("Company products", "Company business and product portfolio"),
                    ("Competitor comparison", "Competitor versus alternative pricing"),
                    ("Integration guide", "API integration security and compliance"),
                ),
                start=1,
            )
        )
        context = AnalysisContext(
            company_id=UUID(int=21),
            company={"company_name": "Acme"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=evidence,
        )

        content = TemplateReportGenerator().generate(context)
        quality = evaluate_report_quality(content.report_payload, evidence)

        self.assertEqual("passed", quality["quality_status"])
        for module_name in ("market", "company", "competitor", "pain", "product"):
            module = content.report_payload[module_name]
            self.assertEqual(3, len(module["facts"]))
            known_evidence_ids = {item["evidence_id"] for item in evidence}
            self.assertTrue(
                all(
                    fact.get("text")
                    and fact.get("evidence_ids")
                    and fact["evidence_ids"][0] in known_evidence_ids
                    for fact in module["facts"]
                )
            )
            self.assertEqual(
                3,
                len({fact["evidence_ids"][0] for fact in module["facts"]}),
            )

    def test_quality_gate_requires_two_sources_per_module(self) -> None:
        module = {
            "facts": [{"text": "fact", "evidence_ids": ["exa:a", "exa:b"]}],
            "inferences": [{"text": "inference", "evidence_ids": ["exa:a", "exa:b"]}],
            "unknowns": [{"item": "budget", "reason": "not published"}],
            "sales_recommendations": [
                {"action": "confirm", "reason": "missing", "evidence_ids": ["exa:a", "exa:b"]}
            ],
        }
        report = {name: dict(module) for name in ("market", "company", "competitor", "pain", "product")}
        evidence = (
            {"evidence_id": "exa:a", "source_type": "exa", "url": "https://one.test/a"},
            {"evidence_id": "exa:b", "source_type": "exa", "url": "https://two.test/b"},
        )

        quality = evaluate_report_quality(report, evidence)

        self.assertEqual("passed", quality["quality_status"])
        self.assertEqual(1.0, quality["source_diversity_score"])
        self.assertEqual(0, quality["unsupported_claim_count"])

    def test_quality_gate_flags_unknown_evidence_ids(self) -> None:
        module = {
            "facts": [{"text": "fact", "evidence_ids": ["exa:missing"]}],
            "inferences": [],
            "unknowns": [],
            "sales_recommendations": [],
        }
        report = {name: dict(module) for name in ("market", "company", "competitor", "pain", "product")}

        quality = evaluate_report_quality(report, ())

        self.assertEqual("needs_review", quality["quality_status"])
        self.assertEqual(5, quality["unsupported_claim_count"])

    def test_report_narrative_rejects_more_than_300_characters(self) -> None:
        with self.assertRaises(ValueError):
            ReportModuleOutput(
                summary="客" * 301,
                findings=["户" * 150],
                confidence=0.8,
            )

    def test_llm_output_normalizes_customer_view_summary_objects(self) -> None:
        narrative = "客户分析结论需要结合公开证据与内部沟通进一步验证，当前判断用于销售准备，不应替代客户确认。" * 4
        module = {
            "summary": narrative[:180],
            "findings": [narrative[:180]],
            "confidence": 0.7,
            "facts": [],
            "inferences": [],
            "unknowns": [],
            "sales_recommendations": [],
        }
        parsed = CustomerAnalysisLLMOutput.model_validate(_normalize_provider_shape({
            "schema_version": "customer-analysis-schema-v1",
            "summary": "客户分析报告已依据现有材料生成，关键判断仍需结合后续沟通持续验证。",
            "confidence": 0.7,
            "section_confidence": {
                "market": 0.7,
                "company": 0.7,
                "competitor": 0.7,
                "pain": 0.7,
                "product": 0.7,
            },
            "report": {name: module for name in ("market", "company", "competitor", "pain", "product")},
            "customer_view": {
                "concerns": {"summary": "\u4ea4\u4ed8\u5468\u671f\u4ecd\u5f85\u5ba2\u6237\u786e\u8ba4"},
                "partners": {"content": "\u5408\u4f5c\u65b9\u4fe1\u606f\u5c1a\u672a\u62ab\u9732"},
                "impression_of_us": {"text": "\u5f53\u524d\u7f3a\u5c11\u5ba2\u6237\u5bf9\u6211\u65b9\u7684\u660e\u786e\u8bc4\u4ef7"},
            },
        }))

        self.assertIsNone(parsed.profile_candidates)
        self.assertIsNone(parsed.meddpicc_candidates)
        self.assertIsNone(parsed.sales_guide)
        self.assertEqual("\u4ea4\u4ed8\u5468\u671f\u4ecd\u5f85\u5ba2\u6237\u786e\u8ba4", parsed.customer_view.concerns)

    def test_llm_output_normalizes_content_claims_and_drops_empty_unknowns(self) -> None:
        candidate = {
            "customer_view": {"concerns": None, "partners": None, "impression_of_us": None},
            "report": {
                name: {
                    "facts": [{"claim": "\u5df2\u6838\u9a8c\u4e8b\u5b9e", "evidence_ids": []}],
                    "inferences": [{"content": "\u5f85\u9a8c\u8bc1\u63a8\u65ad", "evidence_ids": []}],
                    "unknowns": [{"item": None, "reason": "\u6682\u65e0\u8bc1\u636e"}],
                }
                for name in ("market", "company", "competitor", "pain", "product")
            },
        }

        normalized = _normalize_provider_shape(candidate)

        self.assertEqual("\u5df2\u6838\u9a8c\u4e8b\u5b9e", normalized["report"]["market"]["facts"][0]["text"])
        self.assertNotIn("claim", normalized["report"]["market"]["facts"][0])
        self.assertEqual([], normalized["report"]["market"]["unknowns"])

    def test_llm_output_omits_provider_candidate_sets(self) -> None:
        normalized = _normalize_provider_shape({
            "profile_candidates": {"company_type": {"value": "TMC"}},
            "meddpicc_candidates": {"metrics": {"value": "\u5f85\u786e\u8ba4"}},
        })

        self.assertNotIn("profile_candidates", normalized)
        self.assertNotIn("meddpicc_candidates", normalized)

    def test_weknora_auto_write_requires_high_confidence_and_no_conflict(self) -> None:
        company_id = UUID(int=30)
        repository = InMemoryCustomerAnalysisRepository()
        contexts = InMemoryAnalysisContextPort()
        contexts.put_context(
            AnalysisContext(
                company_id=company_id,
                company={"company_name": "Acme"},
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )
        service = CustomerAnalysisService(
            repository=repository,
            context_port=contexts,
            report_generator=TemplateReportGenerator(),
            job_port=QueuedAnalysisJobPort(),
        )
        profile = service.get_profile(company_id)
        evidence = (
            {
                "evidence_id": "weknora:employee-scale",
                "source_type": "weknora",
                "text": "Company employee scale",
            },
        )
        candidate = {
            "value": "200-500",
            "confidence": 0.95,
            "evidence_ids": ["weknora:employee-scale"],
            "source_kind": "weknora",
            "review_status": "conflict",
        }
        content = GeneratedReportContent(
            summary="summary",
            report_payload={},
            sales_guide_payload={},
            content_source="test",
            evidence_refs=evidence,
            profile_candidates={"employee_scale": candidate},
        )

        conflicted, _ = service._apply_trusted_knowledge_candidates(content, profile, [])
        self.assertIsNone(conflicted.employee_scale)

        eligible = replace(
            content,
            profile_candidates={
                "employee_scale": {**candidate, "review_status": "pending_review"}
            },
        )
        evidence_conflicted, _ = service._apply_trusted_knowledge_candidates(
            eligible,
            profile,
            [],
            conflicts=[{"evidence_ids": ["weknora:employee-scale"]}],
        )
        self.assertIsNone(evidence_conflicted.employee_scale)

        updated, _ = service._apply_trusted_knowledge_candidates(eligible, profile, [])
        self.assertEqual("200-500", updated.employee_scale)
        self.assertEqual(
            "weknora_auto_applied",
            updated.field_provenance["employee_scale"]["source"],
        )

    def test_internal_worker_callback_is_protected_idempotent_and_uses_research_evidence(self) -> None:
        company_id = UUID(int=20)
        contexts = InMemoryAnalysisContextPort()
        contexts.put_context(
            AnalysisContext(
                company_id=company_id,
                company={"company_name": "Acme"},
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )

        class CapturingGenerator(TemplateReportGenerator):
            seen_evidence = ()

            def generate(self, context):
                self.seen_evidence = context.evidence_refs
                return super().generate(context)

        generator = CapturingGenerator()
        repository = InMemoryCustomerAnalysisRepository()
        service = CustomerAnalysisService(
            repository=repository,
            context_port=contexts,
            report_generator=generator,
            job_port=QueuedAnalysisJobPort(),
        )
        run = service.request_analysis(company_id, trigger_type="assignment")
        stored = repository.get_run(run.run_id)
        self.assertIsNotNone(stored)
        snapshot = dict(stored.input_snapshot)
        snapshot["evidence_refs"] = [
            {
                "evidence_id": "weknora:chunk-1",
                "source_type": "weknora",
                "text": "Committed research evidence",
            }
        ]
        repository.save_run(
            replace(
                stored,
                input_snapshot=snapshot,
                trigger_context={
                    **stored.trigger_context,
                    "research_job_id": str(run.current_job_id),
                    "weknora_snapshot_id": "sha256:knowledge",
                },
            )
        )

        app = FastAPI()
        app.include_router(build_customer_analysis_router(service), prefix="/api/v1")
        client = TestClient(app)
        forged_assignment = client.post(
            f"/api/v1/companies/{company_id}/analysis-runs",
            headers={"Idempotency-Key": "00000000-0000-0000-0000-000000000099"},
            json={"trigger_type": "assignment"},
        )
        self.assertEqual(403, forged_assignment.status_code)
        path = f"/api/v1/internal/analysis-runs/{run.run_id}:execute"
        with patch.dict("os.environ", {"LTC_INTERNAL_WORKER_TOKEN": "shared-secret"}):
            self.assertEqual(403, client.post(path).status_code)
            self.assertEqual(
                403,
                client.post(path, headers={"X-Worker-Token": "wrong"}).status_code,
            )
            response = client.post(path, headers={"X-Worker-Token": "shared-secret"})
            replay = client.post(path, headers={"X-Worker-Token": "shared-secret"})

        self.assertEqual(200, response.status_code)
        self.assertEqual("completed", response.json()["data"]["status"])
        self.assertEqual("completed", replay.json()["data"]["status"])
        self.assertIn(
            "weknora:chunk-1",
            {item["evidence_id"] for item in generator.seen_evidence},
        )
        report = service.get_current_report(company_id).to_dict()
        self.assertEqual("template", report["content_source"])
        self.assertEqual(
            "sha256:knowledge",
            report["research_meta"]["weknora_snapshot_id"],
        )

    def test_operation_job_payload_contains_policy_and_snapshot_reference_only(self) -> None:
        company_id = UUID(int=10)
        contexts = InMemoryAnalysisContextPort()
        contexts.put_context(
            AnalysisContext(
                company_id=company_id,
                company={"company_name": "Acme"},
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )
        jobs = InlineAnalysisJobPort()
        service = CustomerAnalysisService(
            repository=InMemoryCustomerAnalysisRepository(),
            context_port=contexts,
            report_generator=TemplateReportGenerator(),
            job_port=jobs,
        )
        run = service.request_analysis(company_id, trigger_type="operation")
        payload = jobs.submission_payloads[run.current_job_id]

        self.assertEqual("internal_only", payload["research_mode"])
        self.assertFalse(payload["external_research_allowed"])
        self.assertEqual(f"analysis_run:{run.run_id}:input_snapshot", payload["snapshot_ref"])
        self.assertNotIn("input_snapshot", payload)

    def test_only_assignment_enables_initial_external_research(self) -> None:
        self.assertEqual("initial_external", _research_mode_for_trigger("assignment", None))
        for trigger_type in ("operation", "manual", "pool_entry", "schedule", "migration"):
            self.assertEqual("internal_only", _research_mode_for_trigger(trigger_type, None))

    def test_internal_recovery_operation_enables_initial_external_research(self) -> None:
        self.assertEqual(
            "initial_external",
            _research_mode_for_trigger(
                "operation", {"recovery_external_research": True}
            ),
        )

    def test_external_flag_cannot_enable_an_internal_run(self) -> None:
        run = AnalysisRun(
            run_id=UUID(int=1),
            company_id=UUID(int=2),
            current_job_id=UUID(int=3),
            report_type="customer_analysis",
            trigger_type="operation",
            status="queued",
            input_hash="hash",
            prompt_version="prompt",
            schema_version="schema",
            model_name=None,
            profile_version=0,
            meddpicc_revision="revision",
            input_snapshot={},
            trigger_context={
                "research_mode": "internal_only",
                "external_research_allowed": True,
            },
        )
        self.assertFalse(run.external_research_allowed)

    def test_exa_rows_keep_full_text_and_content_hash(self) -> None:
        evidence = _normalize_external_evidence(
            {
                "provider": "exa",
                "id": "result-1",
                "title": "Acme profile",
                "url": "https://acme.test/about",
                "text": "Full source content",
                "highlights": ["source content"],
            }
        )
        self.assertEqual("exa:result-1", evidence["evidence_id"])
        self.assertEqual("Full source content", evidence["text"])
        self.assertTrue(evidence["content_hash"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
