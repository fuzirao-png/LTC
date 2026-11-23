"""Lossless best-effort mapping for variable AI/provider field names."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from html import unescape
from typing import Any

ALIASES: dict[str, tuple[str, ...]] = {
    "company_name": ("company_name", "company", "name", "organization_name", "企业名称", "公司名称", "公司名", "企业名", "机构名称"),
    "legal_name": ("legal_name", "registered_name", "organization_legal_name", "法人名称", "法定名称", "注册名称"),
    "website": ("website", "website_url", "official_website", "official_website_url", "organization_website_url", "organization_primary_domain", "primary_domain", "官网", "官方网站", "公司官网"),
    "linkedin_company_url": ("linkedin_company_url", "organization_linkedin_url", "company_linkedin", "linkedin", "领英公司页"),
    "company_intro": ("company_intro", "company_description", "organization_description", "description", "short_description", "intro", "summary", "snippet", "text", "公司简介", "企业介绍", "公司描述"),
    "industry_code": ("industry_code", "organization_industry", "industry", "industry_name", "行业", "行业分类", "行业代码", "主营行业"),
    "employee_count": ("employee_count", "employees", "employee_number", "num_employees", "employee_count_estimate", "headcount", "organization_size", "organization_num_employees", "员工数", "员工数量", "员工人数", "雇员数", "团队规模", "公司规模"),
    "country_code": ("country_code", "organization_country", "country", "country_name", "国家", "国家代码", "所在国家"),
    "region_code": ("region_code", "region", "region_name", "地区", "区域", "大区"),
    "city": ("city", "organization_city", "hq_city", "headquarters_city", "headquarters", "headquarters_location", "organization_headquarters", "总部城市", "城市", "所在城市"),
}


def _key(value: Any) -> str:
    return re.sub(r"[\s_\-:/]+", "", str(value or "").strip().casefold())


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {prefix: value} if prefix else {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        result.update(_flatten(item, path) if isinstance(item, Mapping) else {path: item})
    return result


def _first(source: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    wanted = {_key(alias) for alias in aliases}
    for path, value in source.items():
        if _key(path.split(".")[-1]) in wanted and value not in (None, "", [], {}):
            return value
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d[\d, .]*", str(value or ""))
    if not match:
        return None
    try:
        return int(float(match.group(0).replace(",", "").replace(" ", "")))
    except ValueError:
        return None


def normalize_company_intro(value: Any, *, limit: int = 1200) -> str | None:
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"(?s)```(?:\w+)?\s*(.*?)```", r"\1", text)
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|>\s*|[-+*]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"(?<!\w)(?:\*\*|__|~~|`)(.+?)(?:\*\*|__|~~|`)(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)[*_]([^\n*_]+)[*_](?!\w)", r"\1", text)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text[:limit].rstrip() or None


def map_company_fields(*sources: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if source:
            merged.update(_flatten(source))
    recognized: dict[str, Any] = {}
    for field, aliases in ALIASES.items():
        value = _first(merged, aliases)
        if value is not None:
            if field == "employee_count":
                recognized[field] = _integer(value)
            elif field == "company_intro":
                recognized[field] = normalize_company_intro(value)
            else:
                recognized[field] = value
    consumed = {_key(alias) for aliases in ALIASES.values() for alias in aliases}
    extras = {path: value for path, value in merged.items() if _key(path.split(".")[-1]) not in consumed}
    return {"recognized": recognized, "extras": extras, "flattened": merged}


# Provider data is authoritative in this order.  The model is deliberately
# last: it may fill a blank field, but must not overwrite a provider fact.
def merge_company_sources(
    *sources: Mapping[str, Any] | None,
    company_name_hint: str | None = None,
    country_hint: str | None = None,
) -> dict[str, Any]:
    """Merge heterogeneous provider/LLM payloads without losing useful data.

    ``sources`` should be passed from most trusted to least trusted.  Unknown
    keys are returned in ``extras`` so they can be persisted in JSONB.
    """
    flattened: dict[str, Any] = {}
    source_flattened: list[dict[str, Any]] = []
    for source in sources:
        if source:
            current = _flatten(_clean(source))
            source_flattened.append(current)
            for path, value in current.items():
                key = path.split(".")[-1]
                if value not in (None, "", [], {}) and _key(key) not in {_key(k) for k in flattened}:
                    flattened[key] = value

    recognized: dict[str, Any] = {}
    for field, aliases in ALIASES.items():
        value = _first(flattened, aliases)
        if value is not None:
            if field == "employee_count":
                recognized[field] = _integer(value)
            elif field == "company_intro":
                recognized[field] = normalize_company_intro(value)
            else:
                recognized[field] = value

    name = str(recognized.get("company_name") or company_name_hint or "").strip()
    # A provider can return a stale person/company row for a name query.  Do
    # not let that row replace the discovery URL or company identity.
    if company_name_hint and not _company_identity_matches(recognized.get("company_name"), company_name_hint):
        recognized["company_name"] = company_name_hint
        for field in ("website", "legal_name", "company_intro", "industry_code", "employee_count", "city", "linkedin_company_url"):
            if field in recognized and field != "company_name":
                recognized.pop(field, None)
    country = _country_code(recognized.get("country_code") or country_hint)
    recognized["country_code"] = country or recognized.get("country_code")

    text = _text_corpus(flattened)
    if not recognized.get("industry_code"):
        recognized["industry_code"] = infer_industry_code(text, name)
    else:
        recognized["industry_code"] = normalize_industry(recognized["industry_code"], text, name)

    city = recognized.get("city")
    if not valid_city(city, country):
        recognized["city"] = extract_office_city(text, country)

    linkedin = recognized.get("linkedin_company_url")
    if not valid_linkedin_company_url(linkedin, name, recognized.get("website")):
        recognized["linkedin_company_url"] = _first_valid_linkedin(source_flattened, name, recognized.get("website"))

    consumed = {_key(alias) for aliases in ALIASES.values() for alias in aliases}
    extras = {path: value for path, value in flattened.items() if _key(path) not in consumed}
    # Keep a compact text corpus for downstream scoring/auditing.
    if text.strip():
        extras.setdefault("source_text", text[:20000])
        extras.update(extract_company_metrics(text))
    return {"recognized": recognized, "extras": extras, "flattened": flattened}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_clean(v) for v in value]
    return value


def _text_corpus(value: Any, *, limit: int = 30000) -> str:
    chunks: list[str] = []
    def visit(item: Any) -> None:
        if sum(len(chunk) for chunk in chunks) >= limit:
            return
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, Mapping):
            for key, child in item.items():
                chunks.append(str(key))
                visit(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                visit(child)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            chunks.append(str(item))
    visit(value)
    return " ".join(chunks)[:limit]


def _country_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    aliases = {"UNITED STATES": "US", "USA": "US", "U.S.": "US", "JAPAN": "JP", "CHINA": "CN", "SINGAPORE": "SG", "AUSTRALIA": "AU", "UNITED KINGDOM": "GB", "UK": "GB", "GERMANY": "DE", "FRANCE": "FR", "CANADA": "CA"}
    text = aliases.get(text, text)
    return text if len(text) == 2 and text.isalpha() else None


def _company_identity_matches(value: Any, hint: str) -> bool:
    actual = re.sub(r"[^a-z0-9一-龥ぁ-んァ-ン]+", "", str(value or "").casefold())
    expected = re.sub(r"[^a-z0-9一-龥ぁ-んァ-ン]+", "", str(hint or "").casefold())
    if not actual or not expected:
        return False
    if actual == expected or actual in expected or expected in actual:
        return True
    actual_tokens = set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))
    expected_tokens = set(re.findall(r"[a-z0-9]+", str(hint or "").casefold()))
    return bool(actual_tokens and expected_tokens and len(actual_tokens.intersection(expected_tokens)) >= 1)


def normalize_industry(value: Any, text: str = "", company_name: str = "") -> str:
    raw = re.sub(r"[\s-]+", "_", str(value or "").strip().upper())
    corpus = f"{raw} {text}".casefold()
    if raw == "FINTECH":
        return raw
    if raw in {"OTA", "TRAVEL_OTA", "ONLINE_TRAVEL", "ONLINE_TRAVEL_AGENCY", "TRAVEL_AGENCY"}:
        return "TRAVEL_OTA"
    ota_identity_signals = (
        "trip.com",
        "trip.biz",
        "ctrip",
        "携程",
    )
    ota_business_signals = (
        "online travel agency",
        "online travel platform",
        "在线旅行",
        "在线旅游",
    )
    identity = company_name.casefold()
    if (
        any(token in identity for token in ota_identity_signals)
        or any(token in corpus for token in ota_business_signals)
        or re.search(r"(?<![a-z0-9])ota(?![a-z0-9])", corpus)
    ):
        return "TRAVEL_OTA"
    if raw == "TMC":
        return raw
    if any(token in corpus for token in ("business travel", "corporate travel", "travel management company", "商旅", "商务差旅", "ビジネストラベル", "法人出张", "出張")):
        return "TMC"
    if raw == "OTHER":
        return raw
    # Industry is a required display dimension for lead pools. When the
    # evidence does not support one of the active classifications, keep the
    # candidate in the explicit catch-all scenario instead of leaking a
    # pending-confirmation value to the UI.
    return "OTHER"


def infer_industry_code(text: str, company_name: str = "") -> str:
    return normalize_industry(None, text, company_name)


_CITY_COUNTRIES = {
    "JP": ("tokyo", "yokohama", "osaka", "kyoto", "nagoya", "sapporo", "fukuoka", "神戸", "東京", "横浜", "大阪", "京都"),
    "US": ("new york city", "new york", "san francisco", "los angeles", "chicago", "seattle", "boston", "miami", "washington"),
    "AU": ("sydney", "melbourne", "brisbane", "perth", "canberra"),
}


def valid_city(value: Any, country_code: str | None) -> bool:
    city = str(value or "").strip()
    if not city:
        return False
    if not country_code:
        return True
    # Do not reject every unlisted locality (provider data may use wards or
    # suburbs), only values known to belong to another country.
    if country_code == "JP" and city.casefold() in {"makati", "manila", "sydney", "melbourne", "new york", "london"}:
        return False
    return True


def extract_office_city(text: str, country_code: str | None = None) -> str | None:
    corpus = text.casefold()
    candidates = _CITY_COUNTRIES.get(country_code or "", ())
    matches = (city for city in candidates if city.casefold() in corpus)
    city = min(matches, key=lambda value: corpus.index(value.casefold()), default=None)
    return city.title() if city and city.isascii() else city


def valid_linkedin_company_url(value: Any, company_name: str | None, website: Any = None) -> bool:
    url = str(value or "").strip()
    if not url or "linkedin.com/company/" not in url.casefold():
        return False
    slug = url.rstrip("/").split("/")[-1].replace("-", " ").casefold()
    tokens = {token for token in re.findall(r"[a-z0-9]+", str(company_name or "").casefold()) if len(token) >= 3}
    domain = str(website or "").casefold()
    domain_tokens = set(re.findall(r"[a-z0-9]+", domain))
    # Acronyms (JTB, HIS, etc.) are useful identity anchors; reject unrelated
    # pages such as bridge-australia for a Japanese company.
    slug_tokens = set(re.findall(r"[a-z0-9]+", slug))
    if tokens.intersection(slug_tokens) or domain_tokens.intersection(slug_tokens):
        return True
    # Japanese legal names are often non-Latin while their official domain
    # and LinkedIn slug use the parent-group acronym (e.g. JTB/BWT).
    if "business" in slug_tokens and "travel" in slug_tokens and any(token in domain_tokens for token in ("jtb", "bwt", "bts", "tmc")):
        return True
    return False


def _first_valid_linkedin(sources: list[Mapping[str, Any]], company_name: str | None, website: Any) -> str | None:
    for source in sources:
        for url in _linkedin_urls(source):
            if valid_linkedin_company_url(url, company_name, website):
                return url
    return None


def _linkedin_urls(value: Any) -> list[str]:
    if isinstance(value, str):
        return re.findall(r"https?://(?:www\.)?linkedin\.com/company/[^\s\"'<>]+", value, flags=re.IGNORECASE)
    if isinstance(value, Mapping):
        out: list[str] = []
        for child in value.values():
            out.extend(_linkedin_urls(child))
        return out
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out: list[str] = []
        for child in value:
            out.extend(_linkedin_urls(child))
        return out
    return []


def extract_company_metrics(text: str) -> dict[str, Any]:
    """Capture common commercial facts that have no dedicated SQL columns."""
    extras: dict[str, Any] = {}
    patterns = {
        "customer_count": r"(?i)(?:serves?|serving|customers?|clients?|客户|企業顧客)[^\d]{0,20}(\d[\d,]*(?:\+|\s*万)?)",
        "office_locations": r"(?i)(?:offices?|locations?|办公点|拠点)[^。.!\n]{0,180}",
        "global_coverage": r"(?i)(?:\d[\d,]*\+?\s*(?:countries|国家|カ国)|worldwide|global network|全球)[^。.!\n]{0,120}",
        "founded_year": r"(?i)(?:founded|established|成立|設立)[^\d]{0,10}((?:19|20)\d{2})",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            extras[key] = match.group(1).strip() if match.lastindex else match.group(0).strip()
    return extras
