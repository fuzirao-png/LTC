# Tencent Enterprise Mail Parallel Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `global.marketing@51tgt.com` as a second IMAP mailbox monitor alongside the existing 163 mailbox, so inbound mail and replies are both polled and persisted without changing the existing outbound flow.

**Architecture:** Keep the current DB-driven mailbox monitor model. Add one `ltc.mailbox_monitor` row for the Tencent mailbox with its own secret env var, load both monitors at startup, and make manual polling hit every enabled monitor instead of just one. Reuse the existing inbound parser, notification creation, and Postgres persistence path.

**Tech Stack:** FastAPI, IMAP over SSL, PostgreSQL, pg8000, pytest.

---

### Task 1: Add Tencent mailbox configuration

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/.env.example`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/.env`

- [ ] **Step 1: Add a dedicated secret env var for the Tencent mailbox**

```env
INBOUND_MAIL_PASSWORD_51TGT=<tencent_enterprise_mail_password_or_auth_code>
```

- [ ] **Step 2: Keep the existing 163 mailbox config unchanged**

```env
INBOUND_MAIL_ENABLED=true
INBOUND_MAIL_HOST=imap.163.com
INBOUND_MAIL_PORT=993
INBOUND_MAIL_USERNAME=k2638792769@163.com
INBOUND_MAIL_PASSWORD=<163_mail_auth_code>
INBOUND_MAIL_MAILBOX=INBOX
```

- [ ] **Step 3: Verify the env files still parse cleanly**

Run:

```powershell
Get-Content customer-operation-agent/.env
Get-Content customer-operation-agent/.env.example
```

Expected: both files contain the new Tencent secret var and no syntax changes.

### Task 2: Insert the Tencent mailbox monitor row

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/db/migrations/0002_email_mailbox_monitor.sql`
- Test: database via `psql`

- [ ] **Step 1: Keep the mailbox table shape as-is**

```sql
CREATE TABLE ltc.mailbox_monitor (
    mailbox_monitor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code text NOT NULL,
    host text NOT NULL,
    port integer NOT NULL,
    username text NOT NULL,
    secret_env_var text NOT NULL,
    mailbox_name text NOT NULL DEFAULT 'INBOX',
    enabled boolean NOT NULL DEFAULT true,
    poll_seconds integer NOT NULL DEFAULT 60,
    last_uid text,
    last_polled_at timestamptz,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

- [ ] **Step 2: Insert a new enabled row for the Tencent mailbox**

```sql
INSERT INTO ltc.mailbox_monitor (
    provider_code,
    host,
    port,
    username,
    secret_env_var,
    mailbox_name,
    enabled,
    poll_seconds
)
VALUES (
    'imap',
    'imap.exmail.qq.com',
    993,
    'global.marketing@51tgt.com',
    'INBOUND_MAIL_PASSWORD_51TGT',
    'INBOX',
    true,
    60
)
ON CONFLICT (provider_code, username, mailbox_name)
DO UPDATE SET
    host = EXCLUDED.host,
    port = EXCLUDED.port,
    secret_env_var = EXCLUDED.secret_env_var,
    enabled = EXCLUDED.enabled,
    poll_seconds = EXCLUDED.poll_seconds;
```

- [ ] **Step 3: Verify the row exists**

Run:

```sql
select provider_code, host, port, username, mailbox_name, enabled, poll_seconds, secret_env_var
from ltc.mailbox_monitor
order by created_at desc;
```

Expected: one row for `global.marketing@51tgt.com` and the existing 163 row.

### Task 3: Make manual poll cover every enabled monitor

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/app/api/routes.py`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/tests/test_pa_notification_routes.py`

- [ ] **Step 1: Change `/api/inbound-mail/poll-now` to iterate all active pollers**

```python
@router.post("/api/inbound-mail/poll-now")
async def poll_inbound_mail_now(request: Request) -> dict:
    pollers = getattr(request.app.state, "inbound_mail_pollers", None)
    if pollers is None:
        poller = getattr(request.app.state, "inbound_mail_poller", None)
        if poller is None:
            raise HTTPException(status_code=503, detail="Inbound mail polling is not enabled.")
        pollers = [poller]

    created_notifications = []
    for poller in pollers:
        created_notifications.extend(await poller.poll_once())

    return {
        "success": True,
        "createdCount": len(created_notifications),
        "notifications": created_notifications,
    }
```

- [ ] **Step 2: Add a test that multiple pollers are both called**

```python
def test_inbound_mail_poll_now_uses_all_app_pollers():
    class FakePoller:
        def __init__(self, items):
            self.items = items

        async def poll_once(self):
            return self.items

    client = TestClient(app)
    app.state.inbound_mail_pollers = [FakePoller([{"id": "n1"}]), FakePoller([{"id": "n2"}])]
    try:
        response = client.post("/api/inbound-mail/poll-now")
    finally:
        del app.state.inbound_mail_pollers

    assert response.status_code == 200
    assert response.json()["createdCount"] == 2
```

- [ ] **Step 3: Run the route test**

Run:

```powershell
pytest customer-operation-agent/tests/test_pa_notification_routes.py -v
```

Expected: pass.

### Task 4: Verify startup loads both monitors

**Files:**
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/tests/test_mailbox_monitor_store.py`
- Modify: `C:/Users/EDY/Desktop/code/LTC_NEW/LTC/customer-operation-agent/app/main.py` only if startup behavior still needs a small fallback fix

- [ ] **Step 1: Add a test row for the Tencent mailbox monitor**

```python
INSERT INTO ltc.mailbox_monitor (
    provider_code,
    host,
    port,
    username,
    secret_env_var,
    mailbox_name,
    enabled,
    poll_seconds
)
VALUES ('imap', 'imap.exmail.qq.com', 993, 'global.marketing@51tgt.com', 'INBOUND_MAIL_PASSWORD_51TGT', 'INBOX', true, 60)
```

- [ ] **Step 2: Assert `list_enabled_mailbox_monitors()` returns both 163 and Tencent rows**

```python
assert any(item["username"] == "k2638792769@163.com" for item in monitors)
assert any(item["username"] == "global.marketing@51tgt.com" for item in monitors)
```

- [ ] **Step 3: Run the mailbox monitor store test**

Run:

```powershell
pytest customer-operation-agent/tests/test_mailbox_monitor_store.py -v
```

Expected: pass.

### Task 5: End-to-end smoke test

**Files:**
- No code changes expected

- [ ] **Step 1: Restart the app with the updated env**

Run:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8790
```

Expected startup log contains the number of active mailbox monitors.

- [ ] **Step 2: Trigger manual polling**

Run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8790/api/inbound-mail/poll-now
```

Expected: `createdCount` reflects the total across all enabled monitors.

- [ ] **Step 3: Confirm inbound rows are written**

Run:

```sql
select email_id, direction, status, from_address, subject, received_at, created_at
from ltc.email_message
order by created_at desc
limit 20;
```

Expected: inbound mail from either mailbox appears with `direction = 'inbound'` and `status = 'received'`.
