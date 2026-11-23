# Email Sender Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the real inbound sender after opening a customer-operation email notification.

**Architecture:** Preserve real address metadata in the backend read model and expose it through the existing email-history route. Update the Vue email dialog to derive and synchronize contacts from the selected email record.

**Tech Stack:** Python, Pydantic, PostgreSQL, FastAPI, Vue 3, TypeScript

---

### Task 1: Add backend regression coverage

**Files:**
- Modify: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] Assert the seeded inbound history item exposes its real sender, recipient, Message-ID, and contact email.
- [ ] Assert the seeded outbound item exposes its real recipient.
- [ ] Run the targeted test and confirm it fails because those fields are absent.

### Task 2: Preserve email address metadata

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/domain/read_models.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_repository.py`

- [ ] Add optional address, Message-ID, and contact identity fields to `EmailRecord`.
- [ ] Join the email query to `ltc.contact` and map the new fields.
- [ ] Run the targeted backend test and confirm it passes.

### Task 3: Synchronize the frontend sender

**Files:**
- Modify: `apps/web/src/services/operationApi.ts`
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] Extend `OperationEmail` with the new backend fields.
- [ ] Build sender contacts from real inbound address metadata.
- [ ] Select the matched sender after notification navigation or history selection.
- [ ] Remove generated `@example.com` addresses.

### Task 4: Verify the complete flow

**Files:**
- Verify: `apps/api/tests/test_customer_operation_real_routes.py`
- Verify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] Run targeted backend and customer-operation tests.
- [ ] Run the web production build.
- [ ] Restart the API and web app.
- [ ] Open the latest email notification and confirm the displayed email equals the notification sender.
