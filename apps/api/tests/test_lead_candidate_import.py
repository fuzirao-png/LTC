from __future__ import annotations

import unittest

from ltc.modules.lead_intelligence.application.import_service import LeadCandidateImportService


class FakeRepository:
    def __init__(self) -> None:
        self.candidates = []
        self.providers = []
        self.finished = []

    def create_search_run(self, request):
        self.request = request
        return "run-1", "job-1"

    def start_search_run(self, search_run_id):
        self.started = search_run_id

    def upsert_candidate(self, *, search_run_id, candidate):
        self.candidates.append((search_run_id, candidate))

    def record_provider(self, **kwargs):
        self.providers.append(kwargs)

    def finish_search_run(self, *args, **kwargs):
        self.finished.append((args, kwargs))


class LeadCandidateImportTests(unittest.TestCase):
    def test_csv_import_normalizes_and_records_trace(self) -> None:
        repository = FakeRepository()
        content = (
            "company_name,website,industry_code,region_code,employee_count,city,company_intro\n"
            "Upload Example,https://upload.example,TMC,EA,120,Tokyo,# **全球差旅平台**\n"
        ).encode()

        result = LeadCandidateImportService(repository).import_csv(
            content=content, filename="leads.csv"
        )

        self.assertEqual(result, {"search_run_id": "run-1", "imported_count": 1})
        candidate = repository.candidates[0][1]
        self.assertEqual(candidate.company_name, "Upload Example")
        self.assertEqual(candidate.employee_count, 120)
        self.assertEqual(candidate.company_intro, "全球差旅平台")
        self.assertEqual(repository.providers[0]["provider_code"], "manual_upload")
        self.assertEqual(repository.finished[0][1]["status"], "completed")

    def test_csv_import_requires_company_name_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "company_name"):
            LeadCandidateImportService(FakeRepository()).import_csv(
                content=b"website\nhttps://example.com\n", filename="bad.csv"
            )


if __name__ == "__main__":
    unittest.main()
