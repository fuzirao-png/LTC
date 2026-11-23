from __future__ import annotations

import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from ltc.main import create_app
from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.modules.customer_analysis.infrastructure import build_local_container
from ltc.modules.customer_analysis.infrastructure.adapters import TemplateReportGenerator


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
IDEMPOTENCY_KEY = UUID("00000000-0000-0000-0000-000000000002")


def _context() -> AnalysisContext:
    return AnalysisContext(
        company_id=COMPANY_ID,
        company={"company_name": "Acme Travel", "industry": "TMC"},
        sales_lead={"lead_id": str(uuid4()), "stage": "qualified"},
        adopted_icp={
            "total_score": 82,
            "grade": "A",
            "dimension_scores": {"D1": 32, "D2": 25, "D3": 17, "D4": 8},
        },
        adopted_scale={"scale_code": "enterprise", "score": 80},
        contacts=({"contact_id": str(uuid4()), "name": "Alex"},),
        engagement={"intent_level": "product_question", "latest_summary": "Asked about API pilot"},
        evidence_refs=({"url": "https://example.com/evidence", "title": "Evidence"},),
    )


def _local_container():
    container = build_local_container()
    container.service.search_port = None
    return container


def _test_app(container=None):
    return create_app(customer_analysis=container or _local_container())


