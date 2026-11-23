"""Lead discovery workflow with an explicit provider order.

The workflow is deliberately provider-agnostic so the API and worker can use
the same orchestration while tests inject fakes.  One company-level Exa call
is allowed during the missing-field step; contacts are always looked up after
that step.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from dataclasses import asdict
from typing import Any

import psycopg

from ..domain.models import CompanyCandidate, DimensionScore, SearchRequest
from ..domain.icp_rules import normalize_scene_code
from ..domain.field_mapping import merge_company_sources, normalize_company_intro
from ..domain.ports import (
    CompanyLookupPort,
    ContactLookupPort,
    LanguageModelPort,
    LeadRepositoryPort,
    MemoryPort,
    SearchProviderPort,
)
from ltc.platform.contact_ordering import has_contact_data, merge_contacts, normalize_contact

ICP_DIMENSIONS = ("D1", "D2", "D3", "D4")
SCALE_DIMENSIONS = ("D1_SCALE", "D2_COMMERCIAL", "D3_COVERAGE")


class LeadSearchPipeline:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        exa: SearchProviderPort,
        leads_finder: CompanyLookupPort,
        linkedin: ContactLookupPort,
        llm: LanguageModelPort,
        repository: LeadRepositoryPort,
    ) -> None:
        self.memory = memory
        self.exa = exa
        self.leads_finder = leads_finder
        self.linkedin = linkedin
        self.llm = llm
        self.repository = repository

    async def execute(self, *, job_id: str, lock_token: str, payload: dict[str, Any]) -> None:
        del lock_token
        request = SearchRequest(
            query_text=str(payload.get("query_text") or "").strip(),
            search_mode=str(payload.get("search_mode") or "both"),
            target_count=int(payload.get("target_count") or 1),
            scene_code=normalize_scene_code(str(payload.get("scene_code") or "S1")),
            dialogue_session_id=payload.get("dialogue_session_id"),
        )
        if request.scene_code == "S1" and any(token in request.query_text.casefold() for token in ("ota", "在线旅游")):
            request.scene_code = "S2"
        if not request.query_text:
            raise ValueError("query_text is required")
        search_run_id = str(payload.get("search_run_id") or "")
        if not search_run_id:
            search_run_id, _ = self.repository.create_search_run(request)
        self.repository.start_search_run(search_run_id)
        try:
            self._progress(job_id, "started", "pipeline", "线索流程已启动", {"search_run_id": search_run_id}, 5)
            memory = self.memory.read(request)  # memory is read before planning/search
            self._progress(job_id, "step_completed", "memory_read", "已读取线索记忆", {"count": len(memory), "sample": memory[:20]}, 10)
            query = self.llm.plan_query(request=request, memory=memory)
            self._progress(job_id, "step_completed", "exa_candidate_search", "已生成 Exa 企业发现搜索词", {"query": query, "llm_error": getattr(self.llm, "last_error", None)}, 15)
            try:
                results = self.exa.search(query, phase="collection", limit=max(20, request.target_count * 5))
            except Exception as exc:
                self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), operation="search", payload={"query": query, "phase": "collection"}, status="failed", result_count=0, error=str(exc))
                raise
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), operation="search", payload={"query": query, "phase": "collection", "response": results}, status="succeeded", result_count=len(results))
            self._progress(job_id, "step_completed", "exa_candidate_search", "Exa 企业发现完成", {"query": query, "result_count": len(results)}, 25)
            for rank, item in enumerate(results, start=1):
                item["_phase"] = "collection"
                item["_rank_no"] = rank
                item["_evidence_id"] = self.repository.record_evidence(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), phase="collection", query=query, item=item)
            candidates = self.llm.extract_candidates(request=request, results=results, memory=memory)
            refresh_candidate_id = str(payload.get("candidate_id") or "").strip()
            if payload.get("refresh") and refresh_candidate_id:
                # Refreshes must update the requested company, even when the
                # discovery model ranks another similarly named company first.
                candidates = [{
                    "_candidate_id": refresh_candidate_id,
                    "company_name": str(payload.get("company_name") or request.query_text).strip(),
                    "website": payload.get("website"),
                    "industry_code": payload.get("industry_code"),
                    "country_code": payload.get("country_code"),
                    "region_code": payload.get("region_code"),
                }]
            self._progress(job_id, "step_completed", "candidate_extraction", "已提取候选企业", {"candidate_count": len(candidates), "candidates": candidates[:50], "llm_error": getattr(self.llm, "last_error", None)}, 30)
            batch = candidates[: request.target_count]
            processed = 0
            failures: list[str] = []
            completed = 0
            parallelism = min(max(int(os.getenv("LTC_LEAD_CANDIDATE_CONCURRENCY", "3")), 1), 8)
            candidate_slots = asyncio.Semaphore(parallelism)
            self._update_run_progress(search_run_id, job_id, len(batch), 0, 0, 30)

            async def _process_one(raw: dict[str, Any]):
                name = str(raw.get("company_name") or raw.get("name") or "候选企业").strip()
                async with candidate_slots:
                    if await self._is_cancelled(search_run_id):
                        return name, None, asyncio.CancelledError()
                    try:
                        candidate = await self._process_candidate(
                            request=request, search_run_id=search_run_id, job_id=job_id,
                            raw=raw, discovery_results=results,
                        )
                        return name, candidate, None
                    except Exception as exc:
                        return name, None, exc

            tasks = [asyncio.create_task(_process_one(raw)) for raw in batch]
            for task in asyncio.as_completed(tasks):
                name, candidate, error = await task
                completed += 1
                if isinstance(error, asyncio.CancelledError) or await self._is_cancelled(search_run_id):
                    for pending in tasks:
                        pending.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    return
                progress = min(90, 30 + round(60 * completed / max(len(batch), 1)))
                if error is not None:
                    failures.append(f"{name}: {str(error)[:200]}")
                    self._progress(
                        job_id, "candidate_failed", "candidate_failed",
                        f"{name} 暂时获取失败，继续处理其他候选",
                        {"company_name": name, "error": str(error)[:500]}, progress,
                    )
                elif candidate is not None:
                    processed += 1
                    await asyncio.to_thread(self.memory.write, request, candidate)
                    self._progress(
                        job_id, "candidate_completed", "candidate_completed",
                        f"已完成企业 {candidate.company_name}",
                        {"candidate_id": candidate.candidate_id, "completed_count": processed, "target_count": len(batch)},
                        progress,
                    )
                self._update_run_progress(search_run_id, job_id, len(batch), processed, processed, progress)

            if await self._is_cancelled(search_run_id):
                return
            status = "completed" if processed == len(batch) else "partial" if processed else "failed"
            error_summary = "; ".join(failures[:5]) if failures else None
            self.repository.finish_search_run(
                search_run_id,
                job_id,
                status=status,
                counts={"candidate_count": len(batch), "enriched_count": processed, "scored_count": processed},
                error=error_summary,
            )
        except Exception as exc:
            self._progress(job_id, "failed", "pipeline", "线索流程失败", {"error": str(exc)}, 100)
            self.repository.finish_search_run(search_run_id, job_id, status="failed", counts={}, error=str(exc))
            raise

    async def _process_candidate(
        self, *, request: SearchRequest, search_run_id: str, job_id: str,
        raw: dict[str, Any], discovery_results: list[dict[str, Any]],
    ) -> CompanyCandidate | None:
        name = str(raw.get("company_name") or raw.get("name") or raw.get("company_name_guess") or "").strip()
        if not name:
            return None
        try:
            leads = await asyncio.to_thread(
                self.leads_finder.lookup,
                company_name=name,
                country=raw.get("country_code"),
                company_domain=raw.get("website") or raw.get("url"),
            )
        except Exception as exc:
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.leads_finder, "code", "apollo"), operation="company_lookup", payload={"provider": "apify_leads_finder", "company_name": name}, status="failed", result_count=0, error=str(exc))
            leads = {"organization_name": name, "contacts": [], "raw": {}, "provider_error": str(exc)}
        else:
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.leads_finder, "code", "apollo"), operation="company_lookup", payload={"provider": "apify_leads_finder", "company_name": name, "response": leads}, status="succeeded", result_count=1)
        self._progress(job_id, "step_completed", "leads_finder_company_lookup", f"Leads Finder 已返回 {name} 基础字段", {"company_name": name, "fields": sorted(leads.keys())}, 40)
        missing = await asyncio.to_thread(
            self.llm.summarize_missing, request=request, candidate=raw, leads_finder=leads
        )
        self._progress(job_id, "step_completed", "missing_field_analysis", "已判断 Leads Finder 缺失字段", {"company_name": name, "missing_fields": missing.get("missing_fields", []), "search_query": missing.get("search_query"), "llm_error": getattr(self.llm, "last_error", None)}, 45)
        exa_evidence: list[dict[str, Any]] = []
        if missing.get("missing_fields") and request.search_mode != "contact_only":
            missing_query = str(missing.get("search_query") or name).strip()
            try:
                exa_evidence = await asyncio.to_thread(
                    self.exa.search, missing_query, phase="icp_enrichment", limit=10
                )
            except Exception as exc:
                self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), operation="search", payload={"query": missing_query, "phase": "icp_enrichment"}, status="failed", result_count=0, error=str(exc))
                raise
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), operation="search", payload={"query": missing_query, "phase": "icp_enrichment", "response": exa_evidence}, status="succeeded", result_count=len(exa_evidence))
            for rank, item in enumerate(exa_evidence, start=1):
                item["_phase"] = "icp_enrichment"
                item["_rank_no"] = rank
                item["_evidence_id"] = self.repository.record_evidence(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.exa, "code", "web_search"), phase="icp_enrichment", query=missing_query, item=item)
            self._progress(job_id, "step_completed", "exa_missing_fields_once", "已完成一次 Exa 缺失字段补充", {"company_name": name, "query": missing_query, "missing_fields": missing.get("missing_fields", [])}, 55)
        summary = await asyncio.to_thread(
            self.llm.summarize_company,
            request=request, candidate=raw, company_evidence=leads,
            contacts=[], exa_evidence=exa_evidence,
        )
        self._progress(job_id, "step_completed", "company_summary", f"已完成 {name} 公司字段总结", {"llm_error": getattr(self.llm, "last_error", None)}, 75)
        # Provider facts are authoritative.  The summary is only allowed to
        # fill blanks and is validated before it reaches the normalized table.
        mapped = merge_company_sources(
            raw, leads, _company_evidence_fields(exa_evidence), summary,
            company_name_hint=name, country_hint=raw.get("country_code"),
        )
        fields = mapped["recognized"]
        website = _text_or_none(fields.get("website"))
        linkedin_url = _text_or_none(fields.get("linkedin_company_url"))
        raw_contact_payload = (
            mapped["extras"]
            if _leads_source_matches_candidate(
                leads,
                candidate_name=name,
                candidate_website=website or _text_or_none(raw.get("website")),
            )
            else {"summary": summary, "exa_evidence": exa_evidence}
        )
        raw_contacts = _contacts_from_payload(raw_contact_payload)
        leads_finder_contacts = _contacts_from_leads_finder(
            leads,
            candidate_name=name,
            candidate_website=website or _text_or_none(raw.get("website")),
        ) if request.search_mode != "company_only" else []
        linkedin_lookup = linkedin_url or name
        linkedin_failed = False
        try:
            linkedin_contacts = await asyncio.to_thread(
                self.linkedin.lookup, company_url=linkedin_lookup
            ) if request.search_mode != "company_only" else []
        except Exception as exc:
            linkedin_failed = True
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.linkedin, "code", "apollo"), operation="contact_lookup", payload={"provider": "apify_linkedin", "company_url": linkedin_url, "company_name": name, "lookup_value": linkedin_lookup}, status="failed", result_count=0, error=str(exc))
            linkedin_contacts = []
        if request.search_mode == "company_only":
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.linkedin, "code", "apollo"), operation="contact_lookup", payload={"provider": "apify_linkedin", "company_url": linkedin_url, "reason": "search_mode_company_only"}, status="succeeded", result_count=0)
        elif not linkedin_failed:
            self.repository.record_provider(search_run_id=search_run_id, job_id=job_id, provider_code=getattr(self.linkedin, "code", "apollo"), operation="contact_lookup", payload={"provider": "apify_linkedin", "company_url": linkedin_url, "company_name": name, "lookup_value": linkedin_lookup, "response": linkedin_contacts}, status="succeeded", result_count=len(linkedin_contacts))
        contacts = _merge_contacts(leads_finder_contacts, linkedin_contacts, raw_contacts)
        contacts = _fill_missing_contact_emails(contacts, _email_addresses_from_payload(raw_contact_payload))
        self._progress(job_id, "step_completed", "linkedin_contact_lookup", f"联系人补充完成：{name}", {"contact_count": len(contacts), "leads_finder_count": len(leads_finder_contacts), "linkedin_count": len(linkedin_contacts), "company_url": linkedin_url}, 70)
        summary = await asyncio.to_thread(
            self.llm.summarize_company,
            request=request, candidate=summary, company_evidence=leads,
            contacts=contacts, exa_evidence=exa_evidence,
        )
        # The final summary can fill fields using LinkedIn contacts. Re-map it
        # before persistence so those values do not remain only in raw JSON.
        mapped = merge_company_sources(
            raw, leads, _company_evidence_fields(exa_evidence), summary,
            company_name_hint=name, country_hint=raw.get("country_code"),
        )
        fields = mapped["recognized"]
        country_code = _normalize_country(fields.get("country_code"))
        region_code = _normalize_region(fields.get("region_code")) or _region_from_country(country_code)
        resolved_website = _text_or_none(fields.get("website")) or _text_or_none(website)
        if raw.get("_candidate_id") and not raw.get("website"):
            # A legacy duplicate may intentionally have no domain while a
            # canonical sibling owns the discovered domain's unique key.
            resolved_website = None
        resolved_name = _text_or_none(fields.get("company_name")) or _text_or_none(name) or "Unknown company"
        if raw.get("_candidate_id") and raw.get("company_name"):
            resolved_name = str(raw["company_name"]).strip()
        candidate = CompanyCandidate(
            candidate_id=str(raw.get("_candidate_id") or uuid.uuid5(uuid.NAMESPACE_URL, (raw.get("website") or name).strip().lower())),
            company_name=resolved_name,
            legal_name=_text_or_none(fields.get("legal_name")),
            website=resolved_website,
            company_intro=normalize_company_intro(summary.get("company_intro")) or normalize_company_intro(fields.get("company_intro")),
            industry_code=_normalize_industry(fields.get("industry_code")),
            employee_count=_int_or_none(fields.get("employee_count")),
            region_code=region_code, country_code=country_code,
            city=_text_or_none(fields.get("city")), linkedin_company_url=_text_or_none(fields.get("linkedin_company_url")) or _text_or_none(linkedin_url),
            contacts=contacts, evidence=[item for item in discovery_results if _candidate_evidence(raw, name, item)] + exa_evidence,
            raw_ai_output={"summary": summary, "leads_finder": leads, "exa_missing": exa_evidence},
            extra_fields=mapped["extras"],
        )
        scores = await self._score(candidate, scene_code=request.scene_code)
        try:
            await asyncio.to_thread(
                self.repository.upsert_candidate, search_run_id=search_run_id, candidate=candidate
            )
        except psycopg.errors.UniqueViolation:
            # Domain-dedup conflict — same company found via different sources.
            # This is expected when parallel discovery returns the same entity;
            # skip silently so the other candidates still complete.
            self._progress(job_id, "step_completed", "candidate_skipped", f"跳过重复候选 {candidate.company_name}: 已存在", {"candidate_name": candidate.company_name}, 85)
            return None
        except Exception:
            # Other DB errors (connection, constraint) should not silently skip;
            # let the pipeline fail so operators see the real error.
            raise
        await asyncio.to_thread(
            self.repository.record_enrichment,
            search_run_id=search_run_id, job_id=job_id, candidate=candidate,
            scores=scores[0], scale_scores=scores[1], scene_code=request.scene_code,
        )
        self._progress(job_id, "step_completed", "parallel_7_agent_scoring", f"七个评分 Agent 已完成：{name}", {"icp": [{"dimension_code": item.dimension_code, "score": item.score, "provider_status": item.provider_status, "error_message": item.error_message} for item in scores[0]], "scale": [{"dimension_code": item.dimension_code, "score": item.score, "provider_status": item.provider_status, "error_message": item.error_message} for item in scores[1]]}, 85)
        return candidate

    def _progress(self, job_id, event_type, step_code, message, payload=None, progress_percent=None):
        recorder = getattr(self.repository, "record_progress", None)
        if recorder:
            recorder(job_id=job_id, event_type=event_type, step_code=step_code, message=message, payload=payload, progress_percent=progress_percent)

    def _update_run_progress(self, search_run_id, job_id, candidate_count, enriched_count, scored_count, progress_percent):
        updater = getattr(self.repository, "update_search_run_progress", None)
        if updater:
            updater(
                search_run_id, job_id, candidate_count=candidate_count,
                enriched_count=enriched_count, scored_count=scored_count,
                progress_percent=progress_percent,
            )

    async def _is_cancelled(self, search_run_id):
        checker = getattr(self.repository, "is_search_run_cancelled", None)
        return bool(await asyncio.to_thread(checker, search_run_id)) if checker else False

    async def _score(self, candidate: CompanyCandidate, *, scene_code: str = "S1") -> tuple[list[DimensionScore], list[DimensionScore]]:
        evidence = candidate.evidence
        # Per-candidate local semaphore limits intra-candidate fan-out so a
        # single candidate doesn't saturate the gateway.  The infrastructure-
        # level rate limiter (ChineseLanguageModel class) caps total concurrent
        # LLM calls globally — no need to duplicate that concern here.
        local = asyncio.Semaphore(6)

        async def score_one(dimension_code, score_type):
            async with local:
                return await asyncio.to_thread(self._score_dimension, candidate=asdict(candidate), dimension_code=dimension_code, evidence=evidence, score_type=score_type, scene_code=scene_code)

        icp, scale = await asyncio.gather(
            asyncio.gather(*(score_one(d, "icp") for d in ICP_DIMENSIONS)),
            asyncio.gather(*(score_one(d, "scale") for d in SCALE_DIMENSIONS)),
        )
        return list(icp), list(scale)

    def _score_dimension(self, *, candidate, dimension_code, evidence, score_type, scene_code):
        try:
            return self.llm.score_dimension(candidate=candidate, dimension_code=dimension_code, evidence=evidence, score_type=score_type, scene_code=scene_code)
        except TypeError as exc:
            if "scene_code" not in str(exc):
                raise
            return self.llm.score_dimension(candidate=candidate, dimension_code=dimension_code, evidence=evidence, score_type=score_type)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").replace("\x00", "").strip()
    return text or None


def _contacts_from_leads_finder(
    leads: dict[str, Any],
    *,
    candidate_name: str,
    candidate_website: str | None,
) -> list[dict[str, Any]]:
    contacts = leads.get("contacts")
    if isinstance(contacts, list):
        normalized = [normalize_contact(contact) for contact in contacts if isinstance(contact, dict)]
        normalized = [contact for contact in normalized if any(_text_or_none(contact.get(key)) for key in (
            "full_name", "title", "department", "email", "phone", "linkedin_url",
        ))]
        if normalized:
            return normalized
    raw = leads.get("raw") if isinstance(leads.get("raw"), dict) else {}
    provider_name = _text_or_none(raw.get("organization_name") or leads.get("organization_name"))
    provider_domain = _domain_text(raw.get("organization_primary_domain") or leads.get("organization_primary_domain"))
    candidate_domain = _domain_text(candidate_website)
    provider_name_key = _identity_text(provider_name)
    candidate_name_key = _identity_text(candidate_name)
    name_matches = bool(
        provider_name_key and candidate_name_key
        and (provider_name_key == candidate_name_key or provider_name_key in candidate_name_key or candidate_name_key in provider_name_key)
    )
    domain_matches = bool(provider_domain and candidate_domain and provider_domain == candidate_domain)
    if not name_matches and not domain_matches:
        return []
    full_name = " ".join(
        part for part in (
            _text_or_none(raw.get("first_name") or raw.get("firstName")),
            _text_or_none(raw.get("last_name") or raw.get("lastName")),
        ) if part
    ).strip()
    full_name = full_name or _text_or_none(raw.get("full_name") or raw.get("name"))
    if not full_name:
        return []
    return [normalize_contact({**raw, "full_name": full_name, "raw": raw})]


def _leads_source_matches_candidate(
    leads: dict[str, Any],
    *,
    candidate_name: str,
    candidate_website: str | None,
) -> bool:
    raw = leads.get("raw") if isinstance(leads.get("raw"), dict) else {}
    provider_name = _text_or_none(raw.get("organization_name") or leads.get("organization_name"))
    provider_domain = _domain_text(raw.get("organization_primary_domain") or leads.get("organization_primary_domain"))
    candidate_domain = _domain_text(candidate_website)
    provider_name_key = _identity_text(provider_name)
    candidate_name_key = _identity_text(candidate_name)
    name_matches = bool(
        provider_name_key and candidate_name_key
        and (provider_name_key == candidate_name_key or provider_name_key in candidate_name_key or candidate_name_key in provider_name_key)
    )
    domain_matches = bool(provider_domain and candidate_domain and provider_domain == candidate_domain)
    return name_matches or domain_matches or not (provider_name_key or provider_domain)


def _merge_contacts(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return merge_contacts(*groups)


def _contacts_from_payload(payload: Any) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            normalized = normalize_contact(item)
            if _looks_like_contact_payload(item) and has_contact_data(normalized):
                contacts.append(normalized)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(payload)
    return merge_contacts(contacts)


def _looks_like_contact_payload(item: dict[str, Any]) -> bool:
    keys = {str(key).strip().casefold() for key in item.keys()}
    contact_keys = {
        "full_name", "fullname", "display_name", "displayname", "name",
        "first_name", "firstname", "given_name", "givenname",
        "last_name", "lastname", "family_name", "familyname",
        "title", "job_title", "jobtitle", "position", "headline",
        "department", "department_name", "departmentname",
        "email", "email_address", "emailaddress",
        "phone", "phone_number", "phonenumber",
        "linkedin_url", "linkedinurl", "linkedin",
    }
    return bool(keys.intersection(contact_keys))


_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.IGNORECASE)
_NON_EMAIL_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico"}


def _email_addresses_from_payload(payload: Any) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()

    def collect(value: str) -> None:
        for match in _EMAIL_RE.findall(value):
            email = match.strip().casefold()
            tld = email.rsplit(".", 1)[-1]
            if email.endswith("@51tgt.com") or tld in _NON_EMAIL_TLDS or email in seen:
                continue
            seen.add(email)
            emails.append(email)

    def visit(item: Any) -> None:
        if isinstance(item, str):
            collect(item)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(payload)
    return emails


def _fill_missing_contact_emails(contacts: list[dict[str, Any]], emails: list[str]) -> list[dict[str, Any]]:
    if not emails:
        return contacts
    assigned: set[str] = set()
    filled: list[dict[str, Any]] = []
    email_index = 0
    for contact in contacts:
        enriched = dict(contact)
        current_email = _text_or_none(enriched.get("email"))
        if current_email:
            assigned.add(current_email.casefold())
        else:
            while email_index < len(emails) and emails[email_index] in assigned:
                email_index += 1
            if email_index < len(emails):
                enriched["email"] = emails[email_index]
                assigned.add(emails[email_index])
                email_index += 1
        filled.append(enriched)
    while email_index < len(emails):
        email = emails[email_index]
        email_index += 1
        if email in assigned:
            continue
        filled.append({
            "full_name": _email_display_name(email),
            "email": email,
            "email_status": "unknown",
        })
        assigned.add(email)
    return _merge_contacts(filled)


def _email_display_name(email: str) -> str:
    local_part = email.split("@", 1)[0]
    name = re.sub(r"[._+-]+", " ", local_part).strip()
    return name or email


def _identity_text(value: Any) -> str:
    return "".join(char for char in str(value or "").casefold() if char.isalnum())


def _domain_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].removeprefix("www.")


def _company_evidence_fields(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose all Exa company facts to mapping and preserve their provenance."""
    snippets = []
    urls = []
    titles = []
    for item in evidence:
        if _text_or_none(item.get("snippet")):
            snippets.append(_text_or_none(item.get("snippet")))
        if _text_or_none(item.get("title")):
            titles.append(_text_or_none(item.get("title")))
        if _text_or_none(item.get("url")):
            urls.append(_text_or_none(item.get("url")))
    return {
        "company_intro": "\n".join(snippets),
        "exa_titles": titles,
        "exa_urls": urls,
        "exa_evidence": evidence,
    }


