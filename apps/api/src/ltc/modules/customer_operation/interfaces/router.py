from __future__ import annotations

import base64
import json
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ltc.modules.customer_operation.application.email_delivery_service import (
    generate_email_for_payload,
    send_email_for_payload,
    translate_email_for_payload,
)
from ltc.modules.customer_operation.application.email_agent import run_email_agent_for_payload
from ltc.modules.customer_operation.application.inbound_mail_service import (
    get_inbound_email_detail_for_notification,
)
from ltc.modules.customer_operation.application.meeting_job_service import (
    build_meeting_job_response,
    create_meeting_upload_job,
    get_meeting_audio_path,
    get_meeting_job_response,
    process_meeting_job,
)
from ltc.modules.customer_operation.application.service import CustomerOperationService
from ltc.modules.customer_operation.domain.errors import CustomerOperationNotFound
from ltc.modules.customer_operation.application.email_attachment_models import EmailAttachmentInput
from ltc.modules.customer_operation.application.email_draft_errors import DraftVersionConflict
from ltc.modules.customer_operation.interfaces.schemas import CustomerOperationResponse
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context

_logger = logging.getLogger(__name__)


def _analysis_status_message(status: str) -> str:
    return {
        "queued": "Customer analysis generation has been queued.",
        "running": "Customer analysis generation is in progress.",
        "completed": "Customer analysis report is ready.",
    }.get(status, "Customer analysis generation has started.")


