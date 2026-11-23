# Customer Operation Email Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure TOP5 customer-operation contacts always carry a usable email from lead collection through roster display.

**Architecture:** Keep the fix in the backend roster pipeline. Reuse the existing promoted `ltc.contact` fields first, and only fall back to `ltc.candidate_contact` when contact rows are missing email data. Add regression tests around both the roster service and the resulting public payload so the frontend receives the email without changing its rendering logic.

**Tech Stack:** Python, FastAPI, PostgreSQL, `unittest`.

---

### Task 1: Add roster email regression test

**Files:**
- Modify: `apps/api/tests/test_contact_roster_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_public_row_keeps_contact_email_fields():
    row = {
        "contact_id": "c1",
        "company_id": "co1",
        "full_name": "Global Marketing Contact",
        "title": "Director",
        "title_normalized": "director",
        "department": "Marketing",
        "relationship_role": "decision_maker",
        "primary_email": None,
        "normalized_email": None,
        "email_status": "unknown",
        "last_verified_at": None,
    }

    public = ContactRosterService._public_row(row)

    assert public["primary_email"] is None
    assert public["email_status"] == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_roster_service -v`
Expected: FAIL once the new fallback behavior is introduced and the existing assumptions no longer hold.

- [ ] **Step 3: Write minimal implementation**

No code yet in this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_roster_service -v`
Expected: PASS.

### Task 2: Fill roster email from promoted or candidate data

**Files:**
- Modify: `apps/api/src/ltc/modules/sales_crm/application/contact_roster_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_roster_fills_primary_email_from_source_candidate():
    roster = service.get_roster(COMPANY_ID)

    assert roster["active"][0]["primary_email"] == "global.marketing@51tgt.com"
    assert roster["active"][0]["email_status"] == "valid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_roster_service -v`
Expected: the roster row still returns no usable email until the backend fallback is implemented.

- [ ] **Step 3: Write minimal implementation**

Use `COALESCE(ct.primary_email, cc.email)` and matching normalized/status fallbacks in the roster query, then keep `_public_row()` exposing the same keys.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_contact_roster_service -v`
Expected: PASS.

### Task 3: Verify frontend still reads the same payload

**Files:**
- Test: `apps/web/tests/customerOperationPresentation.test.mjs`

- [ ] **Step 1: Keep the existing frontend email selection test green**
- [ ] **Step 2: Run the focused frontend test**

Run: `cd apps/web && node --test tests/customerOperationPresentation.test.mjs`
Expected: PASS without changing the UI logic.
