# LTC Mail Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `LTC_mail` email capabilities into the `LTC` customer-operation-agent while keeping the LTC project skeleton intact.

**Architecture:** Keep `LTC/customer-operation-agent` as the single Python agent entrypoint and add the missing mail-side services from `LTC_mail` into that package. Preserve existing LTC routes and in-memory operation store, but extend them with inbound mail polling, PA notifications, and Resend webhook handling so the customer-operations flow owns email end to end.

**Tech Stack:** FastAPI, Pydantic, Python standard library IMAP, existing in-memory store, `httpx`-based service clients, pytest/unittest.

---

### Task 1: Add mail-side service coverage to the LTC agent

**Files:**
- Modify: `LTC/customer-operation-agent/app/core/settings.py`
- Create: `LTC/customer-operation-agent/app/services/inbound_mail_service.py`
- Create: `LTC/customer-operation-agent/app/services/pa_notification_service.py`
- Create: `LTC/customer-operation-agent/app/services/resend_webhook_service.py`
- Create: `LTC/customer-operation-agent/tests/test_inbound_mail_service.py`
- Create: `LTC/customer-operation-agent/tests/test_pa_notification_service.py`
- Create: `LTC/customer-operation-agent/tests/test_resend_webhook_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_normalizes_inbound_email_to_pa_event():
    email = InboundEmail(
        uid="42",
        message_id="<abc@example.com>",
        from_email="buyer@example.com",
        to_email="sales@example.com",
        subject="Re: Pilot pricing",
        body_preview="Please send the pricing details.",
        body_text="Please send the pricing details.\nRegards",
        received_at="2026-07-20T12:00:00+08:00",
    )
    event = normalize_inbound_email(email)
    assert event["eventType"] == "imap.received"
    assert event["messageId"] == "<abc@example.com>"
    assert event["priority"] == "high"


def test_creates_lists_and_marks_notification_read(tmp_path):
    service = PaNotificationService(data_dir=tmp_path)
    created = service.create_from_event({"eventType": "email.replied", "messageId": "email_123"})
    assert service.list_notifications(role="sales", unread_only=True)[0]["id"] == created["id"]
    assert service.mark_read(created["id"])["read"] is True


def test_normalizes_reply_event_as_high_priority_notification_seed():
    event = normalize_resend_event({"type": "email.replied", "data": {"email_id": "email_123"}})
    assert event["eventType"] == "email.replied"
    assert event["messageId"] == "email_123"
```

- [ ] **Step 2: Run the tests and confirm they fail for missing modules**

Run: `pytest tests/test_inbound_mail_service.py tests/test_pa_notification_service.py tests/test_resend_webhook_service.py -q`

Expected: import or attribute failures because the mail-side modules do not yet exist in `LTC`.

- [ ] **Step 3: Implement the minimal services and settings**

```python
class Settings(BaseSettings):
    ...
    inbound_mail_enabled: bool = False
    inbound_mail_host: str = "imap.163.com"
    inbound_mail_port: int = 993
    inbound_mail_username: str = ""
    inbound_mail_password: str = ""
    inbound_mail_mailbox: str = "INBOX"
    inbound_mail_poll_seconds: int = 60

    def resolve_legacy_demo_dir(self) -> Path | None:
        root = Path(__file__).resolve().parents[3]
        candidates = list(root.glob("*Windows/*/demo/mail-api.js"))
        return candidates[0].parent if candidates else None
```