class CustomerAnalysisDomainTests(unittest.TestCase):
    """Pure domain logic tests — no DI container, no HTTP."""

    def test_profile_finalized_computes_completeness(self) -> None:
        from ltc.modules.customer_analysis.domain.models import CustomerProfile

        p = CustomerProfile(company_id=UUID("00000000-0000-0000-0000-000000000099")).finalized()
        # All 13 fields missing → completeness near 0
        self.assertEqual(p.completeness_score, 0.0)
        self.assertEqual(len(p.missing_fields), 13)

    def test_profile_finalized_recognizes_filled_fields(self) -> None:
        from ltc.modules.customer_analysis.domain.models import CustomerProfile

        p = CustomerProfile(
            company_id=UUID("00000000-0000-0000-0000-000000000099"),
            company_type="TMC",
            business_model="B2B",
            esim_scenario="企业出差",
        ).finalized()
        # 3 of 13 filled → 3/13 ≈ 0.2308
        self.assertAlmostEqual(p.completeness_score, 3 / 13, places=3)
        self.assertEqual(len(p.missing_fields), 10)
        self.assertNotIn("company_type", p.missing_fields)

    def test_profile_patch_rejects_unknown_fields(self) -> None:
        from ltc.modules.customer_analysis.domain.models import CustomerProfile

        p = CustomerProfile(company_id=UUID("00000000-0000-0000-0000-000000000099"))
        with self.assertRaises(ValueError):
            p.patch({"not_a_real_field": 1}, expected_version=0, updated_by=None)

    def test_profile_patch_stores_customer_view_fields_in_extra_payload(self) -> None:
        from ltc.modules.customer_analysis.domain.models import CustomerProfile

        profile = CustomerProfile(company_id=UUID(int=99)).patch(
            {
                "concerns": "交付速度与价格",
                "partners": "现有供应商 A",
                "impression_of_us": "响应及时，技术能力可靠",
            },
            expected_version=0,
            updated_by=None,
        )

        self.assertEqual("交付速度与价格", profile.extra_payload["concerns"])
        self.assertEqual("现有供应商 A", profile.extra_payload["partners"])
        self.assertEqual("响应及时，技术能力可靠", profile.extra_payload["impression_of_us"])
        self.assertEqual("manual", profile.field_provenance["concerns"]["source"])

    def test_profile_structure_prefers_manual_values_then_report_values(self) -> None:
        from types import SimpleNamespace

        from ltc.modules.customer_analysis.interfaces.router import _build_profile_structure

        context = SimpleNamespace(
            meddpicc={"identify_pain": {"summary": "上下文关注点"}},
            engagement={"latest_summary": "上下文评价"},
            company={},
        )
        report = {
            "customer_view": {
                "concerns": "报告关注点",
                "partners": "报告合作方",
                "impression_of_us": "报告评价",
            }
        }

        from_report = _build_profile_structure({}, context, report)["customer_view"]
        self.assertEqual(report["customer_view"], from_report)

        manual = _build_profile_structure(
            {"extra_payload": {"concerns": "手动关注点"}}, context, report
        )["customer_view"]
        self.assertEqual("手动关注点", manual["concerns"])
        self.assertEqual("报告合作方", manual["partners"])

    def test_template_report_includes_customer_view_from_analysis_context(self) -> None:
        from dataclasses import replace

        from ltc.modules.customer_analysis.domain.reporting import build_template_report

        context = replace(
            _context(),
            profile={
                "extra_payload": {
                    "concerns": "API 稳定性",
                    "partners": "集成商 A",
                    "impression_of_us": "方案专业",
                }
            },
        )

        customer_view = build_template_report(context).report_payload["customer_view"]
        self.assertEqual("API 稳定性", customer_view["concerns"])
        self.assertEqual("集成商 A", customer_view["partners"])
        self.assertEqual("方案专业", customer_view["impression_of_us"])

    def test_structured_provider_report_preserves_customer_view(self) -> None:
        from ltc.modules.customer_analysis.infrastructure.adapters import (
            _structured_provider_report,
        )

        fallback = {"customer_view": {"partners": "待确认"}}
        report = _structured_provider_report(
            {
                "customer_view": {
                    "concerns": "交付周期",
                    "partners": "集成商 B",
                    "impression_of_us": "技术方案可靠",
                }
            },
            fallback,
        )

        self.assertEqual("交付周期", report["customer_view"]["concerns"])
        self.assertEqual("集成商 B", report["customer_view"]["partners"])
        self.assertEqual("技术方案可靠", report["customer_view"]["impression_of_us"])

    def test_competitor_evidence_replaces_placeholder_entries(self) -> None:
        from ltc.modules.customer_analysis.infrastructure.adapters import _populate_competitor_evidence

        report = {
            "competitor": {
                "products": [{"name": "待确认竞品1"}, {"name": "待确认竞品2"}],
                "pricing": [{"name": "待确认竞品1"}],
                "services": [{"name": "待确认竞品1"}],
            }
        }
        evidence = ({
            "evidence_id": "weknora:competition-1",
            "source_type": "weknora",
            "title": "竞争合作",
            "text": "Navan 是直接竞争者，Spotnana 是 Travel-as-a-Service 平台。",
        },)

        result = _populate_competitor_evidence(report, evidence)["competitor"]
        self.assertEqual(["Navan", "Spotnana"], [item["name"] for item in result["products"]])
        self.assertEqual("knowledge_supported", result["products"][0]["confirmation_status"])
        self.assertIn("weknora:competition-1", result["products"][0]["evidence_ids"])

    def test_analysis_run_guards_invalid_transitions(self) -> None:
        from ltc.modules.customer_analysis.domain.errors import InvalidStateError
        from ltc.modules.customer_analysis.domain.models import AnalysisRun, AnalysisContext

        ctx = AnalysisContext(
            company_id=UUID("00000000-0000-0000-0000-000000000099"),
            company={}, sales_lead={}, adopted_icp={}, adopted_scale={},
        )
        run = AnalysisRun(
            run_id=uuid4(), company_id=ctx.company_id, current_job_id=uuid4(),
            report_type="customer_analysis", trigger_type="manual", status="completed",
            input_hash="abc", prompt_version="v1", schema_version="v1",
            model_name=None, profile_version=0, meddpicc_revision="r1",
            input_snapshot=ctx.snapshot(),
        )
        # completed → running is not allowed
        with self.assertRaises(InvalidStateError):
            run.transition("running")
        # completed → cancelled is not allowed
        with self.assertRaises(InvalidStateError):
            run.transition("cancelled")

    def test_flattened_report_hides_internal_manual_note_ids(self) -> None:
        from ltc.modules.customer_analysis.interfaces.router import _flatten_report_sections

        report = {
            "market": {
                "scenario_demand": [
                    {
                        "scenario": "商旅",
                        "demand": "需要更低价格",
                        "evidence": "internal-manual-note:3ea5a4b8-8afa-45af-937a-a5dc3b288270",
                    }
                ]
            }
        }

        flattened = _flatten_report_sections(report)

        self.assertIn("销售手工记录", flattened["market_analysis"])
        self.assertNotIn(
            "internal-manual-note:3ea5a4b8-8afa-45af-937a-a5dc3b288270",
            flattened["market_analysis"],
        )

    def test_analysis_run_allows_valid_transitions(self) -> None:
        from ltc.modules.customer_analysis.domain.models import AnalysisRun, AnalysisContext

        ctx = AnalysisContext(
            company_id=UUID("00000000-0000-0000-0000-000000000099"),
            company={}, sales_lead={}, adopted_icp={}, adopted_scale={},
        )
        run = AnalysisRun(
            run_id=uuid4(), company_id=ctx.company_id, current_job_id=uuid4(),
            report_type="customer_analysis", trigger_type="manual", status="queued",
            input_hash="abc", prompt_version="v1", schema_version="v1",
            model_name=None, profile_version=0, meddpicc_revision="r1",
            input_snapshot=ctx.snapshot(),
        )
        running = run.transition("running")
        self.assertEqual(running.status, "running")
        self.assertEqual(running.version, run.version + 1)
        completed = running.transition("completed")
        self.assertEqual(completed.status, "completed")

    def test_meddpicc_dimension_rejects_invalid_code(self) -> None:
        from ltc.modules.customer_analysis.domain.errors import InvalidDimensionError
        from ltc.modules.customer_analysis.domain.models import MeddpiccDimension

        with self.assertRaises(InvalidDimensionError):
            MeddpiccDimension(company_id=UUID(int=1), dimension_code="not_a_real_dimension")

    def test_meddpicc_dimension_rejects_invalid_status(self) -> None:
        from ltc.modules.customer_analysis.domain.models import MeddpiccDimension

        with self.assertRaises(ValueError):
            MeddpiccDimension(
                company_id=UUID(int=1), dimension_code="metrics", status="not_a_status",
            )

