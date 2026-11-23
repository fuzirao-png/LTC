from __future__ import annotations

import unittest
from threading import Barrier

from ltc.modules.lead_intelligence.application.pipeline import (
    LeadSearchPipeline,
    _email_addresses_from_payload,
    _contacts_from_leads_finder,
    _contacts_from_payload,
    _merge_contacts,
)
from ltc.modules.lead_intelligence.domain.models import DimensionScore
from ltc.modules.lead_intelligence.domain.icp_rules import sales_tier_for_customer_grade
from ltc.modules.lead_intelligence.infrastructure.llm import _deterministic_score
from ltc.modules.lead_intelligence.infrastructure.postgres_repository import PostgresLeadRepository
from ltc.modules.lead_intelligence.infrastructure.postgres_repository import (
    _public_contact,
    _reuse_previous_successful_scores,
)


class FakeMemory:
    def __init__(self, events): self.events = events
    def read(self, request): self.events.append("memory"); return []
    def write(self, request, candidate): self.events.append("memory_write")


class FakeExa:
    code = "web_search"
    def __init__(self, events): self.events, self.calls = events, []
    def search(self, query, *, phase, limit=20):
        self.calls.append((phase, query)); self.events.append("exa:" + phase)
        return [{"title": "Acme Travel", "url": "https://acme.example"}] if phase == "collection" else [{"url": "https://acme.example/about", "snippet": "OTA"}]


class FakeLeads:
    def __init__(self, events, raw=None): self.events, self.raw = events, raw
    def lookup(self, *, company_name, country=None, company_domain=None):
        del country, company_domain
        self.events.append("leads_finder")
        return {"organization_name": company_name, "organization_linkedin_url": "https://linkedin.com/company/acme", "raw": self.raw or {}}


class UnavailableLeads(FakeLeads):
    def lookup(self, *, company_name, country=None, company_domain=None):
        del company_name, country, company_domain
        raise OSError("provider quota exceeded")


class FakeLinkedIn:
    def __init__(self, events, contacts=None): self.events, self.contacts, self.company_urls = events, contacts, []
    def lookup(self, *, company_url):
        self.company_urls.append(company_url)
        self.events.append("linkedin")
        return self.contacts if self.contacts is not None else [{"url": "https://linkedin.com/in/a", "title": "A"}]


class FakeLLM:
    def plan_query(self, *, request, memory): return "business travel OTA United States"
    def extract_candidates(self, *, request, results, memory): return [{"company_name": "Acme Travel", "website": "https://acme.example"}]
    def summarize_missing(self, *, request, candidate, leads_finder): return {"missing_fields": ["company_intro"], "search_query": "Acme Travel company profile"}
    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence): return dict(candidate, country_code="US", company_intro="OTA", linkedin_company_url="https://linkedin.com/company/acme")
    def score_dimension(self, *, candidate, dimension_code, evidence, score_type): return DimensionScore(dimension_code, 1, "证据支持", evidence)


class NoLinkedInLLM(FakeLLM):
    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence):
        return dict(candidate, country_code="US", company_intro="OTA", linkedin_company_url=None)


class ChineseIntroLLM(FakeLLM):
    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence):
        return dict(candidate, country_code="US", company_intro="# **艾克米是一家企业差旅平台。**")


class RawContactLLM(FakeLLM):
    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence):
        return dict(
            candidate,
            country_code="US",
            company_intro="OTA",
            linkedin_company_url="https://linkedin.com/company/acme",
            extra_fields={
                "raw_ai_output": {
                    "contacts": [
                        {
                            "full_name": "Ada Lovelace",
                            "title": "Procurement Manager",
                            "email": "ada@example.com",
                        }
                    ]
                }
            },
        )


class RawTextEmailLLM(FakeLLM):
    def summarize_company(self, *, request, candidate, company_evidence, contacts, exa_evidence):
        return dict(
            candidate,
            country_code="US",
            company_intro="OTA",
            linkedin_company_url="https://linkedin.com/company/acme",
            extra_fields={"source_text": "Contact procurement at ada@example.com for business travel requests."},
        )


class NoLinkedInLeads(FakeLeads):
    def lookup(self, *, company_name, country=None, company_domain=None):
        del country, company_domain
        self.events.append("leads_finder")
        return {"organization_name": company_name, "contacts": [], "raw": {}}


