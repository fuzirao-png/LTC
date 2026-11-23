"""Pure mapping helpers for the legacy notification migration."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def _parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = parsedate_to_datetime(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def notification_update_values(item: dict[str, Any]) -> dict[str, Any] | None:
    email_id = str(item.get("emailId") or "").strip()
    sales_user_id = str(item.get("salesUserId") or "").strip()
    if not email_id or not sales_user_id:
        return None
    created_at = _parse_timestamp(item.get("createdAt"))
    read_at = (
        _parse_timestamp(item.get("updatedAt") or item.get("createdAt"))
        if item.get("read")
        else None
    )
    return {
        "email_id": email_id,
        "sales_user_id": sales_user_id,
        "created_at": created_at,
        "read_at": read_at,
    }
