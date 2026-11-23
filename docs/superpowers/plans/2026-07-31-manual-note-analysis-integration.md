# Manual Note Analysis Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make confirmed customer-operation notes create truthful PostgreSQL-backed customer-analysis runs and display accurate frontend feedback.

**Architecture:** Normal API startup will pass an `AppSettings`-derived psycopg connection factory into the customer-analysis container, leaving in-memory adapters only for explicitly constructed tests and demos. Manual-note confirmation will persist first, synchronously attempt run creation, and return structured full-success or partial-success metadata that the frontend renders without losing the saved note.

**Tech Stack:** Python 3.12, FastAPI, psycopg, PostgreSQL, unittest/pytest, Vue 3, TypeScript, Axios.

---

### Task 1: Bind Customer Analysis to Runtime PostgreSQL

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_analysis/infrastructure/bootstrap.py`
- Modify: `apps/api/src/ltc/main.py`
- Test: `apps/api/tests/test_main.py`

- [ ] **Step 1: Write a failing connection-factory test**

Add a test that creates `AppSettings(database_host="db.example", database_port=55432, database_name="ltc_test", database_user="tester", database_password="secret", database_sslmode="prefer")`, patches `psycopg.connect`, calls the new settings-derived factory, and asserts the resolved DSN was passed to psycopg.

```python
@patch("psycopg.connect")
def test_customer_analysis_connection_factory_uses_runtime_settings(self, connect: Mock) -> None:
    settings = AppSettings(
        database_host="db.example",
        database_port=55432,
        database_name="ltc_test",
        database_user="tester",
        database_password="secret",
        database_sslmode="prefer",
    )

    connection_factory = postgres_connection_factory(settings)
    connection_factory()

    connect.assert_called_once_with(settings.database_dsn)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python -m pytest apps/api/tests/test_main.py -k customer_analysis_connection_factory -q`

Expected: import or attribute failure because `postgres_connection_factory` does not exist.

- [ ] **Step 3: Implement the settings-derived factory**

Add to `bootstrap.py`:

```python
def postgres_connection_factory(settings: AppSettings) -> Callable[[], Any]:
    def connect() -> Any:
        import psycopg

        return psycopg.connect(settings.database_dsn)

    return connect
```

Update `create_app()` to call:

```python
customer_analysis = build_local_container(
    llm_base_url=runtime_settings.llm_base_url or None,
    llm_api_key=runtime_settings.llm_api_key or None,
    llm_model_name=runtime_settings.llm_model or None,
    connection_factory=postgres_connection_factory(runtime_settings),
)
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python -m pytest apps/api/tests/test_main.py -q`

Expected: all `test_main.py` tests pass.

### Task 2: Return Truthful Manual-Note Analysis Status

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/ports.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Test: `apps/api/tests/test_manual_note_analysis_trigger_reliability.py`

- [ ] **Step 1: Replace the background-failure test with response-contract tests**

Add one success test where `trigger_manual_note_analysis()` returns `SimpleNamespace(run_id=run_id, status="queued")` and assert:

```python
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()["analysis"], {
    "status": "queued",
    "runId": str(run_id),
    "message": "Customer analysis generation has been queued.",
})
```

Add one failure test where the trigger raises `RuntimeError("analysis unavailable")` and assert the note remains in the response with:

```python
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()["analysis"]["status"], "failed")
self.assertIsNone(response.json()["analysis"]["runId"])
self.assertIn("saved", response.json()["analysis"]["message"])
```

- [ ] **Step 2: Run reliability tests and confirm RED**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python -m pytest apps/api/tests/test_manual_note_analysis_trigger_reliability.py -q`

Expected: response lacks `analysis`, and the existing background task raises after the response starts.

- [ ] **Step 3: Return the created run from the service**

Change `trigger_manual_note_analysis()` and `_trigger_analysis()` to return the result of `trigger.request_analysis(...)`. Update `AnalysisTriggerPort.request_analysis` to permit returning the run object.

```python
def trigger_manual_note_analysis(self, note: dict, extracted_fields: list) -> object:
    return self._trigger_analysis(note, extracted_fields)
```

- [ ] **Step 4: Make run creation synchronous and non-destructive**

