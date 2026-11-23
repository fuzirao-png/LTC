"""Exercise the migrated customer-analysis module against a real PostgreSQL DB."""
from __future__ import annotations
import sys
import time
from uuid import UUID
import psycopg
from ltc.modules.customer_analysis.infrastructure import build_local_container

COMPANY_ID = UUID("00000000-0000-0000-0000-000000000701")

def factory():
    return psycopg.connect(host="127.0.0.1", dbname=sys.argv[1], user="postgres", password=sys.argv[2])


def wait_for_completed(service, run_id, timeout_seconds=10):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = service.get_run(run_id)
        if run.status == "completed":
            return run
        if run.status == "failed":
            raise AssertionError(run)
        time.sleep(0.05)
    raise AssertionError(f"analysis run {run_id} did not complete within {timeout_seconds}s")

container = build_local_container(connection_factory=factory, seed_demo_data=False)
context = container.contexts.load_context(COMPANY_ID)
assert context is not None
assert context.company["company_name"] == "Fixture Company 1"
assert context.adopted_icp["total_score"] == 80.0
assert context.meddpicc["metrics"]["status"] == "confirmed"

first = container.service.request_analysis(COMPANY_ID, force_refresh=True, trigger_type="acceptance")
first = wait_for_completed(container.service, first.run_id)
report = container.service.get_current_report(COMPANY_ID)
assert report.analysis_run_id == first.run_id
assert len(report.to_dict()["modules"]) == 5
assert all(len(module["sections"]) == 3 for module in report.to_dict()["modules"])

restarted = build_local_container(connection_factory=factory, seed_demo_data=False)
restored_run = restarted.service.get_run(first.run_id)
restored_report = restarted.service.get_report(report.report_id)
assert restored_run.status == "completed"
assert restored_report.input_hash == restored_run.input_hash
assert restarted.service.get_current_report(COMPANY_ID).report_id == report.report_id
assert len(restarted.service.get_meddpicc(COMPANY_ID)) == 8
suggestions = restarted.service.list_suggestions(COMPANY_ID)
assert suggestions
reviewed = restarted.service.review_suggestion(
    suggestions[0].suggestion_id, accept=False, expected_version=0
)
assert reviewed.status == "rejected"
restarted_again = build_local_container(connection_factory=factory, seed_demo_data=False)
assert restarted_again.repository.get_suggestion(reviewed.suggestion_id).status == "rejected"

new_company_id = UUID("00000000-0000-0000-0000-00000000ca01")
new_context = context.__class__(
    company_id=new_company_id,
    company={"company_name": "Migrated Event Customer", "client_id": "event-customer", "industry": "TMC", "country": "US", "region": "NA", "region_code": "NA"},
    sales_lead={"stage": "new"},
    adopted_icp={"total_score": 76, "dimension_scores": {"industry": 80}},
    adopted_scale={"score": 65, "scale_code": "medium"},
    contacts=({"contact_id": "event-buyer", "name": "Event Buyer", "title": "VP"},),
    profile={"company_type": "TMC", "business_model": "B2B"},
)
restarted.contexts.put_context(new_context)
event_run = restarted.service.request_analysis(new_company_id, force_refresh=True)
event_run = wait_for_completed(restarted.service, event_run.run_id)
event_restart = build_local_container(connection_factory=factory, seed_demo_data=False)
assert event_restart.service.get_current_report(new_company_id).analysis_run_id == event_run.run_id
event_restart.service.upsert_context(new_company_id, {"communication": {"summary": "Pricing requested", "intent_level": "pricing"}}, reason="communication_update")
rescored = event_restart.service.score_company(new_company_id, change_reason="communication_update")
event_restart_again = build_local_container(connection_factory=factory, seed_demo_data=False)
persisted_event_context = event_restart_again.contexts.load_context(new_company_id)
assert persisted_event_context.engagement["latest_summary"] == "Pricing requested"
assert persisted_event_context.company["client_id"] == "event-customer"
assert event_restart_again.service.find_context_id("event-customer") == new_company_id
assert persisted_event_context.contacts[0]["name"] == "Event Buyer"
assert persisted_event_context.adopted_icp["total_score"] == rescored["total_score"]
second = restarted.service.request_analysis(COMPANY_ID, force_refresh=True, trigger_type="acceptance")
second = wait_for_completed(restarted.service, second.run_id)
assert second.run_id != first.run_id
assert restarted.service.get_current_report(COMPANY_ID).version_no == report.version_no + 1
print("customer-analysis application persistence flow passed")
