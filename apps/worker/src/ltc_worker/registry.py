"""Handler registry — maps ``job_type`` strings to handler instances.

``build_current_phase_registry()`` registers all 13 architecture-defined
handler types.  Most handlers are backed by ``_NotReadyUseCase`` until
the corresponding business module is wired in the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass

from .handlers import (
    AnalysisGenerateReportHandler,
    AnalysisResearchCustomerHandler,
    AutoReleaseOverdueHandler,
    CrmPipelineConsumerHandler,
    DataCompletionRegionHandler,
    DataCompletionScaleHandler,
    EmailGenerateDraftHandler,
    EmailReconcileHandler,
    EmailSendHandler,
    ExternalEventProcessHandler,
    LeadRefreshCandidateHandler,
    LeadSearchPipelineHandler,
    ManualNoteExtractHandler,
    MeetingProcessHandler,
    NotifyHandler,
    OutboxDispatchHandler,
)


@dataclass(slots=True)
class HandlerRegistry:
    _handlers: dict[str, object]
    _aliases: dict[str, object] | None = None

    def register(self, job_type: str, handler: object) -> None:
        self._handlers[job_type] = handler

    def resolve(self, job_type: str) -> object | None:
        return self._handlers.get(job_type) or (self._aliases or {}).get(job_type)

    def register_alias(self, job_type: str, handler: object) -> None:
        if self._aliases is None:
            self._aliases = {}
        self._aliases[job_type] = handler

    def job_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


def build_current_phase_registry() -> HandlerRegistry:
    registry = HandlerRegistry(_handlers={})

    # Lead
    registry.register(LeadSearchPipelineHandler.job_type, LeadSearchPipelineHandler())
    registry.register(LeadRefreshCandidateHandler.job_type, LeadRefreshCandidateHandler())

    # Analysis
    registry.register(AnalysisGenerateReportHandler.job_type, AnalysisGenerateReportHandler())
    registry.register(AnalysisResearchCustomerHandler.job_type, AnalysisResearchCustomerHandler())

    # Email
    registry.register(EmailGenerateDraftHandler.job_type, EmailGenerateDraftHandler())
    registry.register(EmailSendHandler.job_type, EmailSendHandler())
    registry.register(EmailReconcileHandler.job_type, EmailReconcileHandler())

    # Meeting
    registry.register(MeetingProcessHandler.job_type, MeetingProcessHandler())

    # Platform
    registry.register(OutboxDispatchHandler.job_type, OutboxDispatchHandler())
    registry.register(ExternalEventProcessHandler.job_type, ExternalEventProcessHandler())
    registry.register(NotifyHandler.job_type, NotifyHandler())

    # CRM automation
    registry.register(AutoReleaseOverdueHandler.job_type, AutoReleaseOverdueHandler())
    registry.register(CrmPipelineConsumerHandler.job_type, CrmPipelineConsumerHandler())

    # Manual note
    registry.register(ManualNoteExtractHandler.job_type, ManualNoteExtractHandler())

    # Data completion
    registry.register(DataCompletionScaleHandler.job_type, DataCompletionScaleHandler())
    registry.register(DataCompletionRegionHandler.job_type, DataCompletionRegionHandler())

    return registry
