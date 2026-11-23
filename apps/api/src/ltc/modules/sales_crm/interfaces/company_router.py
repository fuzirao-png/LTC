"""Company, Contact, and Timeline HTTP routes (PRD §4.9, §6.1).

POST /api/v1/companies/{company_id}/contacts     Create Contact
PATCH /api/v1/contacts/{contact_id}               Update Contact
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from psycopg.rows import dict_row

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.sales_crm.application.contact_roster_service import ContactRosterError
from ltc.modules.sales_crm.interfaces.company_schemas import (
    CompanyDetailResponse,
    CompanyResponse,
    ContactDetailResponse,
    ContactListResponse,
    ContactResponse,
    ContactRosterMutationRequest,
    ContactRosterResponse,
    CreateContactRequest,
    PatchCompanyRequest,
    PatchContactRequest,
    TimelineEvent,
    TimelineResponse,
)
from ltc.platform.pagination import decode_cursor, encode_cursor, InvalidCursor

router = APIRouter(tags=["Company & Contact"])


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_if_match(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"'))
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"}) from error


def _require_strategic_or_sales(context: AuthContext) -> None:
    if context.actor.account_type not in ("strategic", "sales"):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})


def _raise_roster_error(error: ContactRosterError) -> None:
    status_code = 404 if error.code.endswith("NOT_FOUND") else 409
    if error.code in {
        "INVALID_ACTION", "INVALID_POSITION", "REPLACEMENT_REASON_REQUIRED",
        "REMOVAL_REASON_REQUIRED",
    }:
        status_code = 422
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    ) from error


def _company_from_row(row: dict) -> CompanyResponse:
    return CompanyResponse(
        company_id=row["company_id"],
        origin_candidate_id=row.get("origin_candidate_id"),
        company_name=row["company_name"],
        normalized_company_name=row["normalized_company_name"],
        legal_name=row.get("legal_name"),
        primary_domain=row.get("primary_domain"),
        website=row.get("website"),
        country_code=row.get("country_code"),
        region_code=row.get("region_code"),
        region_mapping_version=row.get("region_mapping_version"),
        city=row.get("city"),
        industry_code=row.get("industry_code"),
        company_intro=row.get("company_intro"),
        employee_count=row.get("employee_count"),
        lifecycle_status=row["lifecycle_status"],
        version=row["version"],
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived_at=row.get("archived_at"),
    )


def _contact_from_row(row: dict) -> ContactResponse:
    return ContactResponse(
        contact_id=row["contact_id"],
        company_id=row["company_id"],
        source_candidate_contact_id=row.get("source_candidate_contact_id"),
        full_name=row["full_name"],
        normalized_name=row["normalized_name"],
        title=row.get("title"),
        title_normalized=row.get("title_normalized"),
        department=row.get("department"),
        relationship_role=row.get("relationship_role"),
        priority=row.get("priority"),
        primary_email=row.get("primary_email"),
        normalized_email=row.get("normalized_email"),
        email_status=row["email_status"],
        email_type=row.get("email_type"),
        email_score=float(row["email_score"]) if row.get("email_score") is not None else None,
        email_pattern=row.get("email_pattern"),
        phone=row.get("phone"),
        linkedin_url=row.get("linkedin_url"),
        source=row["source"],
        last_contacted_at=row.get("last_contacted_at"),
        employment_status=row.get("employment_status") or "unknown",
        legal_basis_status=row.get("legal_basis_status") or "unknown",
        last_verified_at=row.get("last_verified_at"),
        status=row["status"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _audit_contact_change(
    connection: object,
    *,
    actor_user_id: UUID,
    action: str,
    contact_id: UUID,
    before: dict | None,
    after: dict | None,
) -> None:
    connection.execute(
        """
        INSERT INTO ltc.audit_log (
            actor_user_id, action, resource_type, resource_id, before_data, after_data
        )
        VALUES (%s,%s,'contact',%s,%s::jsonb,%s::jsonb)
        """,
        (
            str(actor_user_id),
            action,
            str(contact_id),
            json.dumps(before, default=str, ensure_ascii=False) if before else None,
            json.dumps(after, default=str, ensure_ascii=False) if after else None,
        ),
    )


# ── Company ──────────────────────────────────────────────────────────

@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company(
    company_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> CompanyDetailResponse:
    """Get company details (PRD §4.9)."""
    _require_strategic_or_sales(context)
    db = request.app.state.database
    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT *
                   FROM ltc.company
                   WHERE company_id = %s""",
                (str(company_id),),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "COMPANY_NOT_FOUND"})
    return CompanyDetailResponse(request_id=uuid4(), data=_company_from_row(dict(row)))


