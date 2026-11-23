# Email Agent Official Skill Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Use official-style `SKILL.md`, `scripts`, `references`, and `assets` directories while defining `email-agent` separately under `agents/email_agent`.

**Architecture:** The Agent owns orchestration and a central `skills.json` manifest. Each Skill owns its instructions, executable script, references, and optional assets. The existing application import is a compatibility facade.

---

### Tasks

- [x] Add discovery tests for ordered Skills, duplicate metadata, malformed frontmatter, and nested scripts.
- [x] Move four built-in Skills to `skills/<skill>/scripts`, `references`, and `assets`.
- [x] Move the canonical Agent to `agents/email_agent/agent.py` with `AGENT.md` and `skills.json`.
- [x] Update the loader to read the central manifest and validate nested entrypoints.
- [x] Keep `application/email_agent.py` as a compatibility re-export.
- [ ] Run the full backend and frontend verification suite.
- [ ] Restart API and Web and confirm HTTP 200 responses.
