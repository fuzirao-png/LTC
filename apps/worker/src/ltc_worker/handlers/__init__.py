"""Handler stubs for the 13 architecturally-defined Job Types.

Every handler is a ``UseCaseBackedHandler`` subclass.  Handlers whose
business logic has not been implemented yet use ``_NotReadyUseCase`` to
fail gracefully when a job of that type is claimed.

As business modules are built out, replace ``_NotReadyUseCase`` with
the real ``JobExecutionUseCase`` implementation and wire it in the
composition root (``main.py``).
"""

from __future__ import annotations

from typing import Any

from ..application import JobExecutionUseCase
from ..errors import RetryableError
from .base import UseCaseBackedHandler


class _NotReadyUseCase:
    """Placeholder that signals the handler exists but logic is not wired yet."""

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        raise RetryableError(
            f"Handler registered but use case not wired yet for job {job_id}"
        )


# ── Lead (search / refresh) ─────────────────────────────────────────


class LeadSearchPipelineHandler(UseCaseBackedHandler):
    job_type = "lead.search_pipeline.v1"
    use_case_attr = "lead_search_pipeline"


class LeadRefreshCandidateHandler(UseCaseBackedHandler):
    job_type = "lead.refresh_candidate.v1"
    use_case_attr = "refresh_candidate"


# ── Analysis ────────────────────────────────────────────────────────


class AnalysisGenerateReportHandler(UseCaseBackedHandler):
    job_type = "analysis.generate_report.v1"
    use_case_attr = "generate_analysis_report"


class AnalysisResearchCustomerHandler(UseCaseBackedHandler):
    """Research Worker entry point; kept separate from legacy report jobs."""

    job_type = "analysis.research_customer.v1"
    use_case_attr = "research_customer"


# ── Email (3 stages) ────────────────────────────────────────────────


class EmailGenerateDraftHandler(UseCaseBackedHandler):
    job_type = "engagement.generate_email_draft.v1"
    use_case_attr = "generate_email_draft"


class EmailSendHandler(UseCaseBackedHandler):
    job_type = "engagement.send_email.v1"
    use_case_attr = "send_email"


class EmailReconcileHandler(UseCaseBackedHandler):
    job_type = "engagement.reconcile_email.v1"
    use_case_attr = "reconcile_email"


# ── Meeting ─────────────────────────────────────────────────────────


class MeetingProcessHandler(UseCaseBackedHandler):
    job_type = "engagement.process_meeting.v1"
    use_case_attr = "process_meeting"

    async def handle(self, job, app) -> None:
        handle = getattr(app.process_meeting, "handle", None)
        if handle is not None:
            await handle(job)
        else:
            await super().handle(job, app)


# ── Platform (outbox / external event / notify) ─────────────────────


class OutboxDispatchHandler(UseCaseBackedHandler):
    job_type = "platform.dispatch_outbox.v1"
    use_case_attr = "dispatch_outbox"


class ExternalEventProcessHandler(UseCaseBackedHandler):
    job_type = "platform.process_external_event.v1"
    use_case_attr = "process_external_event"


class NotifyHandler(UseCaseBackedHandler):
    job_type = "platform.notify.v1"
    use_case_attr = "send_notification"


# ── CRM automation ──────────────────────────────────────────────────


class AutoReleaseOverdueHandler(UseCaseBackedHandler):
    job_type = "crm.auto_release_overdue.v1"
    use_case_attr = "auto_release_overdue"


class CrmPipelineConsumerHandler(UseCaseBackedHandler):
    job_type = "crm.pipeline_consumer.v1"
    use_case_attr = "crm_pipeline_consumer"


# ── Manual note ─────────────────────────────────────────────────────


class ManualNoteExtractHandler(UseCaseBackedHandler):
    job_type = "manual_note.extract.v1"
    use_case_attr = "extract_manual_note"


# ── Data completion ─────────────────────────────────────────────────


class DataCompletionScaleHandler(UseCaseBackedHandler):
    job_type = "data_completion.scale.v1"
    use_case_attr = "complete_scale_data"


class DataCompletionRegionHandler(UseCaseBackedHandler):
    job_type = "data_completion.region.v1"
    use_case_attr = "complete_region_data"
