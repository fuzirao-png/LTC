"""Application service for Customer Operation module.

Wires manual note confirmation → customer analysis report generation (PRD §5.1).
Uses AnalysisTriggerPort for inter-module integration instead of a raw global variable.
"""

import logging
from uuid import UUID

from ltc.modules.customer_operation.application.ports import (
    AnalysisRunResult,
    CustomerOperationRepositoryPort,
)
from ltc.modules.customer_operation.application.analysis_trigger import (
    get_analysis_trigger,
    set_analysis_trigger,
)
from ltc.modules.customer_operation.domain.errors import CustomerOperationNotFound
from ltc.modules.customer_operation.infrastructure.manual_note_store import PostgresManualNoteStore
from ltc.modules.customer_operation.infrastructure.manual_note_extractor import ManualNoteExtractor
from ltc.modules.customer_operation.infrastructure.email_draft_store import EmailDraftStore
from ltc.modules.customer_operation.infrastructure.mailbox_monitor_store import (
    list_enabled_mailbox_monitors,
    update_mailbox_monitor,
    upsert_mailbox_monitor,
)
from ltc.modules.customer_operation.infrastructure.postgres_customer_export_store import (
    PostgresCustomerExportStore,
)
from ltc.modules.customer_operation.infrastructure.postgres_customer_home_card_store import (
    PostgresCustomerHomeCardStore,
)
from ltc.modules.customer_operation.application.pa_notification_service import PaNotificationService

_logger = logging.getLogger(__name__)