Use the `LTC_mail` service behavior as the source shape:
- parse IMAP raw mail into `InboundEmail`
- write inbound history and processed keys to JSON
- create PA notifications from inbound events and resend events
- normalize Resend webhook payloads into the same notification shape

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/test_inbound_mail_service.py tests/test_pa_notification_service.py tests/test_resend_webhook_service.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/settings.py app/services/inbound_mail_service.py app/services/pa_notification_service.py app/services/resend_webhook_service.py tests/test_inbound_mail_service.py tests/test_pa_notification_service.py tests/test_resend_webhook_service.py
git commit -m "feat: add mail-side services to customer operation agent"
```

### Task 2: Wire mail endpoints and startup hooks into the LTC API

**Files:**
- Modify: `LTC/customer-operation-agent/app/main.py`
- Modify: `LTC/customer-operation-agent/app/api/routes.py`
- Modify: `LTC/customer-operation-agent/app/services/store.py`
- Modify: `LTC/customer-operation-agent/app/services/email_delivery_service.py`
- Modify: `LTC/customer-operation-agent/app/services/legacy_file_store.py`
- Create: `LTC/customer-operation-agent/tests/test_pa_notification_routes.py`
- Update: `LTC/customer-operation-agent/tests/test_mvp_flow.py`

- [ ] **Step 1: Write the failing route and startup tests**

```python
def test_resend_webhook_creates_pa_notification():
    client = TestClient(app)
    response = client.post("/api/webhooks/resend", json={"type": "email.replied", "data": {"email_id": "email_123"}})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_inbound_mail_poll_now_uses_app_poller():
    class FakePoller:
        async def poll_once(self):
            return [{"id": "n1"}]
    app.state.inbound_mail_poller = FakePoller()
    response = client.post("/api/inbound-mail/poll-now")
    assert response.json()["createdCount"] == 1
```

- [ ] **Step 2: Run the tests and confirm the endpoints are missing**

Run: `pytest tests/test_pa_notification_routes.py tests/test_mvp_flow.py -q`

Expected: route failures because the LTC API has not yet been wired for mail notifications and inbound polling.

- [ ] **Step 3: Implement routes, poller startup, and legacy compatibility**

```python
@app.on_event("startup")
async def start_inbound_mail_poller() -> None:
    settings = get_settings()
    if not settings.inbound_mail_enabled:
        return
    ...

@router.post("/api/webhooks/resend")
async def receive_resend_webhook(request: Request) -> dict:
    payload = await request.json()
    event = normalize_resend_event(payload)
    LegacyFileStore().prepend_json_record("resend-events.json", event, limit=1000)
    notification = PaNotificationService().create_from_event(event)
    return {"success": True, "event": event, "notification": notification}
```

Also expose:
- `/api/inbound-mail/poll-now`
- `/api/inbound-mail/notifications/{notification_id}`
- `/api/pa/notifications`
- `/api/pa/notifications/{notification_id}/read`

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/test_pa_notification_routes.py tests/test_mvp_flow.py -q`

Expected: all route tests pass and the existing customer-operation flow still works.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/api/routes.py app/services/store.py app/services/email_delivery_service.py app/services/legacy_file_store.py tests/test_pa_notification_routes.py tests/test_mvp_flow.py
git commit -m "feat: wire mail notifications into customer operation agent"
```

### Task 3: Verify the merged agent preserves the LTC shell

**Files:**
- Review: `LTC/customer-operation-agent/app/main.py`
- Review: `LTC/customer-operation-agent/app/api/routes.py`
- Review: `LTC/customer-operation-agent/tests/test_mvp_flow.py`
- Review: `LTC/customer-operation-agent/tests/test_inbound_mail_service.py`
- Review: `LTC/customer-operation-agent/tests/test_pa_notification_routes.py`

- [ ] **Step 1: Run the full focused test set**

Run: `pytest tests/test_mvp_flow.py tests/test_inbound_mail_service.py tests/test_pa_notification_routes.py tests/test_pa_notification_service.py tests/test_resend_webhook_service.py -q`

Expected: all tests pass with no import errors.

- [ ] **Step 2: Check the public surface still matches LTC**

Confirm the following still exist and behave as before:
- `GET /api/health`
- `GET /api/customers/{company_id}/operations`
- `POST /api/customers/{company_id}/emails/generate`
- `POST /api/emails/send`
- `POST /api/emails/{email_id}/reply`
- `POST /api/meetings/upload`
- `POST /api/meetings/{meeting_id}/summarize`

- [ ] **Step 3: Commit the finished merge**

```bash
git add app/main.py app/api/routes.py app/core/settings.py app/services/*.py tests/*.py
git commit -m "feat: merge LTC mail capabilities into customer operation agent"
```

