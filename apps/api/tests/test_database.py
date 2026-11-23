from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ltc.platform.config import AppSettings
from ltc.platform.db.postgres import PostgresDatabase


class PostgresDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = AppSettings(
            database_host="postgres",
            database_port=5432,
            database_name="ltc",
            database_user="ltc",
            database_password="secret",
            database_sslmode="disable",
            database_pool_timeout_seconds=2.5,
        )

    @patch("ltc.platform.db.postgres.ConnectionPool")
    def test_open_starts_the_pool_once(self, pool_type: MagicMock) -> None:
        database = PostgresDatabase(self.settings)

        database.open()
        database.open()

        pool_type.return_value.open.assert_called_once_with(wait=True, timeout=2.5)

    @patch("ltc.platform.db.postgres.ConnectionPool")
    def test_ping_executes_a_database_probe(self, pool_type: MagicMock) -> None:
        pool = pool_type.return_value
        connection = MagicMock()
        pool.connection.return_value.__enter__.return_value = connection
        database = PostgresDatabase(self.settings)
        database.open()

        database.ping()

        connection.execute.assert_called_once_with("SELECT 1")

    @patch("ltc.platform.db.postgres.ConnectionPool")
    def test_transaction_wraps_application_work_in_one_transaction(self, pool_type: MagicMock) -> None:
        pool = pool_type.return_value
        connection = MagicMock()
        pool.connection.return_value.__enter__.return_value = connection
        database = PostgresDatabase(self.settings)
        database.open()

        with database.transaction() as active_connection:
            self.assertIs(active_connection, connection)

        connection.transaction.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
