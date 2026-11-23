from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from uuid import UUID, uuid4

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.enrichment import build_deterministic_candidates
from ltc.modules.customer_analysis.domain.models import AnalysisContext, EngagementEvidence
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    TemplateReportGenerator,
)
from ltc.modules.customer_analysis.infrastructure.postgres_engagement_evidence import (
    PostgresEngagementEvidenceReadPort,
    clean_communication_text,
)


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000701")
CONTACT_ID = UUID("00000000-0000-0000-0000-000000000702")
SALES_ID = UUID("00000000-0000-0000-0000-000000000703")


class _Cursor:
    def __init__(self, rows: list[tuple], statements: list[str]) -> None:
        self._rows = rows
        self._statements = statements

    def execute(self, query: str, params: tuple) -> None:
        del params
        self._statements.append(query)

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, rows: list[tuple], statements: list[str]) -> None:
        self._rows = rows
        self._statements = statements

    def cursor(self) -> _Cursor:
        return _Cursor(self._rows, self._statements)

    def close(self) -> None:
        return None


class _ConnectionFactory:
    def __init__(self, result_sets: list[list[tuple]]) -> None:
        self._result_sets = list(result_sets)
        self.statements: list[str] = []

    def __call__(self) -> _Connection:
        return _Connection(self._result_sets.pop(0), self.statements)


class _MutableEvidencePort:
    def __init__(
        self,
        emails: tuple[EngagementEvidence, ...] = (),
        notes: tuple[EngagementEvidence, ...] = (),
    ) -> None:
        self.emails = emails
        self.notes = notes

    def list_email_evidence(
        self, company_id: UUID, *, cutoff_at: datetime, limit: int = 50
    ) -> tuple[EngagementEvidence, ...]:
        del cutoff_at, limit
        return tuple(item for item in self.emails if item.company_id == company_id)

    def list_confirmed_manual_note_evidence(
        self, company_id: UUID, *, cutoff_at: datetime, limit: int = 100
    ) -> tuple[EngagementEvidence, ...]:
        del cutoff_at, limit
        return tuple(item for item in self.notes if item.company_id == company_id)


def _evidence(
    *,
    source_type: str,
    text: str,
    direction: str | None = None,
    extracted_fields: list[dict] | None = None,
    occurred_at: datetime | None = None,
) -> EngagementEvidence:
    resource_id = uuid4()
    metadata = {}
    if direction:
        metadata["direction"] = direction
    if extracted_fields is not None:
        metadata["extracted_fields"] = extracted_fields
        metadata["note_version"] = 0
    prefix = "internal-email" if source_type == "internal_email" else "internal-manual-note"
    return EngagementEvidence(
        evidence_id=f"{prefix}:{resource_id}",
        source_type=source_type,
        source_resource_id=str(resource_id),
        company_id=COMPANY_ID,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        title="客户回复" if source_type == "internal_email" else "销售手工记录",
        text=text,
        content_hash=str(uuid4()),
        metadata=metadata,
    )


