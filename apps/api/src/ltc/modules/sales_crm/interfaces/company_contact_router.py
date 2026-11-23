from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.sales_crm.interfaces.company_contact_schemas import (
    CompanyPatchRequest,
    CompanyResponse,
    ContactListResponse,
    ContactResponse,
    ContactWriteRequest,
)


router = APIRouter(tags=["sales-crm"])


def _service(request: Request):
    return request.app.state.sales_company_contact_service


def _raise(error: AuthenticationError) -> None:
    if error.code.startswith("FORBIDDEN"):
        raise HTTPException(status_code=403, detail={"code": error.code}) from error
    if error.code.endswith("NOT_FOUND"):
        raise HTTPException(status_code=404, detail={"code": error.code}) from error
    if error.code.endswith("_EMPTY"):
        raise HTTPException(status_code=422, detail={"code": error.code}) from error
    raise HTTPException(status_code=409, detail={"code": error.code}) from error


def _parse_if_match(value: str) -> int:
    try:
        return int(value.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error


@router.get("/companies/{company_id}", response_model=CompanyResponse)
def get_company(company_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> CompanyResponse:
    try:
        data = _service(request).get_company(context.actor, company_id)
    except AuthenticationError as error:
        _raise(error)
    return CompanyResponse(request_id=uuid4(), data=data)


@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_contacts(company_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context)) -> ContactListResponse:
    try:
        data = _service(request).list_contacts(context.actor, company_id)
    except AuthenticationError as error:
        _raise(error)
    return ContactListResponse(request_id=uuid4(), data=data)


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    payload: CompanyPatchRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> CompanyResponse:
    try:
        data = _service(request).update_company(
            context.actor,
            company_id,
            _parse_if_match(if_match),
            payload.model_dump(exclude_unset=True),
            idempotency_key,
            uuid4(),
        )
    except AuthenticationError as error:
        _raise(error)
    return CompanyResponse(request_id=uuid4(), data=data)


@router.post("/companies/{company_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    company_id: UUID,
    payload: ContactWriteRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> ContactResponse:
    if not payload.full_name:
        raise HTTPException(status_code=422, detail={"code": "FULL_NAME_REQUIRED"})
    try:
        data = _service(request).create_contact(
            context.actor, company_id, payload.model_dump(exclude_none=True), idempotency_key, uuid4()
        )
    except AuthenticationError as error:
        _raise(error)
    return ContactResponse(request_id=uuid4(), data=data)


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: UUID,
    payload: ContactWriteRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> ContactResponse:
    try:
        data = _service(request).update_contact(
            context.actor,
            contact_id,
            _parse_if_match(if_match),
            payload.model_dump(exclude_unset=True),
            idempotency_key,
            uuid4(),
        )
    except AuthenticationError as error:
        _raise(error)
    return ContactResponse(request_id=uuid4(), data=data)
