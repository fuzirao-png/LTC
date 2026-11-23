# Customer Operation Status Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show outbound and inbound email counts below the corresponding customer-operation milestones while removing the misleading signal/category wording from the activity summary.

**Architecture:** Extend the existing home-card PostgreSQL aggregation to return separate outbound and inbound counts alongside the existing milestone dates. Normalize these fields in the Vue customer card and compose the displayed milestone detail as `date · count`, while deriving the email/meeting summary only from numeric payload fields.

**Tech Stack:** Python 3.12, FastAPI, pg8000/PostgreSQL, Vue 3, TypeScript, Vite

---

### Task 1: Add Failing Home-Card Count Assertions

**Files:**
- Modify: `apps/api/tests/test_customer_operation_real_routes.py:103`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] **Step 1: Extend the existing home-card route test**

Add assertions proving the seeded customer has one outbound email, one inbound email, and a numeric-only activity summary:

```python
assert item["outboundEmailCount"] == 1
assert item["inboundEmailCount"] == 1
assert item["payload"]["outbound_email_count"] == 1
assert item["payload"]["inbound_email_count"] == 1
assert item["signal"] == "2封邮件 · 1场会议"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
pytest apps/api/tests/test_customer_operation_real_routes.py::test_customer_operation_home_cards_include_stage_dates_and_tags -q
```

Expected: FAIL because `outboundEmailCount` and `inboundEmailCount` are not returned and `signal` still contains the category wording.

### Task 2: Return Directional Email Counts

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_customer_home_card_store.py:95`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] **Step 1: Extend the email aggregation query**

Change the per-company email query to return total, outbound, inbound, first outbound date, and first inbound date:

```sql
SELECT
    count(*)::int,
    count(*) FILTER (WHERE direction = 'outbound')::int,
    count(*) FILTER (WHERE direction = 'inbound')::int,
    min(COALESCE(sent_at, created_at)) FILTER (WHERE direction = 'outbound'),
    min(COALESCE(received_at, replied_at, created_at)) FILTER (WHERE direction = 'inbound')
FROM ltc.email_message
WHERE company_id = %s
```

Unpack the row as:

```python
email_count, outbound_email_count, inbound_email_count, emailed_at, replied_at = cur.fetchone()
```

- [ ] **Step 2: Add counts and clean summary to the response**

Add top-level response fields:

```python
"outboundEmailCount": int(outbound_email_count or 0),
"inboundEmailCount": int(inbound_email_count or 0),
```

Add payload compatibility fields:

```python
"outbound_email_count": int(outbound_email_count or 0),
"inbound_email_count": int(inbound_email_count or 0),
```

Replace the summary with:

```python
"signal": f"{int(email_count or 0)}封邮件 · {int(meeting_count or 0)}场会议",
```

- [ ] **Step 3: Run the focused test and verify GREEN**

Run:

```powershell
pytest apps/api/tests/test_customer_operation_real_routes.py::test_customer_operation_home_cards_include_stage_dates_and_tags -q
```

Expected: PASS.

### Task 3: Compose Milestone Date and Count

**Files:**
- Modify: `apps/web/src/services/operationApi.ts:3`
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue:10`

- [ ] **Step 1: Extend the API type**

Add optional fields to `OperationCustomer`:

```typescript
outboundEmailCount?: number;
inboundEmailCount?: number;
```

- [ ] **Step 2: Add a count-aware milestone formatter**

Add the helper next to `formatDateLabel`:

```typescript
const formatDateCountLabel = (value: string | null | undefined, count: number) => {
  const dateLabel = formatDateLabel(value);
  if (dateLabel === '—' || count <= 0) return dateLabel;
  return `${dateLabel} · ${count}封`;
};
```

Update `stageDatesToTimeline` to accept both counts and use this helper only for the emailed and replied milestones:

```typescript
const stageDatesToTimeline = (
  stageDates: OperationCustomer['stageDates'] | undefined,
  outboundEmailCount: number,
  inboundEmailCount: number,
) => [
  formatDateLabel(stageDates?.acquiredAt),
  formatDateCountLabel(stageDates?.emailedAt, outboundEmailCount),
  formatDateCountLabel(stageDates?.repliedAt, inboundEmailCount),
  formatDateLabel(stageDates?.meetingAt),
  formatDateLabel(stageDates?.proposalAt),
  formatDateLabel(stageDates?.wonAt),
];
```

- [ ] **Step 3: Normalize counts and numeric summary**

In `normalizeCustomer`, read camelCase first and fall back to payload snake_case:

```typescript
const outboundEmailCount = Number(customer.outboundEmailCount ?? payload.outbound_email_count ?? 0);
const inboundEmailCount = Number(customer.inboundEmailCount ?? payload.inbound_email_count ?? 0);
const emailCount = Number(payload.email_count ?? outboundEmailCount + inboundEmailCount);
const meetingCount = Number(payload.meeting_count ?? 0);
```

Use the directional counts for `dates` and replace the signal/category string with numeric statistics:

```typescript
dates: stageDatesToTimeline(customer.stageDates, outboundEmailCount, inboundEmailCount),
signal: `${emailCount}封邮件 · ${meetingCount}场会议`,
```

- [ ] **Step 4: Align fallback cards**

Update the demo/fallback card values so their emailed and replied entries use `date · count`, and their `signal` values contain only email and meeting totals.

- [ ] **Step 5: Run frontend typecheck and production build**

Run:

```powershell
npm --prefix apps/web run build
```

Expected: `vue-tsc --noEmit` and `vite build` both succeed.

### Task 4: Regression and Browser Verification

**Files:**
- Verify: `apps/api/tests/test_customer_operation_real_routes.py`
- Verify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] **Step 1: Run customer-operation backend tests**

Run:

```powershell
pytest apps/api/tests/test_customer_operation_real_routes.py apps/api/tests/test_customer_operation_module_skeleton.py -q
```

Expected: all customer-operation tests pass.

- [ ] **Step 2: Restart the local project**

Run from the repository root:

```bash
bash start.local.sh
```

Expected: API listens on `127.0.0.1:8000` and Vite listens on `localhost:5173`.

- [ ] **Step 3: Verify the customer-operation homepage**

Open `http://localhost:5173`, navigate to the customer-operation homepage, and confirm:

```text
已邮件
7/28 · 3封

已回复
7/28 · 2封
```

Confirm the recent-email summary uses only:

```text
3封邮件 · 1场会议
```

and does not contain `信号：` or `其他`.
