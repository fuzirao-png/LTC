from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.enrichment import build_deterministic_candidates
from ltc.modules.customer_analysis.domain.enrichment import confirmed_manual_note_updates
from ltc.modules.customer_analysis.domain.models import AnalysisContext, EngagementEvidence
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    TemplateReportGenerator,
)


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000701")


def _manual_note(text: str) -> EngagementEvidence:
    resource_id = uuid4()
    return EngagementEvidence(
        evidence_id=f"internal-manual-note:{resource_id}",
        source_type="internal_manual_note",
        source_resource_id=str(resource_id),
        company_id=COMPANY_ID,
        occurred_at=datetime.now(timezone.utc),
        title="\u9500\u552e\u624b\u5de5\u8bb0\u5f55",
        text=text,
        content_hash=str(uuid4()),
        metadata={"note_version": 0},
    )


class ManualNoteCompetitorExtractionTests(unittest.TestCase):
    def test_confirmed_manual_fields_map_legacy_competitor_dimensions(self) -> None:
        context = AnalysisContext(
            company_id=COMPANY_ID,
            company={"company_name": "测试客户"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=(
                EngagementEvidence(
                    evidence_id="internal-manual-note:legacy",
                    source_type="internal_manual_note",
                    source_resource_id="legacy",
                    company_id=COMPANY_ID,
                    occurred_at=datetime.now(timezone.utc),
                    title="销售手工记录",
                    text="竞争对手是飞猪",
                    content_hash="legacy",
                    metadata={
                        "note_version": 1,
                        "extracted_fields": [
                            {
                                "dimension": "D2.决策链.竞争态势",
                                "extracted": "竞争对手是飞猪",
                                "selected": True,
                            }
                        ],
                    },
                ).to_dict(),
            ),
        )

        _, meddpicc = build_deterministic_candidates(context)

        self.assertIn("飞猪", meddpicc["competition"]["summary"])

    def test_confirmed_manual_fields_persist_legacy_competitor_dimensions(self) -> None:
        evidence = _manual_note("竞争对手是飞猪")
        evidence = EngagementEvidence(
            **{
                **evidence.__dict__,
                "metadata": {
                    "note_version": 1,
                    "extracted_fields": [{
                        "dimension": "D2.决策链.竞争态势",
                        "extracted": "竞争对手是飞猪",
                        "selected": True,
                    }],
                },
            }
        )
        _, meddpicc, _ = confirmed_manual_note_updates(
            AnalysisContext(
                company_id=COMPANY_ID,
                company={"company_name": "测试客户"},
                sales_lead={}, adopted_icp={}, adopted_scale={},
                evidence_refs=(evidence.to_dict(),),
            )
        )
        self.assertEqual(meddpicc["competition"]["value"], "竞争对手是飞猪")

    def test_competitor_text_is_mapped_into_competition_dimension(self) -> None:
        context = AnalysisContext(
            company_id=COMPANY_ID,
            company={"company_name": "\u6d4b\u8bd5\u5ba2\u6237"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=(
                _manual_note(
                    "\u7ade\u4e89\u5bf9\u624b\u662f\u98de\u732a"
                    "\uff0c\u5ba2\u6237\u8fd8\u5728\u6bd4\u8f83\u5176\u4ed6"
                    "\u4efb\u610f\u516c\u53f8\u3002"
                ).to_dict(),
            ),
        )

        _, meddpicc = build_deterministic_candidates(context)

        self.assertIn("\u98de\u732a", meddpicc["competition"]["summary"])

    def test_competitor_text_reaches_generated_report(self) -> None:
        company_id = UUID("00000000-0000-0000-0000-000000000702")
        note = _manual_note(
            "\u7ade\u4e89\u5bf9\u624b\u662f\u98de\u732a\uff0c\u5ba2\u6237\u8fd8\u5728\u6bd4\u8f83\u5176\u4ed6\u4efb\u610f\u516c\u53f8\u3002"
        )
        repository = InMemoryCustomerAnalysisRepository()
        contexts = InMemoryAnalysisContextPort()
        contexts.put_context(
            AnalysisContext(
                company_id=company_id,
                company={"company_id": str(company_id), "company_name": "\u6d4b\u8bd5\u5ba2\u6237"},
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )

        class EvidencePort:
            def list_email_evidence(self, company_id, *, cutoff_at, limit=50):
                return ()

            def list_confirmed_manual_note_evidence(self, company_id, *, cutoff_at, limit=100):
                return (note,)

        job_port = InlineAnalysisJobPort()
        service = CustomerAnalysisService(
            repository=repository,
            context_port=contexts,
            report_generator=TemplateReportGenerator(),
            job_port=job_port,
            engagement_evidence_port=EvidencePort(),
        )
        job_port.bind(service.execute_analysis)

        run = service.request_analysis(company_id, force_refresh=True)
        report = service.get_current_report(company_id)

        self.assertEqual(service.get_run(run.run_id).status, "completed")
        self.assertIsNotNone(report)
        self.assertIn("\u98de\u732a", report.to_dict()["competitor"]["products"][0]["name"])


if __name__ == "__main__":
    unittest.main()