@router.patch("/companies/{company_id}", response_model=CompanyDetailResponse)
def patch_company(
    company_id: UUID,
    body: PatchCompanyRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> CompanyDetailResponse:
    """Update company master data (PRD §4.9)."""
    _require_strategic_or_sales(context)
    expected_version = _parse_if_match(if_match)
    db = request.app.state.database
    now = datetime.now(timezone.utc)

    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM ltc.company WHERE company_id = %s FOR UPDATE",
                (str(company_id),),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": "COMPANY_NOT_FOUND"})
        current_version: int = row["version"]
        if current_version != expected_version:
            raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail={"code": "INVALID_COMMAND", "message": "No fields to update"})

        set_clauses: list[str] = []
        params: list[object] = []
        for field, value in updates.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        set_clauses.append("version = version + 1")
        set_clauses.append("updated_at = %s")
        params.append(now)
        params.append(str(company_id))

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE ltc.company SET {', '.join(set_clauses)} WHERE company_id = %s",
                params,
            )

        # Re-fetch updated row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM ltc.company WHERE company_id = %s", (str(company_id),))
            updated = cur.fetchone()

    return CompanyDetailResponse(request_id=uuid4(), data=_company_from_row(dict(updated)))


# ── Contacts (sub-resource of Company) ───────────────────────────────

@router.get("/companies/{company_id}/contacts", response_model=ContactListResponse)
def list_contacts(
    company_id: UUID,
    request: Request,
    status: str | None = Query(default=None, pattern=r"^(active|inactive|bounced)$"),
    context: AuthContext = Depends(get_auth_context),
) -> ContactListResponse:
    """List contacts for a company (PRD §4.9)."""
    _require_strategic_or_sales(context)
    db = request.app.state.database
    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if status:
                cur.execute(
                    "SELECT * FROM ltc.contact WHERE company_id = %s AND status = %s ORDER BY priority ASC NULLS LAST, full_name ASC",
                    (str(company_id), status),
                )
            else:
                cur.execute(
                    "SELECT * FROM ltc.contact WHERE company_id = %s ORDER BY priority ASC NULLS LAST, full_name ASC",
                    (str(company_id),),
                )
            rows = cur.fetchall()
    contacts = [_contact_from_row(dict(r)) for r in rows]
    return ContactListResponse(request_id=uuid4(), data=contacts)


