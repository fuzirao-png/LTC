# Contact TOP5 Email Eligibility and Score Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require every TOP5 contact to have an email address and display customer-operation contacts with pinned entries first and remaining entries ordered by score.

**Architecture:** Keep eligibility enforcement in the backend domain scorer so automatic calculation and manual activation share one rule. Extract frontend ordering into a small pure JavaScript module so the large Vue component only consumes deterministic sorted arrays and the ordering can be tested with Node's built-in test runner.

**Tech Stack:** Python 3.12, stdlib `unittest`, Vue 3, JavaScript ES modules, Node built-in `node:test`, TypeScript declarations.

---

### Task 1: Enforce Email Eligibility in Domain Scoring

**Files:**
- Modify: `apps/api/tests/test_contact_priority.py`
- Modify: `apps/api/src/ltc/modules/sales_crm/domain/contact_priority.py`

- [ ] **Step 1: Write failing domain tests**

Add tests proving empty and whitespace-only `primary_email` values are ineligible and that a high-scoring contact without email cannot consume a TOP5 role slot:

```python
def test_contact_without_email_is_ineligible(self) -> None:
    result = score_contact(
        _contact("no-email", "Head of Procurement", primary_email=""),
        now=NOW,
    )
    self.assertFalse(result.eligible)
    self.assertEqual("联系人缺少邮箱", result.blocked_reason)


def test_contact_with_whitespace_email_is_ineligible(self) -> None:
    result = score_contact(
        _contact("blank-email", "VP Commercial", primary_email="   "),
        now=NOW,
    )
    self.assertFalse(result.eligible)
    self.assertEqual("联系人缺少邮箱", result.blocked_reason)


def test_contact_without_email_does_not_consume_top_five_slot(self) -> None:
    contacts = [
        _contact("no-email", "Head of Procurement", primary_email=""),
        _contact("commercial", "VP Commercial"),
    ]
    selected = select_top_contacts(score_contact(item, now=NOW) for item in contacts)
    self.assertEqual(["commercial"], [item.contact["contact_id"] for item in selected])
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd apps/api
$env:PYTHONPATH='src'
python -m unittest tests.test_contact_priority -v
```

Expected: the new tests fail because contacts without email are currently eligible.

- [ ] **Step 3: Implement the email hard filter**

Update `_blocked_reason` so the normalized email is checked before status-specific rules:

```python
def _blocked_reason(contact: dict[str, Any], email_status: str) -> str | None:
    if not _text(contact.get("primary_email") or contact.get("email")):
        return "联系人缺少邮箱"
    # existing status, employment, legal basis, suppression and email-status checks
```

- [ ] **Step 4: Run domain tests and verify GREEN**

Run the same command and expect all `test_contact_priority` tests to pass.

### Task 2: Cover Manual Activation Guard

**Files:**
- Modify: `apps/api/tests/test_contact_roster_service.py`

- [ ] **Step 1: Write a failing activation regression test**

Add a test calling `_activate` with `blocked_reason="联系人缺少邮箱"` and assert `ContactRosterError` contains that message. This confirms manual activation uses the same eligibility result.

- [ ] **Step 2: Run the targeted test**

Run:

```powershell
cd apps/api
$env:PYTHONPATH='src'
python -m unittest tests.test_contact_roster_service.ContactRosterServiceTests.test_contact_without_email_cannot_be_activated -v
```

Expected: PASS with existing `_activate` behavior after Task 1 supplies the blocked reason. No production service change is expected unless the test reveals a gap.

### Task 3: Extract and Test Frontend Roster Ordering

**Files:**
- Create: `apps/web/src/features/customer-operation/contactRosterOrdering.js`
- Create: `apps/web/src/features/customer-operation/contactRosterOrdering.d.ts`
- Create: `apps/web/src/features/customer-operation/contactRosterOrdering.test.js`
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] **Step 1: Write failing Node ordering tests**

Create tests for:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { sortActiveRosterContacts, sortBackupRosterContacts } from './contactRosterOrdering.js';

test('active roster puts pinned contacts first then sorts by score', () => {
  const result = sortActiveRosterContacts([
    { contact_id: 'high', full_name: 'High', priority_score: 95, position: 1, is_pinned: false },
    { contact_id: 'pinned', full_name: 'Pinned', priority_score: 20, position: 3, is_pinned: true },
    { contact_id: 'mid', full_name: 'Mid', priority_score: 80, position: 2, is_pinned: false },
  ]);
  assert.deepEqual(result.map((item) => item.contact_id), ['pinned', 'high', 'mid']);
});

test('active roster uses position when scores tie', () => {
  const result = sortActiveRosterContacts([
    { contact_id: 'second', full_name: 'Second', priority_score: 80, position: 2 },
    { contact_id: 'first', full_name: 'First', priority_score: 80, position: 1 },
  ]);
  assert.deepEqual(result.map((item) => item.contact_id), ['first', 'second']);
});

test('backup roster sorts by score then name', () => {
  const result = sortBackupRosterContacts([
    { contact_id: 'b', full_name: 'Beta', priority_score: 70 },
    { contact_id: 'a', full_name: 'Alpha', priority_score: 70 },
    { contact_id: 'top', full_name: 'Top', priority_score: 90 },
  ]);
  assert.deepEqual(result.map((item) => item.contact_id), ['top', 'a', 'b']);
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
node --test apps/web/src/features/customer-operation/contactRosterOrdering.test.js
```

Expected: FAIL because the ordering module does not exist.

- [ ] **Step 3: Implement pure ordering helpers**

Implement non-mutating sort functions using pinned state, numeric score, numeric position and `localeCompare` on `full_name`. Add matching `.d.ts` declarations using `ContactRosterItem` as an imported type.

- [ ] **Step 4: Run Node tests and verify GREEN**

Run the same `node --test` command and expect all three tests to pass.

- [ ] **Step 5: Wire sorted arrays into Vue**

Import the helpers and replace the current computed values:

```typescript
const activeRosterContacts = computed(() => sortActiveRosterContacts(contactRoster.value?.active || []));
const backupRosterContacts = computed(() => sortBackupRosterContacts(contactRoster.value?.backup || []));
```

Keep move mutations based on persisted `position`; do not remove the existing buttons.

### Task 4: Validate Backend and Frontend

**Files:**
- Verify all files modified in Tasks 1-3.

- [ ] **Step 1: Run targeted backend suites**

```powershell
cd apps/api
$env:PYTHONPATH='src'
python -m unittest tests.test_contact_priority tests.test_contact_roster_service -v
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend ordering tests**

```powershell
node --test apps/web/src/features/customer-operation/contactRosterOrdering.test.js
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend typecheck and production build**

```powershell
cd apps/web
npm run typecheck
npm run build
```

Expected: both commands exit with code 0.

- [ ] **Step 4: Review the final diff**

Confirm the diff contains only the eligibility rule, regression tests, ordering helper, Vue wiring, design document and this plan. Do not commit unless explicitly requested.