class FakeRepository:
    def __init__(self):
        self.saved = False
        self.candidate = None
        self.candidates = []
        self.finished = None
        self.progress = []
    def create_search_run(self, request): return "run-1", "job-1"
    def start_search_run(self, search_run_id): pass
    def record_provider(self, **kwargs): pass
    def record_progress(self, **kwargs): self.progress.append(kwargs)
    def record_evidence(self, **kwargs): pass
    def finish_search_run(self, *args, **kwargs): self.finished = (args, kwargs)
    def upsert_candidate(self, **kwargs):
        self.saved = True
        self.candidate = kwargs["candidate"]
        self.candidates.append(kwargs["candidate"])
    def record_enrichment(self, **kwargs): self.saved = True


class CapturingPostgresRepository(PostgresLeadRepository):
    def __init__(self):
        super().__init__("postgresql://test")
        self.executions = []

    def _execute(self, sql, params=()):
        self.executions.append((sql, params))


def test_public_contact_excludes_provider_payload_and_keeps_business_fields() -> None:
    contact = _public_contact({
        "candidate_contact_id": "contact-1",
        "full_name": "Ada Lovelace",
        "title": "Procurement Director",
        "department": "Procurement",
        "relationship_role": "decision_maker",
        "priority": "P1",
        "email": "ada@example.com",
        "email_status": "valid",
        "email_type": "work",
        "email_score": 98,
        "phone": "+1-555-0100",
        "linkedin_url": "https://linkedin.com/in/ada",
        "source_payload": {"profile": "must not be returned"},
        "experience": [{"company": "raw provider data"}],
    })

    assert contact == {
        "candidate_contact_id": "contact-1",
        "full_name": "Ada Lovelace",
        "title": "Procurement Director",
        "department": "Procurement",
        "relationship_role": "decision_maker",
        "priority": "P1",
        "email": "ada@example.com",
        "email_status": "valid",
        "email_type": "work",
        "email_score": 98,
        "phone": "+1-555-0100",
        "linkedin_url": "https://linkedin.com/in/ada",
    }

class SearchRunCompletionTests(unittest.TestCase):
    def test_cancelled_run_marks_job_cancelled(self):
        repository = CapturingPostgresRepository()

        repository.finish_search_run(
            "run-1",
            "job-1",
            status="cancelled",
            counts={"candidate_count": 1, "enriched_count": 0, "scored_count": 0},
            error="Cancelled by user",
        )

        self.assertEqual("cancelled", repository.executions[1][1][0])