@router.post("/companies/{company_id}/contacts", response_model=ContactDetailResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    company_id: UUID,
    body: CreateContactRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> ContactDetailResponse:
    """Create a new contact for a company (PRD §4.9)."""
    _require_strategic_or_sales(context)
    db = request.app.state.database
    now = datetime.now(timezone.utc)
    contact_id = uuid4()
    normalized_name = body.full_name.casefold()
    normalized_email = body.primary_email.casefold() if body.primary_email else None
    title_normalized = body.title.casefold() if body.title else None

    with db.transaction() as conn:
        # Verify company exists
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM ltc.company WHERE company_id = %s", (str(company_id),))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail={"code": "COMPANY_NOT_FOUND"})

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT contact_id
                FROM ltc.contact
                WHERE company_id=%s AND status <> 'archived'
                  AND (
                    (%s::text IS NOT NULL AND normalized_email=%s)
                    OR (%s::text IS NOT NULL AND lower(linkedin_url)=lower(%s))
                  )
                LIMIT 1
                """,
                (
                    str(company_id), normalized_email, normalized_email,
                    body.linkedin_url, body.linkedin_url,
                ),
            )
            duplicate = cur.fetchone()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTACT_DUPLICATE",
                    "message": "邮箱或LinkedIn已存在，请合并联系人资料。",
                    "contact_id": str(duplicate["contact_id"]),
                },
            )

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ltc.contact
                   (contact_id, company_id, full_name, normalized_name,
                    title, title_normalized, department, relationship_role,
                    priority, primary_email, normalized_email, email_status,
                    phone, linkedin_url, employment_status, legal_basis_status,
                    last_verified_at, source, status, version, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual','active',0,%s,%s)""",
                (str(contact_id), str(company_id), body.full_name, normalized_name,
                 body.title, title_normalized, body.department,
                 body.relationship_role, body.priority,
                 body.primary_email, normalized_email, "unknown",
                 body.phone, body.linkedin_url, body.employment_status,
                 body.legal_basis_status, body.last_verified_at, now, now),
            )

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM ltc.contact WHERE contact_id = %s", (str(contact_id),))
            new_row = cur.fetchone()
        _audit_contact_change(
            conn,
            actor_user_id=context.actor.user_id,
            action="contact.created",
            contact_id=contact_id,
            before=None,
            after=dict(new_row),
        )

    return ContactDetailResponse(request_id=uuid4(), data=_contact_from_row(dict(new_row)))


