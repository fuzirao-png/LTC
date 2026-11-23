from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from ltc.modules.customer_analysis.domain.models import AnalysisSuggestion, CustomerProfile
from ltc.modules.customer_analysis.infrastructure import PostgresCustomerAnalysisRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None
        self.rowcount = 0

    def execute(self, query, params):
        self.connection.queries.append((query, params))
        if query.lstrip().startswith("SELECT"):
            self.row = self.connection.row
        else:
            self.rowcount = 1  # INSERT/UPDATE affects 1 row by default
        if self.connection.error is not None:
            raise self.connection.error

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class CustomerAnalysisDatabaseFlowTests(unittest.TestCase):
    def test_runtime_connection_factory_freezes_environment_at_creation(self):
        from ltc.modules.customer_analysis.infrastructure.bootstrap import _runtime_connection_factory

        with patch("psycopg.connect") as connect:
            with patch.dict(
                "os.environ",
                {
                    "LTC_DB_HOST": "db.example",
                    "LTC_DB_PORT": "55432",
                    "LTC_DB_NAME": "ltc_test",
                    "LTC_DB_USER": "ltc_user",
                    "LTC_DB_PASSWORD": "secret",
                    "LTC_DB_SSLMODE": "require",
                },
            ):
                factory = _runtime_connection_factory()

            self.assertIsNotNone(factory)
            factory()
            connect.assert_called_once_with(
                host="db.example",
                port=55432,
                dbname="ltc_test",
                user="ltc_user",
                password="secret",
                sslmode="require",
            )

    def test_profile_round_trip_uses_database_transaction(self):
        company_id = UUID("00000000-0000-0000-0000-000000000001")
        updated_at = datetime.now(timezone.utc)
        row = (
            company_id, "SaaS", "APAC", "100-500", "B2B", "API", "Global",
            "Medium", "REST", "SOC2", "$10k", "Buyer", None, "2 weeks", 0.5,
            ["coverage"], {}, {}, "source", None, 1, None, updated_at,
        )
        connections = [FakeConnection(row), FakeConnection()]
        repository = PostgresCustomerAnalysisRepository(lambda: connections.pop(0))
        profile = repository.get_profile(company_id)
        self.assertIsNotNone(profile)
        assert profile is not None
        repository.save_profile(profile)
        self.assertEqual(profile.version, 1)

    def test_database_errors_are_raised_and_rolled_back(self):
        connection = FakeConnection(error=RuntimeError("database unavailable"))
        repository = PostgresCustomerAnalysisRepository(lambda: connection)
        profile = CustomerProfile(
            company_id=UUID("00000000-0000-0000-0000-000000000001")
        )
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            repository.save_profile(profile)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertTrue(connection.closed)

    def test_run_mapper_restores_report_relationship(self):
        run_id = UUID("00000000-0000-0000-0000-000000000010")
        company_id = UUID("00000000-0000-0000-0000-000000000011")
        job_id = UUID("00000000-0000-0000-0000-000000000012")
        report_id = UUID("00000000-0000-0000-0000-000000000013")
        now = datetime.now(timezone.utc)
        row = (
            run_id, company_id, None, None, None, None,
            job_id, "customer_analysis", "manual", "completed",
            "hash", "prompt", "schema", None, 0, "revision",
            None, {}, {}, None, "USD", "unknown",
            None, None, None,
            now, now, now, 2, report_id,
        )
        mapped = PostgresCustomerAnalysisRepository._run_from_row(row)
        self.assertEqual(mapped.report_id, report_id)
    def test_report_sql_uses_run_hash_and_schema_columns(self):
        self.assertNotIn("ar.input_hash", PostgresCustomerAnalysisRepository._report_select())
        self.assertIn("run.input_hash", PostgresCustomerAnalysisRepository._report_select())

    def test_suggestion_review_uses_optimistic_version_guard(self):
        connection = FakeConnection()
        repository = PostgresCustomerAnalysisRepository(lambda: connection)
        suggestion = AnalysisSuggestion(
            suggestion_id=UUID("00000000-0000-0000-0000-000000000021"),
            company_id=UUID("00000000-0000-0000-0000-000000000022"),
            report_id=UUID("00000000-0000-0000-0000-000000000023"),
            target_type="profile",
            dimension_code=None,
            target_path="business_model",
            target_version_at_creation=0,
            current_value_snapshot="B2B",
            proposed_value="B2B SaaS",
            version=1,
        )

        repository.save_suggestion(suggestion)

        query, params = connection.queries[0]
        self.assertIn("version=ltc.analysis_suggestion.version + 1", query)
        self.assertIn("ltc.analysis_suggestion.version = %s", query)
        self.assertEqual(0, params[-1])


if __name__ == "__main__":
    unittest.main()