class CustomerAnalysisModuleTests(unittest.TestCase):
    def test_profile_patch_uses_etag_and_rejects_stale_version(self) -> None:
        response = TestClient(_test_app()).get(f"/api/v1/companies/{COMPANY_ID}/profile")
        self.assertEqual(response.status_code, 404)

        app = _test_app()
        app.state.customer_analysis.service.search_port = None
        app.state.customer_analysis.service.report_generator = TemplateReportGenerator()
        app.state.customer_analysis.contexts.put_context(_context())
        client = TestClient(app)
        profile = client.get(f"/api/v1/companies/{COMPANY_ID}/profile")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["data"]["profile_version"], 0)

        patched = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/profile",
            headers={"If-Match": '"0"', "Idempotency-Key": str(IDEMPOTENCY_KEY)},
            json={"business_model": "B2B subscription"},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["data"]["profile_version"], 1)

        stale = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/profile",
            headers={"If-Match": '"0"', "Idempotency-Key": str(uuid4())},
            json={"business_model": "stale"},
        )
        self.assertEqual(stale.status_code, 409)

    def test_analysis_run_generates_immutable_report_and_deduplicates_input(self) -> None:
        app = _test_app()
        app.state.customer_analysis.service.search_port = None
        app.state.customer_analysis.service.report_generator = TemplateReportGenerator()
        app.state.customer_analysis.contexts.put_context(_context())
        client = TestClient(app)
        headers = {"Idempotency-Key": str(IDEMPOTENCY_KEY)}
        first = client.post(
            f"/api/v1/companies/{COMPANY_ID}/analysis-runs",
            headers=headers,
            json={"report_type": "customer_analysis", "force_refresh": False},
        )
        self.assertEqual(first.status_code, 202)
        run_id = first.json()["data"]["resource_id"]
        self.assertEqual(first.json()["data"]["job"]["status"], "queued")

        duplicate = client.post(
            f"/api/v1/companies/{COMPANY_ID}/analysis-runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={"report_type": "customer_analysis", "force_refresh": False},
        )
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(duplicate.json()["data"]["resource_id"], run_id)

        current = client.get(f"/api/v1/companies/{COMPANY_ID}/analysis-reports/current")
        self.assertEqual(current.status_code, 200)
        report = current.json()["data"]
        self.assertEqual(report["version_no"], 1)
        self.assertIn("market", report)
        self.assertIn("sales_guide", report)

        suggestions = client.get(f"/api/v1/companies/{COMPANY_ID}/analysis-suggestions")
        self.assertEqual(suggestions.status_code, 200)
        self.assertIsInstance(suggestions.json()["data"], list)

    def test_force_refresh_creates_new_version_and_non_force_deduplicates(self) -> None:
        container = _local_container()
        container.contexts.put_context(_context())
        first_submitted = container.service.request_analysis(COMPANY_ID, force_refresh=True)
        second_submitted = container.service.request_analysis(COMPANY_ID, force_refresh=True)
        non_force_submitted = container.service.request_analysis(COMPANY_ID, force_refresh=False)
        duplicate_submitted = container.service.request_analysis(COMPANY_ID, force_refresh=False)
        first = container.service.get_run(first_submitted.run_id)
        second = container.service.get_run(second_submitted.run_id)
        non_force = container.service.get_run(non_force_submitted.run_id)
        duplicate = container.service.get_run(duplicate_submitted.run_id)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(container.service.get_current_report(COMPANY_ID).version_no, 3)
        self.assertEqual(duplicate.run_id, non_force.run_id)

    def test_provider_failure_does_not_replace_current_report(self) -> None:
        class FailingGenerator:
            model_name = "failing"

            def generate(self, context):
                raise RuntimeError("provider unavailable")

        successful = _local_container()
        successful.contexts.put_context(_context())
        completed_run = successful.service.request_analysis(COMPANY_ID, force_refresh=True)
        completed = successful.service.get_run(completed_run.run_id)
        current_report_id = successful.service.get_current_report(COMPANY_ID).report_id
        successful.service.report_generator = FailingGenerator()
        failed_run = successful.service.request_analysis(COMPANY_ID, force_refresh=True)
        failed = successful.service.get_run(failed_run.run_id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(successful.service.get_current_report(COMPANY_ID).report_id, current_report_id)
    def test_meddpicc_dimension_update_is_independent(self) -> None:
        app = _test_app()
        app.state.customer_analysis.contexts.put_context(_context())
        client = TestClient(app)
        initial = client.get(f"/api/v1/companies/{COMPANY_ID}/meddpicc")
        self.assertEqual(initial.status_code, 200)
        updated = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/meddpicc/metrics",
            headers={"If-Match": '"0"', "Idempotency-Key": str(uuid4())},
            json={"status": "confirmed", "summary": "Monthly active users", "payload": {"value": 100000}},
        )
        self.assertEqual(updated.status_code, 200)
        metrics = next(item for item in updated.json()["data"]["dimensions"] if item["dimension_code"] == "metrics")
        self.assertEqual(metrics["version"], 1)
        self.assertEqual(metrics["status"], "confirmed")


    def test_http_404_for_missing_report(self) -> None:
        """GET on non-existing report returns 404."""
        app = _test_app()
        client = TestClient(app)
        resp = client.get(f"/api/v1/analysis-reports/{uuid4()}")
        self.assertEqual(resp.status_code, 404)

    def test_http_404_for_missing_run(self) -> None:
        """GET on non-existing run returns 404."""
        app = _test_app()
        client = TestClient(app)
        resp = client.get(f"/api/v1/analysis-runs/{uuid4()}")
        self.assertEqual(resp.status_code, 404)

    def test_http_404_for_missing_current_report(self) -> None:
        """GET current report for un-analysed company returns 404."""
        app = _test_app()
        client = TestClient(app)
        resp = client.get(
            f"/api/v1/companies/{uuid4()}/analysis-reports/current"
        )
        self.assertEqual(resp.status_code, 404)

    def test_http_422_for_invalid_meddpicc_dimension(self) -> None:
        """PATCH on non-existing dimension code returns 422."""
        app = _test_app()
        app.state.customer_analysis.contexts.put_context(_context())
        client = TestClient(app)
        resp = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/meddpicc/not_a_dimension",
            headers={"If-Match": '"0"', "Idempotency-Key": str(uuid4())},
            json={"status": "partial", "summary": "nope"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_meddpicc_stale_version_returns_409(self) -> None:
        """Patching MEDDPICC with wrong ETag returns 409."""
        app = _test_app()
        app.state.customer_analysis.contexts.put_context(_context())
        client = TestClient(app)
        resp = client.patch(
            f"/api/v1/companies/{COMPANY_ID}/meddpicc/metrics",
            headers={"If-Match": '"99"', "Idempotency-Key": str(uuid4())},
            json={"status": "confirmed", "summary": "stale"},
        )
        self.assertEqual(resp.status_code, 409)

    def test_retry_run_rejects_stale_version(self) -> None:
        """retry with wrong If-Match returns 409."""
        container = _local_container()
        container.contexts.put_context(_context())
        submitted = container.service.request_analysis(COMPANY_ID, force_refresh=True)
        run = container.service.get_run(submitted.run_id)
        # run is already completed; retry with stale version
        app = _test_app(container)
        client = TestClient(app)
        # completed runs can't be retried via the http endpoint without a version match
        resp = client.post(
            f"/api/v1/analysis-runs/{run.run_id}:retry",
            headers={"If-Match": '"99"', "Idempotency-Key": str(uuid4())},
        )
        self.assertIn(resp.status_code, {404, 409})

    def test_cancel_run_rejects_completed(self) -> None:
        """Cancelling a completed run raises InvalidStateError."""
        container = _local_container()
        container.contexts.put_context(_context())
        submitted = container.service.request_analysis(COMPANY_ID, force_refresh=True)
        run = container.service.get_run(submitted.run_id)
        from ltc.modules.customer_analysis.domain.errors import InvalidStateError

        with self.assertRaises(InvalidStateError):
            container.service.cancel_run(run.run_id, expected_version=run.version)

    def test_list_reports_pagination(self) -> None:
        """Cursor pagination returns has_more when > limit."""
        container = _local_container()
        container.contexts.put_context(_context())
        for _ in range(3):
            container.service.request_analysis(COMPANY_ID, force_refresh=True)
        reports, cursor = container.service.list_reports(
            COMPANY_ID, limit=1, cursor=None
        )
        self.assertEqual(len(reports), 1)
        self.assertIsNotNone(cursor)

    def test_review_suggestion_accept_and_reject(self) -> None:
        """Accepting/rejecting a suggestion writes back to the domain."""
        container = _local_container()
        container.contexts.put_context(_context())
        # Publish a report so suggestions are generated
        container.service.request_analysis(COMPANY_ID, force_refresh=True)
        suggestions = container.service.list_suggestions(COMPANY_ID)
        if not suggestions:
            self.skipTest("no suggestions generated (template report matches current)")
        s = suggestions[0]
        # Accept
        accepted = container.service.review_suggestion(
            s.suggestion_id, accept=True, expected_version=0, reviewed_by=None,
        )
        self.assertEqual(accepted.status, "accepted")
        # Reject on a second suggestion (if exists)
        others = container.service.list_suggestions(COMPANY_ID)
        if others:
            rejected = container.service.review_suggestion(
                others[0].suggestion_id, accept=False, expected_version=0, reviewed_by=None,
            )
            self.assertEqual(rejected.status, "rejected")

    def test_score_all_batch(self) -> None:
        """Batch scoring returns results for existing contexts."""
        container = _local_container()
        container.contexts.put_context(_context())
        items = container.service.score_all()
        self.assertGreaterEqual(len(items), 1)
        self.assertIn("total_score", items[0])

    def test_score_company_returns_adopted_four_dimension_icp_without_overwriting_it(self) -> None:
        container = _local_container()
        container.contexts.put_context(_context())
        result = container.service.score_company(COMPANY_ID, change_reason="test")
        for key in ("total_score", "dimension_scores"):
            self.assertIn(key, result, f"missing key {key}")
        dims = result["dimension_scores"]
        self.assertEqual({"D1": 32, "D2": 25, "D3": 17, "D4": 8}, dims)
        self.assertEqual(82, result["total_score"])
        self.assertEqual("A", result["grade"])
        self.assertEqual(82, container.contexts.load_context(COMPANY_ID).adopted_icp["total_score"])

if __name__ == "__main__":
    unittest.main()
