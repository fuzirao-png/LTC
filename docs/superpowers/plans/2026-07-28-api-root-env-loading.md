# API Root Environment Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local API startup load the repository-root `.env` regardless of whether Uvicorn starts from the repository root or `apps/api`.

**Architecture:** Extend the configuration file lookup with marker-based repository-root discovery. Preserve environment-variable and current-directory precedence so Docker and explicit local overrides remain unchanged.

**Tech Stack:** Python 3.12, `pathlib`, `unittest`, FastAPI/Uvicorn

---

### Task 1: Add configuration regression coverage

**Files:**
- Modify: `apps/api/tests/test_config.py`

- [ ] Add a test that builds a temporary repository structure containing `compose.yaml`, `apps/api`, and a root `.env`.
- [ ] Patch the configuration module file location and current working directory to simulate Uvicorn starting from `apps/api`.
- [ ] Assert `get_settings()` reads inbound-mail values from the root `.env`.
- [ ] Run `python -m pytest apps/api/tests/test_config.py -q` and confirm the new test fails because only the current-directory `.env` is checked.

### Task 2: Implement repository-root fallback

**Files:**
- Modify: `apps/api/src/ltc/platform/config.py`

- [ ] Add a helper that returns the current-directory `.env` followed by a repository-root `.env` found using `compose.yaml` and `apps/api` markers.
- [ ] Deduplicate candidates while preserving order.
- [ ] Update `_env()` to iterate over those candidates without changing process-environment precedence.
- [ ] Run `python -m pytest apps/api/tests/test_config.py -q` and confirm all configuration tests pass.

### Task 3: Verify customer-operation startup

**Files:**
- Verify: `apps/api/src/ltc/main.py`
- Verify: `apps/api/src/ltc/modules/customer_operation/infrastructure/mailbox_monitor_store.py`

- [ ] Run the targeted customer-operation skeleton and route tests.
- [ ] Build the web application to ensure no integration regression.
- [ ] Start Uvicorn with `apps/api` as its working directory.
- [ ] Verify `/health/live` returns `200` and `/api/v1/inbound-mail/poll-now` returns success instead of `503`.
