from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ltc.modules.iam.application.account_service import AccountManagementService
from ltc.modules.iam.application.auth_service import AuthenticationError
from ltc.modules.iam.domain.models import CurrentActor
from ltc.modules.iam.interfaces.router import AuthContext, get_auth_context
from ltc.modules.sales_crm.application.lead_service import (
    LeadCommandResult,
    SalesLeadService,
    TransferLeadCommand,
)
from ltc.modules.sales_crm.interfaces.router import router


def strategic_actor() -> CurrentActor:
    return CurrentActor(
        user_id=uuid4(),
        username="admin",
        display_name="Administrator",
        account_type="strategic",
        sales_tier=None,
        region_code=None,
        capacity_limit=None,
        token_version=1,
        capabilities=("sales_lead.assign",),
    )


def sales_actor() -> CurrentActor:
    return CurrentActor(
        user_id=uuid4(),
        username="sales.ea",
        display_name="Sales",
        account_type="sales",
        sales_tier="MA",
        region_code="EA",
        capacity_limit=10,
        token_version=1,
        capabilities=("sales_lead.transfer",),
    )


class FakeCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.statements.append((sql, params))

    def fetchone(self) -> dict[str, object]:
        return self.row


class FakeConnection:
    def __init__(self, assignment: dict[str, object]) -> None:
        self.cursor_instance = FakeCursor(assignment)
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self, **_: object) -> FakeCursor:
        return self.cursor_instance

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((sql, params))


class FakeDatabase:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    @contextmanager
    def transaction(self):
        yield self.connection


class FakeReturnPoolCursor:
    def __init__(self, departed_user_id: UUID, assignments: list[dict[str, object]]) -> None:
        self.departed_user_id = departed_user_id
        self.assignments = assignments
        self.last_sql = ""
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "FakeReturnPoolCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.last_sql = sql
        self.statements.append((sql, params))

    def fetchone(self) -> dict[str, object] | None:
        if "FROM ltc.user_account" in self.last_sql:
            return {"user_id": self.departed_user_id, "display_name": "Departed", "status": "departed"}
        return None

    def fetchall(self) -> list[dict[str, object]]:
        if "FROM ltc.lead_assignment" not in self.last_sql:
            return []
        if "sl.pipeline_stage='new'" in self.last_sql:
            return [row for row in self.assignments if row["pipeline_stage"] == "new"]
        return list(self.assignments)

    def close(self) -> None:
        return None


