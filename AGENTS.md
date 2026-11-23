# Repository Guidelines

## Project Structure & Module Organization

LTC is a modular sales platform with a FastAPI backend, a Vue 3 frontend, a separate Python worker, and PostgreSQL. Backend bounded contexts live in `apps/api/src/ltc/modules/`; each module follows `interfaces/`, `application/`, `domain/`, and `infrastructure/` layers. Shared backend capabilities are under `apps/api/src/ltc/platform/`. Worker handlers and runtime code live in `apps/worker/src/ltc_worker/`. Frontend features, shared components, Pinia stores, and application wiring are in `apps/web/src/`.

Tests are split across `apps/api/tests/`, `apps/worker/tests/`, and repository-level `tests/contract/` and `tests/integration/`. Database migrations and seeds are in `db/migrations/` and `db/seeds/`; API contracts are in `contracts/`; architecture documentation is in `docs/architecture/v3.6/`.

## Build, Test, and Development Commands

- `make up`: initialize PostgreSQL, build, and start API and web services.
- `./start.sh`: install local dependencies and run API on `:8000` and Vite on `:5173`.
- `make test`: run contract, API, worker, frontend build, and database verification gates.
- `make api-test` / `make worker-test`: run the corresponding Python suites in Docker.
- `make web-build`: run Vue type checking and the production Vite build.
- `cd apps/web && npm run dev`: start frontend-only development.

## Coding Style & Naming Conventions

Use four spaces in Python and two spaces in Vue/TypeScript. Follow existing Python conventions: `snake_case` functions and modules, `PascalCase` classes, and explicit type hints at public boundaries. Vue components use `PascalCase.vue`; composables use `useThing`; stores and service modules use descriptive `camelCase` exports. Keep domain code framework-free and dependencies pointing inward. No repository-wide formatter is configured, so match nearby code and keep diffs focused.

## Testing Guidelines

Python tests use stdlib `unittest`, with files named `test_*.py`. Run one API module with `cd apps/api && PYTHONPATH=src python -m unittest tests.test_sales_crm_api -v`. Frontend changes must pass `npm run typecheck` and `npm run build`. Add regression tests for behavior changes and architecture tests when module boundaries or table ownership change.

## Commit & Pull Request Guidelines

History follows concise Conventional Commit-style subjects such as `feat:`, `fix:`, and scoped forms like `fix(web):`. Explain intent in the subject and keep commits narrowly scoped. PRs must summarize what and why, complete `.github/pull_request_template.md`, pass `make test`, and include screenshots for UI changes. Update the OpenAPI contract for API changes, add a new numbered migration for schema changes, and never modify distributed migration `0001`.

## Security & Configuration

Copy `.env.example` for local configuration. Never commit `.env`, tokens, provider keys, passwords, or production connection strings.
