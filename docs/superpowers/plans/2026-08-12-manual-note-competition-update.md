# Manual Note Competition Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make confirmed competitor manual notes version-aware, explicitly update the `competition` MEDDPICC dimension, return field-level outcomes, and show accurate pending/failure state in the analysis report.

**Architecture:** Enrich extracted manual-note fields through the customer-analysis port with normalized target metadata and current dimension version. Apply selected `覆盖` fields through that same port before queuing analysis, returning deterministic `updated_dimensions`, `conflicts`, and `skipped_fields`; the analysis run then snapshots the already-updated dimension. Frontend navigation carries the field result, suppresses stale report presentation while the run is pending, and reloads the current report after completion.

**Tech Stack:** FastAPI, Python stdlib `unittest`, PostgreSQL adapters, Vue 3, TypeScript, Node built-in tests.

---

### Task 1: Normalize Competitor Extraction

**Files:**
- Modify: `apps/api/tests/test_manual_note_extractor.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/manual_note_extractor.py`

- [ ] Add failing tests for `飞猪或者任意公司`, `飞猪以及任意公司`, `飞猪 vs 任意公司`, and `飞猪对比任意公司`.
- [ ] Verify tests fail because extracted competitor text is not normalized.
- [ ] Add a pure competitor-name splitter and normalize competitor extraction to `飞猪、任意公司`.
- [ ] Verify extractor tests pass.

### Task 2: Enrich Extraction With Target Version

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/ports.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/tests/test_manual_note_analysis_trigger_reliability.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`

- [ ] Add failing service tests expecting competitor fields to include `target=competition`, `target_table=customer_meddpicc_dimension`, `target_version`, and `previous`.
- [ ] Extend `AnalysisTriggerPort` with dimension read/update methods matching `CustomerAnalysisService`.
- [ ] Enrich extraction results from the current `competition` dimension.
- [ ] Verify extraction API returns the enriched shape.

### Task 3: Apply Versioned Override and Return Outcomes

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Modify: `apps/api/tests/test_manual_note_analysis_trigger_reliability.py`

- [ ] Add failing tests for successful override, arbitrary-company value, version conflict, and skipped unsupported fields.
- [ ] Implement selected `action=覆盖` application through `update_meddpicc` using `target_version`.
- [ ] Return `updated_dimensions`, `conflicts`, and `skipped_fields` from confirmation and include them in analysis trigger context.
- [ ] Verify conflict responses are explicit and database updates are not attempted on stale versions.

### Task 4: Preserve Field Outcomes Through APIs

**Files:**
- Modify: `apps/web/src/services/operationApi.ts`
- Modify: `apps/web/src/shared/utils/customerAnalysisNavigation.js`
- Modify: corresponding `.d.ts` and Node tests if present.
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] Add types for normalized target fields and field-level results.
- [ ] Carry result status to the analysis route without placing full sensitive note content in the URL.
- [ ] Store a short-lived pending update summary in session storage keyed by company/run.
- [ ] Verify navigation helpers with Node tests.

### Task 5: Show Pending, Conflict, and Failure States

**Files:**
- Modify: `apps/web/src/features/customer-analysis/CustomerAnalysis.vue`
- Create or modify a small pure helper and Node tests under `apps/web/src/features/customer-analysis/`.

- [ ] Add failing tests for pending display, completed competition success, conflict, skipped, and failed run states.
- [ ] Hide stale competitor report content while the requested run is queued/running.
- [ ] Reload current report after completion and verify `meddpicc.competition` contains the updated value.
- [ ] Display `竞争对手字段未进入报告` with conflict/skipped reason when appropriate.
- [ ] Clear pending session state after terminal handling.

### Task 6: Add End-to-End Backend Regression

**Files:**
- Modify: `apps/api/tests/test_manual_note_competitor_extraction.py`
- Modify: `apps/api/tests/test_customer_analysis_database_flow.py` or add a focused integration test using the existing database harness.

- [ ] Cover `竞争对手是飞猪`.
- [ ] Cover `竞争对手是任意公司`.
- [ ] Cover replacing an existing competitor with a matching version.
- [ ] Cover stale-version conflict with no dimension update.
- [ ] Assert the final MEDDPICC summary and flattened competitor report contain the new name.

### Task 7: Verify All Changes

- [ ] Run focused customer-operation and customer-analysis Python suites.
- [ ] Run frontend Node helper tests.
- [ ] Run `npm run typecheck` and `npm run build`.
- [ ] Review the diff to ensure prior TOP5 changes remain intact and no commit or push occurs.