class FakeReturnPoolConnection:
    def __init__(self, departed_user_id: UUID, assignments: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeReturnPoolCursor(departed_user_id, assignments)

    def cursor(self, **_: object) -> FakeReturnPoolCursor:
        return self.cursor_instance


class FakeUserRepository:
    def __init__(self) -> None:
        self.filters: tuple[object, ...] | None = None

    def list_user_summaries(self, *filters: object) -> list[dict[str, object]]:
        self.filters = filters
        return []


class FakeIamUnitOfWork:
    def __init__(self, repository: FakeUserRepository) -> None:
        self.repository = repository

    @contextmanager
    def transaction(self):
        yield self.repository


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return password


class FakeHandoverService:
    def __init__(self, result: LeadCommandResult | None = None, error: str | None = None) -> None:
        self.result = result
        self.error = error
        self.command: TransferLeadCommand | None = None

    def assign_handover(self, actor: CurrentActor, command: TransferLeadCommand) -> LeadCommandResult:
        self.command = command
        if self.error:
            raise AuthenticationError(self.error)
        assert actor.account_type == "strategic"
        assert self.result is not None
        return self.result


class FakeHandoverListService:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def list_handover(self, actor: CurrentActor) -> list[dict[str, object]]:
        assert actor.account_type == "strategic"
        return self.rows


class HandoverRouteTests(unittest.TestCase):
    def _client(self, service: object) -> TestClient:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.state.sales_lead_service = service
        actor = strategic_actor()
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(actor, uuid4())
        return TestClient(app)

    def test_handover_list_exposes_customer_grade_sales_tier_region_and_country(self) -> None:
        service = FakeHandoverListService([{
            "lead_id": uuid4(),
            "company_id": uuid4(),
            "company_name": "Example Customer",
            "departed_user_id": uuid4(),
            "departed_user_name": "Departed Sales",
            "sales_tier": "SA",
            "region_code": "EA",
            "required_sales_tier": "MA",
            "customer_grade": "A",
            "customer_region_code": "EA",
            "country_code": "JP",
            "country_name": "日本",
            "pipeline_stage": "new",
            "allocation_status": "claimed",
            "version": 3,
        }])

        response = self._client(service).get("/api/v1/sales-leads/handover")

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"][0]
        self.assertEqual(item["required_sales_tier"], "MA")
        self.assertEqual(item["customer_grade"], "A")
        self.assertEqual(item["customer_region_code"], "EA")
        self.assertEqual(item["country_code"], "JP")
        self.assertEqual(item["country_name"], "日本")

    def test_handover_assign_builds_scoped_transfer_command(self) -> None:
        lead_id = uuid4()
        target_id = uuid4()
        result = LeadCommandResult(
            lead_id=lead_id,
            allocation_status="claimed",
            assignment_id=uuid4(),
            previous_assignment_id=uuid4(),
            owner_user_id=target_id,
            from_owner_user_id=uuid4(),
            assigned_at=None,
            sla_due_at=None,
            pipeline_stage="engaged",
            version=8,
        )
        service = FakeHandoverService(result=result)

        response = self._client(service).post(
            f"/api/v1/sales-leads/{lead_id}:handover-assign",
            json={"to_assignee_user_id": str(target_id), "reason_text": "departure handover"},
            headers={"Idempotency-Key": "handover-1", "If-Match": '"7"'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["owner_user_id"], str(target_id))
        assert service.command is not None
        self.assertEqual(service.command.reason_code, "handover_assign")
        self.assertEqual(service.command.expected_version, 7)
        self.assertEqual(service.command.to_assignee_user_id, target_id)

    def test_handover_assign_maps_non_pending_state_to_conflict(self) -> None:
        service = FakeHandoverService(error="HANDOVER_LEAD_NOT_PENDING")

        response = self._client(service).post(
            f"/api/v1/sales-leads/{uuid4()}:handover-assign",
            json={"to_assignee_user_id": str(uuid4())},
            headers={"Idempotency-Key": "handover-2", "If-Match": "1"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "HANDOVER_LEAD_NOT_PENDING")


class HandoverServiceTests(unittest.TestCase):
    def _command(self, lead_id: UUID, target_id: UUID) -> TransferLeadCommand:
        return TransferLeadCommand(
            lead_id=lead_id,
            expected_version=3,
            to_assignee_user_id=target_id,
            reason_code="handover_assign",
            reason_text=None,
            idempotency_key="handover-service",
            request_id=str(uuid4()),
        )

    def _service(self, pending: bool, source_status: str = "departed") -> tuple[SalesLeadService, FakeConnection, UUID, UUID, UUID]:
        lead_id = uuid4()
        source_id = uuid4()
        target_id = uuid4()
        previous_id = uuid4()
        connection = FakeConnection({
            "assignment_id": previous_id,
            "assignee_user_id": source_id,
            "handover_pending": pending,
        })
        service = SalesLeadService(FakeDatabase(connection))  # type: ignore[arg-type]
        lead = {
            "lead_id": lead_id,
            "company_id": uuid4(),
            "current_owner_user_id": source_id,
            "allocation_status": "claimed",
            "version": 3,
            "first_touch_at": None,
            "pipeline_stage": "engaged",
        }

        def lock_user(_: object, user_id: UUID) -> dict[str, object]:
            if user_id == source_id:
                return {"user_id": source_id, "status": source_status}
            return {"user_id": target_id, "status": "active"}

        patch.object(service, "_read_idempotency", return_value=None).start()
        patch.object(service, "_create_idempotency").start()
        patch.object(service, "_read_lead_owner", return_value=source_id).start()
        patch.object(service, "_lock_user", side_effect=lock_user).start()
        patch.object(service, "_lock_lead", return_value=lead).start()
        patch.object(service, "_check_eligibility").start()
        patch.object(service, "_check_capacity").start()
        patch.object(service, "_insert_assignment", return_value=uuid4()).start()
        patch.object(service, "_append_transition_and_event").start()
        patch.object(service, "_complete_idempotency").start()
        self.addCleanup(patch.stopall)
        return service, connection, lead_id, source_id, target_id

    def test_assign_handover_rejects_non_pending_assignment(self) -> None:
        service, _, lead_id, _, target_id = self._service(pending=False)

        with self.assertRaisesRegex(AuthenticationError, "HANDOVER_LEAD_NOT_PENDING"):
            service.assign_handover(strategic_actor(), self._command(lead_id, target_id))

    def test_assign_handover_rejects_assignment_not_owned_by_departed_sales(self) -> None:
        service, _, lead_id, _, target_id = self._service(pending=True, source_status="active")

        with self.assertRaisesRegex(AuthenticationError, "HANDOVER_LEAD_NOT_PENDING"):
            service.assign_handover(strategic_actor(), self._command(lead_id, target_id))

    def test_assign_handover_closes_pending_assignment_before_reassignment(self) -> None:
        service, connection, lead_id, _, target_id = self._service(pending=True)

        result = service.assign_handover(strategic_actor(), self._command(lead_id, target_id))

        self.assertEqual(result.owner_user_id, target_id)
        assignment_updates = [sql for sql, _ in connection.executed if "UPDATE ltc.lead_assignment" in sql]
        self.assertEqual(len(assignment_updates), 1)
        self.assertIn("handover_pending=false", assignment_updates[0])

    def test_assign_handover_requires_strategic_actor(self) -> None:
        service, _, lead_id, _, target_id = self._service(pending=True)

        with self.assertRaisesRegex(AuthenticationError, "FORBIDDEN_STRATEGIC_REQUIRED"):
            service.assign_handover(sales_actor(), self._command(lead_id, target_id))

    def test_return_to_pool_only_releases_new_stage_handover_leads(self) -> None:
        departed_user_id = uuid4()
        new_lead_id = uuid4()
        engaged_lead_id = uuid4()
        assignments = [
            {
                "assignment_id": uuid4(), "lead_id": new_lead_id, "company_id": uuid4(),
                "company_name": "Pool Customer", "pipeline_stage": "new", "version": 2,
                "current_owner_user_id": departed_user_id,
            },
            {
                "assignment_id": uuid4(), "lead_id": engaged_lead_id, "company_id": uuid4(),
                "company_name": "Engaged Customer", "pipeline_stage": "engaged", "version": 4,
                "current_owner_user_id": departed_user_id,
            },
        ]
        connection = FakeReturnPoolConnection(departed_user_id, assignments)
        service = SalesLeadService(FakeDatabase(connection))  # type: ignore[arg-type]
        with patch.object(service, "_read_json_idempotency", return_value=None), \
             patch.object(service, "_create_idempotency"), \
             patch.object(service, "_complete_json_idempotency"):
            result = service.return_handover_to_pool(
                strategic_actor(), departed_user_id, "return-new-only", uuid4()
            )

        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["leads"][0]["lead_id"], str(new_lead_id))  # type: ignore[index]
        assignment_query = next(
            sql for sql, _ in connection.cursor_instance.statements
            if "FROM ltc.lead_assignment" in sql
        )
        self.assertIn("sl.pipeline_stage='new'", assignment_query)
        updated_lead_ids = {
            params[-1] for sql, params in connection.cursor_instance.statements
            if "UPDATE ltc.sales_lead" in sql
        }
        self.assertEqual(updated_lead_ids, {new_lead_id})
        self.assertNotIn(engaged_lead_id, updated_lead_ids)


class ActiveSalesSearchTests(unittest.TestCase):
    def test_user_search_forwards_account_status_and_query_filters(self) -> None:
        repository = FakeUserRepository()
        service = AccountManagementService(FakeIamUnitOfWork(repository), FakePasswordHasher())  # type: ignore[arg-type]

        rows = service.list_users(
            strategic_actor(),
            "sales",
            "EA",
            "MA",
            "active",
            "lin",
            None,
            21,
        )

        self.assertEqual(rows, [])
        self.assertEqual(repository.filters, ("sales", "EA", "MA", "active", "lin", None, 21))


if __name__ == "__main__":
    unittest.main()