class PostgresEngagementEvidenceTests(unittest.TestCase):
    def test_clean_text_removes_quoted_history_and_signature(self) -> None:
        value = "预算为 5 万美元。\r\n> 旧邮件\r\n--\r\n签名"
        self.assertEqual(clean_communication_text(value), "预算为 5 万美元。")

    def test_adapter_reads_only_valid_email_and_confirmed_note_shapes(self) -> None:
        now = datetime.now(timezone.utc)
        email_id = uuid4()
        note_id = uuid4()
        factory = _ConnectionFactory(
            [
                [
                    (
                        email_id,
                        COMPANY_ID,
                        CONTACT_ID,
                        "inbound",
                        "processed",
                        "预算确认",
                        "预算控制在 5 万美元以内。\n> 历史邮件",
                        "pricing",
                        {"source": "imap"},
                        "安排报价",
                        now,
                        1,
                        "thread-1",
                    )
                ],
                [
                    (
                        note_id,
                        COMPANY_ID,
                        SALES_ID,
                        "公司约 200 人。",
                        [{"dimension": "D4.企业画像.公司规模", "extracted": "200 人"}],
                        2,
                        now,
                        now,
                    )
                ],
            ]
        )
        adapter = PostgresEngagementEvidenceReadPort(factory)

        emails = adapter.list_email_evidence(COMPANY_ID, cutoff_at=now + timedelta(seconds=1))
        notes = adapter.list_confirmed_manual_note_evidence(
            COMPANY_ID, cutoff_at=now + timedelta(seconds=1)
        )

        self.assertEqual(emails[0].evidence_id, f"internal-email:{email_id}")
        self.assertEqual(emails[0].text, "预算控制在 5 万美元以内。")
        self.assertEqual(emails[0].metadata["direction"], "inbound")
        self.assertEqual(notes[0].evidence_id, f"internal-manual-note:{note_id}")
        self.assertEqual(notes[0].metadata["note_version"], 2)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in factory.statements))
        self.assertFalse(any("UPDATE " in statement.upper() or "DELETE " in statement.upper() for statement in factory.statements))


class EngagementCandidateTests(unittest.TestCase):
    def test_inbound_and_confirmed_note_create_candidates_but_outbound_does_not(self) -> None:
        inbound = _evidence(
            source_type="internal_email",
            direction="inbound",
            text="预算控制在 5 万美元以内，希望 9 月完成 API 接入，目前主要问题是多国流量包管理困难。",
        )
        outbound = _evidence(
            source_type="internal_email",
            direction="outbound",
            text="我方建议预算 8 万美元。",
        )
        note = _evidence(
            source_type="internal_manual_note",
            text="公司约 200 人，CFO 王经理负责预算审批。",
            extracted_fields=[
                {"dimension": "D4.企业画像.公司规模", "extracted": "200 人", "confidence": 0.9}
            ],
        )
        context = AnalysisContext(
            company_id=COMPANY_ID,
            company={"company_name": "测试客户"},
            sales_lead={},
            adopted_icp={},
            adopted_scale={},
            evidence_refs=(inbound.to_dict(), outbound.to_dict(), note.to_dict()),
        )

        profile, meddpicc = build_deterministic_candidates(context)

        self.assertIn("5 万美元", profile["budget_text"]["value"])
        self.assertNotIn("8 万美元", profile["budget_text"]["value"])
        self.assertEqual(profile["employee_scale"]["value"], "200 人")
        self.assertEqual(profile["integration"]["value"].upper(), "API")
        self.assertIn("王经理", meddpicc["economic_buyer"]["summary"])
        self.assertIn("问题", meddpicc["identify_pain"]["summary"])


class EngagementAnalysisFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryCustomerAnalysisRepository()
        self.contexts = InMemoryAnalysisContextPort()
        self.contexts.put_context(
            AnalysisContext(
                company_id=COMPANY_ID,
                company={"company_id": str(COMPANY_ID), "company_name": "测试客户"},
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )
        self.note = _evidence(
            source_type="internal_manual_note",
            text="公司约 200 人，客户明确存在多国流量包管理痛点。",
            extracted_fields=[
                {
                    "target_table": "customer_profile",
                    "target_column": "employee_scale",
                    "extracted_value": "200 人",
                    "target_version": 0,
                    "confidence": 0.9,
                },
                {
                    "target_table": "customer_profile",
                    "target_column": "compliance",
                    "extracted_value": "GDPR",
                    "target_version": 0,
                    "confidence": 0.9,
                },
                {
                    "target_table": "customer_meddpicc_dimension",
                    "target_column": "identify_pain",
                    "extracted_value": "多国流量包管理困难",
                    "target_version": 0,
                    "confidence": 0.9,
                },
            ],
        )
        self.inbound = _evidence(
            source_type="internal_email",
            direction="inbound",
            text="预算为 5 万美元，希望 9 月完成 API 接入。",
        )
        self.evidence_port = _MutableEvidencePort(
            emails=(self.inbound,), notes=(self.note,)
        )
        jobs = InlineAnalysisJobPort()
        self.service = CustomerAnalysisService(
            repository=self.repository,
            context_port=self.contexts,
            report_generator=TemplateReportGenerator(),
            job_port=jobs,
            engagement_evidence_port=self.evidence_port,
        )
        jobs.bind(self.service.execute_analysis)

    def test_confirmed_note_backfills_and_report_freezes_communication_evidence(self) -> None:
        run = self.service.request_analysis(COMPANY_ID, force_refresh=True)
        completed = self.service.get_run(run.run_id)
        profile = self.service.get_profile(COMPANY_ID)
        meddpicc = {item.dimension_code: item for item in self.service.get_meddpicc(COMPANY_ID)}
        report = self.service.get_current_report(COMPANY_ID)

        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.engagement_cutoff_at)
        self.assertEqual(profile.employee_scale, "200 人")
        self.assertEqual(profile.compliance, "GDPR")
        self.assertEqual(meddpicc["identify_pain"].status, "confirmed")
        self.assertIn("多国流量包", meddpicc["identify_pain"].summary or "")
        self.assertEqual(profile.field_provenance["employee_scale"]["source"], "confirmed_manual_note")
        self.assertIsNotNone(report)
        assert report is not None
        summary = report.to_dict()["evidence_summary"]
        self.assertEqual(summary["inbound_email_count"], 1)
        self.assertEqual(summary["manual_note_count"], 1)
        self.assertGreaterEqual(summary["grade_counts"]["A"], 1)
        self.assertGreaterEqual(summary["grade_counts"]["B"], 1)
        self.assertTrue(
            any(
                item.get("metadata", {}).get("evidence_grade") == "B"
                for item in report.to_dict()["evidence_refs"]
            )
        )
        snapshot_ids = {
            item["evidence_id"] for item in completed.input_snapshot["evidence_refs"]
        }
        self.assertIn(self.inbound.evidence_id, snapshot_ids)
        self.assertIn(self.note.evidence_id, snapshot_ids)

    def test_new_email_changes_input_hash(self) -> None:
        first = self.service.request_analysis(COMPANY_ID)
        self.evidence_port.emails += (
            _evidence(
                source_type="internal_email",
                direction="inbound",
                text="新增确认：需要 SOC 2 合规。",
                occurred_at=datetime.now(timezone.utc) + timedelta(seconds=1),
            ),
        )

        second = self.service.request_analysis(COMPANY_ID)

        self.assertNotEqual(first.input_hash, second.input_hash)
        self.assertNotEqual(first.run_id, second.run_id)

    def test_legacy_note_without_target_version_requires_review(self) -> None:
        legacy_note = _evidence(
            source_type="internal_manual_note",
            text="公司约 300 人。",
            extracted_fields=[
                {
                    "dimension": "D4.企业画像.公司规模",
                    "extracted": "300 人",
                    "confidence": 0.9,
                }
            ],
        )
        self.evidence_port.notes = (legacy_note,)

        run = self.service.request_analysis(COMPANY_ID, force_refresh=True)

        self.assertEqual(self.service.get_run(run.run_id).status, "completed")
        self.assertIsNone(self.service.get_profile(COMPANY_ID).employee_scale)
        conflict_queue = self.service.get_run(run.run_id).input_snapshot["engagement"]["conflict_queue"]
        self.assertTrue(conflict_queue)
        self.assertEqual(conflict_queue[0]["reason"], "missing_target_version")
        suggestions = self.service.list_suggestions(COMPANY_ID)
        self.assertTrue(
            any(
                item.target_type == "profile"
                and item.target_path == "employee_scale"
                and item.proposed_value == "300 人"
                for item in suggestions
            )
        )


if __name__ == "__main__":
    unittest.main()
