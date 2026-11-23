# User Mailbox Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement encrypted one-salesperson-one-mailbox delivery, polling, notification, history, and customer-scope isolation for `li.ming` and `zong.lin`.

**Architecture:** Add a dedicated `user_mailbox` aggregate keyed uniquely by IAM user, encrypt credentials with an environment-held Fernet key, and stamp `email_message.sales_user_id`. Authentication determines outbound ownership while each mailbox poller supplies inbound ownership; repositories enforce read isolation.

**Tech Stack:** FastAPI, PostgreSQL, psycopg/pg8000, cryptography Fernet, Vue, pytest.

---

### Task 1: Schema and credential encryption

**Files:**
- Create: `db/migrations/0010_user_mailbox_isolation.sql`
- Create: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_credential_cipher.py`
- Modify: `apps/api/requirements.txt`
- Test: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] Write tests proving credential round-trip and missing/invalid key failures.
- [ ] Run the focused tests and confirm they fail before implementation.
- [ ] Add Fernet dependency, cipher adapter, mailbox table, `sales_user_id`, constraints, and indexes.
- [ ] Run focused tests and confirm they pass.

### Task 2: Authenticated outbound mailbox selection

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/user_email_resolver.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/email_provider_adapter.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/email_delivery_service.py`
- Test: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] Write route and resolver tests proving authenticated-user selection and no cross-user fallback.
- [ ] Run tests and confirm the old behavior fails.
- [ ] Resolve only enabled `user_mailbox` records and inject `context.actor.user_id` into sending.
- [ ] Stamp outbound messages with `sales_user_id` and rerun tests.

### Task 3: Inbound ownership and notification isolation

**Files:**
- Modify: `apps/api/src/ltc/main.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/pa_notification_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Test: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] Write tests proving pollers stamp owners and notification list/detail reject other sales users.
- [ ] Run tests and confirm failures.
- [ ] Carry mailbox `user_id` through polling, persistence, and notification payloads.
- [ ] Filter sales reads by actor while preserving strategic access; rerun tests.

### Task 4: Customer and history scope

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_customer_home_card_store.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] Write tests showing sales home/history isolation and strategic full visibility.
- [ ] Run tests and confirm failures.
- [ ] Reuse claimed-owner filtering and add `sales_user_id` history filtering.
- [ ] Rerun focused customer-operation tests.

### Task 5: Local users, bindings, and verification

**Files:**
- Create: `scripts/configure_local_user_mailboxes.py`
- Modify: `.env` locally only (ignored)

- [ ] Apply migration and record its schema artifact.
- [ ] Generate/store a local encryption key without printing it.
- [ ] Create/update `li.ming` and `zong.lin` with approved sales tiers and regions.
- [ ] Encrypt and bind both supplied mailbox credentials without logging them.
- [ ] Restart services and verify two-way send, poll, notification isolation, focused tests, and frontend build.
