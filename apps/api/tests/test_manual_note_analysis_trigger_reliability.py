from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    TemplateReportGenerator,
)
from ltc.modules.customer_operation.application.service import (
    CustomerOperationService,
    set_analysis_trigger,
)
from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


class _OperationRepository:
    def company_exists(self, company_id: str) -> bool:
        return True

    def can_sales_access_company(self, company_id: str, sales_user_id: str) -> bool:
        return True


class _AnalysisTrigger:
    def __init__(self) -> None:
        self.requests: list[tuple[UUID, str, dict | None]] = []
        self.profile_error: Exception | None = None
        self.request_error: Exception | None = None
        self.run = SimpleNamespace(run_id=uuid4(), status="queued")
        self.meddpicc = [
            SimpleNamespace(
                dimension_code="competition",
                summary="旧竞争对手",
                version=3,
                status="confirmed",
                payload={},
                level=None,
            )
        ]
        self.meddpicc_updates: list[dict] = []

    def get_profile(self, company_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(version=3)

    def update_profile(
        self, company_id: UUID, updates: dict, *, expected_version: int, updated_by: object
    ) -> None:
        if self.profile_error is not None:
            raise self.profile_error

    def get_meddpicc(self, company_id: UUID) -> list[SimpleNamespace]:
        return self.meddpicc

    def update_meddpicc(
        self,
        company_id: UUID,
        dimension_code: str,
        *,
        expected_version: int,
        status: str,
        summary: str | None,
        payload: dict | None,
        level: str | None = None,
        updated_by: UUID | None = None,
    ) -> SimpleNamespace:
        current = self.meddpicc[0]
        if expected_version != current.version:
            from ltc.modules.customer_analysis.domain.errors import VersionConflictError

            raise VersionConflictError(
                f"MEDDPICC version {current.version} does not match {expected_version}"
            )
        update = {
            "company_id": company_id,
            "dimension_code": dimension_code,
            "expected_version": expected_version,
            "status": status,
            "summary": summary,
            "payload": payload,
            "level": level,
            "updated_by": updated_by,
        }
        self.meddpicc_updates.append(update)
        updated = SimpleNamespace(
            dimension_code=dimension_code,
            summary=summary,
            version=current.version + 1,
            status=status,
            payload=payload or {},
            level=level,
        )
        self.meddpicc = [updated]
        return updated

    def request_analysis(
        self,
        company_id: UUID,
        *,
        trigger_type: str,
        trigger_context: dict | None = None,
    ) -> SimpleNamespace:
        if self.request_error is not None:
            raise self.request_error
        self.requests.append((company_id, trigger_type, trigger_context))
        return self.run


def _sales_actor() -> CurrentActor:
    return CurrentActor(uuid4(), "sales.actor", "Sales Actor", "sales", "MA", "EA", 10, 1, ())


class ManualNoteAnalysisTriggerReliabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_analysis_trigger(None)  # type: ignore[arg-type]

    def test_missing_analysis_trigger_is_not_silently_ignored(self) -> None:
        set_analysis_trigger(None)  # type: ignore[arg-type]
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "not configured"):
            service.trigger_manual_note_analysis(
                {"companyId": "00000000-0000-0000-0000-000000000041"}, []
            )

    def test_competitor_extraction_includes_target_and_current_version(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with patch(
            "ltc.modules.customer_operation.application.service.ManualNoteExtractor.extract",
            return_value={
                "fields": [
                    {
                        "dimension": "D2.决策链.竞争对手",
                        "extracted": "飞猪",
                        "action": "覆盖",
                        "selected": True,
                    }
                ],
                "unidentified": "（无）",
            },
        ):
            result = service.extract_manual_note_fields(
                company_id=str(company_id),
                raw_text="竞争对手是飞猪",
            )

        self.assertEqual(
            result["fields"][0],
            {
                "dimension": "D2.决策链.竞争对手",
                "target": "competition",
                "target_table": "customer_meddpicc_dimension",
                "target_version": 3,
                "previous": "旧竞争对手",
                "extracted": "飞猪",
                "action": "覆盖",
                "selected": True,
            },
        )

    def test_confirmed_competitor_override_updates_dimension_and_returns_outcome(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]
        fields = [
            {
                "dimension": "D2.决策链.竞争对手",
                "target": "competition",
                "target_table": "customer_meddpicc_dimension",
                "target_version": 3,
                "previous": "旧竞争对手",
                "extracted": "任意公司",
                "action": "覆盖",
                "selected": True,
            }
        ]

        with patch(
            "ltc.modules.customer_operation.application.service.PostgresManualNoteStore.create_confirmed_note",
            return_value={"id": "note-1", "companyId": str(company_id)},
        ):
            note = service.confirm_manual_note(
                company_id=company_id,
                sales_id=str(uuid4()),
                raw_text="竞争对手是任意公司",
                extracted_fields=fields,
            )

        self.assertEqual(note["field_update_result"], {
            "updated_dimensions": ["competition"],
            "conflicts": [],
            "skipped_fields": [],
        })
        self.assertEqual(trigger.meddpicc_updates[0]["summary"], "任意公司")
        self.assertEqual(trigger.meddpicc_updates[0]["expected_version"], 3)

        service.trigger_manual_note_analysis(note, fields)
        self.assertEqual(
            trigger.requests[0][2]["field_update_result"],
            note["field_update_result"],
        )

    def test_stale_competitor_override_returns_conflict_without_update(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with patch(
            "ltc.modules.customer_operation.application.service.PostgresManualNoteStore.create_confirmed_note",
            return_value={"id": "note-1", "companyId": str(company_id)},
        ):
            note = service.confirm_manual_note(
                company_id=company_id,
                sales_id=str(uuid4()),
                raw_text="竞争对手是飞猪",
                extracted_fields=[{
                    "dimension": "D2.决策链.竞争对手",
                    "target": "competition",
                    "target_table": "customer_meddpicc_dimension",
                    "target_version": 2,
                    "extracted": "飞猪",
                    "action": "覆盖",
                    "selected": True,
                }],
            )

        self.assertEqual(note["field_update_result"]["updated_dimensions"], [])
        self.assertEqual(note["field_update_result"]["conflicts"][0]["target"], "competition")
        self.assertEqual(note["field_update_result"]["conflicts"][0]["current_version"], 3)
        self.assertEqual(trigger.meddpicc_updates, [])

    def test_unsupported_confirmed_field_is_reported_as_skipped(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with patch(
            "ltc.modules.customer_operation.application.service.PostgresManualNoteStore.create_confirmed_note",
            return_value={"id": "note-1", "companyId": str(company_id)},
        ):
            note = service.confirm_manual_note(
                company_id=company_id,
                sales_id=str(uuid4()),
                raw_text="其他字段",
                extracted_fields=[{
                    "dimension": "D9.未知",
                    "target": "unsupported",
                    "target_version": 1,
                    "extracted": "值",
                    "action": "覆盖",
                    "selected": True,
                }],
            )

        self.assertEqual(note["field_update_result"]["updated_dimensions"], [])
        self.assertEqual(note["field_update_result"]["conflicts"], [])
        self.assertEqual(note["field_update_result"]["skipped_fields"][0]["target"], "unsupported")

    def test_analysis_request_failure_propagates_from_trigger(self) -> None:
        trigger = _AnalysisTrigger()
        trigger.request_error = RuntimeError("analysis unavailable")
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "analysis unavailable"):
            service.trigger_manual_note_analysis(
                {"companyId": "00000000-0000-0000-0000-000000000041"}, []
            )

    def test_analysis_run_is_returned_from_trigger(self) -> None:
        trigger = _AnalysisTrigger()
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        run = service.trigger_manual_note_analysis(
            {"companyId": "00000000-0000-0000-0000-000000000041"}, []
        )

        self.assertIs(run, trigger.run)

    def test_profile_failure_is_logged_and_analysis_is_still_requested(self) -> None:
        trigger = _AnalysisTrigger()
        trigger.profile_error = RuntimeError("profile unavailable")
        set_analysis_trigger(trigger)  # type: ignore[arg-type]
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]

        with self.assertLogs(
            "ltc.modules.customer_operation.application.service", level="ERROR"
        ) as logs:
            service.trigger_manual_note_analysis(
                {"companyId": str(company_id)},
                [{"dimension": "D1.采购意愿.预算区间", "extracted": "5 万美元"}],
            )

        self.assertIn("could not update customer profile", logs.output[0])
        self.assertEqual(
            [(company_id, "operation", {
                "source": "manual_note",
                "company_id": str(company_id),
                "note_id": "",
                "field_update_result": {
                    "updated_dimensions": [],
                    "conflicts": [],
                    "skipped_fields": [],
                },
            })],
            trigger.requests,
        )

    def test_confirmed_note_response_includes_queued_analysis_run(self) -> None:
        service = Mock()
        company_id = uuid4()
        note_id = uuid4()
        run_id = uuid4()
        service.confirm_manual_note.return_value = {
            "id": str(note_id),
            "companyId": str(company_id),
            "field_update_result": {
                "updated_dimensions": ["competition"],
                "conflicts": [],
                "skipped_fields": [],
            },
        }
        service.trigger_manual_note_analysis.return_value = SimpleNamespace(
            run_id=run_id,
            status="queued",
        )
        app = FastAPI()
        app.include_router(build_customer_operation_router(service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/customers/{company_id}/manual-notes",
                json={"rawText": "confirmed", "confirmStatus": "confirmed"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["analysis"],
            {
                "status": "queued",
                "runId": str(run_id),
                "message": "Customer analysis generation has been queued.",
            },
        )
        self.assertEqual(response.json()["updated_dimensions"], ["competition"])
        self.assertEqual(response.json()["conflicts"], [])
        self.assertEqual(response.json()["skipped_fields"], [])
        service.trigger_manual_note_analysis.assert_called_once()

    def test_confirmed_note_response_reports_completed_analysis_run(self) -> None:
        service = Mock()
        company_id = uuid4()
        run_id = uuid4()
        service.confirm_manual_note.return_value = {
            "id": str(uuid4()),
            "companyId": str(company_id),
        }
        service.trigger_manual_note_analysis.return_value = SimpleNamespace(
            run_id=run_id,
            status="completed",
        )
        app = FastAPI()
        app.include_router(build_customer_operation_router(service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/customers/{company_id}/manual-notes",
                json={"rawText": "confirmed", "confirmStatus": "confirmed"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["analysis"],
            {
                "status": "completed",
                "runId": str(run_id),
                "message": "Customer analysis report is ready.",
            },
        )

    def test_confirmed_note_response_reports_analysis_start_failure(self) -> None:
        service = Mock()
        company_id = uuid4()
        note_id = uuid4()
        note = {
            "id": str(note_id),
            "companyId": str(company_id),
        }
        service.confirm_manual_note.return_value = note
        service.trigger_manual_note_analysis.side_effect = RuntimeError("analysis unavailable")
        app = FastAPI()
        app.include_router(build_customer_operation_router(service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())

        with self.assertLogs(
            "ltc.modules.customer_operation.interfaces.router", level="ERROR"
        ) as logs:
            with TestClient(app) as client:
                response = client.post(
                    f"/api/v1/customers/{company_id}/manual-notes",
                    json={"rawText": "confirmed", "confirmStatus": "confirmed"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["note"], note)
        self.assertEqual(
            response.json()["analysis"],
            {
                "status": "failed",
                "runId": None,
                "message": "The manual note was saved, but customer analysis could not be started.",
            },
        )
        self.assertIn(str(company_id), logs.output[0])
        self.assertIn(str(note_id), logs.output[0])
        self.assertIn("analysis unavailable", logs.output[0])
        service.trigger_manual_note_analysis.assert_called_once()

    def test_non_confirmed_note_response_is_unchanged(self) -> None:
        service = Mock()
        company_id = uuid4()
        note = {"id": str(uuid4()), "companyId": str(company_id)}
        service.create_manual_note.return_value = note
        app = FastAPI()
        app.include_router(build_customer_operation_router(service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/customers/{company_id}/manual-notes",
                json={"rawText": "draft", "confirmStatus": "draft"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "note": note})
        service.trigger_manual_note_analysis.assert_not_called()

    def test_manual_note_route_updates_competition_and_current_report_twice(self) -> None:
        company_id = UUID("00000000-0000-0000-0000-000000000041")
        repository = InMemoryCustomerAnalysisRepository()
        contexts = InMemoryAnalysisContextPort()
        contexts.put_context(
            AnalysisContext(
                company_id=company_id,
                company={
                    "company_id": str(company_id),
                    "company_name": "测试客户",
                },
                sales_lead={},
                adopted_icp={},
                adopted_scale={},
            )
        )
        job_port = InlineAnalysisJobPort()
        analysis_service = CustomerAnalysisService(
            repository=repository,
            context_port=contexts,
            report_generator=TemplateReportGenerator(),
            job_port=job_port,
        )
        job_port.bind(analysis_service.execute_analysis)
        set_analysis_trigger(analysis_service)  # type: ignore[arg-type]
        operation_service = CustomerOperationService(_OperationRepository())  # type: ignore[arg-type]
        app = FastAPI()
        app.include_router(build_customer_operation_router(operation_service), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())

        def extracted(value: str) -> dict:
            return {
                "fields": [{
                    "dimension": "D2.决策链.竞争对手",
                    "extracted": value,
                    "action": "覆盖",
                    "selected": True,
                }],
                "unidentified": "（无）",
            }

        with (
            patch(
                "ltc.modules.customer_operation.application.service.PostgresManualNoteStore.create_confirmed_note",
                side_effect=lambda **kwargs: {
                    "id": str(uuid4()),
                    "companyId": kwargs["company_id"],
                },
            ),
            patch(
                "ltc.modules.customer_operation.application.service.ManualNoteExtractor.extract",
                side_effect=lambda raw_text: extracted(
                    "飞猪" if "飞猪" in raw_text else "任意公司"
                ),
            ),
        ):
            with TestClient(app) as client:
                for raw_text, expected in (
                    ("竞争对手是飞猪", "飞猪"),
                    ("竞争对手是任意公司", "任意公司"),
                ):
                    extraction = client.post(
                        f"/api/v1/customers/{company_id}/manual-notes/extract",
                        json={"rawText": raw_text},
                    )
                    self.assertEqual(extraction.status_code, 200)
                    field = extraction.json()["fields"][0]
                    confirmation = client.post(
                        f"/api/v1/customers/{company_id}/manual-notes",
                        json={
                            "rawText": raw_text,
                            "confirmStatus": "confirmed",
                            "extractedFields": [field],
                        },
                    )
                    self.assertEqual(confirmation.status_code, 200)
                    self.assertEqual(confirmation.json()["updated_dimensions"], ["competition"])
                    self.assertEqual(confirmation.json()["conflicts"], [])
                    current = {
                        item.dimension_code: item
                        for item in analysis_service.get_meddpicc(company_id)
                    }["competition"]
                    self.assertEqual(current.summary, expected)
                    report = analysis_service.get_current_report(company_id)
                    self.assertIsNotNone(report)
                    competitor_names = [
                        item["name"]
                        for item in report.to_dict()["competitor"]["products"]
                    ]
                    self.assertIn(expected, competitor_names)

    def test_meeting_upload_injects_background_tasks(self) -> None:
        app = FastAPI()
        app.include_router(build_customer_operation_router(Mock()), prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(_sales_actor(), uuid4())
        job = {"id": "meeting-job-1"}

        with (
            patch(
                "ltc.modules.customer_operation.interfaces.router.create_meeting_upload_job",
                return_value=job,
            ) as create_job,
            patch(
                "ltc.modules.customer_operation.interfaces.router.build_meeting_job_response",
                return_value={"id": job["id"]},
            ),
            patch(
                "ltc.modules.customer_operation.interfaces.router.process_meeting_job"
            ) as process_job,
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/meeting/upload",
                    json={"customerName": "Example Co", "audioBase64": "YQ=="},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"], {"id": job["id"]})
        create_job.assert_called_once()
        process_job.assert_called_once_with(job["id"])


if __name__ == "__main__":
    unittest.main()
