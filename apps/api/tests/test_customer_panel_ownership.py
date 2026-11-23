from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.customer_analysis.domain.models import AnalysisContext
from ltc.modules.customer_analysis.infrastructure.postgres_context import PostgresAnalysisContextPort
from ltc.modules.customer_analysis.interfaces.router import build_customer_analysis_router
from ltc.modules.customer_operation.interfaces.router import build_customer_operation_router
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context


def _sales_actor(user_id: UUID) -> CurrentActor:
    return CurrentActor(
        user_id,
        "sales.user",
        "Sales User",
        "sales",
        "MA",
        "EA",
        10,
        0,
        (),
    )


def _context(company_id: UUID, owner_id: UUID) -> AnalysisContext:
    return AnalysisContext(
        company_id=company_id,
        company={
            "company_id": str(company_id),
            "company_name": str(company_id),
            "country": "KR",
            "region": "EA",
            "time_zone": "Asia/Seoul",
        },
        sales_lead={"owner_id": str(owner_id), "allocation_status": "claimed"},
        adopted_icp={"total_score": 80},
        adopted_scale={},
    )


def test_customer_operation_home_cards_pass_current_sales_owner_to_service() -> None:
    owner_id = uuid4()
    service = Mock()
    service.list_home_cards.return_value = []
    app = FastAPI()
    app.include_router(build_customer_operation_router(service), prefix="/api/v1")

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        _sales_actor(owner_id), uuid4()
    )
    response = TestClient(app).get("/api/v1/internal/customers/home-cards")

    assert response.status_code == 200
    service.list_home_cards.assert_called_once_with(limit=500, owner_user_id=str(owner_id))


def test_customer_analysis_list_only_returns_current_sales_customers() -> None:
    owner_id = uuid4()
    owned_company_id = uuid4()
    service = Mock()
    service.list_contexts.return_value = [
        _context(owned_company_id, owner_id),
    ]
    service.get_profile.return_value.to_dict.return_value = {}
    service.repository.get_current_report.return_value = None
    app = FastAPI()
    app.include_router(build_customer_analysis_router(service), prefix="/api/v1")

    with patch(
        "ltc.modules.customer_analysis.interfaces.router.get_auth_context",
        return_value=AuthContext(_sales_actor(owner_id), uuid4()),
    ):
        response = TestClient(app).get(
            "/api/v1/api/customers/analysis/list",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["client_id"] for item in items] == [str(owned_company_id)]
    assert items[0]["timeZone"] == "Asia/Seoul"
    service.list_contexts.assert_called_once_with(owner_user_id=str(owner_id))


def test_customer_analysis_postgres_query_uses_shared_sales_visibility() -> None:
    owner_id = str(uuid4())
    context_port = PostgresAnalysisContextPort(Mock())
    context_port._query = Mock(return_value=[])

    assert context_port.list_contexts(owner_user_id=owner_id) == []

    query, params = context_port._query.call_args.args
    assert "ltc.customer_operation_owner" in query
    assert "ltc.sales_lead" in query
    assert "sl.allocation_status = 'claimed'" in query
    assert "company_name" in query
    assert "!~*" in query
    assert "primary_domain" in query
    assert params == (owner_id, owner_id)
