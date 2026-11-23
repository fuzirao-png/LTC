from __future__ import annotations

import unittest
from unittest.mock import Mock

from ltc.modules.customer_analysis.infrastructure.postgres_context import (
    PostgresAnalysisContextPort,
)


class CustomerAnalysisIcpOwnershipTests(unittest.TestCase):
    def test_assessments_exposes_persisted_four_dimensions(self) -> None:
        port = PostgresAnalysisContextPort(Mock())
        port._query = Mock(side_effect=[
            (100, "A", "S1", 0.95, 40, 30, 20, 10, {"D1": 40}, {"D1": "最高档"}),
            (80, "large", "large", "MA", {}),
        ])
        lead = [None] * 11
        lead[9] = "icp-assessment"
        lead[10] = "scale-assessment"

        icp, scale = port._assessments(lead)

        self.assertEqual(100.0, icp["total_score"])
        self.assertEqual({"D1": 40.0, "D2": 30.0, "D3": 20.0, "D4": 10.0}, icp["dimension_scores"])
        self.assertEqual({"D1": 40}, icp["score_breakdown"])
        self.assertEqual("large", scale["effective_tier"])


if __name__ == "__main__":
    unittest.main()
