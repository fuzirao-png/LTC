# First-Touch Signature Fallback Implementation Plan

> **For agentic workers:** Execute the tasks inline with test-first checkpoints.

**Goal:** Ensure translated first-touch emails always contain the configured sales signature before quality validation and sending.

**Architecture:** Add a small pure helper beside the email-outreach agent that appends `Best regards,` plus the configured sales name only when the translated body does not already contain that name. Invoke it after translation and before the existing complete-translation and quality checks; retain those checks as a safety net.

**Tech Stack:** Python, stdlib `unittest`, existing email automation agent.

---

### Task 1: Add regression coverage

**Files:**
- Modify: `apps/api/tests/test_email_automation_agent.py`

- [ ] Add tests for missing and existing sales signatures.
- [ ] Run the focused tests and confirm the new missing-signature test fails before implementation.

### Task 2: Implement signature fallback

**Files:**
- Modify: `apps/api/src/ltc/modules/lead_intelligence/agents/email_outreach_agent/agent.py`

- [ ] Add a pure helper that appends `Best regards,\\n{sales_name}` when the configured name is absent, preserving existing body text.
- [ ] Apply the helper to translated bodies before complete-translation validation and sending.

### Task 3: Verify behavior

**Files:**
- No additional files.

- [ ] Run the focused email automation tests.
- [ ] Run the broader API test module if dependencies are available.
- [ ] Run frontend checks only if the change affects generated frontend artifacts; this change does not.
