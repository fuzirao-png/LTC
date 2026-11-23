from __future__ import annotations

import json
import unittest

from ltc.modules.lead_intelligence.infrastructure.promotion_adapter import PostgresPromotionAdapter


class _Cursor:
    def __init__(self) -> None:
        self.query = ""

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query

    def fetchone(self) -> dict[str, str]:
        return {"company_name": "Acme Travel", "website": "https://acme.example"}


class _Connection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self, **kwargs: object) -> _Cursor:
        return _Cursor()

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.statements.append((query, params))


class _Transaction:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, *args: object) -> None:
        pass


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    def transaction(self) -> _Transaction:
        return _Transaction(self.connection)


class LeadEnrichmentRefreshTests(unittest.TestCase):
    def test_refresh_creates_valid_queued_run_and_executable_search_payload(self) -> None:
        database = _Database()
        adapter = PostgresPromotionAdapter(database)

        result = adapter.prepare_refresh_enrichment("c3000000-0000-4000-8000-000000000003")

        statements = database.connection.statements
        self.assertIn("INSERT INTO ltc.job", statements[0][0])
        self.assertIn("INSERT INTO ltc.lead_search_run", statements[1][0])
        self.assertIn("UPDATE ltc.lead_candidate", statements[2][0])
        self.assertIn("INSERT INTO ltc.lead_enrichment_run", statements[3][0])
        self.assertIn("COALESCE(MAX(version_no),0)+1", statements[3][0])
        self.assertIn("%s,false,clock_timestamp(),0", statements[3][0])

        payload = json.loads(str(statements[0][1][2]))
        self.assertEqual("Acme Travel https://acme.example", payload["query_text"])
        self.assertEqual(result["search_run_id"], payload["search_run_id"])
        self.assertTrue(payload["refresh"])
        self.assertEqual(payload, result["pipeline_payload"])


if __name__ == "__main__":
    unittest.main()
