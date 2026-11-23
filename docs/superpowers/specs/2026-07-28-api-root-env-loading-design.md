# API Root Environment Loading Design

## Problem

The API configuration loader only checks process environment variables and `Path.cwd() / .env`. Local launch scripts start Uvicorn with `apps/api` as the working directory, while the supported configuration file lives at the repository root. As a result, local API processes silently use defaults and do not create the inbound-mail poller.

## Design

Keep process environment variables as the highest-priority source and keep the current-working-directory `.env` as the first file fallback. Add one safe repository-root fallback discovered by walking ancestors of the configuration module and selecting the first directory that contains both `compose.yaml` and `apps/api`.

This avoids the previous fixed `parents[5]` implementation, which was unsafe in the Docker filesystem layout. Docker continues to use Compose-provided environment variables and does not depend on a repository `.env` inside the image.

## Precedence

1. Process environment variable.
2. `.env` in the current working directory.
3. `.env` in the detected repository root.
4. Existing default value.

## Verification

- Add a regression test that simulates running from `apps/api` while `.env` exists only at the repository root.
- Preserve tests for process-environment precedence and defaults.
- Start the API from `apps/api`, verify inbound mail is enabled, and verify `/api/v1/inbound-mail/poll-now` no longer returns `503`.
