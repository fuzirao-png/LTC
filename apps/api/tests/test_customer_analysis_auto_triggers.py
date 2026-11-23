from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID
from unittest.mock import AsyncMock, Mock, patch

from ltc.modules.customer_operation.application.analysis_trigger import (
    set_analysis_trigger,
    trigger_customer_analysis_best_effort,
)
from ltc.modules.customer_operation.application.email_delivery_service import (
    send_email_for_payload,
)
from ltc.modules.customer_operation.application.inbound_mail_service import (
    InboundEmail,
    InboundMailProcessor,
)
from ltc.modules.customer_analysis.application.service import CustomerAnalysisService
from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.modules.customer_analysis.infrastructure.adapters import (
    InMemoryAnalysisContextPort,
    InMemoryCustomerAnalysisRepository,
    InlineAnalysisJobPort,
    TemplateReportGenerator,
)
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.sales_crm.application.lead_service import (
    AssignLeadCommand,
    LeadCommandResult,
    SalesLeadService,
)


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000041")
LEAD_ID = UUID("00000000-0000-0000-0000-000000000042")
USER_ID = UUID("00000000-0000-0000-0000-000000000043")
ASSIGNMENT_ID = UUID("00000000-0000-0000-0000-000000000044")


class _Connection:
    def execute(self, *args, **kwargs) -> None:
        del args, kwargs


class _Database:
    def __init__(self) -> None:
        self.committed = False

    @contextmanager
    def transaction(self):
        try:
            yield _Connection()
        except Exception:
            raise
        else:
            self.committed = True


class _ClaimService(SalesLeadService):
    def __init__(self, database, analysis_trigger, existing=None) -> None:
        super().__init__(database, analysis_trigger)
        self.existing = existing

    def _read_idempotency(self, *args, **kwargs):
        del args, kwargs
        return self.existing

    def _create_idempotency(self, *args, **kwargs) -> None:
        del args, kwargs

    def _lock_user(self, connection, user_id):
        del connection, user_id
        return {
            "user_id": USER_ID,
            "status": "active",
            "account_type": "sales",
            "sales_tier": "A",
            "region_code": "EA",
            "capacity_limit": 20,
        }

    def _lock_lead(self, connection, lead_id):
        del connection, lead_id
        return {
            "lead_id": LEAD_ID,
            "company_id": COMPANY_ID,
            "allocation_status": "claimable",
            "pipeline_stage": "lead",
            "current_owner_user_id": None,
            "required_sales_tier": "A",
            "pool_region_code": "EA",
            "data_completion_pool": None,
            "version": 1,
            "icp_grade": "A",
            "scale_tier": "large",
        }

    def _check_capacity(self, *args, **kwargs) -> None:
        del args, kwargs

    def _insert_assignment(self, *args, **kwargs):
        del args, kwargs
        return ASSIGNMENT_ID

    def _append_transition_and_event(self, *args, **kwargs) -> None:
        del args, kwargs

    def _complete_idempotency(self, *args, **kwargs) -> None:
        del args, kwargs


def _actor() -> CurrentActor:
    return CurrentActor(
        user_id=USER_ID,
        username="sales.ea.a",
        display_name="EA Sales A",
        account_type="sales",
        sales_tier="A",
        region_code="EA",
        capacity_limit=20,
        token_version=0,
        capabilities=(),
    )


def _command() -> AssignLeadCommand:
    return AssignLeadCommand(
        lead_id=LEAD_ID,
        expected_version=1,
        assignee_user_id=USER_ID,
        assignment_type="claim",
        reason_code="sales_claim",
        reason_text=None,
        idempotency_key="claim-once",
        request_id="00000000-0000-0000-0000-000000000045",
    )


