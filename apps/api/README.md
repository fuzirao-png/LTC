# LTC Core API foundation

This directory is the FastAPI modular-monolith boundary defined by the v3.6 architecture baseline.

Current implementation includes:

- one application factory and `/health/live` endpoint;
- centralized `LTC_*` runtime settings injected by Compose;
- five business modules plus query-only `read_models`;
- explicit ownership of all 42 database tables: 34 by modules and 8 by Task Runtime platform capabilities;
- architecture tests for layer direction and framework-free domains.

Business routers are intentionally added only with implemented Application Use Cases. IAM, dialogue search, Job persistence/SSE, Provider adapters, ICP scoring, pool assignment, and customer operations are not represented by placeholder routes.

## Layer contract

Each business module uses `interfaces`, `application`, `domain`, and `infrastructure`. Dependencies point inward; infrastructure implements ports. `read_models` contains only `interfaces` and `queries`.

## Docker commands

Run from the repository root:

```bash
make api-run
make api-test
```

Configuration belongs in the repository-root `.env`, copied from `.env.example`. Do not create module-local environment files.