class CustomerOperationService:
    def __init__(self, repository: CustomerOperationRepositoryPort) -> None:
        self.repository = repository

    def email_drafts(self, company_id: UUID, sales_user_id: str) -> list[dict]:
        return EmailDraftStore().list(company_id=str(company_id), sales_user_id=sales_user_id)

    def email_draft(self, email_id: UUID, sales_user_id: str) -> dict | None:
        return EmailDraftStore().get(email_id=str(email_id), sales_user_id=sales_user_id)

    def create_email_draft(self, **kwargs) -> dict:
        return EmailDraftStore().create(**kwargs)

    def update_email_draft(self, **kwargs) -> dict | None:
        return EmailDraftStore().update(**kwargs)

    def delete_email_draft(self, **kwargs) -> bool:
        return EmailDraftStore().delete(**kwargs)

    def delete_email_draft_attachment(self, **kwargs) -> bool:
        return EmailDraftStore().remove_attachment(**kwargs)

    def can_sales_access_company(self, company_id: UUID, sales_user_id: str) -> bool:
        return self.repository.can_sales_access_company(str(company_id), sales_user_id)

    def get_customer_operations(self, company_id: UUID, sales_user_id: str | None = None) -> dict:
        snapshot = self.repository.get_customer_operations(company_id, sales_user_id=sales_user_id)
        if snapshot is None:
            raise CustomerOperationNotFound(f"Company not found: {company_id}")
        return snapshot

    def list_timeline(self, company_id: UUID, sales_user_id: str | None = None) -> list:
        company_id_text = str(company_id)
        if not self.repository.company_exists(company_id_text):
            raise CustomerOperationNotFound(f"Company not found: {company_id}")
        return self.repository.list_activities(company_id_text, sales_user_id=sales_user_id)

    def list_tasks(self, company_id: UUID, sales_user_id: str | None = None) -> list:
        company_id_text = str(company_id)
        if not self.repository.company_exists(company_id_text):
            raise CustomerOperationNotFound(f"Company not found: {company_id}")
        return self.repository.list_tasks(company_id_text, sales_user_id=sales_user_id)

    def create_manual_note(self, *, company_id: UUID, sales_id: str, raw_text: str) -> dict:
        return PostgresManualNoteStore().create_note(
            company_id=str(company_id),
            sales_id=sales_id,
            raw_text=raw_text,
        )

    def confirm_manual_note(
        self, *, company_id: UUID, sales_id: str, raw_text: str, extracted_fields: list
    ) -> dict:
        note = PostgresManualNoteStore().create_confirmed_note(
            company_id=str(company_id),
            sales_id=sales_id,
            raw_text=raw_text,
            extracted_fields=extracted_fields,
        )
        field_update_result = self._apply_confirmed_fields(
            company_id=company_id,
            sales_id=sales_id,
            extracted_fields=extracted_fields,
        )
        return {**note, "field_update_result": field_update_result}

    def trigger_manual_note_analysis(
        self, note: dict, extracted_fields: list
    ) -> AnalysisRunResult:
        return self._trigger_analysis(note, extracted_fields)

    def update_manual_note_status(
        self, *, note_id: UUID, confirm_status: str, extracted_fields: list | None = None, sales_id: str | None = None
    ) -> dict | None:
        note = PostgresManualNoteStore().update_note_status(
            note_id=str(note_id),
            confirm_status=confirm_status,
            extracted_fields=extracted_fields,
            sales_id=sales_id,
        )
        # PRD §5.1: trigger customer analysis report v_next
        if note and confirm_status == "confirmed" and get_analysis_trigger() is not None:
            self._trigger_analysis(note, extracted_fields)
        return note

    def extract_manual_note_fields(self, *, company_id: str, raw_text: str) -> dict:
        if not raw_text.strip():
            raise ValueError("rawText is required.")
        if not self.repository.company_exists(company_id):
            raise CustomerOperationNotFound(f"Company not found: {company_id}")
        result = ManualNoteExtractor().extract(raw_text)
        fields = result.get("fields")
        if not isinstance(fields, list):
            return result

        trigger = get_analysis_trigger()
        if trigger is None:
            return result
        dimensions = {
            item.dimension_code: item
            for item in trigger.get_meddpicc(UUID(company_id))
        }
        competition = dimensions.get("competition")
        enriched_fields: list[dict] = []
        for field in fields:
            enriched = dict(field)
            dimension = str(enriched.get("dimension") or "")
            if "竞争对手" in dimension or "竞争态势" in dimension:
                enriched.update(
                    {
                        "target": "competition",
                        "target_table": "customer_meddpicc_dimension",
                        "target_version": competition.version if competition else 0,
                        "previous": competition.summary if competition else None,
                    }
                )
            enriched_fields.append(enriched)
        return {**result, "fields": enriched_fields}

    def export_customers(self, *, limit: int = 500, owner_user_id: str | None = None) -> list[dict]:
        return PostgresCustomerExportStore().export_customers(limit=limit, owner_user_id=owner_user_id)

    def list_home_cards(
        self, *, limit: int = 500, owner_user_id: str | None = None
    ) -> list[dict]:
        return PostgresCustomerHomeCardStore().list_home_cards(
            limit=limit, owner_user_id=owner_user_id
        )

    def list_email_history(self, company_id: UUID, sales_user_id: str | None = None) -> list[dict]:
        if not self.repository.company_exists(str(company_id)):
            raise CustomerOperationNotFound(f"Company not found: {company_id}")
        return list(self.repository.list_emails(str(company_id), sales_user_id))

    def get_email_attachment(self, *, company_id: UUID, email_id: UUID, attachment_id: UUID, sales_user_id: str | None = None) -> dict | None:
        item = self.repository.get_email_attachment(
            company_id=str(company_id), email_id=str(email_id), attachment_id=str(attachment_id), sales_user_id=sales_user_id
        )
        if item is None:
            return None
        from ltc.modules.customer_operation.infrastructure.email_attachment_service import EmailAttachmentService
        path = EmailAttachmentService().resolve_path(item["storage_key"])
        if not path.is_file():
            return None
        return {**item, "path": path}

    def list_notifications(self, *, role: str = "sales", unread_only: bool = True, user_id: str = "") -> list[dict]:
        return PaNotificationService().list_notifications(role=role, unread_only=unread_only, user_id=user_id)

    def mark_notification_read(self, notification_id: str, *, role: str = "sales", user_id: str = "") -> dict:
        if role != "sales":
            raise KeyError(notification_id)
        return PaNotificationService().mark_read(notification_id, user_id=user_id)

    def get_notification_detail(self, notification_id: str, *, user_id: str) -> dict:
        item = PaNotificationService().get_detail(notification_id, user_id=user_id)
        if item is None:
            raise KeyError(notification_id)
        return item

    def list_mailbox_monitors(self) -> list[dict]:
        return list_enabled_mailbox_monitors()

    def create_mailbox_monitor(
        self,
        *,
        provider_code: str,
        host: str,
        port: int,
        username: str,
        secret_env_var: str,
        secret_value: str | None,
        mailbox_name: str,
        enabled: bool,
        poll_seconds: int,
    ) -> dict | None:
        return upsert_mailbox_monitor(
            provider_code=provider_code,
            host=host,
            port=port,
            username=username,
            secret_env_var=secret_env_var,
            secret_value=secret_value,
            mailbox_name=mailbox_name,
            enabled=enabled,
            poll_seconds=poll_seconds,
        )

    def update_mailbox_monitor(
        self,
        *,
        mailbox_monitor_id: str,
        host: str | None = None,
        port: int | None = None,
        secret_env_var: str | None = None,
        secret_value: str | None = None,
        mailbox_name: str | None = None,
        enabled: bool | None = None,
        poll_seconds: int | None = None,
    ) -> dict | None:
        return update_mailbox_monitor(
            mailbox_monitor_id=mailbox_monitor_id,
            host=host,
            port=port,
            secret_env_var=secret_env_var,
            secret_value=secret_value,
            mailbox_name=mailbox_name,
            enabled=enabled,
            poll_seconds=poll_seconds,
        )

    def _apply_confirmed_fields(
        self, *, company_id: UUID, sales_id: str, extracted_fields: list
    ) -> dict:
        result = {
            "updated_dimensions": [],
            "conflicts": [],
            "skipped_fields": [],
        }
        trigger = get_analysis_trigger()
        if trigger is None:
            return result

        dimensions = {item.dimension_code: item for item in trigger.get_meddpicc(company_id)}
        for field in extracted_fields:
            if field.get("selected") is False:
                continue
            target = str(field.get("target") or "").strip()
            if not target:
                continue
            if (
                field.get("action") != "覆盖"
                or field.get("target_table") != "customer_meddpicc_dimension"
                or target != "competition"
            ):
                result["skipped_fields"].append(
                    {
                        "dimension": field.get("dimension"),
                        "target": target,
                        "reason": "unsupported_target_or_action",
                    }
                )
                continue

            current = dimensions.get(target)
            target_version = field.get("target_version")
            current_version = current.version if current is not None else None
            if current is None or not isinstance(target_version, int) or target_version != current_version:
                result["conflicts"].append(
                    {
                        "dimension": field.get("dimension"),
                        "target": target,
                        "target_version": target_version,
                        "current_version": current_version,
                        "reason": "version_conflict",
                    }
                )
                continue

            value = str(field.get("extracted") or "").strip()
            if not value:
                result["skipped_fields"].append(
                    {
                        "dimension": field.get("dimension"),
                        "target": target,
                        "reason": "empty_value",
                    }
                )
                continue
            try:
                updated = trigger.update_meddpicc(
                    company_id,
                    target,
                    expected_version=target_version,
                    status="confirmed",
                    summary=value,
                    payload=current.payload,
                    level=current.level,
                    updated_by=UUID(sales_id),
                )
            except Exception as exc:
                if exc.__class__.__name__ != "VersionConflictError":
                    raise
                refreshed = {
                    item.dimension_code: item for item in trigger.get_meddpicc(company_id)
                }.get(target)
                result["conflicts"].append(
                    {
                        "dimension": field.get("dimension"),
                        "target": target,
                        "target_version": target_version,
                        "current_version": refreshed.version if refreshed is not None else None,
                        "reason": "version_conflict",
                    }
                )
                continue
            dimensions[target] = updated
            result["updated_dimensions"].append(target)
        return result

    # ── PRD §5.1: manual note → analysis trigger ──

    def _trigger_analysis(
        self, note: dict, extracted_fields: list | None
    ) -> AnalysisRunResult:
        """Apply confirmed fields to CustomerProfile and trigger analysis run."""
        from uuid import UUID as _UUID

        trigger = get_analysis_trigger()
        if trigger is None:
            raise RuntimeError("Customer analysis trigger is not configured.")

        company_id = _UUID(note["companyId"])

        # Update profile with extracted fields (best-effort, but observable)
        profile_updates: dict = {}
        if extracted_fields:
            for field in extracted_fields:
                if field.get("selected") is False:
                    continue
                dimension = str(field.get("dimension", ""))
                value = str(field.get("extracted", "")).strip()
                if not dimension or not value:
                    continue
                if "关注点" in dimension or "客户关注" in dimension:
                    profile_updates["concerns"] = value
                elif "合作方" in dimension or "合作伙伴" in dimension:
                    profile_updates["partners"] = value
                elif any(label in dimension for label in ("觉得我们如何", "对我方印象", "对我们的评价")):
                    profile_updates["impression_of_us"] = value
                elif "决策人" in dimension:
                    profile_updates["decision_maker_text"] = value
                elif "预算" in dimension:
                    profile_updates["budget_text"] = value
                elif "公司规模" in dimension or "企业画像" in dimension:
                    profile_updates["employee_scale"] = value
                elif "行业" in dimension:
                    profile_updates["company_type"] = value
        if profile_updates:
            try:
                profile = trigger.get_profile(company_id)
                trigger.update_profile(
                    company_id,
                    profile_updates,
                    expected_version=profile.version,
                    updated_by=None,
                )
            except Exception:
                _logger.exception(
                    "Manual-note analysis could not update customer profile company_id=%s",
                    company_id,
                )

        return trigger.request_analysis(
            company_id,
            trigger_type="operation",
            trigger_context={
                "source": "manual_note",
                "company_id": str(company_id),
                "note_id": str(note.get("id") or ""),
                "field_update_result": note.get("field_update_result") or {
                    "updated_dimensions": [],
                    "conflicts": [],
                    "skipped_fields": [],
                },
            },
        )
