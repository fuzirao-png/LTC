# Manual Note to Customer Analysis Integration Design

## Problem

Confirmed manual notes are persisted by customer operation in PostgreSQL, but the customer analysis container can silently start with in-memory repositories. Its bootstrap decides whether PostgreSQL is available by reading `LTC_DB_HOST` directly from `os.environ`, while application configuration reads `.env` values and supplies database defaults without exporting them.

The manual-note endpoint also returns success before its background analysis trigger finishes. If analysis cannot find the PostgreSQL company in the in-memory context, the note remains saved, no analysis run is created, and the frontend still reports that a report entered the queue.

## Goals

- Make customer analysis use the same PostgreSQL configuration as the API.
- Preserve a confirmed note when analysis startup fails.
- Return explicit full-success or partial-success analysis metadata.
- Never claim a report was queued unless a run was created.
- Preserve sales-user visibility and mailbox isolation.

## Non-Goals

- Redesigning the report prompt or layout.
- Changing extraction dimensions.
- Adding automatic retries.
- Adding database migrations.

## Selected Approach

### Shared PostgreSQL Connection Factory

`create_app()` constructs the customer analysis container with a connection factory derived from resolved `AppSettings`. Normal API startup no longer depends on `LTC_DB_HOST` being exported. In-memory adapters remain available for explicitly constructed tests and demos.

### Manual Note Result Semantics

The endpoint saves the confirmed note, then synchronously attempts to create an analysis run so it can return a truthful result.

Full success returns the note plus `analysis.status`, `analysis.runId`, and the created run state.

Partial success remains HTTP 200 because the customer information is durable. It returns the note plus `analysis.status = "failed"` and a stable user-facing message. The server logs the original exception with company and note identifiers and does not re-raise after the response starts.

### Frontend Feedback

The frontend shows the queue-success message only when the response contains a created analysis run. If startup fails, it shows that the record was saved but analysis generation failed and can be retried later.

## Data Flow

1. Sales confirms extracted fields.
2. Customer operation persists the note, activity, and audit data.
3. Supported profile fields are updated.
4. Customer analysis loads the same PostgreSQL company context.
5. Customer analysis creates and returns an `analysis_run`.
6. The API returns the note and truthful analysis status.
7. The frontend displays full or partial success.

## Error Handling

- Note persistence failure returns an error.
- Profile update failure is logged and analysis creation is still attempted.
- Analysis-run creation failure retains the note and returns partial success.
- Later asynchronous generation failure remains recorded on the created run.

## Tests

- API startup passes an AppSettings-derived PostgreSQL connection factory.
- Missing exported `LTC_DB_HOST` cannot silently select memory during normal startup.
- Successful manual-note confirmation returns queued run metadata.
- Failed run creation returns partial success while preserving the note.
- Frontend messages match the returned analysis status.
- Existing ownership and mailbox-isolation behavior remains unchanged.

## Acceptance Criteria

- A zonglin manual note for a visible PostgreSQL customer creates an operation-triggered analysis run.
- The normal local customer-analysis list reads PostgreSQL customers, not demo contexts.
- A failed trigger never produces the false queue-success message.
- No migration or credential change is required.
