# PA Email Notification Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let inbound email create a clickable PA notification that opens customer operation and lands on the matching historical email detail.

**Architecture:** Reuse the existing inbound-mail -> PA notification pipeline. Enrich the notification payload with the fields needed to identify the target customer and email record, then let the web app store a pending navigation target and consume it inside the customer-operation email drawer. Keep the PA popup as the entry point; do not introduce a second email viewer.

**Tech Stack:** FastAPI, pytest, Vue 3, Pinia, TypeScript

---

### Task 1: Enrich inbound-mail notifications with jump metadata

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/api/src/ltc/modules/customer_operation/application/pa_notification_service.py`
- Test: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/api/tests/test_customer_operation_real_routes.py`

- [ ] **Step 1: Write the failing test**

```python
def test_inbound_mail_creates_notification_with_jump_fields() -> None:
    _seed_demo_data()
    client = _client()

    response = client.post("/api/v1/inbound-mail/poll-now")
    assert response.status_code == 200

    notification = response.json()["notifications"][0]
    assert notification["type"] == "email"
    assert notification["customerName"] == "Pacific TMC Japan"
    assert notification["messageId"]
    assert notification["subject"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/api/tests/test_customer_operation_real_routes.py -k inbound_mail -q`

Expected: FAIL because the notification payload does not yet carry the fields the UI needs.

- [ ] **Step 3: Write minimal implementation**

Add the missing notification metadata in the inbound-mail event path:

```python
event["companyId"] = str(company_id)
event["emailId"] = str(email_id)
event["notificationTarget"] = {
    "companyId": str(company_id),
    "emailId": str(email_id),
    "messageId": str(message_id),
}
```

Keep `PaNotificationService.create_from_event()` storing these fields in the notification JSON so the frontend can open the right customer and email row.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/api/tests/test_customer_operation_real_routes.py -k inbound_mail -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py apps/api/src/ltc/modules/customer_operation/application/pa_notification_service.py apps/api/tests/test_customer_operation_real_routes.py
git commit -m "feat: add inbound mail notification jump metadata"
```

### Task 2: Make PA notifications clickable and publish a pending email target

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/shared/components/PAPopup.vue`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/stores/app.ts`
- Test: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/shared/components/PAPopup.vue` (manual verification via browser)

- [ ] **Step 1: Write the failing test**

No automated unit test exists for the popup yet. Add a small Pinia store assertion if needed, but the main proof is browser behavior: clicking a PA email notification should set a pending target.

```ts
// pseudo-check for the store contract
expect(app.pendingEmailTarget).toEqual({
  companyId: '...',
  emailId: '...',
  messageId: '...'
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run typecheck`

Expected: FAIL or compile complaints until the new store fields and methods exist.

- [ ] **Step 3: Write minimal implementation**

Add `pendingEmailTarget` and helpers to the app store:

```ts
const pendingEmailTarget = ref<{ companyId: string; emailId: string; messageId?: string } | null>(null)
function openEmailTarget(target: { companyId: string; emailId: string; messageId?: string }) {
  pendingEmailTarget.value = target
  currentView.value = 'customer-mgmt'
}
function clearEmailTarget() {
  pendingEmailTarget.value = null
}
```

Render PA email notifications as clickable items in `PAPopup.vue`, calling `store.openEmailTarget(...)` and closing the popup.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/stores/app.ts apps/web/src/shared/components/PAPopup.vue
git commit -m "feat: make pa email notifications clickable"
```

### Task 3: Auto-open the matching historical email in customer operation

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/features/customer-operation/CustomerOperation.vue`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/services/operationApi.ts`
- Optional modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/apps/web/src/app/layouts/AppLayout.vue`

- [ ] **Step 1: Write the failing test**

Add a focused browser check or a small store-level test for the pending target flow:

```ts
// once a pending target is set, the email list should auto-select the matching record
expect(selectedEmailHistoryKey).toBe(target.emailId)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run typecheck`

Expected: FAIL until customer-operation consumes the pending target.

- [ ] **Step 3: Write minimal implementation**

When customer operation opens, if `pendingEmailTarget` exists:

```ts
await loadEmailHistory(customer)
selectedEmailHistory.value = emailHistory.value.find(
  (item) => item.email_id === target.emailId || item.id === target.emailId || item.messageId === target.messageId,
) || null
```

Keep the editor read-only only while `selectedEmailHistory` is set. Do not open a new dialog. After opening, clear the pending target in the app store.

- [ ] **Step 4: Run test to verify it passes**

Run:
`npm run typecheck`
`python -m pytest apps/api/tests/test_customer_operation_real_routes.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/customer-operation/CustomerOperation.vue apps/web/src/services/operationApi.ts apps/web/src/app/layouts/AppLayout.vue
git commit -m "feat: jump from pa notification to email history"
```

### Task 4: Verify end-to-end flow

**Files:**
- No code changes expected

- [ ] **Step 1: Run backend verification**

Run: `python -m pytest apps/api/tests/test_customer_operation_real_routes.py -q`

- [ ] **Step 2: Run frontend verification**

Run: `npm run typecheck`

- [ ] **Step 3: Manual browser check**

Open the app, trigger or simulate an inbound mail notification, click it in PA, and confirm the customer-operation page opens with the correct historical email shown in the existing viewer area.

- [ ] **Step 4: Commit any final polish**

```bash
git add -A
git commit -m "feat: wire pa notifications to inbound email history"
```

## Self-Review

- Spec coverage: inbound-mail notification payload, PA clickable notifications, customer-operation auto-open, and verification are all covered.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: `companyId`, `emailId`, and `messageId` are used consistently across tasks.
