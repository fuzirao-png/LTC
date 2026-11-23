from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from ltc.main import create_app
from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.sales_crm.application.lead_service import LeadCommandResult, SalesLeadClaimConflict


class FakeDatabase:
    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def ping(self) -> None:
        pass


class FakeTimelineCursor:
    def __init__(self) -> None:
        self._query_count = 0

    def __enter__(self) -> "FakeTimelineCursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: str, params: object) -> None:
        self._query_count += 1
        if self._query_count == 2:
            if "::text AS event_id" in query and "%s::uuid" in query:
                raise RuntimeError("operator does not exist: text < uuid")

    def fetchall(self) -> list[tuple[UUID]]:
        if self._query_count == 1:
            return [(uuid4(),)]
        return []


class FakeTimelineConnection:
    def __init__(self, cursor: FakeTimelineCursor) -> None:
        self._cursor = cursor

    def cursor(self, **kwargs: object) -> FakeTimelineCursor:
        return self._cursor


class FakeTimelineTransaction:
    def __init__(self, connection: FakeTimelineConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeTimelineConnection:
        return self._connection

    def __exit__(self, *args: object) -> None:
        pass


class FakeTimelineDatabase(FakeDatabase):
    def __init__(self) -> None:
        cursor = FakeTimelineCursor()
        self._connection = FakeTimelineConnection(cursor)

    def transaction(self) -> FakeTimelineTransaction:
        return FakeTimelineTransaction(self._connection)


class FakeLeadService:
    def __init__(self) -> None:
        self.called: list[str] = []

    @staticmethod
    def _row() -> dict[str, object]:
        now = datetime.now(timezone.utc)
        return {
            "lead_id": uuid4(),
            "company_id": uuid4(),
            "company_name": "API Fixture Company",
            "website": "https://fixture.example",
            "company_intro": "Fixture profile",
            "industry_code": "TMC",
            "country_code": "JP",
            "city": "Tokyo",
            "required_sales_tier": "MA",
            "pool_region_code": "EA",
            "allocation_status": "claimable",
            "pipeline_stage": "new",
            "sla_due_at": None,
            "current_owner_user_id": None,
            "owner_name": None,
            "owner_username": None,
            "icp_score": 100,
            "icp_grade": "A",
            "customer_size_grade": "A",
            "last_activity_at": None,
            "updated_at": now,
            "version": 2,
        }

    def list_all(self, *args: object) -> list[dict[str, object]]:
        self.called.append("list_all")
        return [self._row()]

    def list_mine(self, *args: object) -> list[dict[str, object]]:
        self.called.append("list_mine")
        return [self._row()]

    def get_detail(self, *args: object) -> dict[str, object]:
        self.called.append("get_detail")
        row = self._row()
        row.update({
            "current_assignment_started_at": None,
            "first_touch_at": None,
            "assignment_id": None,
            "assignee_user_id": None,
            "assigned_at": None,
            "assignment_type": None,
            "assignment_status": None,
        })
        return row

    @staticmethod
    def _command() -> LeadCommandResult:
        return LeadCommandResult(uuid4(), "claimed", uuid4(), None, uuid4(), None, datetime.now(timezone.utc), None, "new", 3)

    def claim(self, *args: object) -> LeadCommandResult:
        self.called.append("claim")
        return self._command()

    def assign(self, actor: CurrentActor, *args: object) -> LeadCommandResult:
        self.called.append("assign")
        if actor.account_type != "strategic":
            raise AuthenticationError("FORBIDDEN_STRATEGIC_REQUIRED")
        return self._command()

    def release(self, *args: object) -> LeadCommandResult:
        self.called.append("release")
        result = self._command()
        return LeadCommandResult(result.lead_id, "claimable", None, result.assignment_id, None, result.owner_user_id, None, None, result.pipeline_stage, result.version)

    def transfer(self, *args: object) -> LeadCommandResult:
        self.called.append("transfer")
        return self._command()

    def batch_transfer(self, *args: object) -> dict[str, list[dict[str, object]]]:
        self.called.append("batch_transfer")
        return {"succeeded": [{"lead_id": str(uuid4())}], "failed": []}

    def get_adopted_icp(self, *args: object) -> dict[str, object]:
        self.called.append("get_adopted_icp")
        return {"icp_assessment_id": uuid4(), "total_score": 75, "grade": "B"}

    def get_adopted_scale(self, *args: object) -> dict[str, object]:
        self.called.append("get_adopted_scale")
        return {"scale_assessment_id": uuid4(), "effective_tier": "large"}

    def first_touch(self, *args: object) -> dict[str, object]:
        self.called.append("first_touch")
        return {"lead_id": uuid4(), "transition_id": uuid4(), "contact_id": uuid4(), "first_touch_at": datetime.now(timezone.utc), "pipeline_stage": "contacted", "version": 3}

    def change_stage(self, *args: object) -> dict[str, object]:
        self.called.append("change_stage")
        return {"lead_id": uuid4(), "transition_id": uuid4(), "from_stage": "new", "to_stage": "meeting", "occurred_at": datetime.now(timezone.utc), "version": 3}


class FakeCompanyContactService:
    def get_company(self, *args: object) -> dict[str, object]:
        return {"company_id": uuid4(), "company_name": "API Fixture Company", "version": 2}

    def update_company(self, *args: object) -> dict[str, object]:
        return {"company_id": uuid4(), "company_name": "Updated", "version": 3}

    def list_contacts(self, *args: object) -> list[dict[str, object]]:
        return []

    def create_contact(self, *args: object) -> dict[str, object]:
        return {"contact_id": uuid4(), "full_name": "New Contact", "version": 1}

    def update_contact(self, *args: object) -> dict[str, object]:
        return {"contact_id": uuid4(), "full_name": "Updated Contact", "version": 3}


def actor(account_type: str = "strategic") -> CurrentActor:
    return CurrentActor(uuid4(), "api.actor", "API Actor", account_type, "MA" if account_type == "sales" else None, "EA" if account_type == "sales" else None, 10 if account_type == "sales" else None, 1, (), "active", 0, 2)


class SalesCrmApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(database=FakeDatabase())
        self.leads = FakeLeadService()
        self.app.state.sales_lead_service = self.leads
        self.app.state.sales_company_contact_service = FakeCompanyContactService()
        self.app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor(), uuid4())
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_queries_and_commands_use_api_contract(self) -> None:
        lead_id = uuid4()
        company_id = uuid4()
        contact_id = uuid4()
        headers = {"Idempotency-Key": "api-test-1", "If-Match": "2"}

        for path in (f"/api/v1/sales-leads", f"/api/v1/sales-leads/mine", f"/api/v1/sales-leads/{lead_id}", f"/api/v1/sales-leads/{lead_id}/adopted-icp", f"/api/v1/sales-leads/{lead_id}/adopted-scale"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("request_id", response.json())
            self.assertIn("data", response.json())

        list_item = self.client.get("/api/v1/sales-leads/mine").json()["data"][0]
        self.assertEqual(list_item["industry_code"], "TMC")
        self.assertEqual(list_item["city"], "Tokyo")
        self.assertEqual(list_item["icp_score"], 100)
        self.assertEqual(list_item["icp_grade"], "A")
        self.assertEqual(list_item["customer_size_grade"], "A")

        command_cases = [
            (f"/api/v1/sales-leads/{lead_id}:claim", {}, headers),
            (f"/api/v1/sales-leads/{lead_id}:assign", {"assignee_user_id": str(uuid4()), "reason_code": "api_test"}, headers),
            (f"/api/v1/sales-leads/{lead_id}:release", {"reason_code": "api_test"}, headers),
            (f"/api/v1/sales-leads/{lead_id}:transfer", {"to_assignee_user_id": str(uuid4()), "reason_code": "api_test"}, headers),
            (f"/api/v1/sales-leads/{lead_id}:first-touch", {"contact_id": str(contact_id), "channel": "email", "occurred_at": "2026-07-23T00:00:00Z"}, headers),
            (f"/api/v1/sales-leads/{lead_id}:change-stage", {"target_stage": "meeting", "reason_code": "api_test"}, headers),
        ]
        for path, body, request_headers in command_cases:
            response = self.client.post(path, json=body, headers=request_headers)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("request_id", response.json())
            self.assertIn("data", response.json())

        batch = {"items": [{"lead_id": str(lead_id), "expected_version": 2, "to_assignee_user_id": str(uuid4()), "reason_code": "api_test"}]}
        response = self.client.post("/api/v1/sales-leads:batch-transfer", json=batch, headers={"Idempotency-Key": "batch-api-test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()["data"]), {"succeeded", "failed"})

        self.assertIn("assign", self.leads.called)
        self.assertIn("transfer", self.leads.called)
        self.assertIn("first_touch", self.leads.called)

    def test_sales_actor_cannot_use_strategic_assign(self) -> None:
        self.app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor("sales"), uuid4())
        response = self.client.post(
            f"/api/v1/sales-leads/{uuid4()}:assign",
            json={"assignee_user_id": str(uuid4()), "reason_code": "api_test"},
            headers={"Idempotency-Key": "forbidden", "If-Match": "2"},
        )
        self.assertEqual(response.status_code, 403)

    def test_claim_conflict_identifies_current_owner(self) -> None:
        owner_id = uuid4()

        def conflict(*args: object) -> LeadCommandResult:
            raise SalesLeadClaimConflict(owner_id, "李明")

        self.leads.claim = conflict  # type: ignore[method-assign]
        self.app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor("sales"), uuid4())
        response = self.client.post(
            f"/api/v1/sales-leads/{uuid4()}:claim",
            headers={"Idempotency-Key": "claim-conflict", "If-Match": "2"},
        )

        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "SALES_LEAD_NOT_CLAIMABLE")
        self.assertEqual(detail["message"], "该线索已由李明领取")
        self.assertEqual(detail["current_owner_user_id"], str(owner_id))
        self.assertEqual(detail["current_owner_name"], "李明")

    def test_company_timeline_uses_uuid_event_ids_for_cursor_comparison(self) -> None:
        app = create_app(database=FakeTimelineDatabase())
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor(), uuid4())
        client = TestClient(app)
        try:
            response = client.get(f"/api/v1/companies/{uuid4()}/timeline")
        finally:
            client.close()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], [])

if __name__ == "__main__":
    unittest.main()