class LeadClaimAnalysisTriggerTests(unittest.TestCase):
    def test_claim_triggers_analysis_after_transaction_commit(self) -> None:
        database = _Database()
        analysis_trigger = Mock()

        def request_after_commit(*args, **kwargs):
            del args, kwargs
            self.assertTrue(database.committed)

        analysis_trigger.request_analysis.side_effect = request_after_commit
        service = _ClaimService(database, analysis_trigger)

        result = service.claim(_actor(), _command())

        self.assertEqual(result.assignment_id, ASSIGNMENT_ID)
        analysis_trigger.request_analysis.assert_called_once_with(
            COMPANY_ID,
            trigger_type="assignment",
        )

    def test_claim_succeeds_when_analysis_trigger_fails(self) -> None:
        database = _Database()
        analysis_trigger = Mock()
        analysis_trigger.request_analysis.side_effect = RuntimeError("analysis unavailable")
        service = _ClaimService(database, analysis_trigger)

        result = service.claim(_actor(), _command())

        self.assertEqual(result.allocation_status, "claimed")
        self.assertTrue(database.committed)

    def test_idempotent_claim_replay_does_not_trigger_analysis_again(self) -> None:
        database = _Database()
        analysis_trigger = Mock()
        existing = LeadCommandResult(
            LEAD_ID,
            "claimed",
            ASSIGNMENT_ID,
            None,
            USER_ID,
            None,
            None,
            None,
            "lead",
            2,
        )
        service = _ClaimService(database, analysis_trigger, existing=existing)

        result = service.claim(_actor(), _command())

        self.assertEqual(result, existing)
        analysis_trigger.request_analysis.assert_not_called()


class CustomerOperationAnalysisTriggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_analysis_trigger(None)

    def test_best_effort_trigger_swallows_analysis_failure(self) -> None:
        analysis_trigger = Mock()
        analysis_trigger.request_analysis.side_effect = RuntimeError("analysis unavailable")
        set_analysis_trigger(analysis_trigger)

        result = trigger_customer_analysis_best_effort(
            COMPANY_ID,
            source="inbound_email",
        )

        self.assertIsNone(result)
        analysis_trigger.request_analysis.assert_called_once_with(
            COMPANY_ID,
            trigger_type="operation",
            trigger_context={"source": "inbound_email"},
        )

    def test_outbound_email_triggers_only_after_database_persistence(self) -> None:
        store = Mock()
        store.resolve_outbound_target.return_value = (
            "Pacific TMC Japan",
            "James Wilson",
            "james@example.com",
        )
        store.is_configured.return_value = True
        store.record_outbound_email.return_value = Mock(
            company_id=str(COMPANY_ID),
            contact_id="00000000-0000-0000-0000-000000000052",
            email_id="00000000-0000-0000-0000-000000000053",
        )
        smtp = Mock()
        smtp.send = AsyncMock(return_value={
            "deliveredTo": "james@example.com",
            "mode": "mock",
            "provider": "mock",
            "messageId": "message-1",
        })

        with (
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.PostgresMailStore",
                return_value=store,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.SmtpEmailClient",
                return_value=smtp,
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.LegacyFileStore"
            ),
            patch(
                "ltc.modules.customer_operation.application.email_delivery_service.trigger_customer_analysis_best_effort"
            ) as analysis_request,
        ):
            result = asyncio.run(send_email_for_payload({
                "companyId": str(COMPANY_ID),
                "contactId": "00000000-0000-0000-0000-000000000052",
                "subject": "Next steps",
                "body": "Please confirm the decision process.",
            }))

        self.assertTrue(result["success"])
        analysis_request.assert_called_once_with(
            str(COMPANY_ID),
            source="outbound_email",
        )

    def test_associated_inbound_email_triggers_analysis(self) -> None:
        store = Mock()
        store.is_configured.return_value = True
        store.record_inbound_email.return_value = Mock(
            company_id=str(COMPANY_ID),
            email_id="00000000-0000-0000-0000-000000000054",
        )
        notifications = Mock()
        notifications.get_notification.return_value = None
        message = InboundEmail(
            uid="43",
            message_id="<customer@example.com>",
            from_email="buyer@example.com",
            to_email="sales@example.com",
            subject="Budget confirmed",
            body_preview="Budget is USD 50,000.",
            body_text="Budget is USD 50,000 and the CFO approves it.",
            received_at="2026-08-04T06:05:10+00:00",
        )

        with TemporaryDirectory() as temp_dir:
            processor = InboundMailProcessor(
                data_dir=Path(temp_dir),
                notification_service=notifications,
                sales_user_id="sales-1",
            )
            with (
                patch(
                    "ltc.modules.customer_operation.application.inbound_mail_service.PostgresMailStore",
                    return_value=store,
                ),
                patch(
                    "ltc.modules.customer_operation.application.inbound_mail_service.trigger_customer_analysis_best_effort"
                ) as analysis_request,
            ):
                processor.process_emails([message])

        analysis_request.assert_called_once_with(
            str(COMPANY_ID),
            source="inbound_email",
        )


class CustomerAnalysisDebounceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.company_id = UUID("00000000-0000-0000-0000-000000000055")
        self.repository = InMemoryCustomerAnalysisRepository()
        self.contexts = InMemoryAnalysisContextPort()
        self.job_port = InlineAnalysisJobPort()
        self.service = CustomerAnalysisService(
            repository=self.repository,
            context_port=self.contexts,
            report_generator=TemplateReportGenerator(),
            job_port=self.job_port,
        )
        self.contexts.put_context(
            AnalysisContext(
                company_id=self.company_id,
                company={"company_name": "Acme Travel", "industry": "TMC"},
                sales_lead={"lead_id": str(UUID(int=2)), "stage": "qualified"},
                adopted_icp={"total_score": 82},
                adopted_scale={"scale_code": "enterprise"},
            )
        )

    def _request_at(
        self,
        when: datetime,
        *,
        trigger_context: dict[str, object] | None = None,
    ):
        with patch("ltc.modules.customer_analysis.application.service.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = when
            return self.service.request_analysis(
                self.company_id,
                force_refresh=False,
                trigger_type="operation",
                trigger_context=trigger_context,
            )

    def test_repeated_triggers_within_five_minutes_reuse_recent_run(self) -> None:
        first = self._request_at(
            datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc),
            trigger_context={"source": "inbound_email"},
        )
        second = self._request_at(
            datetime(2026, 8, 7, 9, 3, tzinfo=timezone.utc),
            trigger_context={"source": "manual_note"},
        )

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(1, len(self.job_port.submissions))
        self.assertEqual("inbound_email", first.trigger_context["source"])

    def test_trigger_after_window_uses_new_context(self) -> None:
        first = self._request_at(
            datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc),
            trigger_context={"source": "inbound_email"},
        )
        self.contexts.put_context(
            AnalysisContext(
                company_id=self.company_id,
                company={"company_name": "Acme Travel", "industry": "Travel technology"},
                sales_lead={"lead_id": str(UUID(int=2)), "stage": "qualified"},
                adopted_icp={"total_score": 90},
                adopted_scale={"scale_code": "enterprise"},
            )
        )
        second = self._request_at(
            datetime(2026, 8, 7, 9, 6, tzinfo=timezone.utc),
            trigger_context={"source": "manual_note"},
        )

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(2, len(self.job_port.submissions))

    def test_incremental_refresh_reuses_recent_run(self) -> None:
        first = self.service.request_incremental_refresh(
            self.company_id,
            trigger_context={"source": "inbound_email"},
        )
        second = self.service.request_incremental_refresh(
            self.company_id,
            trigger_context={"source": "manual_note"},
        )

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual("incremental", first.trigger_context["refresh_mode"])
        self.assertEqual(1, len(self.job_port.submissions))

    def test_full_calibration_creates_new_run_and_marks_full_mode(self) -> None:
        first = self.service.request_incremental_refresh(
            self.company_id,
            trigger_context={"source": "inbound_email"},
        )
        second = self.service.request_full_calibration(
            self.company_id,
            trigger_context={"source": "nightly_calibration"},
        )

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual("full", second.trigger_context["refresh_mode"])
        self.assertEqual("nightly", second.trigger_context["calibration_mode"])
        self.assertEqual(2, len(self.job_port.submissions))
