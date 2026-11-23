"""Opaque keyset cursors and deterministic advisory-lock keys."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any


class InvalidCursor(ValueError):
    """Raised when a cursor is malformed or has the wrong shape."""


def encode_cursor(*values: Any) -> str:
    raw = json.dumps([str(value) for value in values], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str | None, size: int) -> list[str] | None:
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidCursor("invalid cursor") from error
    if not isinstance(decoded, list) or len(decoded) != size or not all(isinstance(item, str) for item in decoded):
        raise InvalidCursor("invalid cursor")
    return decoded


def stable_advisory_key(*parts: str) -> int:
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=True)
    return value or 1