@router.patch("/contacts/{contact_id}", response_model=ContactDetailResponse)
def patch_contact(
    contact_id: UUID,
    body: PatchContactRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    if_match: str = Header(..., alias="If-Match", min_length=1),
) -> ContactDetailResponse:
    """Update a contact (PRD §4.9)."""
    _require_strategic_or_sales(context)
    expected_version = _parse_if_match(if_match)
    db = request.app.state.database
    now = datetime.now(timezone.utc)

    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM ltc.contact WHERE contact_id = %s FOR UPDATE",
                (str(contact_id),),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": "CONTACT_NOT_FOUND"})
        current_version: int = row["version"]
        if current_version != expected_version:
            raise HTTPException(status_code=409, detail={"code": "VERSION_CONFLICT"})

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail={"code": "INVALID_COMMAND", "message": "No fields to update"})

        # Re-normalize if full_name or primary_email changes
        if "full_name" in updates and updates["full_name"]:
            updates["normalized_name"] = updates["full_name"].casefold()
        if "primary_email" in updates:
            updates["normalized_email"] = updates["primary_email"].casefold() if updates["primary_email"] else None
        if "title" in updates:
            updates["title_normalized"] = updates["title"].casefold() if updates["title"] else None

        email_check = updates.get("normalized_email") if "normalized_email" in updates else None
        linkedin_check = updates.get("linkedin_url") if "linkedin_url" in updates else None
        if email_check or linkedin_check:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT contact_id
                    FROM ltc.contact
                    WHERE company_id=%s AND contact_id<>%s AND status<>'archived'
                      AND (
                        (%s::text IS NOT NULL AND normalized_email=%s)
                        OR (%s::text IS NOT NULL AND lower(linkedin_url)=lower(%s))
                      )
                    LIMIT 1
                    """,
                    (
                        str(row["company_id"]), str(contact_id),
                        email_check, email_check, linkedin_check, linkedin_check,
                    ),
                )
                duplicate = cur.fetchone()
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONTACT_DUPLICATE",
                        "message": "邮箱或LinkedIn已存在，请合并联系人资料。",
                        "contact_id": str(duplicate["contact_id"]),
                    },
                )

        set_clauses: list[str] = []
        params: list[object] = []
        for field, value in updates.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        set_clauses.append("version = version + 1")
        set_clauses.append("updated_at = %s")
        params.append(now)
        params.append(str(contact_id))

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE ltc.contact SET {', '.join(set_clauses)} WHERE contact_id = %s",
                params,
            )

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM ltc.contact WHERE contact_id = %s", (str(contact_id),))
            updated = cur.fetchone()
        _audit_contact_change(
            conn,
            actor_user_id=context.actor.user_id,
            action="contact.updated",
            contact_id=contact_id,
            before=dict(row),
            after=dict(updated),
        )

    return ContactDetailResponse(request_id=uuid4(), data=_contact_from_row(dict(updated)))


# ── Contact Top 5 roster ────────────────────────────────────────────

@router.get("/companies/{company_id}/contact-roster", response_model=ContactRosterResponse)
def get_contact_roster(
    company_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> ContactRosterResponse:
    _require_strategic_or_sales(context)
    try:
        data = request.app.state.contact_roster_service.get_roster(company_id)
    except ContactRosterError as error:
        _raise_roster_error(error)
    return ContactRosterResponse(request_id=uuid4(), data=data)


@router.post("/companies/{company_id}/contact-roster/recalculate", response_model=ContactRosterResponse)
def recalculate_contact_roster(
    company_id: UUID,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> ContactRosterResponse:
    _require_strategic_or_sales(context)
    try:
        data = request.app.state.contact_roster_service.recalculate(
            company_id,
            context.actor.user_id,
        )
    except ContactRosterError as error:
        _raise_roster_error(error)
    return ContactRosterResponse(request_id=uuid4(), data=data)


@router.patch(
    "/companies/{company_id}/contact-roster/{contact_id}",
    response_model=ContactRosterResponse,
)
def mutate_contact_roster(
    company_id: UUID,
    contact_id: UUID,
    body: ContactRosterMutationRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
) -> ContactRosterResponse:
    _require_strategic_or_sales(context)
    try:
        data = request.app.state.contact_roster_service.mutate(
            company_id,
            contact_id,
            action=body.action,
            actor_user_id=context.actor.user_id,
            position=body.position,
            replace_contact_id=body.replace_contact_id,
            reason=body.reason,
        )
    except ContactRosterError as error:
        _raise_roster_error(error)
    return ContactRosterResponse(request_id=uuid4(), data=data)


# ── Customer Timeline (PRD §6.1) ─────────────────────────────────────

@router.get("/companies/{company_id}/timeline", response_model=TimelineResponse)
def get_company_timeline(
    company_id: UUID,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    context: AuthContext = Depends(get_auth_context),
) -> TimelineResponse:
    """Aggregated customer timeline (PRD §6.1).

    Returns stage transitions, emails, meetings, tasks, activities, and
    analysis reports in a unified reverse-chronological feed.
    """
    _require_strategic_or_sales(context)
    db = request.app.state.database

    try:
        raw_cursor = decode_cursor(cursor, 2) if cursor else None
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor_occurred = raw_cursor[0] if raw_cursor else now_iso
        cursor_id = raw_cursor[1] if raw_cursor else "00000000-0000-0000-0000-000000000000"
    except (InvalidCursor, ValueError):
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"})

    # Query: find all related lead IDs for this company
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT lead_id FROM ltc.sales_lead WHERE company_id = %s",
                (str(company_id),),
            )
            lead_ids = [str(r[0]) for r in cur.fetchall()]

    if not lead_ids:
        # No leads — return empty (no timeline without related leads)
        return TimelineResponse(
            request_id=uuid4(),
            data=[],
            page={"next_cursor": None, "has_more": False},
        )

    lead_placeholders = ",".join(["%s"] * len(lead_ids))

    # Union query across all timeline sources.
    # Each branch that uses IN (lead_placeholders) needs its own copy of lead_ids.
    company_id_str = str(company_id)

    query = f"""
    SELECT * FROM (
        -- Stage transitions
        SELECT tl.transition_id AS event_id,
               'stage_transition' AS event_type,
               tl.occurred_at,
               ('Pipeline: ' || COALESCE(tl.from_pipeline_stage, '') || ' → ' || COALESCE(tl.to_pipeline_stage, '')) AS title,
               tl.reason_text AS description,
               jsonb_build_object(
                   'lead_id', tl.lead_id,
                   'from_stage', tl.from_pipeline_stage,
                   'to_stage', tl.to_pipeline_stage,
                   'event_type', tl.event_type
               ) AS metadata
        FROM ltc.lead_stage_transition tl
        WHERE tl.company_id = %s

        UNION ALL

        -- Emails
        SELECT em.email_id AS event_id,
               'email' AS event_type,
               COALESCE(em.sent_at, em.received_at, em.created_at) AS occurred_at,
               COALESCE(NULLIF(em.subject, ''), '(no subject)') AS title,
               substring(COALESCE(em.body_text, ''), 1, 200) AS description,
               jsonb_build_object(
                   'lead_id', em.lead_id,
                   'contact_id', em.contact_id,
                   'direction', em.direction,
                   'status', em.status
               ) AS metadata
        FROM ltc.email_message em
        WHERE em.company_id = %s
           OR em.lead_id IN ({lead_placeholders})

        UNION ALL

        -- Meetings
        SELECT m.meeting_id AS event_id,
               'meeting' AS event_type,
               COALESCE(m.meeting_started_at, m.created_at) AS occurred_at,
               COALESCE(NULLIF(m.title, ''), 'Meeting') AS title,
               m.next_step AS description,
               jsonb_build_object(
                   'lead_id', m.lead_id,
                   'contact_id', m.primary_contact_id,
                   'duration_seconds', m.duration_seconds,
                   'processing_status', m.processing_status
               ) AS metadata
        FROM ltc.meeting m
        WHERE m.company_id = %s
           OR m.lead_id IN ({lead_placeholders})

        UNION ALL

        -- Tasks
        SELECT ft.task_id AS event_id,
               'task' AS event_type,
               COALESCE(ft.due_at, ft.created_at) AS occurred_at,
               ft.title AS title,
               ft.description AS description,
               jsonb_build_object(
                   'lead_id', ft.lead_id,
                   'status', ft.status,
                   'priority', ft.priority,
                   'task_type', ft.task_type
               ) AS metadata
        FROM ltc.follow_up_task ft
        WHERE ft.company_id = %s
           OR ft.lead_id IN ({lead_placeholders})

        UNION ALL

        -- Customer Activities
        SELECT ca.activity_id AS event_id,
               'activity' AS event_type,
               ca.occurred_at,
               ca.subject AS title,
               ca.body AS description,
               jsonb_build_object(
                   'lead_id', ca.lead_id,
                   'activity_type', ca.activity_type,
                   'direction', ca.direction
               ) AS metadata
        FROM ltc.customer_activity ca
        WHERE ca.company_id = %s
           OR ca.lead_id IN ({lead_placeholders})

        UNION ALL

        -- Analysis Reports
        SELECT ar.report_id AS event_id,
               'report' AS event_type,
               ar.generated_at AS occurred_at,
               ('Analysis Report v' || ar.version_no::text) AS title,
               ar.summary AS description,
               jsonb_build_object(
                   'analysis_run_id', ar.analysis_run_id,
                   'version_no', ar.version_no,
                   'report_type', ar.report_type
               ) AS metadata
        FROM ltc.analysis_report ar
        WHERE ar.company_id = %s
    ) timeline
    WHERE (occurred_at, event_id) < (%s::timestamptz, %s::uuid)
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT %s
    """

    params: list[object] = [
        company_id_str,  # stage transitions
        company_id_str, *lead_ids,  # emails
        company_id_str, *lead_ids,  # meetings
        company_id_str, *lead_ids,  # tasks
        company_id_str, *lead_ids,  # activities
        company_id_str,  # reports
        cursor_occurred, cursor_id, limit + 1,
    ]

    with db.transaction() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    has_more = len(rows) > limit
    visible = rows[:limit]
    events = [
        TimelineEvent(
            event_id=UUID(r["event_id"]),
            event_type=r["event_type"],
            occurred_at=r["occurred_at"],
            title=r["title"],
            description=r.get("description"),
            metadata=r.get("metadata") or {},
        )
        for r in visible
    ]

    next_cursor = None
    if has_more and events:
        last = visible[-1]
        next_cursor = encode_cursor(
            last["occurred_at"].isoformat() if hasattr(last["occurred_at"], "isoformat") else str(last["occurred_at"]),
            last["event_id"],
        )

    return TimelineResponse(
        request_id=uuid4(),
        data=events,
        page={"next_cursor": next_cursor, "has_more": has_more},
    )
