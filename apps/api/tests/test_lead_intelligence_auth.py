from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from ltc.main import create_app


class LeadIntelligenceAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(), raise_server_exceptions=False)

    def tearDown(self) -> None:
        self.client.close()

    def test_reads_require_authentication_before_accessing_repository(self) -> None:
        resource_id = uuid4()
        for path in (
            f"/api/v1/lead-search-runs/{resource_id}",
            f"/api/v1/lead-search-runs/{resource_id}/trace",
            "/api/v1/lead-candidates",
            f"/api/v1/lead-candidates/{resource_id}",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)

    def test_create_search_run_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/v1/lead-search-runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "query_text": "Japan enterprise travel",
                "search_mode": "both",
                "target_count": 10,
                "scene_code": "S1",
            },
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_candidate_import_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/v1/lead-candidates:import",
            files={"file": ("leads.csv", b"company_name\nPrivate Lead\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
