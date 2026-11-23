from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.sales_crm.application.lead_service import SalesLeadService


def connection_with_active_count(count: int) -> MagicMock:
    connection = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = (count,)
    connection.cursor.return_value = cursor
    return connection


class SalesCrmCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SalesLeadService(MagicMock())
        self.user = {"user_id": uuid4(), "capacity_limit": 25}

    def test_rejects_assignment_when_active_count_reaches_capacity(self) -> None:
        with self.assertRaisesRegex(AuthenticationError, "SALES_CAPACITY_EXCEEDED"):
            self.service._check_capacity(connection_with_active_count(25), self.user)

    def test_allows_assignment_immediately_below_capacity(self) -> None:
        self.service._check_capacity(connection_with_active_count(24), self.user)


if __name__ == "__main__":
    unittest.main()
