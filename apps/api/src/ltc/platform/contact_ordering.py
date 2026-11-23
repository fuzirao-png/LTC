from __future__ import annotations

from typing import Any, Iterable


_PROCUREMENT_TERMS = ("procurement", "purchasing", "strategic sourcing", "采购", "采买")
_COMMERCIAL_TERMS = ("commercial", "business development", "business manager", "商务", "商业")
_MANAGEMENT_TERMS = (
    "manager", "head", "director", "vice president", "president", "chief", "lead",
    "经理", "主管", "总监", "负责人", "主任", "总裁", "首席",
)


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _first(contact: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(contact.get(key))
        if value:
            return value
    return ""


def normalize_contact(contact: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(contact)
    first_name = _first(contact, "first_name", "firstName", "given_name", "givenName")
    last_name = _first(contact, "last_name", "lastName", "family_name", "familyName")
    full_name = _first(contact, "full_name", "fullName", "display_name", "displayName", "name")
    full_name = full_name or " ".join(part for part in (first_name, last_name) if part)
    canonical = {
        "full_name": full_name,
        "title": _first(contact, "title", "job_title", "jobTitle", "position", "headline"),
        "department": _first(contact, "department", "department_name", "departmentName"),
        "email": _first(contact, "email", "email_address", "emailAddress"),
        "phone": _first(contact, "phone", "phone_number", "phoneNumber"),
        "linkedin_url": _first(contact, "linkedin_url", "linkedinUrl", "linkedin", "url"),
    }
    for key, value in canonical.items():
        if value:
            normalized[key] = value
    return normalized


def has_contact_data(contact: dict[str, Any]) -> bool:
    normalized = normalize_contact(contact)
    return any(_text(normalized.get(key)) for key in (
        "full_name", "title", "department", "email", "phone", "linkedin_url",
    ))


def contact_priority(contact: dict[str, Any]) -> str:
    category, _ = _contact_rank(contact)
    return "P1" if category == 0 else "P2" if category == 1 else "P3"


def sort_contacts(contacts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_contact(contact) for contact in contacts if isinstance(contact, dict) and has_contact_data(contact)]
    indexed = list(enumerate(normalized))
    indexed.sort(key=lambda item: (*_contact_rank(item[1]), item[0]))
    ordered = []
    for _, contact in indexed:
        enriched = dict(contact)
        enriched["priority"] = contact_priority(contact)
        ordered.append(enriched)
    return ordered


def merge_contacts(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    identities: dict[str, int] = {}
    for group in groups:
        for raw_contact in group:
            if not isinstance(raw_contact, dict) or not has_contact_data(raw_contact):
                continue
            contact = normalize_contact(raw_contact)
            keys = _identity_keys(contact)
            existing_index = next((identities[key] for key in keys if key in identities), None)
            if existing_index is None:
                existing_index = len(merged)
                merged.append(contact)
            else:
                existing = merged[existing_index]
                for key, value in contact.items():
                    if value not in (None, "", [], {}) and existing.get(key) in (None, "", [], {}):
                        existing[key] = value
            for key in _identity_keys(merged[existing_index]):
                identities[key] = existing_index
    return sort_contacts(merged)


def contact_order_sql(title_expression: str) -> str:
    title = f"lower(COALESCE({title_expression}, ''))"
    procurement = _sql_contains_any(title, _PROCUREMENT_TERMS)
    commercial = _sql_contains_any(title, _COMMERCIAL_TERMS)
    management = _sql_contains_any(title, _MANAGEMENT_TERMS)
    return f"""
        CASE
          WHEN ({procurement}) AND ({management}) THEN 0
          WHEN ({commercial}) AND ({management}) THEN 1
          ELSE 2
        END,
        CASE
          WHEN {title} LIKE '%chairman%' OR {title} LIKE '%董事长%' THEN 0
          WHEN {title} LIKE '%chief executive officer%' OR {title} LIKE '%ceo%'
            OR {title} LIKE '%president%' OR {title} LIKE '%founder%'
            OR {title} LIKE '%managing director%' OR {title} LIKE '%首席执行官%'
            OR {title} LIKE '%总裁%' OR {title} LIKE '%总经理%' OR {title} LIKE '%创始人%' THEN 1
          WHEN {title} LIKE '%chief %' OR {title} LIKE '%cfo%' OR {title} LIKE '%cto%'
            OR {title} LIKE '%coo%' OR {title} LIKE '%cmo%' OR {title} LIKE '%首席%' THEN 2
          WHEN {title} LIKE '%vice president%' OR {title} LIKE '%vp%'
            OR {title} LIKE '%副总裁%' THEN 3
          WHEN {title} LIKE '%director%' OR {title} LIKE '%head%'
            OR {title} LIKE '%总监%' OR {title} LIKE '%负责人%' OR {title} LIKE '%部长%' THEN 4
          WHEN {title} LIKE '%manager%' OR {title} LIKE '%经理%' OR {title} LIKE '%主管%' THEN 5
          WHEN {title} LIKE '%lead%' OR {title} LIKE '%principal%' OR {title} LIKE '%senior%'
            OR {title} LIKE '%资深%' OR {title} LIKE '%高级%' THEN 6
          ELSE 7
        END
    """.strip()


def _contact_rank(contact: dict[str, Any]) -> tuple[int, int]:
    title = _first(normalize_contact(contact), "title").casefold()
    is_management = any(term in title for term in _MANAGEMENT_TERMS)
    if is_management and any(term in title for term in _PROCUREMENT_TERMS):
        category = 0
    elif is_management and any(term in title for term in _COMMERCIAL_TERMS):
        category = 1
    else:
        category = 2
    return category, _seniority_rank(title)


def _seniority_rank(title: str) -> int:
    levels = (
        ("chairman", "董事长"),
        ("chief executive officer", "ceo", "president", "founder", "managing director", "首席执行官", "总裁", "总经理", "创始人"),
        ("chief ", "cfo", "cto", "coo", "cmo", "首席"),
        ("vice president", "vp", "副总裁"),
        ("director", "head", "总监", "负责人", "部长"),
        ("manager", "经理", "主管"),
        ("lead", "principal", "senior", "资深", "高级"),
    )
    return next((rank for rank, terms in enumerate(levels) if any(term in title for term in terms)), len(levels))


def _identity_keys(contact: dict[str, Any]) -> list[str]:
    return [
        f"{key}:{value.casefold()}"
        for key in ("email", "linkedin_url", "full_name")
        if (value := _text(contact.get(key)))
    ]


def _sql_contains_any(expression: str, terms: tuple[str, ...]) -> str:
    return " OR ".join(f"{expression} LIKE '%{term}%'" for term in terms)


def contact_order_sql(title_expression: str) -> str:
    title = f"lower(COALESCE({title_expression}, ''))"

    def contains_any(terms: tuple[str, ...]) -> str:
        return " OR ".join(f"POSITION('{term}' IN {title}) > 0" for term in terms)

    procurement = contains_any(_PROCUREMENT_TERMS)
    commercial = contains_any(_COMMERCIAL_TERMS)
    management = contains_any(_MANAGEMENT_TERMS)
    return f"""
        CASE
          WHEN ({procurement}) AND ({management}) THEN 0
          WHEN ({commercial}) AND ({management}) THEN 1
          ELSE 2
        END,
        CASE
          WHEN POSITION('chairman' IN {title}) > 0 THEN 0
          WHEN POSITION('chief executive officer' IN {title}) > 0
            OR POSITION('ceo' IN {title}) > 0
            OR POSITION('president' IN {title}) > 0
            OR POSITION('founder' IN {title}) > 0
            OR POSITION('managing director' IN {title}) > 0 THEN 1
          WHEN POSITION('chief ' IN {title}) > 0
            OR POSITION('cfo' IN {title}) > 0
            OR POSITION('cto' IN {title}) > 0
            OR POSITION('coo' IN {title}) > 0
            OR POSITION('cmo' IN {title}) > 0 THEN 2
          WHEN POSITION('vice president' IN {title}) > 0 OR POSITION('vp' IN {title}) > 0 THEN 3
          WHEN POSITION('director' IN {title}) > 0 OR POSITION('head' IN {title}) > 0 THEN 4
          WHEN POSITION('manager' IN {title}) > 0 THEN 5
          WHEN POSITION('lead' IN {title}) > 0 OR POSITION('principal' IN {title}) > 0 OR POSITION('senior' IN {title}) > 0 THEN 6
          ELSE 7
        END
    """.strip()
