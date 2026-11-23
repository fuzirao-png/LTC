from typing import Any

from pg8000 import dbapi

from ltc.platform.config import get_settings


def _is_db_configured() -> bool:
    settings = get_settings()
    return all([settings.db_host, settings.db_name, settings.db_user, settings.db_password])


def _connect():
    settings = get_settings()
    return dbapi.connect(
        user=settings.db_user,
        host=settings.db_host,
        database=settings.db_name,
        port=settings.db_port,
        password=settings.db_password,
        timeout=30,
    )


def _try_postgres_context(payload: dict[str, Any]) -> dict[str, str]:
    company_id = str(payload.get("companyId") or payload.get("company_id") or "").strip()
    contact_id = str(payload.get("contactId") or payload.get("contact_id") or "").strip()
    sales_user_id = str(payload.get("salesUserId") or payload.get("sales_user_id") or "").strip()
    if not company_id or not _is_db_configured():
        return {}

    try:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT company_name, company_intro, industry_code, country_code, city, website
                FROM ltc.company
                WHERE company_id = %s
                """,
                (company_id,),
            )
            company = cur.fetchone()
            if company is None:
                return {}

            contact = None
            if contact_id:
                cur.execute(
                    """
                    SELECT full_name, primary_email, title, relationship_role
                    FROM ltc.contact
                    WHERE contact_id = %s
                      AND company_id = %s
                    """,
                    (contact_id, company_id),
                )
                contact = cur.fetchone()
            if contact is None:
                cur.execute(
                    """
                    SELECT full_name, primary_email, title, relationship_role
                    FROM ltc.contact
                    WHERE company_id = %s
                    ORDER BY priority NULLS LAST, created_at DESC
                    LIMIT 1
                    """,
                    (company_id,),
                )
                contact = cur.fetchone()

            cur.execute(
                """
                SELECT direction, subject, intent_level, next_action
                FROM ltc.email_message
                WHERE company_id = %s
                  AND (%s = '' OR contact_id::text = %s)
                  AND (%s = '' OR sales_user_id::text = %s)
                ORDER BY COALESCE(received_at, sent_at, created_at) DESC
                LIMIT 5
                """,
                (company_id, contact_id, contact_id, sales_user_id, sales_user_id),
            )
            emails = [
                f"{row[0]} | {row[1] or ''} | intent={row[2] or ''} | next={row[3] or ''}"
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT title, next_step, risks, keywords
                FROM ltc.meeting
                WHERE company_id = %s
                  AND deleted_at IS NULL
                ORDER BY COALESCE(meeting_started_at, created_at) DESC
                LIMIT 1
                """,
                (company_id,),
            )
            meeting = cur.fetchone()

            cur.execute(
                """
                SELECT title, description, status
                FROM ltc.follow_up_task
                WHERE company_id = %s
                  AND status IN ('pending', 'in_progress')
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (company_id,),
            )
            tasks = [f"{row[0]} | {row[1] or ''} | status={row[2]}" for row in cur.fetchall()]

            cur.execute(
                """
                SELECT payload->>'event_type', subject, body
                FROM ltc.customer_activity
                WHERE company_id = %s
                ORDER BY occurred_at DESC
                LIMIT 20
                """,
                (company_id,),
            )
            activities = [f"{row[0] or ''} | {row[1] or ''} | {row[2] or ''}" for row in cur.fetchall()]
    except Exception:
        return {}

    customer_profile = " | ".join(
        str(item)
        for item in [
            company[1],
            f"industry={company[2]}" if company[2] else "",
            f"country={company[3]}" if company[3] else "",
            f"city={company[4]}" if company[4] else "",
            f"website={company[5]}" if company[5] else "",
        ]
        if item
    )
    latest_meeting = ""
    if meeting:
        latest_meeting = f"{meeting[0] or ''} | next_step={meeting[1] or ''} | risks={meeting[2] or []} | keywords={meeting[3] or []}"

    return {
        "customerName": str(company[0] or "").strip(),
        "recipientName": str(contact[0] if contact else "").strip(),
        "recipientEmail": str(contact[1] if contact else "").strip(),
        "recipientTitle": str(contact[2] if contact else "").strip(),
        "recipientRole": str(contact[3] if contact else "").strip(),
        "customerProfile": customer_profile,
        "recentEmails": "\n".join(emails),
        "latestMeeting": latest_meeting,
        "openTasks": "\n".join(tasks),
        "recentActivities": "\n".join(activities),
    }


def build_email_generation_memory(payload: dict[str, Any]) -> dict[str, str]:
    postgres_context = _try_postgres_context(payload)
    base = {
        "salesName": str(payload.get("salesName") or "").strip(),
        "customerName": str(payload.get("customerName") or "").strip(),
        "recipientName": str(payload.get("recipientName") or "").strip(),
        "recipientEmail": str(payload.get("recipientEmail") or payload.get("to") or "").strip(),
        "recipientTitle": str(payload.get("recipientTitle") or "").strip(),
        "recipientRole": "",
        "customerProfile": "",
        "recentEmails": "",
        "latestMeeting": "",
        "openTasks": "",
        "recentActivities": "",
        "currentSubject": str(payload.get("currentSubject") or "").strip(),
        "currentBody": str(payload.get("currentBody") or "").strip(),
        "customPrompt": str(payload.get("customPrompt") or "").strip(),
        "purpose": str(payload.get("purpose") or "first_touch").strip(),
        "mode": str(payload.get("mode") or "initial").strip() or "initial",
    }
    for key, value in postgres_context.items():
        if value:
            base[key] = value
    return base


def build_email_agent_context(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    normalized = dict(payload)
    normalized["currentSubject"] = str(payload.get("subject") or payload.get("currentSubject") or "").strip()
    normalized["currentBody"] = str(payload.get("body") or payload.get("currentBody") or "").strip()
    normalized["customPrompt"] = str(payload.get("instruction") or payload.get("customPrompt") or "").strip()
    normalized["mode"] = "initial" if operation == "generate" else "regenerate"
    context = build_email_generation_memory(normalized)
    context["operation"] = operation
    context["targetLanguage"] = str(payload.get("targetLanguage") or "").strip()
    context["salesUserId"] = str(payload.get("salesUserId") or "").strip()
    if payload.get("structuredTranslation"):
        context["structuredTranslation"] = True
        context["translationSegments"] = payload.get("translationSegments") or []
    return context



