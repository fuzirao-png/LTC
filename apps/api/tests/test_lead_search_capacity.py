from __future__ import annotations

import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from ltc.modules.lead_intelligence.interfaces.router import list_lead_candidates
from ltc.modules.lead_intelligence.interfaces.schemas import (
    DEFAULT_LEAD_SEARCH_TARGET,
    MAX_LEAD_SEARCH_RESULTS,
    LeadSearchRunCreate,
)


class LeadSearchCapacityTests(unittest.TestCase):
    def test_default_search_supports_large_collection_runs(self) -> None:
        request = LeadSearchRunCreate(query_text="Find enterprise travel companies")

        self.assertEqual(DEFAULT_LEAD_SEARCH_TARGET, request.target_count)
        self.assertGreaterEqual(request.target_count, 500)

    def test_search_accepts_more_than_five_hundred_companies(self) -> None:
        request = LeadSearchRunCreate(
            query_text="Find 600 enterprise travel companies",
            target_count=600,
        )

        self.assertEqual(600, request.target_count)

    def test_search_rejects_only_above_the_safety_limit(self) -> None:
        LeadSearchRunCreate(
            query_text="Find companies up to the supported limit",
            target_count=MAX_LEAD_SEARCH_RESULTS,
        )

        with self.assertRaises(ValidationError):
            LeadSearchRunCreate(
                query_text="Find too many companies in one run",
                target_count=MAX_LEAD_SEARCH_RESULTS + 1,
            )

    def test_candidate_list_does_not_truncate_at_two_hundred(self) -> None:
        class Repository:
            requested_limit = 0

            def list_candidates(self, *, search_run_id=None, limit=50):
                del search_run_id
                self.requested_limit = limit
                return []

            def count_candidates(self, *, search_run_id=None, analysis_pool=False):
                del search_run_id, analysis_pool
                return 0

        repository = Repository()
        request = SimpleNamespace(
            headers={},
            app=SimpleNamespace(
                state=SimpleNamespace(
                    lead_intelligence=SimpleNamespace(repository=repository),
                ),
            ),
        )

        response = list_lead_candidates(
            request=request,
            search_run_id=None,
            limit=600,
            context=None,
        )

        self.assertEqual(600, repository.requested_limit)
        self.assertEqual(600, response["page"]["limit"])

    def test_candidate_list_returns_repository_total(self) -> None:
        class Repository:
            def list_candidates(self, *, search_run_id=None, limit=50, analysis_pool=False):
                del search_run_id, limit, analysis_pool
                return [{"candidate_id": "one"}]

            def count_candidates(self, *, search_run_id=None, analysis_pool=False):
                del search_run_id, analysis_pool
                return 37

        repository = Repository()
        request = SimpleNamespace(
            headers={},
            app=SimpleNamespace(
                state=SimpleNamespace(
                    lead_intelligence=SimpleNamespace(repository=repository),
                ),
            ),
        )

        response = list_lead_candidates(
            request=request,
            search_run_id=None,
            analysis_pool=True,
            limit=100,
            context=None,
        )

        self.assertEqual(37, response["page"]["total"])


if __name__ == "__main__":
    unittest.main()
