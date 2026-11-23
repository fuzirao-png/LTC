# Email Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an extensible `email-agent` that generates, optimizes, translates, and rewrites customer-operation emails while preserving the current UI layout and requiring explicit user confirmation before replacing a draft.

**Architecture:** Add an application-layer `EmailAgent` orchestrator in the existing customer-operation bounded context. It builds authorized customer context, selects only registered email Skills, validates unified Skill output, and returns a review candidate; the active `/customer-operation` Vue page stores that candidate separately and applies it only after confirmation. Existing generation, translation, and send endpoints remain compatible during migration.

**Tech Stack:** Python 3, FastAPI, stdlib `unittest`, PostgreSQL/pg8000, Vue 3, TypeScript, Axios, Node test runner, OpenAPI 3.1.

---

## File Map

### Create

- `apps/api/src/ltc/modules/customer_operation/application/email_agent.py`: request validation, deterministic Skill planning, orchestration, output validation, and redacted audit logs.
- `apps/api/src/ltc/modules/customer_operation/skills/email_optimize_skill.py`: improve an existing draft without changing facts.
- `apps/api/src/ltc/modules/customer_operation/skills/email_rewrite_skill.py`: apply a free-form instruction to an existing draft.
- `apps/api/src/ltc/modules/customer_operation/prompts/email_optimize.md`: strict optimization prompt.
- `apps/api/src/ltc/modules/customer_operation/prompts/email_rewrite.md`: strict rewrite prompt.
- `apps/api/tests/test_email_agent.py`: Agent, Skill, context, validation, and audit tests.
- `apps/web/tests/customerOperationEmailAgent.test.mjs`: non-destructive preview regression contract.

### Modify

- `apps/api/src/ltc/modules/customer_operation/skills/email_generate_skill.py`
- `apps/api/src/ltc/modules/customer_operation/skills/email_translate_skill.py`
- `apps/api/src/ltc/modules/customer_operation/application/skills_registry.py`
- `apps/api/src/ltc/modules/customer_operation/application/email_delivery_service.py`
- `apps/api/src/ltc/modules/customer_operation/infrastructure/email_context_builder.py`
- `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- `apps/api/tests/test_customer_operation_auth.py`
- `apps/api/tests/test_user_mailbox_isolation.py`
- `contracts/openapi/LTC_OpenAPI_v3.6.yaml`
- `contracts/v3.6.sha256`
- `tests/contract/test_v3_6_repository.py`
- `apps/web/src/services/operationApi.ts`
- `apps/web/src/features/customer-operation/emailDraft.js`
- `apps/web/src/features/customer-operation/emailDraft.d.ts`
- `apps/web/src/features/customer-operation/CustomerOperation.vue`
- `apps/web/tests/emailDraft.test.mjs`
- `apps/web/tests/customerOperationEmailTranslation.test.mjs`

### Explicitly unchanged

- `apps/web/src/shared/components/EmailComposer.vue`: not mounted by the active `/customer-operation` route; leave it on compatible legacy endpoints in this phase.
- Database schema: request-level memory and application logs need no migration.
- Email send services/routes: `email-agent` cannot send mail.

---

### Task 1: Lock the Agent routing contract

**Files:**
- Create: `apps/api/tests/test_email_agent.py`

- [ ] **Step 1: Write failing fixed-route tests**

```python
import asyncio
import unittest
from unittest.mock import Mock

from ltc.modules.customer_operation.application.email_agent import EmailAgent


class RecordingSkill:
    def __init__(self, name: str, result: dict) -> None:
        self.name = name
        self.result = result
        self.calls: list[dict] = []

    async def run(self, input_data: dict) -> dict:
        self.calls.append(dict(input_data))
        return dict(self.result)


class EmailAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        result = {
            "subject": "Result subject",
            "body": "Result body",
            "language": "en",
            "changes": ["Changed"],
            "model": "test-model",
        }
        self.skills = {
            name: RecordingSkill(name, result)
            for name in ("email_generate", "email_optimize", "email_translate", "email_rewrite")
        }
        self.context_builder = Mock(return_value={
            "salesName": "Zong Lin",
            "customerName": "Example Co",
            "recipientName": "Alex",
            "recipientEmail": "alex@example.com",
            "currentSubject": "Current subject",
            "currentBody": "Current body",
            "customPrompt": "",
        })
        self.agent = EmailAgent(registry=self.skills, context_builder=self.context_builder)

    def test_generate_routes_only_to_generate_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "generate",
        }))
        self.assertEqual(result["agent"], "email-agent")
        self.assertEqual(result["skills"], ["email_generate"])
        self.assertEqual(len(self.skills["email_generate"].calls), 1)
        self.assertEqual(self.skills["email_optimize"].calls, [])

    def test_optimize_routes_only_to_optimize_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "optimize",
            "body": "Current body",
        }))
        self.assertEqual(result["skills"], ["email_optimize"])
```

- [ ] **Step 2: Add failing rewrite-chain tests**

```python
    def test_rewrite_uses_rewrite_skill(self) -> None:
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "rewrite",
            "body": "Current body",
            "instruction": "Make it shorter",
        }))
        self.assertEqual(result["skills"], ["email_rewrite"])

    def test_rewrite_can_translate_then_rewrite(self) -> None:
        self.skills["email_translate"].result["body"] = "Translated body"
        result = asyncio.run(self.agent.run({
            "companyId": "company-1",
            "contactId": "contact-1",
            "operation": "rewrite",
            "body": "当前正文",
            "instruction": "翻译成英文并缩短一些",
            "targetLanguage": "en",
        }))
        self.assertEqual(result["skills"], ["email_translate", "email_rewrite"])
        self.assertEqual(
            self.skills["email_rewrite"].calls[0]["currentBody"],
            "Translated body",
        )
