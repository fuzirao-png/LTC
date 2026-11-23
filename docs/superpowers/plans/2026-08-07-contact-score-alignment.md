# Contact Score Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align customer-operation contact ranking with the PRD so scoring updates from real outreach facts, contact quality matches the documented weights, and customer-analysis refresh hooks stay consistent.

**Architecture:** Keep scoring logic centralized in `apps/api/src/ltc/modules/sales_crm/domain/contact_priority.py`, with database-backed roster persistence still owned by `contact_roster_service.py`. Add the smallest number of refresh hooks needed so email and meeting writes can mark roster entries stale or recompute them, while the frontend continues to display the persisted roster payload.

**Tech Stack:** Python `unittest`, FastAPI routes, PostgreSQL-backed roster table, Vue 3 frontend utilities, existing customer-operation services.

---

### Task 1: Lock in PRD scoring behavior

**Files:**
- Modify: `apps/api/src/ltc/modules/sales_crm/domain/contact_priority.py`
- Test: `apps/api/tests/test_contact_priority.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_verified_email_scores_more_than_unverified_email():
    verified = score_contact(_contact("verified", "BD Manager", email_status="valid"), now=NOW)
    unverified = score_contact(_contact("unverified", "BD Manager", email_status="unknown"), now=NOW)
    assert verified.breakdown["contact_quality"] == 10
    assert verified.score > unverified.score
    assert unverified.breakdown["risk_deduction"] == 15

def test_linkedin_only_contact_gets_prd_quality_score():
    contact = score_contact(_contact("linkedin", "BD Manager", primary_email="", linkedin_url="https://linkedin.com/in/x"), now=NOW)
    assert contact.breakdown["contact_quality"] == 3

def test_scene_relevance_tracks_title_and_department_not_company_keywords():
    contact = score_contact(_contact("cto", "CTO", department="Technology"), now=NOW, scene_text="Travel API esim telecom")
    assert contact.breakdown["scene_relevance"] >= 0
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_priority -v`
Expected: fail on the new assertions because the current scoring model does not distinguish verified email, unverified email, and LinkedIn-only quality the PRD way.

- [ ] **Step 3: Implement the minimal scoring update**

```python
def _contact_quality_points(contact):
    status = _text(contact.get("email_status")).casefold()
    email = _text(contact.get("primary_email") or contact.get("email"))
    linkedin = _text(contact.get("linkedin_url"))
    if status == "valid":
        return 10.0
    if email:
        return 6.0
    if linkedin:
        return 3.0
    return 0.0
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_priority -v`
Expected: pass.

### Task 2: Refresh roster when outreach facts change

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Modify: `apps/api/src/ltc/modules/sales_crm/application/contact_roster_service.py`
- Test: `apps/api/tests/test_customer_operation_repository_isolation.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_outbound_email_marks_roster_dirty_or_refreshes_engagement_score():
    ...
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_customer_operation_repository_isolation -v`
Expected: the new refresh expectation fails because outreach writes do not currently force a roster recompute path.

- [ ] **Step 3: Implement the minimal refresh hook**

```python
connection.execute(
    "UPDATE ltc.company_contact_roster SET updated_at=clock_timestamp() WHERE company_id=%s AND contact_id=%s",
    (company_id, contact_id),
)
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_customer_operation_repository_isolation -v`
Expected: pass.

### Task 3: Tighten frontend fallback ordering

**Files:**
- Modify: `apps/web/src/shared/utils/contactOrdering.js`
- Test: `apps/web/src/shared/utils/contactOrdering.test.js` if needed, or the closest existing frontend unit test file

- [ ] **Step 1: Write the failing tests**

```javascript
test('procurement-commercial-seniority fallback keeps PRD order')
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd apps/web && npm run typecheck && npm run build`
Expected: the new fallback assertion fails until the ranking terms line up with the PRD order.

- [ ] **Step 3: Implement the minimal ordering update**

```javascript
const category = managed && procurementTerms.some((term) => title.includes(term)) ? 0
  : managed && commercialTerms.some((term) => title.includes(term)) ? 1
  : managed ? 2 : 3;
```

- [ ] **Step 4: Run the frontend checks and verify they pass**

Run: `cd apps/web && npm run typecheck && npm run build`
Expected: pass.

### Task 4: Verify the cross-module behavior

**Files:**
- Test: `apps/api/tests/test_contact_priority.py`
- Test: `apps/api/tests/test_customer_operation_auth.py`
- Test: `apps/web/src/features/customer-operation/CustomerOperation.vue` behavior through existing checks

- [ ] **Step 1: Run the focused API tests**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_priority tests.test_customer_operation_repository_isolation -v`

- [ ] **Step 2: Run the frontend validation**

Run: `cd apps/web && npm run typecheck && npm run build`

- [ ] **Step 3: Manually inspect one customer roster**

Open the customer-operation page for a known company and confirm the roster scores are no longer effectively frozen after an outreach-changing event.

