from unittest.mock import MagicMock
from uuid import UUID

from ltc.scripts.seed_helpers import promote_grade_a_large_candidates, upsert_demo_user


DEMO_SALES_USER = (
    "wang.fang",
    "123456",
    "Wang Fang",
    "wangfang@ltc.test",
    "sales",
    "MA",
    "NA",
    10,
)


def test_upsert_demo_user_skips_terminal_departed_account() -> None:
    connection = MagicMock()
    status_result = MagicMock()
    status_result.fetchone.return_value = ("departed",)
    connection.execute.return_value = status_result
    hasher = MagicMock()

    created = upsert_demo_user(connection, hasher, DEMO_SALES_USER)

    assert created is False
    assert connection.execute.call_count == 1
    hasher.hash.assert_not_called()


def test_upsert_demo_user_reactivates_non_terminal_account() -> None:
    connection = MagicMock()
    status_result = MagicMock()
    status_result.fetchone.return_value = ("disabled",)
    connection.execute.side_effect = [status_result, MagicMock()]
    hasher = MagicMock()
    hasher.hash.return_value = "hashed-password"

    created = upsert_demo_user(connection, hasher, DEMO_SALES_USER)

    assert created is True
    assert connection.execute.call_count == 2
    hasher.hash.assert_called_once_with("123456")


def _query_result(*, one=None, many=None) -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = one
    result.fetchall.return_value = many or []
    return result


def _candidate(index: int, company_name: str) -> tuple[object, ...]:
    return (
        UUID(int=index),
        company_name,
        company_name.casefold(),
        f"https://{company_name.casefold().replace(' ', '-')}.test",
        "US",
        "NA",
        "v3.2-seed",
        "New York",
        "OTHER",
        f"{company_name} introduction",
        1000,
        UUID(int=100 + index),
        UUID(int=200 + index),
    )


def test_promote_grade_a_large_candidates_creates_missing_pool_leads() -> None:
    names = [
        "Engine",
        "Navan",
        "FCM Travel Americas",
        "Christopherson Business Travel",
        "Ramp",
    ]
    connection = MagicMock()
    candidates = [_candidate(index, name) for index, name in enumerate(names, start=1)]

    def execute(query: str, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT lc.candidate_id"):
            return _query_result(many=candidates)
        if normalized.startswith("SELECT lead_id, company_id"):
            return _query_result(one=None)
        if normalized.startswith("SELECT company_id FROM ltc.company"):
            return _query_result(one=None)
        if normalized.startswith("SELECT lead_id FROM ltc.sales_lead"):
            return _query_result(one=None)
        return _query_result()

    connection.execute.side_effect = execute

    promoted = promote_grade_a_large_candidates(connection, UUID(int=999))

    assert promoted == names
    executed_queries = [" ".join(call.args[0].split()) for call in connection.execute.call_args_list]
    assert sum(query.startswith("INSERT INTO ltc.company") for query in executed_queries) == 5
    assert sum(query.startswith("INSERT INTO ltc.sales_lead") for query in executed_queries) == 5
    assert sum(query.startswith("UPDATE ltc.lead_candidate") for query in executed_queries) == 5

    lead_calls = [
        call for call in connection.execute.call_args_list
        if "INSERT INTO ltc.sales_lead" in call.args[0]
    ]
    assert all(call.args[1][5:7] == ("NA", "v3.2-seed") for call in lead_calls)


def test_promote_grade_a_large_candidates_reuses_existing_open_lead() -> None:
    candidate = _candidate(1, "TechVentures Inc")
    existing_lead_id = UUID(int=301)
    existing_company_id = UUID(int=302)
    connection = MagicMock()

    def execute(query: str, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT lc.candidate_id"):
            return _query_result(many=[candidate])
        if normalized.startswith("SELECT lead_id, company_id"):
            return _query_result(one=(existing_lead_id, existing_company_id, "MA", "NA", None))
        return _query_result()

    connection.execute.side_effect = execute

    promoted = promote_grade_a_large_candidates(connection, UUID(int=999))

    assert promoted == ["TechVentures Inc"]
    executed_queries = [" ".join(call.args[0].split()) for call in connection.execute.call_args_list]
    assert not any(query.startswith("INSERT INTO ltc.company") for query in executed_queries)
    assert not any(query.startswith("INSERT INTO ltc.sales_lead") for query in executed_queries)
    update_call = next(
        call for call in connection.execute.call_args_list
        if "UPDATE ltc.lead_candidate" in call.args[0]
    )
    assert update_call.args[1][:2] == (existing_company_id, existing_lead_id)
