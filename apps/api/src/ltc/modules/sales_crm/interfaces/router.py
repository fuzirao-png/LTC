"""Sales CRM HTTP routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.sales_crm.application.lead_service import (
    AssignLeadCommand,
    LeadCommandResult,
    ReleaseLeadCommand,
    SalesLeadClaimConflict,
    SalesLeadService,
    TransferLeadCommand,
)
from ltc.modules.sales_crm.application.pool_service import SalesPoolService
from ltc.modules.sales_crm.interfaces.lead_schemas import (
    AssignLeadRequest,
    BatchTransferRequest,
    BatchTransferResponse,
    ChangeStageRequest,
    FirstTouchRequest,
    HandoverAssignRequest,
    LeadCommandData,
    LeadCommandResponse,
    PipelineChangeData,
    PipelineChangeResponse,
    ReasonRequest,
    TerminalStageRequest,
    TransferLeadRequest,
    HandoverResponse,
    HandoverLead,
    HandoverReturnRequest,
    HandoverReturnResponse,
)
from ltc.modules.sales_crm.interfaces.query_schemas import AssessmentResponse, LeadDetail, LeadDetailResponse, LeadListItem, LeadListResponse
from ltc.modules.sales_crm.interfaces.schemas import PoolLead, PoolLeadResponse
from ltc.platform.pagination import InvalidCursor, decode_cursor, encode_cursor
from ltc.platform.first_page_cache import first_page


router = APIRouter(prefix="/sales-leads", tags=["sales-crm"])


@router.post("/auto-release-overdue", response_model=dict)
def trigger_auto_release(
    request: Request,
    dry_run: bool = False,
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    """Admin endpoint to run the auto-release overdue scan (PRD §6.18).

    Pass ?dry_run=true to list overdue leads without releasing.
    """
    if context.actor.account_type != "strategic":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_STRATEGIC_REQUIRED"})
    from ltc.modules.sales_crm.application.auto_release import run_auto_release
    try:
        result = run_auto_release(request.app.state.database, dry_run=dry_run)
    except Exception as exc:
        return {"request_id": str(uuid4()), "data": {"released": [], "failed": [], "scanned": 0, "error": str(exc)}}
    return {"request_id": str(uuid4()), "data": result}


@router.get("/handover", response_model=HandoverResponse)
def list_handover(request: Request, context: AuthContext = Depends(get_auth_context)) -> HandoverResponse:
    try:
        rows = _lead_service(request).list_handover(context.actor)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return HandoverResponse(request_id=uuid4(), data=[HandoverLead(**row) for row in rows])


@router.post(":handover-return-to-pool", response_model=HandoverReturnResponse)
def return_handover_to_pool(
    payload: HandoverReturnRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> HandoverReturnResponse:
    request_id = uuid4()
    try:
        result = _lead_service(request).return_handover_to_pool(context.actor, payload.departed_user_id, idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return HandoverReturnResponse(request_id=request_id, data=result)


@router.get("/pool", response_model=PoolLeadResponse)
def sales_lead_pool(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> PoolLeadResponse:
    try:
        raw_cursor = decode_cursor(cursor, 1)
        lead_cursor = UUID(raw_cursor[0]) if raw_cursor else None
        actor = context.actor
        key = None
        if not cursor and actor.account_type == "sales" and actor.sales_tier and actor.region_code:
            key = ("sales-pool", actor.user_id, actor.sales_tier, actor.region_code, limit)
        rows = first_page(
            request, key, lambda: request.app.state.sales_pool_service.list_for_actor(actor, lead_cursor, limit + 1),
        )
    except (InvalidCursor, ValueError) as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from error
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": str(error)}) from error
    has_more = len(rows) > limit
    items = [PoolLead(**row) for row in rows[:limit]]
    next_cursor = encode_cursor(items[-1].lead_id) if has_more and items else None
    return PoolLeadResponse(request_id=uuid4(), data=items, page={"next_cursor": next_cursor, "has_more": has_more})


def _lead_service(request: Request) -> SalesLeadService:
    return request.app.state.sales_lead_service


def _parse_if_match(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error


def _raise_lead_error(error: AuthenticationError) -> None:
    if isinstance(error, SalesLeadClaimConflict):
        owner_name = error.owner_display_name or "其他销售"
        raise HTTPException(
            status_code=409,
            detail={
                "code": error.code,
                "message": f"该线索已由{owner_name}领取",
                "current_owner_user_id": str(error.owner_user_id) if error.owner_user_id else None,
                "current_owner_name": error.owner_display_name,
            },
        ) from error
    # 403: Capability-based denial (user fundamentally lacks the right to perform this action)
    if error.code in {"FORBIDDEN_STRATEGIC_REQUIRED", "FORBIDDEN_SALES_REQUIRED", "FORBIDDEN_LEAD_OWNER_REQUIRED", "FORBIDDEN", "SALES_POOL_REQUIRED"}:
        raise HTTPException(status_code=403, detail={"code": error.code}) from error
    # 404: Resource does not exist or is invisible to this actor
    if error.code in {"SALES_LEAD_NOT_FOUND", "USER_NOT_FOUND", "FORBIDDEN_LEAD_ACCESS"}:
        raise HTTPException(status_code=404, detail={"code": error.code}) from error
    # 409: Conflict — resource state doesn't allow this command right now
    if error.code in {
        "VERSION_CONFLICT", "IDEMPOTENCY_KEY_REUSED", "IDEMPOTENCY_IN_PROGRESS",
        "ASSIGNMENT_NOT_FOUND", "TRANSFER_TARGET_SAME_OWNER",
        "SALES_LEAD_NOT_CLAIMABLE", "SALES_LEAD_NOT_CLAIMED",
        "HANDOVER_LEAD_NOT_PENDING",
    }:
        raise HTTPException(status_code=409, detail={"code": error.code}) from error
    # 422: Validation / business precondition failed
    raise HTTPException(status_code=422, detail={"code": error.code}) from error


def _lead_response(result: LeadCommandResult, request_id: str) -> LeadCommandResponse:
    return LeadCommandResponse(
        request_id=UUID(request_id),
        data=LeadCommandData(
            lead_id=result.lead_id,
            assignment_id=result.assignment_id,
            previous_assignment_id=result.previous_assignment_id,
            allocation_status=result.allocation_status,
            owner_user_id=result.owner_user_id,
            from_owner_user_id=result.from_owner_user_id,
            assigned_at=result.assigned_at,
            sla_due_at=result.sla_due_at,
            pipeline_stage=result.pipeline_stage,
            version=result.version,
        ),
    )


def _list_response(rows: list[dict[str, object]], limit: int) -> LeadListResponse:
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = encode_cursor(visible[-1]["updated_at"], visible[-1]["lead_id"]) if has_more and visible else None
    return LeadListResponse(request_id=uuid4(), data=[LeadListItem(**row) for row in visible], page={"next_cursor": next_cursor, "has_more": has_more})


@router.get("", response_model=LeadListResponse)
def list_all_sales_leads(
    request: Request,
    allocation_status: str | None = None,
    owner_user_id: str | None = None,
    required_sales_tier: str | None = None,
    pool_region_code: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> LeadListResponse:
    try:
        raw_cursor = decode_cursor(cursor, 2)
        lead_cursor = (datetime.fromisoformat(raw_cursor[0]), UUID(raw_cursor[1])) if raw_cursor else None
        rows = _lead_service(request).list_all(context.actor, allocation_status, owner_user_id, required_sales_tier, pool_region_code, lead_cursor, limit + 1)
    except (InvalidCursor, ValueError) as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from error
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _list_response(rows, limit)


@router.get("/mine", response_model=LeadListResponse)
def list_my_sales_leads(
    request: Request,
    pipeline_stage: str | None = None,
    allocation_status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> LeadListResponse:
    try:
        raw_cursor = decode_cursor(cursor, 2)
        lead_cursor = (datetime.fromisoformat(raw_cursor[0]), UUID(raw_cursor[1])) if raw_cursor else None
        actor = context.actor
        key = None
        if not cursor and actor.account_type == "sales":
            key = ("sales-mine", actor.user_id, pipeline_stage, allocation_status, limit)
        rows = first_page(request, key, lambda: _lead_service(request).list_mine(
            actor, pipeline_stage, allocation_status, lead_cursor, limit + 1,
        ))
    except (InvalidCursor, ValueError) as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from error
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _list_response(rows, limit)


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_sales_lead(lead_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> LeadDetailResponse:
    try:
        row = _lead_service(request).get_detail(context.actor, lead_id)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return LeadDetailResponse(request_id=uuid4(), data=LeadDetail(**row))


@router.post("/{lead_id}:claim", response_model=LeadCommandResponse)
def claim_sales_lead(
    lead_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> LeadCommandResponse:
    request_id = str(uuid4())
    command = AssignLeadCommand(lead_id, _parse_if_match(if_match), context.actor.user_id, "claim", "sales_claim", None, idempotency_key, request_id)
    try:
        result = _lead_service(request).claim(context.actor, command)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _lead_response(result, request_id)


@router.post("/{lead_id}:assign", response_model=LeadCommandResponse)
def assign_sales_lead(
    lead_id: UUID,
    payload: AssignLeadRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> LeadCommandResponse:
    request_id = str(uuid4())
    command = AssignLeadCommand(lead_id, _parse_if_match(if_match), payload.assignee_user_id, "manual", payload.reason_code, payload.reason_text, idempotency_key, request_id)
    try:
        result = _lead_service(request).assign(context.actor, command)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _lead_response(result, request_id)


@router.post("/{lead_id}:release", response_model=LeadCommandResponse)
def release_sales_lead(
    lead_id: UUID,
    payload: ReasonRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> LeadCommandResponse:
    request_id = str(uuid4())
    command = ReleaseLeadCommand(lead_id, _parse_if_match(if_match), payload.reason_code, payload.reason_text, idempotency_key, request_id)
    try:
        result = _lead_service(request).release(context.actor, command)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _lead_response(result, request_id)


@router.post("/{lead_id}:transfer", response_model=LeadCommandResponse)
def transfer_sales_lead(
    lead_id: UUID,
    payload: TransferLeadRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> LeadCommandResponse:
    request_id = str(uuid4())
    command = TransferLeadCommand(lead_id, _parse_if_match(if_match), payload.to_assignee_user_id, payload.reason_code, payload.reason_text, idempotency_key, request_id)
    try:
        result = _lead_service(request).transfer(context.actor, command)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _lead_response(result, request_id)


@router.post("/{lead_id}:handover-assign", response_model=LeadCommandResponse)
def assign_handover_sales_lead(
    lead_id: UUID,
    payload: HandoverAssignRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> LeadCommandResponse:
    request_id = str(uuid4())
    command = TransferLeadCommand(
        lead_id,
        _parse_if_match(if_match),
        payload.to_assignee_user_id,
        "handover_assign",
        payload.reason_text,
        idempotency_key,
        request_id,
    )
    try:
        result = _lead_service(request).assign_handover(context.actor, command)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _lead_response(result, request_id)


@router.post(":batch-transfer", response_model=BatchTransferResponse)
def batch_transfer_sales_leads(
    payload: BatchTransferRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> BatchTransferResponse:
    request_id = uuid4()
    try:
        result = _lead_service(request).batch_transfer(context.actor, [item.model_dump() for item in payload.items], idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return BatchTransferResponse(request_id=request_id, data=result)


@router.get("/{lead_id}/adopted-icp", response_model=AssessmentResponse)
def get_adopted_icp(lead_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> AssessmentResponse:
    try:
        data = _lead_service(request).get_adopted_icp(context.actor, lead_id)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return AssessmentResponse(request_id=uuid4(), data=data)


@router.get("/{lead_id}/adopted-scale", response_model=AssessmentResponse)
def get_adopted_scale(lead_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> AssessmentResponse:
    try:
        data = _lead_service(request).get_adopted_scale(context.actor, lead_id)
    except AuthenticationError as error:
        _raise_lead_error(error)
    return AssessmentResponse(request_id=uuid4(), data=data)


def _pipeline_response(result: dict[str, object], request_id: str) -> PipelineChangeResponse:
    return PipelineChangeResponse(request_id=UUID(request_id), data=PipelineChangeData(**result))


@router.post("/{lead_id}:first-touch", response_model=PipelineChangeResponse)
def first_touch_sales_lead(
    lead_id: UUID,
    payload: FirstTouchRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> PipelineChangeResponse:
    request_id = str(uuid4())
    try:
        result = _lead_service(request).first_touch(context.actor, lead_id, _parse_if_match(if_match), payload.contact_id, payload.channel, payload.occurred_at, payload.note, idempotency_key, UUID(request_id))
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _pipeline_response(result, request_id)


@router.post("/{lead_id}:change-stage", response_model=PipelineChangeResponse)
def change_sales_lead_stage(
    lead_id: UUID,
    payload: ChangeStageRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> PipelineChangeResponse:
    request_id = str(uuid4())
    try:
        result = _lead_service(request).change_stage(context.actor, lead_id, _parse_if_match(if_match), payload.target_stage, payload.reason_code, payload.reason_text, None, idempotency_key, UUID(request_id))
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _pipeline_response(result, request_id)


def _terminal_stage(
    lead_id: UUID,
    target_stage: str,
    payload: TerminalStageRequest,
    request: Request,
    context: AuthContext,
    idempotency_key: str,
    if_match: str,
) -> PipelineChangeResponse:
    request_id = str(uuid4())
    try:
        result = _lead_service(request).change_stage(context.actor, lead_id, _parse_if_match(if_match), target_stage, payload.reason_code, payload.reason_text, payload.closed_at, idempotency_key, UUID(request_id))
    except AuthenticationError as error:
        _raise_lead_error(error)
    return _pipeline_response(result, request_id)


@router.post("/{lead_id}:mark-won", response_model=PipelineChangeResponse)
def mark_sales_lead_won(lead_id: UUID, payload: TerminalStageRequest, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> PipelineChangeResponse:
    return _terminal_stage(lead_id, "won", payload, request, context, idempotency_key, if_match)


@router.post("/{lead_id}:mark-lost", response_model=PipelineChangeResponse)
def mark_sales_lead_lost(lead_id: UUID, payload: TerminalStageRequest, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> PipelineChangeResponse:
    return _terminal_stage(lead_id, "lost", payload, request, context, idempotency_key, if_match)
