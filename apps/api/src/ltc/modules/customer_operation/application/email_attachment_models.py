from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailAttachmentInput:
    filename: str
    content_type: str
    content: bytes
