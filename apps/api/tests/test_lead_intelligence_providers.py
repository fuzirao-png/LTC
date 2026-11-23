from __future__ import annotations

import json
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ltc.modules.lead_intelligence.infrastructure.providers import (
    ApifyLeadsFinderProvider,
    ApifyLinkedInProvider,
    ExaHttpProvider,
    _items,
    _read_json,
)


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class LeadProviderAdapterTests(unittest.TestCase):
    def test_apify_retries_concurrency_limit_and_preserves_error_detail(self) -> None:
        request = type("Request", (), {"full_url": "https://api.apify.test", "data": None})()
        calls = 0

        def fake_urlopen(_request, timeout):
            nonlocal calls
            del timeout
            calls += 1
            if calls < 3:
                raise HTTPError(
                    request.full_url, 403, "Forbidden", hdrs=None,
                    fp=io.BytesIO(b'{"error":{"type":"actor-runs-limit-exceeded"}}'),
                )
            return _Response({"data": {"id": "run-1"}})

        with (
            patch("ltc.modules.lead_intelligence.infrastructure.providers.urlopen", fake_urlopen),
            patch("ltc.modules.lead_intelligence.infrastructure.providers.time.sleep"),
        ):
            result = _read_json(request, float("inf"))

        self.assertEqual("run-1", result["data"]["id"])
        self.assertEqual(3, calls)

    def test_exa_retries_and_falls_back_to_basic_search_payload(self) -> None:
        payloads: list[dict] = []

        def fake_urlopen(request, timeout):
            del timeout
            payloads.append(json.loads(request.data.decode()))
            if len(payloads) < 3:
                raise HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":"temporary validation failure"}'),
                )
            return _Response({"results": [{"url": "https://trip.com", "title": "Trip.com"}]})

        with (
            patch("ltc.modules.lead_intelligence.infrastructure.providers.urlopen", fake_urlopen),
            patch("ltc.modules.lead_intelligence.infrastructure.providers.time.sleep"),
        ):
            results = ExaHttpProvider(api_key="test").search("trip ota", phase="collection", limit=20)

        self.assertEqual("https://trip.com", results[0]["url"])
        self.assertEqual(10, payloads[0]["numResults"])
        self.assertIn("contents", payloads[0])
        self.assertIn("contents", payloads[1])
        self.assertNotIn("contents", payloads[2])

    def test_items_extracts_first_email_from_actor_email_array(self) -> None:
        contacts = _items(
            {
                "data": [{
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "emails": [{"email": "ada@acme.example", "status": "verified"}],
                }]
            },
            1,
        )

        self.assertEqual("ada@acme.example", contacts[0]["email"])

    def test_leads_finder_uses_supported_filters_and_rejects_wrong_company(self) -> None:
        rows = [
            {
                "organization_name": "Bridge",
                "organization_primary_domain": "bridge.website",
                "email": "wrong@bridge.website",
            },
            {
                "organization_name": "Acme Travel",
                "organization_primary_domain": "acme.example",
                "organization_website_url": "https://acme.example",
                "organization_linkedin_url": "https://linkedin.com/company/acme-travel",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada@acme.example",
            },
        ]
        captured: dict = {}

        def fake_urlopen(request, timeout):
            del timeout
            if request.data:
                captured.update(json.loads(request.data.decode()))
                return _Response({"data": {
                    "id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "dataset-1",
                }})
            return _Response(rows)

        with patch("ltc.modules.lead_intelligence.infrastructure.providers.urlopen", fake_urlopen):
            result = ApifyLeadsFinderProvider(api_key="test").lookup(
                company_name="Acme Travel",
                company_domain="https://www.acme.example/about",
                country="United States",
            )

        self.assertEqual(["acme.example"], captured["company_domains"])
        self.assertNotIn("company_locations", captured)
        self.assertNotIn("company_names", captured)
        self.assertNotIn("person_locations", captured)
        self.assertEqual("Acme Travel", result["organization_name"])
        self.assertEqual("ada@acme.example", result["contacts"][0]["email"])

    def test_linkedin_lookup_enables_email_search(self) -> None:
        captured: dict = {}

        def fake_urlopen(request, timeout):
            del timeout
            if request.data:
                captured.update(json.loads(request.data.decode()))
                return _Response({"data": {
                    "id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "dataset-1",
                }})
            return _Response([{
                "firstName": "Ada",
                "lastName": "Lovelace",
                "linkedinUrl": "https://linkedin.com/in/ada",
                "emails": ["ada@acme.example"],
            }])

        with patch("ltc.modules.lead_intelligence.infrastructure.providers.urlopen", fake_urlopen):
            contacts = ApifyLinkedInProvider(api_key="test").lookup(
                company_url="https://linkedin.com/company/acme-travel"
            )

        self.assertIn("email search", captured["profileScraperMode"].lower())
        self.assertEqual("ada@acme.example", contacts[0]["email"])


if __name__ == "__main__":
    unittest.main()