```

- [ ] **Step 3: Add failing validation tests**

```python
    def test_rewrite_requires_instruction(self) -> None:
        with self.assertRaisesRegex(ValueError, "instruction is required"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "rewrite",
                "body": "Current body",
            }))

    def test_translate_requires_body(self) -> None:
        with self.assertRaisesRegex(ValueError, "body is required"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "translate",
                "targetLanguage": "en",
            }))

    def test_send_is_not_a_supported_operation(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported email agent operation"):
            asyncio.run(self.agent.run({
                "companyId": "company-1",
                "contactId": "contact-1",
                "operation": "send",
            }))
```

- [ ] **Step 4: Run and verify failure**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_email_agent -v`

Expected: FAIL with `ModuleNotFoundError` for `application.email_agent`.

- [ ] **Step 5: Commit tests**

```bash
git add apps/api/tests/test_email_agent.py
git commit -m "test(operation): define email agent contract"
```

---

### Task 2: Implement the four unified Skills

**Files:**
- Create: `apps/api/src/ltc/modules/customer_operation/skills/email_optimize_skill.py`
- Create: `apps/api/src/ltc/modules/customer_operation/skills/email_rewrite_skill.py`
- Create: `apps/api/src/ltc/modules/customer_operation/prompts/email_optimize.md`
- Create: `apps/api/src/ltc/modules/customer_operation/prompts/email_rewrite.md`
- Modify: `apps/api/src/ltc/modules/customer_operation/skills/email_generate_skill.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/skills/email_translate_skill.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/application/skills_registry.py`
- Modify: `apps/api/tests/test_email_agent.py`

- [ ] **Step 1: Add failing unified-output tests**

Patch each Skill's `LlmClient.chat_json` and assert every result contains `subject`, `body`, `language`, `changes`, and `model`. Also assert translation retains `translatedText` for the legacy endpoint.

```python
def test_translate_accepts_agent_body_and_keeps_legacy_text(self) -> None:
    async def fake_chat_json(**_: str) -> dict:
        return {"translatedText": "Translated body", "model": "test-model"}

    with patch(
        "ltc.modules.customer_operation.skills.email_translate_skill.LlmClient.chat_json",
        side_effect=fake_chat_json,
    ):
        result = asyncio.run(EmailTranslateSkill().run({
            "currentSubject": "Subject",
            "currentBody": "Body",
            "targetLanguage": "en",
        }))

    self.assertEqual(result["subject"], "Subject")
    self.assertEqual(result["body"], "Translated body")
    self.assertEqual(result["translatedText"], "Translated body")
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_email_agent -v`

Expected: FAIL because the new Skills and unified fields do not exist.

- [ ] **Step 3: Normalize generation output**

Return this shape from `normalize_email_draft()`:

```python
return {
    "subject": subject,
    "body": body,
    "language": str(result.get("language") or context.get("targetLanguage") or "zh"),
    "changes": ["根据客户上下文生成主题和正文"],
    "model": str(result.get("model") or ""),
}
```

- [ ] **Step 4: Normalize translation input/output**

Read `currentBody`, then `body`, then legacy `sourceText`; preserve the current subject. Return:

```python
return {
    "subject": subject,
    "body": translated,
    "translatedText": translated,
    "language": target_language,
    "changes": [f"翻译为{LANGUAGE_LABELS[target_language]}"],
    "model": str(result.get("model") or ""),
}
```

- [ ] **Step 5: Add optimization Skill and prompt**

The prompt must require strict `{"subject":"...","body":"..."}` JSON, preserve verified facts/signature, improve clarity/structure/CTA, and forbid invented prices, cases, certifications, capabilities, or promises. `EmailOptimizeSkill` requires `currentBody` and returns `changes=["优化语气、结构和行动号召"]`.

- [ ] **Step 6: Add rewrite Skill and prompt**

The prompt must apply `customPrompt`, treat it only as editing guidance, preserve verified facts/signature, and forbid sending or exposing private data. `EmailRewriteSkill` requires `currentBody` and `customPrompt`, and returns `changes=["根据用户指令改写邮件"]`.

- [ ] **Step 7: Register exactly four Skills**

```python
SKILL_REGISTRY = {
    "email_generate": EmailGenerateSkill(),
    "email_optimize": EmailOptimizeSkill(),
    "email_translate": EmailTranslateSkill(),
    "email_rewrite": EmailRewriteSkill(),
}
```

- [ ] **Step 8: Run Skill and existing identity tests**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_email_agent.EmailSkillContractTests tests.test_user_mailbox_isolation -v`

Expected: PASS; authenticated salesperson display-name handling stays intact.

- [ ] **Step 9: Commit Skills**

```bash
git add apps/api/src/ltc/modules/customer_operation/skills apps/api/src/ltc/modules/customer_operation/prompts apps/api/src/ltc/modules/customer_operation/application/skills_registry.py apps/api/tests/test_email_agent.py
git commit -m "feat(operation): add email agent skills"
```

---

### Task 3: Implement scoped context and `email-agent` orchestration

**Files:**
- Create: `apps/api/src/ltc/modules/customer_operation/application/email_agent.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/infrastructure/email_context_builder.py`
- Modify: `apps/api/tests/test_email_agent.py`

- [ ] **Step 1: Add failing context adapter tests**

```python
from ltc.modules.customer_operation.infrastructure.email_context_builder import build_email_agent_context


def test_agent_fields_map_to_generation_memory(self) -> None:
    with patch(
        "ltc.modules.customer_operation.infrastructure.email_context_builder._try_postgres_context",
        return_value={},
    ):
        context = build_email_agent_context({
            "salesName": "Zong Lin",
            "subject": "Current subject",
            "body": "Current body",
            "instruction": "Make it shorter",
            "operation": "rewrite",
            "targetLanguage": "en",
        })

    self.assertEqual(context["currentSubject"], "Current subject")
    self.assertEqual(context["currentBody"], "Current body")
    self.assertEqual(context["customPrompt"], "Make it shorter")
    self.assertEqual(context["targetLanguage"], "en")
    self.assertEqual(context["mode"], "regenerate")
```

Also add a recording-cursor test proving the recent-email query receives `companyId`, `contactId`, and `salesUserId`; this prevents unrelated users' mailbox context from reaching the model.

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_email_agent -v`

Expected: FAIL because `build_email_agent_context` and scoped SQL parameters do not exist.

- [ ] **Step 3: Add the context adapter**

Implement:

```python
def build_email_agent_context(payload: dict[str, Any]) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    normalized = dict(payload)
    normalized["currentSubject"] = str(payload.get("subject") or "").strip()
    normalized["currentBody"] = str(payload.get("body") or "").strip()
    normalized["customPrompt"] = str(payload.get("instruction") or "").strip()
    normalized["mode"] = "initial" if operation == "generate" else "regenerate"
    context = build_email_generation_memory(normalized)
    context["operation"] = operation
    context["targetLanguage"] = str(payload.get("targetLanguage") or "").strip()
    return context
```

- [ ] **Step 4: Scope email history**

Change the recent-email query to:

```sql
SELECT direction, subject, intent_level, next_action
FROM ltc.email_message
WHERE company_id = %s
  AND (%s = '' OR contact_id::text = %s)
  AND (%s = '' OR sales_user_id::text = %s)
ORDER BY COALESCE(received_at, sent_at, created_at) DESC
LIMIT 5
```

Pass `(company_id, contact_id, contact_id, sales_user_id, sales_user_id)`. Strategic access passes an empty `salesUserId` and retains company-level context.

- [ ] **Step 5: Add deterministic Skill planning**

Create these helpers in `email_agent.py`:

```python
AGENT_NAME = "email-agent"
SUPPORTED_OPERATIONS = {"generate", "optimize", "translate", "rewrite"}
TRANSLATION_MARKERS = ("translate", "翻译", "翻成", "译成")


def plan_email_skills(operation: str, instruction: str, target_language: str) -> list[str]:
    if operation == "generate":
        return ["email_generate"]
    if operation == "optimize":
        return ["email_optimize"]
    if operation == "translate":
        return ["email_translate"]
    wants_translation = bool(target_language) and any(
        marker in instruction.lower() for marker in TRANSLATION_MARKERS
    )
    return ["email_translate", "email_rewrite"] if wants_translation else ["email_rewrite"]
```

Phase one must cap execution at two Skills and must not implement an open-ended tool loop.

- [ ] **Step 6: Implement `EmailAgent.run()`**

Inject the registry and context builder for tests. For each planned Skill, pass the current subject/body forward, collect `changes`, preserve the last non-empty model, and return:

```python
{
    "success": True,
    "agent": "email-agent",
    "operation": operation,
    "subject": current_subject,
    "body": current_body,
    "language": target_language or None,
    "skills": skill_names,
    "changes": changes,
    "model": model,
    "message": "邮件草稿已生成，请确认后使用",
}
```

Reject unsupported operations, missing body for optimize/translate/rewrite, missing instruction for rewrite, and unsupported translation languages before calling a Skill.

- [ ] **Step 7: Add redacted audit logging**

Use structured `extra` fields and never include subject, body, instruction, recipient email, or raw context:

```python
_logger.info(
    "email_agent_completed",
    extra={
        "agent_name": "email-agent",
        "operation": operation,
        "skill_names": skill_names,
        "company_id": str(payload.get("companyId") or ""),
        "contact_id": str(payload.get("contactId") or ""),
        "model": model,
        "duration_ms": duration_ms,
        "status": "success",
    },
)
```

Add failure logging with `status="failed"` and `error_type`, then re-raise. Test the redaction with `assertLogs()`.

- [ ] **Step 8: Run orchestration tests**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_email_agent -v`

Expected: PASS.

- [ ] **Step 9: Commit orchestration**

```bash
git add apps/api/src/ltc/modules/customer_operation/application/email_agent.py apps/api/src/ltc/modules/customer_operation/infrastructure/email_context_builder.py apps/api/tests/test_email_agent.py
git commit -m "feat(operation): orchestrate email agent skills"
```

---

### Task 4: Expose the authenticated Agent API and preserve legacy routes

**Files:**
- Modify: `apps/api/src/ltc/modules/customer_operation/application/email_delivery_service.py`
- Modify: `apps/api/src/ltc/modules/customer_operation/interfaces/router.py`
- Modify: `apps/api/tests/test_customer_operation_auth.py`
- Modify: `apps/api/tests/test_user_mailbox_isolation.py`

- [ ] **Step 1: Add failing authentication and ownership tests**

Add `/api/v1/customer-operation/email/agent` to the unauthenticated request table and add these authenticated cases:

```python
def test_sales_email_agent_requires_company_access(self) -> None:
    service = Mock()
    service.can_sales_access_company.return_value = False
    app = _app(service)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(_actor("sales"), uuid4())

    with patch("ltc.modules.customer_operation.interfaces.router.run_email_agent_for_payload") as run_agent:
        response = TestClient(app).post(
            "/api/v1/customer-operation/email/agent",
            json={"companyId": str(uuid4()), "contactId": str(uuid4()), "operation": "generate"},
        )

    self.assertEqual(response.status_code, 404)
    run_agent.assert_not_called()
```

Also assert that an authenticated caller's display name and `salesUserId` replace spoofed request values before delegation.

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_customer_operation_auth -v`

Expected: FAIL because the Agent route and wrapper do not exist.

- [ ] **Step 3: Add the application entry point**

In `email_agent.py`:

```python
EMAIL_AGENT = EmailAgent()


async def run_email_agent_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return await EMAIL_AGENT.run(payload)
```

- [ ] **Step 4: Add the FastAPI route**

Add `POST /customer-operation/email/agent`. Require non-empty `companyId` and `contactId`, call `require_company_access(UUID(company_id), context)`, overwrite `salesName` with `context.actor.display_name`, set `salesUserId` for sales accounts, and map `ValueError` to 400 and other Agent errors to 502. Invalid UUID input must also return 400.

- [ ] **Step 5: Keep legacy response shapes**

Update legacy generation/translation wrappers only to read unified Skill fields while continuing to return `subject/body` and `translatedText` respectively. Do not route `/email/send` through the Agent.

- [ ] **Step 6: Run focused API tests**

Run: `cd apps/api && PYTHONPATH=src python -m unittest tests.test_customer_operation_auth tests.test_user_mailbox_isolation tests.test_email_agent -v`

Expected: PASS.

- [ ] **Step 7: Commit API exposure**

```bash
git add apps/api/src/ltc/modules/customer_operation/application/email_agent.py apps/api/src/ltc/modules/customer_operation/application/email_delivery_service.py apps/api/src/ltc/modules/customer_operation/interfaces/router.py apps/api/tests/test_customer_operation_auth.py apps/api/tests/test_user_mailbox_isolation.py
git commit -m "feat(api): expose authenticated email agent"
```

---

### Task 5: Publish the OpenAPI contract

**Files:**
- Modify: `contracts/openapi/LTC_OpenAPI_v3.6.yaml`
- Modify: `contracts/v3.6.sha256`
- Modify: `tests/contract/test_v3_6_repository.py`

- [ ] **Step 1: Add the failing contract assertion**

```python
def test_email_agent_contract_is_declared(self) -> None:
    self.assertIn("/customer-operation/email/agent:", self.openapi)
    self.assertIn("operationId: runEmailAgent", self.openapi)
    self.assertIn("EmailAgentRequest:", self.openapi)
    self.assertIn("EmailAgentResult:", self.openapi)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.contract.test_v3_6_repository.FrozenContractTests.test_email_agent_contract_is_declared -v`

Expected: FAIL because the path and schemas are absent.

- [ ] **Step 3: Add path and schemas**

Document the protected JSON endpoint with operation ID `runEmailAgent`, request fields `companyId`, `contactId`, `subject`, `body`, `instruction`, `operation`, and `targetLanguage`; constrain operations to `generate`, `optimize`, `translate`, `rewrite`. Define a result with `success`, `agent: email-agent`, `operation`, `subject`, `body`, `language`, `skills`, `changes`, `model`, and `message`, plus 400/401/404/502 responses.

- [ ] **Step 4: Update the frozen checksum**

```powershell
$hash = (Get-FileHash contracts/openapi/LTC_OpenAPI_v3.6.yaml -Algorithm SHA256).Hash.ToLower()
$manifest = Get-Content contracts/v3.6.sha256
$manifest = $manifest -replace '^[0-9a-f]{64}  contracts/openapi/LTC_OpenAPI_v3.6.yaml$', "$hash  contracts/openapi/LTC_OpenAPI_v3.6.yaml"
[System.IO.File]::WriteAllLines((Resolve-Path contracts/v3.6.sha256), $manifest, [System.Text.UTF8Encoding]::new($false))
```

- [ ] **Step 5: Run contract tests**

Run: `python -m unittest tests.contract.test_v3_6_repository tests.contract.boundary.test_module_boundary -v`

Expected: PASS, including the checksum manifest test.

- [ ] **Step 6: Commit contract changes**

```bash
git add contracts/openapi/LTC_OpenAPI_v3.6.yaml contracts/v3.6.sha256 tests/contract/test_v3_6_repository.py
git commit -m "docs(api): define email agent contract"
```

---

### Task 6: Add typed frontend Agent payloads

**Files:**
- Modify: `apps/web/src/services/operationApi.ts`
- Modify: `apps/web/src/features/customer-operation/emailDraft.js`
- Modify: `apps/web/src/features/customer-operation/emailDraft.d.ts`
- Modify: `apps/web/tests/emailDraft.test.mjs`

- [ ] **Step 1: Add failing payload-helper test**

```javascript
import { buildEmailAgentPayload } from '../src/features/customer-operation/emailDraft.js';

const agentPayload = buildEmailAgentPayload({
  customer,
  contact,
  subject: 'Re: Topic',
  body: base,
  instruction: '强调 GDPR 合规',
  operation: 'rewrite',
  targetLanguage: 'en',
});

assert.deepEqual(agentPayload, {
  companyId: 'company-1',
  contactId: 'contact-1',
  customerName: 'GlobalLink Travel',
  recipientName: 'Sarah Chen',
  recipientEmail: 's.chen@globallink.com',
  recipientTitle: 'Head of Technology',
  subject: 'Re: Topic',
  body: base,
  instruction: '强调 GDPR 合规',
  operation: 'rewrite',
  targetLanguage: 'en',
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/web && node --test tests/emailDraft.test.mjs`

Expected: FAIL because `buildEmailAgentPayload` is not exported.

- [ ] **Step 3: Implement payload helper and declaration**

```javascript
export const buildEmailAgentPayload = ({
  customer,
  contact,
  subject = '',
  body = '',
  instruction = '',
  operation,
  targetLanguage = '',
}) => ({
  companyId: customer.companyId || customer.company_id || '',
  contactId: contact.contactId || contact.contact_id || '',
  customerName: customer.name || customer.customerName || '',
  recipientName: contact.name || '',
  recipientEmail: contact.email || contact.primary_email || '',
  recipientTitle: contact.role || contact.title || '',
  subject,
  body,
  instruction: instruction.trim(),
  operation,
  targetLanguage,
});
```

Declare `EmailAgentOperation = 'generate' | 'optimize' | 'translate' | 'rewrite'` and the helper argument/result types in `emailDraft.d.ts`.

- [ ] **Step 4: Add typed API method**

Add to `operationApi.ts`:

```typescript
export interface EmailAgentPayload {
  companyId: string;
  contactId: string;
  customerName?: string;
  recipientName?: string;
  recipientEmail?: string;
  recipientTitle?: string;
  subject?: string;
  body?: string;
  instruction?: string;
  operation: EmailAgentOperation;
  targetLanguage?: string;
}

export interface EmailAgentResult {
  success: boolean;
  agent: 'email-agent';
  operation: EmailAgentOperation;
  subject: string;
  body: string;
  language?: string | null;
  skills: string[];
  changes: string[];
  model: string;
  message: string;
}

async runEmailAgent(payload: EmailAgentPayload) {
  const { data } = await operationHttp.post<EmailAgentResult>('/customer-operation/email/agent', payload);
  return data;
},
```

Keep `generateEmail()` and `translateEmail()` for legacy callers.

- [ ] **Step 5: Run frontend contract checks**

Run: `cd apps/web && node --test tests/emailDraft.test.mjs && npm run typecheck`

Expected: PASS.

- [ ] **Step 6: Commit frontend client contracts**

```bash
git add apps/web/src/services/operationApi.ts apps/web/src/features/customer-operation/emailDraft.js apps/web/src/features/customer-operation/emailDraft.d.ts apps/web/tests/emailDraft.test.mjs
git commit -m "feat(web): add email agent client contract"
```

---

### Task 7: Integrate non-destructive Agent preview into the active page

**Files:**
- Modify: `apps/web/src/features/customer-operation/CustomerOperation.vue`
- Create: `apps/web/tests/customerOperationEmailAgent.test.mjs`
- Modify: `apps/web/tests/customerOperationEmailTranslation.test.mjs`

**UI checkpoint:** Preserve the existing layout and result modal. Before editing this task, show the user the exact proposed copy change: translation keeps `翻译结果`; generation/rewrite uses `邮件调整结果`; the existing confirmation action applies the candidate. No new panel, button, CSS rule, or layout container is allowed.

- [ ] **Step 1: Add failing non-destructive preview contract**

Create `customerOperationEmailAgent.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/features/customer-operation/CustomerOperation.vue', import.meta.url),
  'utf8',
);

assert.match(source, /const emailAgentCandidate = ref<EmailAgentResult \| null>\(null\)/);
assert.match(source, /await operationApi\.runEmailAgent\(/);
assert.match(source, /emailAgentCandidate\.value = result/);
assert.match(source, /const confirmEmailReplacement = \(\) => \{[\s\S]*emailSubject\.value = emailAgentCandidate\.value\.subject[\s\S]*emailDraft\.value = emailAgentCandidate\.value\.body/);
assert.doesNotMatch(source, /runEmailAgent\([\s\S]*?emailSubject\.value = result\.subject[\s\S]*?emailDraft\.value = result\.body/);

console.log('customer operation email agent test passed');
```

- [ ] **Step 2: Update the translation contract test**

Require `runEmailAgent(buildEmailAgentPayload(... operation: 'translate', targetLanguage: selectedTranslateLanguage.value.key ...))` and keep assertions for loading, result display, and no fixed local template.

- [ ] **Step 3: Run and verify failure**

Run: `cd apps/web && node --test tests/customerOperationEmailAgent.test.mjs tests/customerOperationEmailTranslation.test.mjs`

Expected: FAIL because the page calls legacy methods and directly replaces regenerated drafts.

- [ ] **Step 4: Add candidate state without layout changes**

Import `EmailAgentResult` and `buildEmailAgentPayload`, then add:

```typescript
const emailAgentCandidate = ref<EmailAgentResult | null>(null);
const emailAgentPreviewTitle = computed(() =>
  emailAgentCandidate.value?.operation === 'translate'
    ? `${selectedTranslateLanguage.value.name}翻译结果`
    : '邮件调整结果',
);
```

- [ ] **Step 5: Route regeneration through the Agent**

Use `operation: 'generate'` when the current body is empty and `operation: 'rewrite'` when it is present. Pass customer/contact, current subject/body, and the optimization instruction to `runEmailAgent()`. Store the response in `emailAgentCandidate`; do not assign its subject/body to the active editor.

- [ ] **Step 6: Route history replies through explicit generation**

`generateFromEmailHistory()` passes the historical subject/body as context, operation `generate`, and its reply/follow-up instruction. Store the result as a candidate. Set `emailPurpose = 'reply_followup'` and clear selected history only after confirmation.

- [ ] **Step 7: Route translation through the Agent**

Pass current subject/body and selected language with operation `translate`; store the complete response in `emailAgentCandidate`. Keep existing loading/error behavior and send flow.

- [ ] **Step 8: Apply both fields only from confirmation**

```typescript
const confirmEmailReplacement = () => {
  if (!emailAgentCandidate.value) return;
  emailSubject.value = emailAgentCandidate.value.subject || emailSubject.value;
  emailDraft.value = emailAgentCandidate.value.body;
  if (emailAgentCandidate.value.operation === 'generate' && selectedEmailHistory.value) {
    emailPurpose.value = 'reply_followup';
    selectedEmailHistory.value = null;
  }
  emailAgentCandidate.value = null;
  emailTranslateOpen.value = false;
  emailTranslateMenuOpen.value = false;
  emailReplaceConfirmOpen.value = false;
  emailFeedback.value = '已使用确认后的邮件版本。';
};
```

Closing/cancelling the preview clears only the candidate and leaves the active subject/body unchanged.

- [ ] **Step 9: Reuse existing result markup**

Bind the current result title to `emailAgentPreviewTitle`, display `emailAgentCandidate.body`, and keep existing CSS classes and confirmation controls. Do not add a new panel or stylesheet rule.

- [ ] **Step 10: Run focused frontend tests and type checking**

Run: `cd apps/web && node --test tests/emailDraft.test.mjs tests/customerOperationEmailAgent.test.mjs tests/customerOperationEmailTranslation.test.mjs tests/customerOperationEmailCursor.test.mjs && npm run typecheck`

Expected: PASS.

- [ ] **Step 11: Commit active-page integration**

```bash
git add apps/web/src/features/customer-operation/CustomerOperation.vue apps/web/tests/customerOperationEmailAgent.test.mjs apps/web/tests/customerOperationEmailTranslation.test.mjs
git commit -m "feat(web): preview email agent results before apply"
```

---

### Task 8: Run complete regression gates

**Files:**
- Verify only; no planned source changes.

- [ ] **Step 1: Run focused API tests**

```powershell
cd apps/api
$env:PYTHONPATH='src'
python -m unittest tests.test_email_agent tests.test_customer_operation_auth tests.test_user_mailbox_isolation -v
```

Expected: PASS.

- [ ] **Step 2: Run customer-operation API and contract suites**

```powershell
cd apps/api
$env:PYTHONPATH='src'
python -m unittest tests.test_customer_operation_real_routes tests.test_customer_operation_repository_isolation tests.test_customer_panel_ownership -v
cd ../..
python -m unittest tests.contract.test_v3_6_repository tests.contract.boundary.test_module_boundary -v
```

Expected: PASS. Report pre-existing or environment-only failures instead of fixing unrelated code.

- [ ] **Step 3: Run frontend tests and production build**

```powershell
cd apps/web
node --test tests/emailDraft.test.mjs tests/customerOperationEmailAgent.test.mjs tests/customerOperationEmailTranslation.test.mjs tests/customerOperationEmailCursor.test.mjs
npm run typecheck
npm run build
```

Expected: PASS and successful Vite output.

- [ ] **Step 4: Run repository gate when services are available**

Run: `make test`

Expected: PASS. If Docker/PostgreSQL is unavailable, preserve focused-test evidence and report the blocker.

- [ ] **Step 5: Review prohibited frontend changes**

Run:

```powershell
git diff -- apps/web/src/features/customer-operation/CustomerOperation.vue
git diff --check
```

Expected: no new layout containers, CSS changes, Agent chat panel, direct Agent-result assignment outside confirmation, or whitespace errors.

- [ ] **Step 6: Commit only task-scoped verification corrections**

```bash
git status --short
git diff --check
git commit -am "fix(operation): complete email agent verification"
```

Do not commit unrelated formatting or pre-existing failures.