def build_customer_operation_router(service: CustomerOperationService) -> APIRouter:
    router = APIRouter(dependencies=[Depends(get_auth_context)])

    def require_strategic(context: AuthContext) -> None:
        if context.actor.account_type != "strategic":
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_STRATEGIC_REQUIRED"})

    def require_sales(context: AuthContext) -> None:
        if context.actor.account_type != "sales":
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_SALES_REQUIRED"})

    def require_company_access(company_id: UUID, context: AuthContext) -> str | None:
        if context.actor.account_type == "strategic":
            return None
        require_sales(context)
        sales_user_id = str(context.actor.user_id)
        if not service.can_sales_access_company(company_id, sales_user_id):
            raise HTTPException(status_code=404, detail="Customer not found.")
        return sales_user_id

    @router.get("/customers/{company_id}/operations", response_model=CustomerOperationResponse)
    def get_customer_operations(company_id: UUID, context: AuthContext = Depends(get_auth_context)) -> CustomerOperationResponse:
        sales_user_id = require_company_access(company_id, context)
        try:
            return CustomerOperationResponse(data=service.get_customer_operations(company_id, sales_user_id=sales_user_id))
        except CustomerOperationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/customers/{company_id}/timeline")
    def get_customer_timeline(company_id: UUID, context: AuthContext = Depends(get_auth_context)) -> dict:
        sales_user_id = require_company_access(company_id, context)
        try:
            return {"success": True, "items": service.list_timeline(company_id, sales_user_id=sales_user_id)}
        except CustomerOperationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/customers/{company_id}/tasks")
    def get_customer_tasks(company_id: UUID, context: AuthContext = Depends(get_auth_context)) -> dict:
        sales_user_id = require_company_access(company_id, context)
        try:
            return {"success": True, "items": service.list_tasks(company_id, sales_user_id=sales_user_id)}
        except CustomerOperationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/customers/{company_id}/manual-notes/extract")
    def extract_manual_note(
        company_id: UUID, payload: dict, context: AuthContext = Depends(get_auth_context)
    ) -> dict:
        require_company_access(company_id, context)
        try:
            result = service.extract_manual_note_fields(
                company_id=str(company_id),
                raw_text=str(payload.get("rawText") or payload.get("raw_text") or "").strip(),
            )
        except CustomerOperationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"success": True, **result}

    @router.post("/customers/{company_id}/manual-notes")
    def create_manual_note(
        company_id: UUID,
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        sales_user_id = require_company_access(company_id, context)
        confirmed = payload.get("confirmStatus") == "confirmed"
        try:
            raw_text = str(payload.get("rawText") or payload.get("raw_text") or "").strip()
            extracted_fields = payload.get("extractedFields") or payload.get("extracted_fields")
            if confirmed:
                note = service.confirm_manual_note(
                    company_id=company_id,
                    sales_id=str(context.actor.user_id),
                    raw_text=raw_text,
                    extracted_fields=extracted_fields if isinstance(extracted_fields, list) else [],
                )
            else:
                note = service.create_manual_note(
                    company_id=company_id,
                    sales_id=str(context.actor.user_id),
                    raw_text=raw_text,
                )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if confirmed:
            try:
                run = service.trigger_manual_note_analysis(
                    note,
                    extracted_fields if isinstance(extracted_fields, list) else [],
                )
                analysis_status = run.status
                analysis = {
                    "status": analysis_status,
                    "runId": str(run.run_id),
                    "message": _analysis_status_message(analysis_status),
                }
            except Exception:
                _logger.exception(
                    "Manual-note analysis could not be started company_id=%s note_id=%s",
                    company_id,
                    note.get("id") or note.get("noteId"),
                )
                analysis = {
                    "status": "failed",
                    "runId": None,
                    "message": "The manual note was saved, but customer analysis could not be started.",
                }
            field_update_result = note.get("field_update_result") or {
                "updated_dimensions": [],
                "conflicts": [],
                "skipped_fields": [],
            }
            return {
                "success": True,
                "note": note,
                "analysis": analysis,
                **field_update_result,
            }
        return {"success": True, "note": note}

    @router.patch("/manual-notes/{note_id}")
    def update_manual_note(note_id: UUID, payload: dict, context: AuthContext = Depends(get_auth_context)) -> dict:
        require_sales(context)
        sales_user_id = str(context.actor.user_id)
        try:
            note = service.update_manual_note_status(
                note_id=note_id,
                confirm_status=str(payload.get("confirmStatus") or payload.get("confirm_status") or "").strip(),
                extracted_fields=payload.get("extractedFields") or payload.get("extracted_fields"),
                sales_id=sales_user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if note is None:
            raise HTTPException(status_code=404, detail="Manual note not found.")
        return {"success": True, "note": note}

    @router.get("/internal/customers/export")
    def export_customers(
        limit: int = Query(default=500, ge=1, le=5000),
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        owner_user_id = str(context.actor.user_id) if context.actor.account_type == "sales" else None
        return {"success": True, "items": service.export_customers(limit=limit, owner_user_id=owner_user_id)}

    @router.get("/internal/customers/home-cards")
    def list_home_cards(
        limit: int = Query(default=500, ge=1, le=5000),
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        owner_user_id = str(context.actor.user_id) if context.actor.account_type == "sales" else None
        return {
            "success": True,
            "items": service.list_home_cards(
                limit=limit, owner_user_id=owner_user_id
            ),
        }

    @router.get("/customers/{company_id}/email-history")
    def list_customer_email_history(
        company_id: UUID,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        sales_user_id = require_company_access(company_id, context)
        try:
            return {"success": True, "items": service.list_email_history(company_id, sales_user_id)}
        except CustomerOperationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/customers/{company_id}/email-drafts")
    def list_customer_email_drafts(company_id: UUID, context: AuthContext = Depends(get_auth_context)) -> dict:
        sales_user_id = require_company_access(company_id, context)
        if not sales_user_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_SALES_REQUIRED"})
        return {"success": True, "items": service.email_drafts(company_id, sales_user_id)}

    @router.post("/customers/{company_id}/email-drafts")
    async def create_customer_email_draft(company_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> dict:
        sales_user_id = require_company_access(company_id, context)
        if not sales_user_id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_SALES_REQUIRED"})
        payload = await _parse_email_draft_payload(request)
        try:
            item = service.create_email_draft(
                company_id=str(company_id),
                contact_id=str(payload.get("contactId") or payload.get("contact_id") or ""),
                sales_user_id=sales_user_id,
                subject=str(payload.get("subject") or ""),
                body_text=str(payload.get("body") or payload.get("body_text") or ""),
                purpose=str(payload.get("purpose") or "first_touch"),
                parent_email_id=str(payload.get("parentEmailId") or payload.get("parent_email_id") or ""),
                attachments=payload.get("attachments") or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"success": True, "item": item}

    @router.get("/email-drafts/{email_id}")
    def get_customer_email_draft(email_id: UUID, context: AuthContext = Depends(get_auth_context)) -> dict:
        require_sales(context)
        item = service.email_draft(email_id, str(context.actor.user_id))
        if item is None or item.get("status") != "draft":
            raise HTTPException(status_code=404, detail="Email draft not found.")
        return {"success": True, "item": item}

    @router.patch("/email-drafts/{email_id}")
    async def update_customer_email_draft(email_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> dict:
        require_sales(context)
        payload = await _parse_email_draft_payload(request)
        try:
            version = int(request.headers.get("if-match", payload.get("version", -1)))
            item = service.update_email_draft(
                email_id=str(email_id), sales_user_id=str(context.actor.user_id), expected_version=version,
                contact_id=str(payload.get("contactId") or payload.get("contact_id") or ""),
                subject=str(payload.get("subject") or ""),
                body_text=str(payload.get("body") or payload.get("body_text") or ""),
                purpose=str(payload.get("purpose") or "first_touch"),
                attachments=payload.get("attachments") or [],
            )
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "DRAFT_VERSION_CONFLICT"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="Email draft not found.")
        return {"success": True, "item": item}

    @router.delete("/email-drafts/{email_id}")
    def delete_customer_email_draft(email_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> dict:
        require_sales(context)
        try:
            deleted = service.delete_email_draft(
                email_id=str(email_id), sales_user_id=str(context.actor.user_id),
                expected_version=int(request.headers.get("if-match", "-1")),
            )
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "DRAFT_VERSION_CONFLICT"}) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Email draft not found.")
        return {"success": True}

    @router.delete("/email-drafts/{email_id}/attachments/{attachment_id}")
    def delete_customer_email_draft_attachment(
        email_id: UUID, attachment_id: UUID, request: Request,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_sales(context)
        try:
            deleted = service.delete_email_draft_attachment(
                email_id=str(email_id), attachment_id=str(attachment_id),
                sales_user_id=str(context.actor.user_id),
                expected_version=int(request.headers.get("if-match", "-1")),
            )
        except DraftVersionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "DRAFT_VERSION_CONFLICT"}) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Draft attachment not found.")
        return {"success": True, "item": service.email_draft(email_id, str(context.actor.user_id))}

    @router.get("/customers/{company_id}/emails/{email_id}/attachments/{attachment_id}/download")
    def download_customer_email_attachment(
        company_id: UUID,
        email_id: UUID,
        attachment_id: UUID,
        context: AuthContext = Depends(get_auth_context),
    ) -> FileResponse:
        sales_user_id = require_company_access(company_id, context)
        item = service.get_email_attachment(
            company_id=company_id,
            email_id=email_id,
            attachment_id=attachment_id,
            sales_user_id=sales_user_id,
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Email attachment not found.")
        return FileResponse(
            item["path"],
            media_type=item["content_type"],
            filename=item["filename"],
        )

    @router.post("/email/generate")
    async def generate_email_draft(
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
        if company_id:
            require_company_access(UUID(company_id), context)
        try:
            payload["salesName"] = context.actor.display_name
            return await generate_email_for_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/customer-operation/email/agent")
    async def run_customer_operation_email_agent(
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
        contact_id = str(payload.get("contactId") or payload.get("contact_id") or "").strip()
        if not company_id or not contact_id:
            raise HTTPException(status_code=400, detail="companyId and contactId are required")
        try:
            require_company_access(UUID(company_id), context)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="companyId must be a valid UUID") from exc
        payload["salesName"] = context.actor.display_name
        payload["salesUserId"] = str(context.actor.user_id) if context.actor.account_type == "sales" else ""
        try:
            return await run_email_agent_for_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/email/translate")
    async def translate_email_draft(payload: dict) -> dict:
        try:
            return await translate_email_for_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/customers/operation/email/generate")
    async def generate_customer_operation_email(
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        return await generate_email_draft(payload, context)

    @router.post("/email/send")
    async def send_email_compat(
        request: Request,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        try:
            payload = await _parse_email_send_payload(request)
            company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
            if company_id:
                require_company_access(UUID(company_id), context)
            payload["userId"] = str(context.actor.user_id)
            return await send_email_for_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/customers/operation/email/send")
    async def send_customer_operation_email(
        request: Request,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        return await send_email_compat(request, context)

    @router.post("/inbound-mail/poll-now")
    async def poll_inbound_mail_now(
        request: Request,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_strategic(context)
        pollers = getattr(request.app.state, "inbound_mail_pollers", None)
        if pollers is None:
            poller = getattr(request.app.state, "inbound_mail_poller", None)
            if poller is None:
                raise HTTPException(status_code=503, detail="Inbound mail polling is not enabled.")
            pollers = [poller]

        notifications = []
        errors = []
        for poller in pollers:
            try:
                notifications.extend(await poller.poll_once())
            except Exception as exc:
                errors.append(str(exc))
        return {"success": True, "createdCount": len(notifications), "notifications": notifications, "errors": errors}

    @router.get("/inbound-mail/notifications")
    def list_inbound_mail_notifications(
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        user_id = str(context.actor.user_id) if context.actor.account_type == "sales" else ""
        return {"success": True, "items": service.list_notifications(role="sales", unread_only=False, user_id=user_id)}

    @router.patch("/inbound-mail/notifications/{notification_id}/read")
    def mark_inbound_mail_notification_read(
        notification_id: str,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_sales(context)
        try:
            user_id = str(context.actor.user_id)
            item = service.mark_notification_read(notification_id, role="sales", user_id=user_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Inbound email notification not found.") from exc
        return {"success": True, "item": item}

    @router.get("/inbound-mail/notifications/{notification_id}")
    def get_inbound_mail_notification_detail(
        notification_id: str,
        request: Request,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        try:
            item = get_inbound_email_detail_for_notification(
                notification_id,
                data_dir=getattr(request.app.state, "inbound_mail_data_dir", None),
                user_id=str(context.actor.user_id) if context.actor.account_type == "sales" else "",
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Inbound email detail not found.") from exc
        return {"success": True, "item": item}

    @router.get("/inbound-mail/monitors")
    def list_inbound_mail_monitors(
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_strategic(context)
        return {"success": True, "items": service.list_mailbox_monitors()}

    @router.post("/mailbox-monitors")
    def create_mailbox_monitor(
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_strategic(context)
        try:
            item = service.create_mailbox_monitor(
                provider_code=str(payload.get("providerCode") or "imap"),
                host=str(payload.get("host") or "").strip(),
                port=int(payload.get("port") or 993),
                username=str(payload.get("username") or "").strip(),
                secret_env_var=str(payload.get("secretEnvVar") or "INBOUND_MAIL_PASSWORD").strip(),
                secret_value=str(payload.get("secretValue") or "").strip() or None,
                mailbox_name=str(payload.get("mailboxName") or "INBOX").strip(),
                enabled=bool(payload.get("enabled", True)),
                poll_seconds=int(payload.get("pollSeconds") or 60),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=503, detail="Database settings are not configured.")
        return {"success": True, "item": item}

    @router.patch("/mailbox-monitors/{mailbox_monitor_id}")
    def patch_mailbox_monitor(
        mailbox_monitor_id: str,
        payload: dict,
        context: AuthContext = Depends(get_auth_context),
    ) -> dict:
        require_strategic(context)
        try:
            item = service.update_mailbox_monitor(
                mailbox_monitor_id=mailbox_monitor_id,
                host=str(payload["host"]).strip() if "host" in payload else None,
                port=int(payload["port"]) if "port" in payload else None,
                secret_env_var=str(payload["secretEnvVar"]).strip() if "secretEnvVar" in payload else None,
                secret_value=str(payload["secretValue"]).strip() if "secretValue" in payload else None,
                mailbox_name=str(payload["mailboxName"]).strip() if "mailboxName" in payload else None,
                enabled=bool(payload["enabled"]) if "enabled" in payload else None,
                poll_seconds=int(payload["pollSeconds"]) if "pollSeconds" in payload else None,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="Mailbox monitor not found.")
        return {"success": True, "item": item}

    @router.get("/meeting/job")
    def get_meeting_job(id: str = Query()) -> dict:
        job = get_meeting_job_response(id)
        if job is None:
            raise HTTPException(status_code=404, detail="Meeting job not found.")
        return {"success": True, "job": job}

    @router.post("/meeting/upload")
    async def upload_meeting_compat(request: Request, background_tasks: BackgroundTasks) -> dict:
        try:
            payload = await _parse_meeting_upload_payload(request)
            job = create_meeting_upload_job(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(process_meeting_job, job["id"])
        return {
            "success": True,
            "message": "录音已上传到客户运营 Agent，正在生成会议纪要。",
            "job": build_meeting_job_response(job),
        }

    @router.get("/meeting/audio")
    def get_meeting_audio(id: str = Query()) -> FileResponse:
        audio_path = get_meeting_audio_path(id)
        if audio_path is None:
            raise HTTPException(status_code=404, detail="Meeting audio not found.")
        return FileResponse(audio_path)

    return router


async def _parse_email_draft_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        return await request.json()
    form = await request.form()
    payload: dict[str, object] = {}
    for key, value in form.multi_items():
        if key != "attachments":
            payload[key] = value
    attachments: list[EmailAttachmentInput] = []
    for upload in form.getlist("attachments"):
        if not hasattr(upload, "filename"):
            continue
        raw = await upload.read()
        await upload.close()
        if raw:
            attachments.append(EmailAttachmentInput(
                filename=str(upload.filename or "attachment.bin"),
                content_type=str(upload.content_type or "application/octet-stream"),
                content=raw,
            ))
    payload["attachments"] = attachments
    return payload


async def _parse_email_send_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload = {
            "companyId": form.get("companyId"),
            "contactId": form.get("contactId"),
            "purpose": form.get("purpose"),
            "draftId": form.get("draftId"),
            "customerName": form.get("customerName"),
            "recipientName": form.get("recipientName"),
            "recipientEmail": form.get("recipientEmail") or form.get("to"),
            "to": form.get("to"),
            "subject": form.get("subject"),
            "body": form.get("body"),
            "chineseDraft": form.get("chineseDraft"),
            "locale": form.get("locale"),
        }
        attachments = []
        for upload in form.getlist("attachments"):
            if not hasattr(upload, "filename"):
                continue
            raw = await upload.read()
            await upload.close()
            if not raw:
                continue
            attachments.append(
                {
                    "filename": upload.filename,
                    "content": base64.b64encode(raw).decode("ascii"),
                    "contentType": upload.content_type or "application/octet-stream",
                    "size": len(raw),
                }
            )
        payload["attachments"] = attachments
        return payload
    return await request.json()


async def _parse_meeting_upload_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        try:
            return await request.json()
        except json.JSONDecodeError:
            return {}

    form = await request.form()
    payload: dict = {}
    for key, value in form.multi_items():
        if key == "file":
            continue
        payload[key] = value

    upload = form.get("file")
    if upload is not None and hasattr(upload, "read"):
        payload["audioBytes"] = await upload.read()
        payload.setdefault("fileName", getattr(upload, "filename", "") or "meeting.webm")
        payload.setdefault("mimeType", getattr(upload, "content_type", "") or "application/octet-stream")

    for key in ("segments", "actionItems"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = []
            payload[key] = parsed if isinstance(parsed, list) else []

    return payload
