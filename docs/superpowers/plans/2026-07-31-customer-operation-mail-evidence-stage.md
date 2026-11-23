# Customer Operation Mail Evidence Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This plan is executed inline in the current session; do not dispatch subagents and do not commit unless the user explicitly requests it.

**Goal:** Drive customer-operation progress from proposal/won evidence found in email bodies and attachments, provide secure inbound attachment downloads, and apply the exact requested progress percentages.

**Architecture:** Add a focused attachment document service for safe persistence and text extraction, extend the seven-value reply classifier, and store structured evidence on `email_message`. Incoming and outgoing mail feed evidence into the same persistence model, while home cards derive proposal/won directly from email intent timestamps instead of tasks or CRM transitions.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL/pg8000, Pydantic, pypdf, python-docx, openpyxl, Vue 3, TypeScript, Axios.

---

### Task 1: Expand the intent contract

**Files:**
- Create: `db/migrations/0015_email_evidence_intents.sql`
- Modify: `apps/api/src/ltc/modules/customer_operation/domain/read_models.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/domain/email_message.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/reply_intent_agent.py`
- Test: `apps/api/tests/test_reply_intent_agent.py`

- [ ] Write failing tests asserting `proposal` for actual option/pricing-plan content, not “please send a proposal”, and `won` only for explicit signed/stamped/final-terms/cooperation confirmation language.
- [ ] Run `python -m pytest apps/api/tests/test_reply_intent_agent.py -q` and verify the new cases fail.
- [ ] Extend `IntentLevel`, `EmailIntent`, and `ALLOWED_INTENTS` with `proposal` and `won`.
- [ ] Add deterministic helpers with explicit positive and negative guards:

```python
def classify_progress_evidence(content: str) -> ReplyIntent | None:
    if has_explicit_won_evidence(content):
        return ReplyIntent(intent_level="won", next_action="Record the confirmed deal and prepare handoff.")
    if has_actual_proposal_evidence(content) and not is_proposal_request_only(content):
        return ReplyIntent(intent_level="proposal", next_action="Track the proposal and confirm the selected option.")
    return None
```

- [ ] Update the LLM prompt to allow exactly seven values and state the proposal/won false-positive rules.
- [ ] Add migration SQL that drops and recreates `ck_email_message_intent_level` with the seven allowed values.
- [ ] Re-run the focused tests and verify they pass.

### Task 2: Add safe attachment persistence and extraction

**Files:**
- Modify: `apps/api/requirements.txt`
- Modify: `apps/api/src/ltc/platform/config.py`
- Create: `apps/api/src/ltc/modules/customer_operation/infrastructure/email_attachment_service.py`
- Test: `apps/api/tests/test_email_attachment_service.py`

- [ ] Write failing tests for TXT, PDF, DOCX, XLSX extraction; unsupported-file retention; generated storage keys; path traversal rejection; and size limits.
- [ ] Run `python -m pytest apps/api/tests/test_email_attachment_service.py -q` and verify failure.
- [ ] Add `pypdf`, `python-docx`, and `openpyxl` requirements.
- [ ] Add settings loaded from `LTC_MAIL_ATTACHMENT_DIR`, `LTC_MAIL_ATTACHMENT_MAX_FILE_BYTES`, and `LTC_MAIL_ATTACHMENT_MAX_MESSAGE_BYTES`, defaulting to a local ignored data directory and conservative limits.
- [ ] Implement immutable attachment input/output records:

```python
@dataclass(frozen=True)
class EmailAttachmentInput:
    filename: str
    content_type: str
    content: bytes

@dataclass(frozen=True)
class StoredEmailAttachment:
    storage_key: str
    safe_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    extracted_text: str
    extraction_status: str
```

- [ ] Implement safe write/read resolution under the configured root and format-specific extractors.
- [ ] Ensure extraction exceptions return `extraction_status="failed"` without failing storage.
- [ ] Re-run focused tests and verify they pass.

### Task 3: Parse and persist incoming attachments

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/inbound_mail_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Test: `apps/api/tests/test_inbound_mail_poller.py`
- Test: `apps/api/tests/test_mail_store_invariants.py`

