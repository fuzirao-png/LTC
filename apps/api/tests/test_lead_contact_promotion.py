from __future__ import annotations

from datetime import datetime, timezone

from ltc.modules.lead_intelligence.infrastructure.promotion_adapter import PostgresPromotionAdapter


class _Cursor:
    def __init__(self, connection: "_Connection", *, mapping: bool) -> None:
        self.connection = connection
        self.mapping = mapping
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.connection.executions.append((query, params))

    def fetchall(self):
        if self.mapping:
            return [{
                "candidate_contact_id": "20000000-0000-4000-8000-000000000001",
                "full_name": "Ada Lovelace",
                "normalized_name": "ada lovelace",
                "relationship_role": "decision_maker",
                "email_status": "valid",
            }]
        return []

    def fetchone(self):
        return None


class _Connection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self, **kwargs: object):
        return _Cursor(self, mapping=bool(kwargs))


def test_promoted_contacts_use_the_contact_table_candidate_source() -> None:
    connection = _Connection()

    PostgresPromotionAdapter._promote_contacts(
        connection,
        "10000000-0000-4000-8000-000000000001",
        "30000000-0000-4000-8000-000000000001",
        datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    insert = next(query for query, _ in connection.executions if "INSERT INTO ltc.contact" in query)
    assert "'candidate','active'" in insert
    assert "candidate_promotion" not in insert
    assert any(
        "source_candidate_contact_id = %s" in query
        for query, _ in connection.executions
        if "SELECT contact_id FROM ltc.contact" in query
    )
