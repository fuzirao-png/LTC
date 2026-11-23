# Database

PostgreSQL 16 is the only formal business store. SQLite, JSON files, memory stores, and frontend fixtures under the legacy directories are migration inputs only.

## Artifact order

1. `migrations/0001_v3_6_initial.sql`
2. `seeds/0001_region_country_v5.sql`

The files are copied from the reviewed v3.6 architecture package without schema changes. Do not edit the initial migration after it has been distributed. Add a new numbered migration instead.

## Local initialization

```bash
cp .env.example .env
./scripts/init_database.sh
```

The initializer:

- runs inside the `database-init` Compose service and starts its PostgreSQL dependency;
- requires PostgreSQL major version 16;
- records SHA-256 checksums in `public.ltc_schema_artifact`;
- refuses an unexplained existing `ltc` schema or a changed initial Migration;
- applies the idempotent region-country seed;
- verifies 42 tables, 3 views, 205 countries/regions, and 6 allocation regions.

For a completely disposable verification, without using the Compose volume:

```bash
make db-verify
```

This runs the verifier in Docker, creates a randomly named PostgreSQL 16 container without a host volume, executes positive and negative invariants, runs two-session concurrency tests, verifies a full backup/restore, and removes the container.

Production roles, credentials, backup retention, and PITR are deployment concerns. They must not be embedded in the Migration or committed `.env` files.
