"""Small HTTP adapters for Exa and the two Apify actors."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


_APIFY_CONCURRENCY = min(max(int(os.getenv("LTC_APIFY_CONCURRENCY", "2")), 1), 8)
_APIFY_SLOTS = threading.BoundedSemaphore(_APIFY_CONCURRENCY)
_APIFY_RETRY_DELAYS = (1.0, 2.0, 4.0)


def _items(payload: dict, limit: int) -> list[dict]:
    out = []
    for item in payload.get("results") or payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        raw = item
        full_name = " ".join(part for part in (_clean_text(item.get("firstName") or item.get("first_name")), _clean_text(item.get("lastName") or item.get("last_name"))) if part).strip()
        out.append({
            "url": _clean_text(item.get("url") or item.get("linkedin_url") or item.get("linkedinUrl")),
            "title": _clean_text(item.get("title") or item.get("job_title") or item.get("jobTitle") or item.get("position") or item.get("headline")),
            "full_name": full_name or _clean_text(item.get("full_name") or item.get("fullName") or item.get("displayName") or item.get("name")),
            "department": _clean_text(item.get("department") or item.get("department_name")),
            "email": _first_email(item),
            "phone": _clean_text(item.get("phone") or item.get("phone_number") or item.get("phoneNumber")),
            "snippet": _clean_text(item.get("text") or item.get("snippet") or item.get("headline")),
            "raw": raw,
        })
        if len(out) >= limit:
            break
    return out


def _first_email(item: dict[str, Any]) -> str:
    def find(value: Any) -> str:
        if isinstance(value, str):
            text = _clean_text(value)
            return text if "@" in text else ""
        if isinstance(value, dict):
            for key in ("email", "address", "value"):
                result = find(value.get(key))
                if result:
                    return result
            for child in value.values():
                result = find(child)
                if result:
                    return result
        if isinstance(value, list):
            for child in value:
                result = find(child)
                if result:
                    return result
        return ""

    return find(item.get("email")) or find(item.get("emailAddress")) or find(item.get("emails"))


def _first_value(*values):
    return next((value for value in values if value not in (None, "", [], {})), "")


def _clean_text(value) -> str:
    return str(value or "").replace("\x00", "").strip()


class ExaHttpProvider:
    code = "web_search"

    def __init__(self, api_key: str | None = None, timeout: float = 30, event_emitter: Any = None) -> None:
        self.api_key, self.timeout = api_key or os.getenv("EXA_API_KEY"), timeout
        self._emitter = event_emitter

    def search(self, query: str, *, phase: str, limit: int = 20) -> list[dict]:
        del phase
        if not self.api_key:
            return []
        started = time.monotonic()
        request_limit = min(max(int(limit), 1), 10)
        rich_payload = {
            "query": query,
            "numResults": request_limit,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 1500}},
        }
        payloads = (rich_payload, rich_payload, {"query": query, "numResults": request_limit, "type": "auto"})
        last_error: Exception | None = None
        try:
            for retry, payload in enumerate(payloads):
                request = Request(
                    "https://api.exa.ai/search",
                    data=json.dumps(payload).encode(),
                    headers={"x-api-key": self.api_key, "Content-Type": "application/json"}, method="POST",
                )
                try:
                    with urlopen(request, timeout=self.timeout) as response:
                        result = json.loads(response.read().decode())
                    duration_ms = int((time.monotonic() - started) * 1000)
                    _emit_provider_event(
                        self._emitter, "Exa", "exa.ai", "/search", 200,
                        duration_ms, cache_hit=False, retry=retry,
                    )
                    return _items(result, request_limit)
                except HTTPError as exc:
                    detail = exc.read().decode("utf-8", "replace").strip()
                    last_error = RuntimeError(
                        f"Exa search returned HTTP {exc.code}: {detail or exc.reason}"
                    )
                except Exception as exc:
                    last_error = exc
                if retry < len(payloads) - 1:
                    time.sleep(0.8 * (retry + 1))
            if last_error is not None:
                raise last_error
            raise RuntimeError("Exa search failed without an error response")
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            _emit_provider_event(self._emitter, "Exa", "exa.ai", "/search", None, duration_ms, cache_hit=False, error=str(exc)[:200])
            raise


class ApifyLeadsFinderProvider:
    code = "apollo"
    actor = "microworlds~leads-finder"

    def __init__(self, api_key: str | None = None, timeout: float = 180) -> None:
        self.api_key, self.timeout = api_key or os.getenv("APIFY_API_KEY"), timeout

    def lookup(self, *, company_name: str, country: str | None = None, company_domain: str | None = None) -> dict:
        if not self.api_key:
            return {"organization_name": company_name, "contacts": []}
        domain = _domain(company_domain)
        payload = {"max_result": 5, "contact_email_exclude_catch_all_domains": False}
        if domain:
            payload["company_domains"] = [domain]
        else:
            payload["keywords"] = [company_name]
        if country and not domain:
            payload["company_locations"] = [country]
        rows = _run_actor(self.actor, self.api_key, payload, self.timeout)
        candidates = rows if isinstance(rows, list) else [rows]
        matched = [
            row for row in candidates
            if isinstance(row, dict) and _organization_matches(row, company_name, domain)
        ]
        if not matched:
            return {"organization_name": company_name, "contacts": [], "raw": {}}
        row = matched[0]
        organization = row.get("organization") if isinstance(row.get("organization"), dict) else {}
        return {
            "organization_name": _first_value(row.get("organization_name"), organization.get("name"), company_name),
            "organization_legal_name": _first_value(row.get("organization_legal_name"), organization.get("legal_name"), organization.get("registered_name")),
            "organization_primary_domain": _first_value(row.get("organization_primary_domain"), organization.get("primary_domain")),
            "organization_website_url": _first_value(row.get("organization_website_url"), organization.get("website_url"), organization.get("website")),
            "organization_linkedin_url": _first_value(row.get("organization_linkedin_url"), organization.get("linkedin_url")),
            "organization_size": _first_value(row.get("organization_estimated_num_employees"), row.get("organization_num_employees"), row.get("organization_employee_count"), row.get("organization_employees"), row.get("organization_headcount"), row.get("organization_size"), organization.get("estimated_num_employees"), organization.get("num_employees"), organization.get("employee_count")),
            "organization_description": _first_value(row.get("organization_description"), organization.get("description"), organization.get("short_description")),
            "organization_industry": _first_value(row.get("organization_industry"), organization.get("industry"), organization.get("industry_name")),
            "organization_country": _first_value(row.get("organization_country"), organization.get("country")),
            "organization_city": _first_value(row.get("organization_city"), organization.get("city"), organization.get("headquarters_city")),
            "contacts": _items({"data": matched}, len(matched)),
            "raw": row,
        }


class ApifyLinkedInProvider:
    code = "apollo"
    actor = "harvestapi~linkedin-company-employees"

    def __init__(self, api_key: str | None = None, timeout: float = 120) -> None:
        self.api_key, self.timeout = api_key or os.getenv("APIFY_API_KEY"), timeout

    def lookup(self, *, company_url: str) -> list[dict]:
        if not self.api_key or not company_url:
            return []
        payload = {
            "companies": [company_url],
            "maxItems": 8,
            "profileScraperMode": "Full + email search ($12 per 1k)",
            "recentlyChangedJobs": False,
        }
        return _items({"data": _run_actor(self.actor, self.api_key, payload, self.timeout)}, 8)


def _run_actor(actor: str, api_key: str, payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not _APIFY_SLOTS.acquire(timeout=remaining):
        raise TimeoutError("Apify concurrency slot deadline exceeded")
    try:
        query = urlencode({"token": api_key})
        start_request = Request(
            f"https://api.apify.com/v2/acts/{actor}/runs?{query}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        run = _read_json(start_request, deadline).get("data") or {}
        run_id = _clean_text(run.get("id"))
        if not run_id:
            raise RuntimeError(f"Apify actor {actor} did not return a run id")

        while run.get("status") not in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Apify actor {actor} exceeded {timeout:g}s")
            time.sleep(min(1.0, remaining))
            run_request = Request(f"https://api.apify.com/v2/actor-runs/{run_id}?{query}")
            run = _read_json(run_request, deadline).get("data") or {}

        if run.get("status") != "SUCCEEDED":
            message = _clean_text(run.get("statusMessage")) or _clean_text(run.get("status"))
            raise RuntimeError(f"Apify actor {actor} failed: {message}")
        dataset_id = _clean_text(run.get("defaultDatasetId"))
        if not dataset_id:
            return []
        dataset_request = Request(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items?{query}&clean=true"
        )
        items = _read_json(dataset_request, deadline)
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    finally:
        _APIFY_SLOTS.release()


def _read_json(request: Request, deadline: float) -> Any:
    for attempt in range(len(_APIFY_RETRY_DELAYS) + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Apify request deadline exceeded")
        try:
            with urlopen(request, timeout=min(30.0, remaining)) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace").strip()
            detail_lower = detail.casefold()
            retryable_403 = exc.code == 403 and any(marker in detail_lower for marker in (
                "concurrent", "rate-limit", "rate limit", "too many", "actor-runs-limit",
            ))
            retryable = retryable_403 or exc.code in {408, 409, 429} or exc.code >= 500
            if not retryable or attempt >= len(_APIFY_RETRY_DELAYS):
                raise RuntimeError(
                    f"Apify returned HTTP {exc.code}: {detail or exc.reason}"
                ) from exc
            time.sleep(min(_APIFY_RETRY_DELAYS[attempt], max(deadline - time.monotonic(), 0)))
    raise RuntimeError("Apify request failed without an error response")


def _domain(value: Any) -> str:
    text = _clean_text(value).casefold()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").removeprefix("www.")


def _identity(value: Any) -> str:
    return "".join(char for char in _clean_text(value).casefold() if char.isalnum())


def _organization_matches(row: dict[str, Any], company_name: str, company_domain: str) -> bool:
    organization = row.get("organization") if isinstance(row.get("organization"), dict) else {}
    row_domain = _domain(_first_value(
        row.get("organization_primary_domain"),
        row.get("organization_website_url"),
        organization.get("primary_domain"),
        organization.get("website_url"),
    ))
    if company_domain and row_domain == company_domain:
        return True
    requested_name = _identity(company_name)
    returned_name = _identity(_first_value(row.get("organization_name"), organization.get("name")))
    return bool(
        requested_name and returned_name
        and (requested_name == returned_name or requested_name in returned_name or returned_name in requested_name)
    )


def _emit_provider_event(
    emitter: Any | None,
    tool_name: str,
    provider: str,
    api: str,
    response_code: int | None,
    duration_ms: int,
    *,
    cache_hit: bool = False,
    retry: int = 0,
    error: str | None = None,
) -> None:
    if emitter is None:
        return
    try:
        emitter.tool_call(
            tool_name=tool_name,
            provider=provider,
            api=api,
            duration_ms=duration_ms,
            retry=retry,
            cache_hit=cache_hit,
            response_code=response_code,
            error_code=error,
        )
    except Exception:
        pass
