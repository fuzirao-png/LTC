"""Module metadata and ownership constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


STANDARD_LAYER_NAMES: Final[tuple[str, ...]] = (
    "interfaces",
    "application",
    "domain",
    "infrastructure",
)

READ_MODEL_LAYER_NAMES: Final[tuple[str, ...]] = (
    "interfaces",
    "queries",
)


@dataclass(frozen=True)
class ModuleDefinition:
    name: str
    owner: str
    description: str
    owned_tables: tuple[str, ...]


MODULE_DEFINITIONS: Final[tuple[ModuleDefinition, ...]] = (
    ModuleDefinition(
        name="iam",
        owner="apps/api/src/ltc/modules/iam",
        description="Identity, authentication, and authorization boundaries.",
        owned_tables=(
            "user_account",
            "auth_session",
            "ref_region_country",
        ),
    ),
    ModuleDefinition(
        name="lead_intelligence",
        owner="apps/api/src/ltc/modules/lead_intelligence",
        description="Lead discovery, enrichment, scoring, and tagging boundaries.",
        owned_tables=(
            "lead_search_run",
            "search_provider_execution",
            "search_evidence",
            "lead_candidate",
            "candidate_observation",
            "candidate_evidence",
            "candidate_contact",
            "lead_enrichment_run",
            "enrichment_evidence",
            "lead_icp_assessment",
            "customer_scale_assessment",
            "lead_negative_filter_result",
            "email_automation_config",
            "email_automation_run",
            "email_automation_touch",
        ),
    ),
    ModuleDefinition(
        name="sales_crm",
        owner="apps/api/src/ltc/modules/sales_crm",
        description="Sales-facing customer, account, and CRM workflows.",
        owned_tables=(
            "company",
            "contact",
            "company_contact_roster",
            "sales_lead",
            "lead_assignment",
            "lead_stage_transition",
        ),
    ),
    ModuleDefinition(
        name="customer_analysis",
        owner="apps/api/src/ltc/modules/customer_analysis",
        description="Customer profile, report, and insight generation workflows.",
        owned_tables=(
            "customer_profile",
            "customer_meddpicc_dimension",
            "analysis_run",
            "analysis_report",
            "analysis_suggestion",
        ),
    ),
    ModuleDefinition(
        name="customer_operation",
        owner="apps/api/src/ltc/modules/customer_operation",
        description="Operational email, meeting, and follow-up coordination workflows.",
        owned_tables=(
            "email_message",
            "email_attachment",
            "email_delivery_attempt",
            "email_suppression",
            "company_outreach_state",
            "follow_up_task",
            "customer_activity",
            "manual_note",
        ),
    ),
    ModuleDefinition(
        name="read_models",
        owner="apps/api/src/ltc/modules/read_models",
        description="Projection and query-focused read models across modules.",
        owned_tables=(),
    ),
    ModuleDefinition(
        name="meeting_analysis",
        owner="apps/api/src/ltc/modules/meeting_analysis",
        description="Meeting upload, audio transcription, and AI-powered summarization workflows.",
        owned_tables=(
            "meeting",
            "meeting_segment",
            "meeting_asr_checkpoint",
            "media_asset",
        ),
    ),
)

MODULE_NAMES: Final[tuple[str, ...]] = tuple(module.name for module in MODULE_DEFINITIONS)

MODULE_OWNERSHIP: Final[dict[str, str]] = {
    module.name: module.owner for module in MODULE_DEFINITIONS
}

MODULE_OWNED_TABLES: Final[dict[str, tuple[str, ...]]] = {
    module.name: module.owned_tables for module in MODULE_DEFINITIONS
}

# Task Runtime is a supporting platform capability, not a bounded context.
# Keep its table ownership explicit so every v3.6 table has one accountable
# write boundary without pretending that these tables belong to a business module.
PLATFORM_OWNED_TABLES: Final[dict[str, tuple[str, ...]]] = {
    "jobs": (
        "job",
        "job_attempt",
        "job_progress_event",
    ),
    "idempotency": ("idempotency_record",),
    "events": (
        "outbox_event",
        "external_event",
        "audit_log",
    ),
}
