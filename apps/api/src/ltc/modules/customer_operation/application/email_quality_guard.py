import re
from dataclasses import dataclass
from typing import Any


_EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"\d{2,}")
_URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(r"\[(?:insert|填写|补充)[^\]]*\]", re.IGNORECASE),
    re.compile(r"\b(?:TODO|TBD)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class EmailQualityInspection:
    subject: str
    body: str
    flags: tuple[str, ...]


def _strip_markdown_fence(value: str) -> str:
    stripped = value.strip()
    match = re.fullmatch(r"```(?:[A-Za-z0-9_-]+)?\s*\n?(.*?)\n?```", stripped, re.DOTALL)
    return match.group(1).strip() if match else stripped


def _missing_tokens(source: str, output: str, pattern: re.Pattern[str], prefix: str) -> list[str]:
    source_tokens = dict.fromkeys(pattern.findall(source))
    output_lower = output.lower()
    return [f"{prefix}:{token}" for token in source_tokens if token.lower() not in output_lower]


def inspect_email_quality(
    *,
    input_data: dict[str, Any],
    subject: str,
    body: str,
) -> EmailQualityInspection:
    clean_subject = _strip_markdown_fence(subject)
    clean_body = _strip_markdown_fence(body)
    source_body = str(input_data.get("currentBody") or input_data.get("body") or "")
    flags: list[str] = []
    flags.extend(_missing_tokens(source_body, clean_body, _EMAIL_PATTERN, "missing_email"))
    flags.extend(_missing_tokens(source_body, clean_body, _URL_PATTERN, "missing_url"))
    flags.extend(_missing_tokens(source_body, clean_body, _NUMBER_PATTERN, "missing_number"))
    if any(pattern.search(clean_subject) or pattern.search(clean_body) for pattern in _PLACEHOLDER_PATTERNS):
        flags.append("unresolved_placeholder")
    sales_name = str(input_data.get("salesName") or "").strip()
    if sales_name and sales_name.lower() not in clean_body.lower():
        flags.append("missing_sales_signature")
    return EmailQualityInspection(
        subject=clean_subject,
        body=clean_body,
        flags=tuple(dict.fromkeys(flags)),
    )
