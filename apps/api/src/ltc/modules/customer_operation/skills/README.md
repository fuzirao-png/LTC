# Email Agent Skills

Each child directory is an Agent Skill. The API discovers the Skill directories from the manifest owned by `agents/email_agent` when it starts.

## Layout

```text
skills/
└─ email-edit/
   ├─ SKILL.md
   ├─ scripts/
   │  └─ edit.py
   ├─ references/
   │  └─ email-editing.md
   └─ assets/
      └─ templates.md
```

`assets/` is optional. It is present in the built-in Skills so assets can be added without changing the loader.

## Add a Skill

1. Copy an existing Skill directory and rename it with kebab-case.
2. Update `SKILL.md`, the script class and `name`, the reference files, and optional assets.
3. Add one entry to `agents/email_agent/skills.json` with `directory`, `registry_name`, `operation` or `operations`, `order`, and `entrypoint`.
4. Restart the API. The registry and `email-agent` code do not need to change for an existing operation.

Supported operations are `generate`, `optimize`, `translate`, and `rewrite`. A Skill can declare one `operation` or multiple `operations`. Multiple Skills serving the same operation run in ascending `order`.

A completely new operation still requires backend request validation, OpenAPI, frontend types, and a UI trigger.
