# Email Agent Skill Directory Design

## Goal

Use official-style Skill folders for customer-operation email capabilities while keeping the LTC runtime adapter and current API/frontend contracts stable.

## Final layout

```text
customer_operation/
├─ agents/
│  └─ email_agent/
│     ├─ AGENT.md
│     ├─ agent.py
│     └─ skills.json
└─ skills/
   └─ email-optimize/
      ├─ SKILL.md
      ├─ scripts/optimize.py
      ├─ references/email-optimization.md
      └─ assets/
```

`AGENT.md` documents orchestration boundaries. `agent.py` owns request validation, context use, Skill planning, result validation, and audit behavior. `skills.json` is the Agent-owned runtime manifest because the standard Skill directory should not contain LTC-specific registry metadata.

Each Skill owns its instructions in `SKILL.md`, executable code in `scripts/`, model references in `references/`, and optional static resources in `assets/`.

## Runtime behavior

The loader scans the `skills/` root using the manifest from `agents/email_agent/skills.json`. It validates Skill names, frontmatter, registry names, operations, order, and nested entrypoints. Multiple Skills can share an operation and run in ascending order.

The application-layer `email_agent.py` remains a compatibility re-export so existing imports and API routes do not change. New code and the canonical Agent definition live under `agents/email_agent/`.

## Constraints

- No frontend layout or public API change.
- No automatic sending.
- No database migration.
- Existing operations accept new Skills without changing Agent code.
- A new operation still needs backend validation, OpenAPI, frontend types, and a trigger.