def _candidate_evidence(raw: dict[str, Any], name: str, item: dict[str, Any]) -> bool:
    """Keep discovery evidence attached to the matching company only."""
    expected_domain = str(raw.get("website") or "").lower().replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.")
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").casefold()
    return bool((expected_domain and expected_domain in url) or name.casefold() in title)


def _normalize_country(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    aliases = {
        "UNITED STATES": "US", "USA": "US", "U.S.": "US", "U.S.A.": "US",
        "JAPAN": "JP", "CHINA": "CN", "SOUTH KOREA": "KR", "KOREA": "KR",
        "SINGAPORE": "SG", "UNITED KINGDOM": "GB", "UK": "GB",
        "GERMANY": "DE", "FRANCE": "FR", "CANADA": "CA", "AUSTRALIA": "AU",
        "UNITED ARAB EMIRATES": "AE", "UAE": "AE", "SAUDI ARABIA": "SA",
    }
    text = aliases.get(text, text)
    return text if len(text) == 2 and text.isalpha() else None


def _normalize_region(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in {"NA", "EA", "SEA", "EU", "ME", "OTHER"} else None


def _region_from_country(country_code: str | None) -> str | None:
    if country_code in {"US", "CA", "MX"}:
        return "NA"
    if country_code in {"CN", "HK", "JP", "KR", "MO", "TW"}:
        return "EA"
    if country_code in {"BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "VN"}:
        return "SEA"
    if country_code in {"AT", "BE", "CH", "DE", "DK", "ES", "FI", "FR", "GB", "IE", "IT", "NL", "NO", "PL", "PT", "SE"}:
        return "EU"
    if country_code in {"AE", "BH", "IL", "KW", "OM", "QA", "SA"}:
        return "ME"
    return None


def _normalize_industry(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_")
    aliases = {"OTA": "TRAVEL_OTA", "TRAVEL OTA": "TRAVEL_OTA", "TRAVEL_AGENCY": "TMC", "BUSINESS_TRAVEL": "TMC"}
    text = aliases.get(text, text)
    return text if text in {"TMC", "TRAVEL_OTA", "FINTECH", "OTHER"} else "OTHER"