- [ ] Write failing tests proving MIME attachments are returned by `parse_raw_email`, passed to `record_inbound_email`, stored in `media_asset`/`email_attachment`, and included in classification text.
- [ ] Run the focused tests and verify failure.
- [ ] Add `attachments: tuple[EmailAttachmentInput, ...]` to `InboundEmail` and collect attachment MIME parts rather than skipping them.
- [ ] Extend `record_inbound_email(..., attachments=...)` to persist bytes, metadata, extraction status, and extracted text.
- [ ] Classify `subject + body + extracted attachment text`, storing evidence source metadata in `intent_payload`.
- [ ] Remove `_create_follow_up_task_for_email` invocation so positive reply intents no longer create automatic tasks.
- [ ] Preserve unsubscribe suppression, activity creation, notifications, idempotency, and mailbox ownership.
- [ ] Re-run focused tests and verify they pass.

### Task 4: Detect outgoing proposal and won evidence

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/email_delivery_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mail_store.py`
- Test: `apps/api/tests/test_mail_store_invariants.py`

- [ ] Write failing tests proving outgoing actual proposals and explicitly signed agreements store `proposal`/`won`, while ordinary outreach and draft contracts store no progress intent.
- [ ] Run the focused tests and verify failure.
- [ ] Decode outbound base64 attachments once, persist retrievable bytes through the attachment service, and extract supported text.
- [ ] Run `classify_progress_evidence` on outgoing subject/body/attachment text and only persist `proposal` or `won` results.
- [ ] Store evidence source metadata in `intent_payload`; do not run the general negative reply classifier on outbound mail.
- [ ] Re-run focused tests and verify they pass.

### Task 5: Derive cards from email evidence

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_customer_home_card_store.py`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`
- Test: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] Write failing tests for exact percentages and direct highest-event jumps.
- [ ] Write failing tests proving proposal tasks and CRM won transitions no longer advance customer-operation cards.
- [ ] Replace progress values with:

```python
{
    "assigned": 8.5,
    "emailed": 25,
    "replied": 42,
    "meeting": 58.5,
    "proposal": 75.5,
    "won": 100,
}
```

- [ ] Query earliest email timestamps filtered by `intent_level='proposal'` and `intent_level='won'`, using sales ownership filtering consistently.
- [ ] Remove proposal-task and lead-stage-transition queries from card stage calculation while retaining task counts for statistics.
- [ ] Keep `_stage_from_dates` highest-event precedence so stages can jump directly.
- [ ] Re-run focused tests and verify they pass.

### Task 6: Add authorized attachment downloads

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/domain/read_models.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/postgres_repository.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/ports.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Test: `apps/api/tests/test_customer_operation_auth.py`
- Test: `apps/api/tests/test_customer_operation_real_routes.py`

- [ ] Write failing tests for attachment metadata in email history, successful authenticated download, cross-sales denial, mismatched company/email/attachment denial, and missing-file handling.
- [ ] Run the focused tests and verify failure.
- [ ] Add an `EmailAttachmentRecord` model and `attachments` list on `EmailRecord`.
- [ ] Join `email_attachment` and `media_asset` metadata into each history email without loading bytes.
- [ ] Add a repository/service method returning a verified attachment path and metadata only when company, email, attachment, and sales scope match.
- [ ] Add `GET /customers/{company_id}/emails/{email_id}/attachments/{attachment_id}/download` returning `FileResponse` with safe MIME type and filename.
- [ ] Re-run focused tests and verify they pass.

### Task 7: Align the frontend progress and attachment links

**Files:**
- Modify: `apps/web/src/services/operationApi.ts`
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`
- Test: add or update the nearest existing frontend unit test if the project has a configured runner; otherwise validate through typecheck/build.

- [ ] Add typed attachment metadata and a download URL builder to `OperationEmail`/`operationApi`.
- [ ] Replace fallback stage percentages with `8.5`, `25`, `42`, `58.5`, `75.5`, and `100`.
- [ ] Add a stage-rank helper and change node completion from `index * 20 <= customer.progress` to `index <= currentStageRank`.
- [ ] In the selected inbound history preview only, render filename, formatted size, and an authenticated download link/button when attachments exist.
- [ ] Keep the current history layout and omit intent/next-action UI.
- [ ] Run `npm run typecheck` and `npm run build` from `apps/web`.

### Task 8: Apply migration and run verification

**Files:**
- Verify all files above.

- [ ] Apply `db/migrations/0015_email_evidence_intents.sql` to the local PostgreSQL database.
- [ ] Run the new focused backend test files first.
- [ ] Run all customer-operation backend tests that do not depend on absent local seed usernames.
- [ ] Run frontend typecheck and production build.
- [ ] Send controlled incoming and outgoing probe messages/records for proposal and won evidence, verify card stages and attachment download, then clean probe data.
- [ ] Review `git diff --check`, `git status --short`, and ensure `.env`, credentials, runtime attachments, and backup files remain untracked.