class IcpFallbackScoringTests(unittest.TestCase):
    def test_d3_fallback_uses_employee_count_instead_of_unconditional_zero(self) -> None:
        score, explanation = _deterministic_score(
            {"employee_count": 1599}, "D3", []
        )

        self.assertEqual(20.0, score)
        self.assertIn("D3=20", explanation)

    def test_provider_fallback_reuses_previous_score_and_explanation_atomically(self) -> None:
        scores = [
            DimensionScore(
                "D3", 0.0, "评分模型不可用，暂不加分", [],
                provider_status="fallback", error_message="APITimeoutError",
            )
        ]
        previous_row = (
            40, 30, 20, 10,
            {"D3": "评分为20分。规模证据充分。"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
        )

        _reuse_previous_successful_scores(scores, previous_row)

        self.assertEqual(20.0, scores[0].score)
        self.assertEqual("评分为20分。规模证据充分。", scores[0].explanation)
        self.assertEqual("reused_previous_success", scores[0].provider_status)

    def test_consecutive_fallback_can_reuse_an_already_reused_success(self) -> None:
        scores = [DimensionScore("D4", 0.0, "本次超时", [], provider_status="fallback")]
        previous_row = (
            40, 30, 20, 10,
            {"D4": "评分为10分。技术证据充分。"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "reused_previous_success"},
        )

        _reuse_previous_successful_scores(scores, previous_row)

        self.assertEqual(10.0, scores[0].score)
        self.assertEqual("评分为10分。技术证据充分。", scores[0].explanation)

    def test_successful_rescore_never_reuses_an_old_explanation(self) -> None:
        scores = [DimensionScore("D3", 15.0, "本次评分为15分。", [])]
        previous_row = (
            40, 30, 20, 10,
            {"D3": "评分为20分。旧证据。"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
            {"provider_status": "succeeded"},
        )

        _reuse_previous_successful_scores(scores, previous_row)

        self.assertEqual(15.0, scores[0].score)
        self.assertEqual("本次评分为15分。", scores[0].explanation)


class CustomerGradeSalesTierTests(unittest.TestCase):
    def test_customer_grade_maps_to_required_sales_tier(self) -> None:
        self.assertEqual("MA", sales_tier_for_customer_grade("A"))
        self.assertEqual("SA", sales_tier_for_customer_grade("B"))
        self.assertEqual("A", sales_tier_for_customer_grade("C"))


class ContactEnrichmentTests(unittest.TestCase):
    def test_provider_contact_with_title_but_no_email_is_retained(self) -> None:
        contacts = _contacts_from_leads_finder(
            {
                "contacts": [{
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "jobTitle": "Procurement Manager",
                }],
            },
            candidate_name="Acme Travel",
            candidate_website="https://acme.example",
        )

        self.assertEqual("Ada Lovelace", contacts[0]["full_name"])
        self.assertEqual("Procurement Manager", contacts[0]["title"])

    def test_duplicate_provider_contacts_merge_richer_fields(self) -> None:
        contacts = _merge_contacts(
            [{"full_name": "Ada Lovelace", "email": "ada@acme.example"}],
            [{
                "full_name": "Ada Lovelace",
                "email": "ada@acme.example",
                "title": "Commercial Manager",
                "phone": "+1-555-0100",
            }],
        )

        self.assertEqual(1, len(contacts))
        self.assertEqual("Commercial Manager", contacts[0]["title"])
        self.assertEqual("+1-555-0100", contacts[0]["phone"])

    def test_raw_payload_contacts_are_preserved(self) -> None:
        contacts = _contacts_from_payload({
            "raw_ai_output": {
                "contacts": [
                    {
                        "full_name": "Ada Lovelace",
                        "title": "Procurement Manager",
                        "email": "ada@example.com",
                    }
                ]
            }
        })

        self.assertEqual(1, len(contacts))
        self.assertEqual("ada@example.com", contacts[0]["email"])

    def test_raw_email_extraction_ignores_image_asset_names(self) -> None:
        emails = _email_addresses_from_payload({
            "source_text": "logo@3x.cd15fc34.png real contact ada@example.com",
        })

        self.assertEqual(["ada@example.com"], emails)


class TwoCandidateLLM(FakeLLM):
    def extract_candidates(self, *, request, results, memory):
        return [
            {"company_name": "Good Travel", "website": "https://good.example"},
            {"company_name": "Bad Travel", "website": "https://bad.example"},
        ]

    def summarize_missing(self, *, request, candidate, leads_finder):
        return {"missing_fields": []}


class ConcurrentLeads:
    def __init__(self, *, failing_company=None):
        self.barrier = Barrier(2)
        self.failing_company = failing_company

    def lookup(self, *, company_name, country=None, company_domain=None):
        del country, company_domain
        self.barrier.wait(timeout=1)
        if company_name == self.failing_company:
            raise OSError("provider unavailable")
        return {"organization_name": company_name, "raw": {}}


class PipelineOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_quota_failure_degrades_to_exa_candidate_persistence(self):
        events = []
        repository = FakeRepository()
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=UnavailableLeads(events),
            linkedin=FakeLinkedIn(events, contacts=[]), llm=FakeLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找美国商旅OTA", "target_count": 1,
            "search_mode": "company_only", "scene_code": "S1",
        })

        self.assertTrue(repository.saved)
        self.assertEqual("Acme Travel", repository.candidate.company_name)
        self.assertEqual("completed", repository.finished[1]["status"])

    async def test_chinese_plain_text_summary_wins_over_provider_english_intro(self):
        events = []
        repository = FakeRepository()
        leads = FakeLeads(events, raw={
            "organization_name": "Acme Travel",
            "organization_description": "# Global business travel platform",
        })
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=leads,
            linkedin=FakeLinkedIn(events, contacts=[]), llm=ChineseIntroLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找美国商旅OTA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual("艾克米是一家企业差旅平台。", repository.candidate.company_intro)

    async def test_memory_then_tools_and_single_missing_exa(self):
        events = []
        exa = FakeExa(events)
        pipeline = LeadSearchPipeline(memory=FakeMemory(events), exa=exa, leads_finder=FakeLeads(events), linkedin=FakeLinkedIn(events), llm=FakeLLM(), repository=FakeRepository())
        await pipeline.execute(job_id="job-1", lock_token="lock", payload={"query_text": "找美国商旅OTA", "target_count": 1, "search_mode": "both", "scene_code": "S1"})
        self.assertEqual(["memory", "exa:collection", "leads_finder", "exa:icp_enrichment", "linkedin", "memory_write"], events)
        self.assertEqual(["collection", "icp_enrichment"], [phase for phase, _ in exa.calls])

    async def test_leads_finder_contact_is_kept_when_linkedin_returns_none(self):
        events = []
        repository = FakeRepository()
        leads = FakeLeads(events, raw={
            "organization_name": "Acme Travel",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "title": "VP Travel",
            "email": "ada@example.com",
            "linkedin_url": "https://linkedin.com/in/ada",
        })
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=leads,
            linkedin=FakeLinkedIn(events, contacts=[]), llm=FakeLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找美国商旅OTA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertIsNotNone(repository.candidate)
        self.assertEqual("Ada Lovelace", repository.candidate.contacts[0]["full_name"])
        self.assertEqual("ada@example.com", repository.candidate.contacts[0]["email"])

    async def test_raw_extraction_contacts_are_persisted(self):
        events = []
        repository = FakeRepository()
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=NoLinkedInLeads(events),
            linkedin=FakeLinkedIn(events, contacts=[]), llm=RawContactLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "鎵剧編鍥藉晢鏃匫TA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual("Ada Lovelace", repository.candidate.contacts[0]["full_name"])
        self.assertEqual("ada@example.com", repository.candidate.contacts[0]["email"])

    async def test_raw_text_email_fills_existing_contact_email(self):
        events = []
        repository = FakeRepository()
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=NoLinkedInLeads(events),
            linkedin=FakeLinkedIn(events, contacts=[{
                "full_name": "Ada Lovelace",
                "title": "Procurement Manager",
            }]),
            llm=RawTextEmailLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "鎵剧編鍥藉晢鏃匫TA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual("Ada Lovelace", repository.candidate.contacts[0]["full_name"])
        self.assertEqual("ada@example.com", repository.candidate.contacts[0]["email"])

    async def test_company_name_is_used_when_linkedin_company_url_is_missing(self):
        events = []
        linkedin = FakeLinkedIn(events, contacts=[{
            "full_name": "Ada Lovelace",
            "email": "ada@acme.example",
        }])
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events),
            leads_finder=NoLinkedInLeads(events), linkedin=linkedin,
            llm=NoLinkedInLLM(), repository=FakeRepository(),
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找美国商旅OTA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual(["Acme Travel"], linkedin.company_urls)

    async def test_leads_finder_contact_is_rejected_for_a_different_company(self):
        events = []
        repository = FakeRepository()
        leads = FakeLeads(events, raw={
            "organization_name": "Different Company",
            "organization_primary_domain": "different.example",
            "first_name": "Wrong",
            "last_name": "Person",
            "email": "wrong@different.example",
        })
        pipeline = LeadSearchPipeline(
            memory=FakeMemory(events), exa=FakeExa(events), leads_finder=leads,
            linkedin=FakeLinkedIn(events, contacts=[]), llm=FakeLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找美国商旅OTA", "target_count": 1,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertIsNotNone(repository.candidate)
        self.assertEqual([], repository.candidate.contacts)

    async def test_candidates_enter_blocking_provider_calls_concurrently(self):
        repository = FakeRepository()
        pipeline = LeadSearchPipeline(
            memory=FakeMemory([]), exa=FakeExa([]), leads_finder=ConcurrentLeads(),
            linkedin=FakeLinkedIn([], contacts=[]), llm=TwoCandidateLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找两家商旅公司", "target_count": 2,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual(2, len(repository.candidates))
        self.assertEqual("completed", repository.finished[1]["status"])

    async def test_one_provider_failure_keeps_all_discovered_candidates(self):
        repository = FakeRepository()
        pipeline = LeadSearchPipeline(
            memory=FakeMemory([]), exa=FakeExa([]),
            leads_finder=ConcurrentLeads(failing_company="Bad Travel"),
            linkedin=FakeLinkedIn([], contacts=[]), llm=TwoCandidateLLM(), repository=repository,
        )

        await pipeline.execute(job_id="job-1", lock_token="lock", payload={
            "query_text": "找两家商旅公司", "target_count": 2,
            "search_mode": "both", "scene_code": "S1",
        })

        self.assertEqual(
            {"Good Travel", "Bad Travel"},
            {item.company_name for item in repository.candidates},
        )
        self.assertEqual("completed", repository.finished[1]["status"])
        self.assertEqual(2, repository.finished[1]["counts"]["enriched_count"])
        self.assertIsNone(repository.finished[1]["error"])


if __name__ == "__main__":
    unittest.main()
