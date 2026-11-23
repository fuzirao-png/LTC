from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import UUID

from ltc.modules.lead_intelligence.infrastructure.postgres_repository import PostgresLeadRepository
from ltc.modules.customer_operation.application.service import (
    CustomerOperationService,
    set_analysis_trigger,
)
from ltc.modules.sales_crm.infrastructure.pool_repository import PostgresSalesPoolRepository
from ltc.platform.db.customer_visibility import clean_customer_company_clause


class _Cursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.query = ""
        self.params: list[object] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: list[object]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple]:
        return self.rows

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def cursor(self, **kwargs: object) -> _Cursor:
        return self._cursor


class _Repository(PostgresLeadRepository):
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        super().__init__("postgresql://test")

    def _connect(self) -> _Connection:
        return self._connection


class LeadPoolDataFlowTests(unittest.TestCase):
    def test_candidate_pool_excludes_manually_promoted_rows(self) -> None:
        cursor = _Cursor([])
        repository = _Repository(_Connection(cursor))

        repository.list_candidates(limit=50)

        self.assertIn("c.processing_status <> 'promoted'", cursor.query)

    def test_analysis_pool_is_clean_unclaimed_and_exposes_version_and_size_grade(self) -> None:
        cursor = _Cursor(
            [
                (
                    "candidate-1", "Acme Travel", None, "https://acme.example", "profile",
                    "travel_ota", "Tokyo", "promoted", "JP", "EA", 800,
                    20, 20, 20, 20, 80, "A", 40, 20, 10, 70, "large",
                    [], "web_search", 7, "A",
                    {"D1": "跨境业务证据", "D2": "企业服务证据", "D3": "规模证据", "D4": "技术能力证据"},
                    "company-1", "lead-1",
                )
            ]
        )
        repository = _Repository(_Connection(cursor))

        rows = repository.list_candidates(limit=50, analysis_pool=True)

        self.assertIn("c.validation_status='valid'", cursor.query)
        self.assertIn("c.processing_status='promoted'", cursor.query)
        self.assertIn("allocation_status='claimable'", cursor.query)
        self.assertIn("sl.source_candidate_id=c.candidate_id", cursor.query)
        self.assertIn("lower(btrim(c.company_name)) NOT IN", cursor.query)
        self.assertIn("COALESCE(ia.grade, 'C') AS customer_size_grade", cursor.query)
        self.assertEqual(7, rows[0]["version"])
        self.assertEqual("A", rows[0]["customer_size_grade"])
        self.assertEqual("company-1", rows[0]["promoted_company_id"])
        self.assertEqual("lead-1", rows[0]["promoted_lead_id"])
        self.assertEqual("跨境业务证据", rows[0]["icp_score"]["explanations"]["D1"])

    def test_analysis_pool_count_uses_the_same_eligibility_filters(self) -> None:
        cursor = _Cursor([(137,)])
        repository = _Repository(_Connection(cursor))

        total = repository.count_candidates(analysis_pool=True)

        self.assertEqual(137, total)
        self.assertIn("c.validation_status='valid'", cursor.query)
        self.assertIn("c.processing_status='promoted'", cursor.query)
        self.assertIn("allocation_status='claimable'", cursor.query)
        self.assertNotIn("LIMIT", cursor.query)

    def test_sales_pool_rejects_placeholder_company_names(self) -> None:
        cursor = _Cursor([])
        repository = PostgresSalesPoolRepository()

        repository.list_claimable_for_sales(
            _Connection(cursor),
            UUID("00000000-0000-0000-0000-000000000011"),
            "EA",
            "MA",
            None,
            20,
        )

        self.assertIn("btrim(company.company_name) <> ''", cursor.query)
        self.assertIn("lower(btrim(company.company_name)) NOT IN", cursor.query)

    def test_clean_customer_clause_allows_brand_name_matching_domain_stem(self) -> None:
        clause = clean_customer_company_clause()

        self.assertIn("!~*", clause)
        self.assertNotIn("split_part", clause)


class _OperationRepository:
    pass


class _AnalysisTrigger:
    def __init__(self) -> None:
        self.updates: list[dict] = []
        self.requests: list[tuple[UUID, str]] = []

    def get_profile(self, company_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(version=3)

    def update_profile(
        self, company_id: UUID, updates: dict, *, expected_version: int, updated_by: object
    ) -> None:
        self.updates.append({"company_id": company_id, "updates": updates, "version": expected_version})

    def request_analysis(self, company_id: UUID, *, trigger_type: str, **_: object) -> None:
        self.requests.append((company_id, trigger_type))


class ManualNoteAnalysisFlowTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_analysis_trigger(None)  # type: ignore[arg-type]

    def test_confirmed_manual_note_updates_profile_and_requests_analysis(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        service.trigger_manual_note_analysis(
            {"companyId": str(company_id)},
            [
                {"dimension": "D1.采购意愿.预算区间", "extracted": "5 万美元", "selected": True},
                {"dimension": "D2.决策链.决策人", "extracted": "CFO", "selected": True},
                {"dimension": "画像结构.客户视角.关注点", "extracted": "价格与交付速度", "selected": True},
                {"dimension": "画像结构.客户视角.合作方", "extracted": "供应商 A", "selected": True},
                {"dimension": "画像结构.客户视角.觉得我们如何", "extracted": "响应及时", "selected": True},
            ],
        )

        self.assertEqual(
            {
                "budget_text": "5 万美元",
                "decision_maker_text": "CFO",
                "concerns": "价格与交付速度",
                "partners": "供应商 A",
                "impression_of_us": "响应及时",
            },
            trigger.updates[0]["updates"],
        )
        self.assertEqual([(company_id, "operation")], trigger.requests)

    def test_fallback_extractor_recognizes_customer_view_fields(self) -> None:
        from ltc.modules.customer_operation.infrastructure.manual_note_extractor import (
            ManualNoteExtractor,
        )

        extractor = object.__new__(ManualNoteExtractor)
        result = extractor._fallback_extraction(
            "客户最关注价格和交付速度，合作方是供应商 A，对我方印象是响应及时。"
        )
        fields = {item["dimension"]: item["extracted"] for item in result["fields"]}

        self.assertEqual("价格和交付速度", fields["画像结构.客户视角.关注点"])
        self.assertEqual("供应商 A", fields["画像结构.客户视角.合作方"])
        self.assertEqual("响应及时", fields["画像结构.客户视角.觉得我们如何"])


if __name__ == "__main__":
    unittest.main()
