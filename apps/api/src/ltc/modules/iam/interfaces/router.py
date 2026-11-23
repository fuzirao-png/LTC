"""FastAPI routes for IAM authentication and sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ltc.modules.iam.application.auth_service import (
    AuthenticationError,
    AuthenticationService,
    DepartSalesCommand,
    LoginCommand,
    RefreshCommand,
)
from ltc.modules.iam.application.account_service import (
    AccountManagementService,
    CreateUserCommand,
    UpdateUserCommand,
)
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.schemas import AuthData, AuthResponse, LoginRequest, UserResponse
from ltc.modules.iam.interfaces.departure_schemas import DepartSalesRequest, DepartSalesResponse, DepartSalesResponseData, ReturnedPool
from ltc.modules.iam.interfaces.account_schemas import (
    PageMeta,
    PasswordResetData,
    PasswordResetResponse,
    UserCommandData,
    UserCommandResponse,
    UserCreateRequest,
    UserEnvelope,
    UserListResponse,
    UserPatchRequest,
    UserSummary,
)
from ltc.platform.auth import AccessTokenCodec, AccessTokenError, new_refresh_token, refresh_token_hash
from ltc.platform.config import AppSettings
from ltc.platform.pagination import InvalidCursor, decode_cursor, encode_cursor


router = APIRouter(tags=["iam"])
bearer = HTTPBearer(auto_error=False)
ACCESS_COOKIE = "ltc_access_token"
REFRESH_COOKIE = "ltc_refresh_token"


def _service(request: Request) -> AuthenticationService:
    return request.app.state.iam_authentication_service


def _account_service(request: Request) -> AccountManagementService:
    return request.app.state.iam_account_management_service


def _codec(request: Request) -> AccessTokenCodec:
    return AccessTokenCodec(request.app.state.settings)


def _cookie_kwargs(settings: AppSettings) -> dict[str, object]:
    return {
        "httponly": True,
        "secure": settings.environment == "production",
        "samesite": "lax",
        "path": "/",
    }


def _response(actor: CurrentActor, request_id: UUID) -> AuthResponse:
    return AuthResponse(
        request_id=request_id,
        data=AuthData(
            user=UserResponse(
                user_id=actor.user_id,
                username=actor.username,
                display_name=actor.display_name,
                account_type=actor.account_type,
                sales_tier=actor.sales_tier,
                region_code=actor.region_code,
                capacity_limit=actor.capacity_limit,
                status=actor.status,
                active_assignment_count=actor.active_assignment_count,
            ),
            capabilities=actor.capabilities,
        ),
    )


def _raise_auth_error(error: AuthenticationError) -> None:
    status_code = status.HTTP_401_UNAUTHORIZED
    if error.code == "USER_LOCKED":
        status_code = status.HTTP_423_LOCKED
    raise HTTPException(status_code=status_code, detail={"code": error.code, "message": error.code}) from error


def _access_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    access_cookie: str | None,
):
    token = credentials.credentials if credentials else access_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_INVALID_SESSION"})
    try:
        return _codec(request).decode(token)
    except AccessTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_INVALID_SESSION"}) from error


class AuthContext:
    def __init__(self, actor: CurrentActor, session_id: UUID) -> None:
        self.actor = actor
        self.session_id = session_id


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> AuthContext:
    claims = _access_claims(request, credentials, access_cookie)
    try:
        actor = _service(request).get_current_actor(
            session_id=claims.session_id,
            user_id=claims.user_id,
            issued_token_version=claims.token_version,
        )
    except AuthenticationError as error:
        _raise_auth_error(error)
    return AuthContext(actor=actor, session_id=claims.session_id)


@router.post("/auth/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> AuthResponse:
    refresh_token = new_refresh_token()
    now = datetime.now(timezone.utc)
    command = LoginCommand(
        username=payload.username,
        password=payload.password,
        refresh_token_hash=refresh_token_hash(refresh_token),
        refresh_expires_at=now + timedelta(days=request.app.state.settings.refresh_session_ttl_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    try:
        session = _service(request).login(command, now=now)
    except AuthenticationError as error:
        _raise_auth_error(error)
    access_token = _codec(request).issue(session.session_id, session.actor.user_id, session.actor.token_version)
    cookies = _cookie_kwargs(request.app.state.settings)
    response.set_cookie(ACCESS_COOKIE, access_token, **cookies)
    response.set_cookie(REFRESH_COOKIE, refresh_token, **cookies)
    return _response(session.actor, uuid4())


@router.post("/auth/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> AuthResponse:
    if not refresh_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "AUTH_INVALID_SESSION"})
    replacement = new_refresh_token()
    now = datetime.now(timezone.utc)
    command = RefreshCommand(
        refresh_token_hash=refresh_token_hash(refresh_cookie),
        new_refresh_token_hash=refresh_token_hash(replacement),
        refresh_expires_at=now + timedelta(days=request.app.state.settings.refresh_session_ttl_days),
    )
    try:
        session = _service(request).refresh(command, now=now)
    except AuthenticationError as error:
        _raise_auth_error(error)
    access_token = _codec(request).issue(session.session_id, session.actor.user_id, session.actor.token_version)
    cookies = _cookie_kwargs(request.app.state.settings)
    response.set_cookie(ACCESS_COOKIE, access_token, **cookies)
    response.set_cookie(REFRESH_COOKIE, replacement, **cookies)
    return _response(session.actor, uuid4())


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(request: Request, context: AuthContext = Depends(get_auth_context)) -> Response:
    _service(request).logout(context.session_id)
    cookies = _cookie_kwargs(request.app.state.settings)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(ACCESS_COOKIE, path=cookies["path"])
    response.delete_cookie(REFRESH_COOKIE, path=cookies["path"])
    return response


@router.get("/auth/me", response_model=AuthResponse)
def me(context: AuthContext = Depends(get_auth_context)) -> AuthResponse:
    return _response(context.actor, uuid4())


def _parse_if_match(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error


def _raise_management_error(error: AuthenticationError) -> None:
    if error.code in {"FORBIDDEN_STRATEGIC_REQUIRED"}:
        raise HTTPException(status_code=403, detail={"code": error.code}) from error
    if error.code in {"USER_NOT_FOUND"}:
        raise HTTPException(status_code=404, detail={"code": error.code}) from error
    if error.code in {"USERNAME_ALREADY_EXISTS", "EMAIL_ALREADY_EXISTS", "USER_VERSION_CONFLICT", "IDEMPOTENCY_KEY_REUSED", "IDEMPOTENCY_IN_PROGRESS", "USER_ALREADY_DEPARTED", "INVALID_USER_STATUS"}:
        raise HTTPException(status_code=409, detail={"code": error.code}) from error
    raise HTTPException(status_code=422, detail={"code": error.code}) from error


@router.get("/users", response_model=UserListResponse)
def list_users(
    request: Request,
    account_type: str | None = None,
    region_code: str | None = None,
    sales_tier: str | None = None,
    user_status: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, alias="q", max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_auth_context),
) -> UserListResponse:
    try:
        raw_cursor = decode_cursor(cursor, 2)
        user_cursor = (raw_cursor[0], UUID(raw_cursor[1])) if raw_cursor else None
        rows = _account_service(request).list_users(context.actor, account_type, region_code, sales_tier, user_status, query, user_cursor, limit + 1)
    except (InvalidCursor, ValueError) as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from error
    except AuthenticationError as error:
        _raise_management_error(error)
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = encode_cursor(visible[-1]["username"].lower(), visible[-1]["user_id"]) if has_more and visible else None
    return UserListResponse(request_id=uuid4(), data=[UserSummary(**row) for row in visible], page=PageMeta(next_cursor=next_cursor, has_more=has_more))


@router.post("/users", response_model=UserEnvelope, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
) -> UserEnvelope:
    command = CreateUserCommand(
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        email=payload.email,
        account_type=payload.account_type,
        sales_tier=payload.sales_tier,
        region_code=payload.region_code,
        capacity_limit=payload.capacity_limit,
        idempotency_key=idempotency_key,
        request_id=str(uuid4()),
    )
    try:
        result = _account_service(request).create_user(context.actor, command)
    except AuthenticationError as error:
        _raise_management_error(error)
    return UserEnvelope(request_id=UUID(command.request_id), data=UserSummary(**result))


@router.patch("/users/{user_id}", response_model=UserEnvelope)
def update_user(
    user_id: UUID,
    payload: UserPatchRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> UserEnvelope:
    command = UpdateUserCommand(
        user_id=user_id,
        expected_version=_parse_if_match(if_match),
        display_name=payload.display_name,
        email=payload.email,
        email_present="email" in payload.model_fields_set,
        idempotency_key=idempotency_key,
        request_id=str(uuid4()),
    )
    try:
        result = _account_service(request).update_user(context.actor, command)
    except AuthenticationError as error:
        _raise_management_error(error)
    return UserEnvelope(request_id=UUID(command.request_id), data=UserSummary(**result))


def _command_response(result: object, request_id: str) -> UserCommandResponse:
    command = result
    return UserCommandResponse(
        request_id=UUID(request_id),
        data=UserCommandData(
            user_id=command.user_id,
            status=command.status,
            version=command.version,
            active_assignment_count=command.active_assignment_count,
        ),
    )


@router.post("/users/{user_id}:disable", response_model=UserCommandResponse)
def disable_user(user_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> UserCommandResponse:
    request_id = str(uuid4())
    try:
        result = _account_service(request).disable_user(context.actor, user_id, _parse_if_match(if_match), idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_management_error(error)
    return _command_response(result, request_id)


@router.post("/users/{user_id}:enable", response_model=UserCommandResponse)
def enable_user(user_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> UserCommandResponse:
    request_id = str(uuid4())
    try:
        result = _account_service(request).enable_user(context.actor, user_id, _parse_if_match(if_match), idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_management_error(error)
    return _command_response(result, request_id)


@router.post("/users/{user_id}:unlock", response_model=UserCommandResponse)
def unlock_user(user_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> UserCommandResponse:
    request_id = str(uuid4())
    try:
        result = _account_service(request).unlock_user(context.actor, user_id, _parse_if_match(if_match), idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_management_error(error)
    return _command_response(result, request_id)


@router.post("/users/{user_id}:reset-password", response_model=PasswordResetResponse)
def reset_password(user_id: UUID, request: Request, context: AuthContext = Depends(get_auth_context), idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1), if_match: str = Header(..., alias="If-Match", min_length=1)) -> PasswordResetResponse:
    request_id = str(uuid4())
    try:
        result = _account_service(request).reset_password(context.actor, user_id, _parse_if_match(if_match), idempotency_key, request_id)
    except AuthenticationError as error:
        _raise_management_error(error)
    return PasswordResetResponse(request_id=UUID(request_id), data=PasswordResetData(user_id=result.user_id, temporary_password=result.temporary_password))


@router.post("/users/{user_id}:depart", response_model=DepartSalesResponse)
def depart_sales(
    user_id: UUID,
    payload: DepartSalesRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> DepartSalesResponse:
    try:
        expected_version = int(if_match.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error
    command = DepartSalesCommand(
        target_user_id=user_id,
        actor_user_id=context.actor.user_id,
        reason_text=payload.reason,
        expected_version=expected_version,
        request_id=str(uuid4()),
        idempotency_key=idempotency_key,
    )
    try:
        result = _service(request).depart_sales(command, request.app.state.sales_departure_port)
    except AuthenticationError as error:
        if error.code == "FORBIDDEN_STRATEGIC_REQUIRED":
            raise HTTPException(status_code=403, detail={"code": error.code}) from error
        if error.code in {"USER_NOT_FOUND", "TARGET_NOT_SALES"}:
            raise HTTPException(status_code=404, detail={"code": error.code}) from error
        if error.code == "USER_VERSION_CONFLICT":
            raise HTTPException(status_code=409, detail={"code": error.code}) from error
        raise HTTPException(status_code=409, detail={"code": error.code}) from error
    return DepartSalesResponse(
        request_id=UUID(command.request_id),
        data=DepartSalesResponseData(
            user_id=result.user_id,
            status="departed",
            released_lead_count=result.released_lead_count,
            returned_pools=[ReturnedPool(**pool) for pool in result.returned_pools],
            departed_at=result.departed_at,
            handover_lead_count=result.handover_lead_count,
        ),
    )