Remove the `BackgroundTasks` dependency from confirmed-note creation. After `confirm_manual_note()`, call the trigger inside a dedicated `try/except`, log failures, and return:

```python
analysis = {
    "status": str(getattr(run, "status", "queued")),
    "runId": str(getattr(run, "run_id")),
    "message": "Customer analysis generation has been queued.",
}
```

On failure return:

```python
analysis = {
    "status": "failed",
    "runId": None,
    "message": "The manual note was saved, but customer analysis could not be started.",
}
```

- [ ] **Step 5: Run reliability tests and confirm GREEN**

Run: `$env:PYTHONPATH="$PWD\apps\api\src"; python -m pytest apps/api/tests/test_manual_note_analysis_trigger_reliability.py -q`

Expected: all tests pass without `response already started` errors.

### Task 3: Display Full and Partial Success Correctly

**Files:**
- Modify: `apps/web/src/services/operationApi.ts`
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`

- [ ] **Step 1: Add the response types**

```typescript
export interface ManualNoteAnalysisResult {
  status: 'queued' | 'running' | 'completed' | 'failed';
  runId: string | null;
  message: string;
}

export interface ManualNoteConfirmationResult {
  note: ManualNoteRecord;
  analysis: ManualNoteAnalysisResult;
}
```

Change `confirmManualNote()` to return both `data.note` and `data.analysis`.

- [ ] **Step 2: Render truthful feedback**

Update `confirmManualRecord()` to inspect `result.analysis.status`:

```typescript
const result = await operationApi.confirmManualNote(companyId, manualRecordNote.value.trim(), selectedFields);
manualRecordStep.value = 'saved';
manualRecordMessage.value = result.analysis.status === 'failed'
  ? `已保存 ${selectedFields.length} 条结构化信息，但新版客户分析启动失败，请稍后重试。`
  : `已保存 ${selectedFields.length} 条结构化信息，新版客户分析已进入生成队列。`;
```

- [ ] **Step 3: Run frontend validation**

Run: `cd apps/web; npm run typecheck; npm run build`

Expected: both commands exit successfully.

### Task 4: Verify the Real PostgreSQL Flow

**Files:**
- Verify only; remove probe data after testing.

- [ ] **Step 1: Restart with `start.local.sh`**

Stop the listeners on ports 8000 and 5173, then start the project using the local script so the updated backend is loaded.

- [ ] **Step 2: Verify customer-analysis visibility**

Log in as `zonglin` and call `/api/v1/api/customers/analysis/list`. Assert PostgreSQL-owned companies such as Berlin Mobility Services and Global Connectivity Alliance are returned instead of zero customers or demo contexts.

- [ ] **Step 3: Submit a uniquely marked manual note**

Confirm a note for Global Connectivity Alliance with a unique marker and selected decision-maker/budget fields. Assert the response contains a non-null `analysis.runId` and a non-failed status.

- [ ] **Step 4: Verify database integration**

Query PostgreSQL and assert:

```sql
SELECT status, trigger_type
FROM ltc.analysis_run
WHERE analysis_run_id = :run_id;
```

Expected: `trigger_type = 'operation'` and status is `queued`, `running`, or `completed`.

Also assert the selected profile fields are reflected in `ltc.customer_profile` and the current report endpoint resolves the PostgreSQL company.

- [ ] **Step 5: Verify the frontend**

Open customer analysis as zonglin and confirm owned PostgreSQL companies are visible. Submit a manual record through the UI and confirm the displayed message matches the returned analysis status.

- [ ] **Step 6: Clean the unique probe data**

Delete only rows identified by the unique marker and their exact `manual_note:{note_id}` activity/audit references. Do not delete user-created records.

- [ ] **Step 7: Run final verification**

Run:

```powershell
$env:PYTHONPATH="$PWD\apps\api\src"
python -m pytest apps/api/tests/test_main.py apps/api/tests/test_manual_note_analysis_trigger_reliability.py apps/api/tests/test_p0_lead_data_flow.py -q
cd apps/web
npm run typecheck
npm run build
```

Expected: focused backend suites pass and frontend typecheck/build succeed. Report any unrelated fixture-dependent failures separately.
