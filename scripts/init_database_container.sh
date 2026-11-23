#!/usr/bin/env sh
set -eu

cd /workspace

database_host=${LTC_DB_HOST:-postgres}
database_port=${LTC_DB_PORT:-5432}
database_user=${LTC_DB_USER:-ltc}
database_name=${LTC_DB_NAME:-ltc}
migration_file=db/migrations/0001_v3_6_initial.sql
mailbox_migration_file=db/migrations/0002_email_mailbox_monitor.sql
mailbox_secret_migration_file=db/migrations/0003_email_mailbox_monitor_secret_value.sql
seed_file=db/seeds/0001_region_country_v5.sql
customer_operation_seed_file=db/seeds/0002_customer_operation_demo.sql
lead_demo_seed_file=db/seeds/0003_lead_demo_leads.sql
export PGPASSWORD=${LTC_DB_PASSWORD:-ltc_local_change_me}

artifact_sha256() {
  sha256sum "$1" | awk '{print $1}'
}

psql_exec() {
  psql -X -q -v ON_ERROR_STOP=1 \
    -h "$database_host" -p "$database_port" \
    -U "$database_user" -d "$database_name" "$@"
}

attempt=0
until pg_isready -h "$database_host" -p "$database_port" -U "$database_user" -d "$database_name" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 45 ]; then
    echo "PostgreSQL did not become ready within 45 seconds" >&2
    exit 1
  fi
  sleep 1
done

server_version=$(psql_exec -A -t -c "SHOW server_version_num;")
if [ "$server_version" -lt 160000 ] || [ "$server_version" -ge 170000 ]; then
  echo "PostgreSQL 16 is required; server_version_num=$server_version" >&2
  exit 1
fi

migration_checksum=$(artifact_sha256 "$migration_file")
seed_checksum=$(artifact_sha256 "$seed_file")
customer_operation_seed_checksum=$(artifact_sha256 "$customer_operation_seed_file")
lead_demo_seed_checksum=$(artifact_sha256 "$lead_demo_seed_file")
schema_exists=$(psql_exec -A -t -c "SELECT to_regnamespace('ltc') IS NOT NULL;")

if [ "$schema_exists" = "f" ]; then
  psql_exec < "$migration_file"
else
  recorded_checksum=$(psql_exec -A -t -c "SELECT sha256 FROM public.ltc_schema_artifact WHERE artifact_name='0001_v3_6_initial.sql';" 2>/dev/null || true)
  if [ -z "$recorded_checksum" ]; then
    echo "ltc schema exists without the v3.6 artifact record; refusing to guess its origin" >&2
    exit 1
  fi
  if [ "$recorded_checksum" != "$migration_checksum" ]; then
    echo "initial migration checksum drifted; create a new migration instead of editing 0001" >&2
    exit 1
  fi
fi

psql_exec -c "
CREATE TABLE IF NOT EXISTS public.ltc_schema_artifact (
    artifact_name text PRIMARY KEY,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256)
VALUES ('0001_v3_6_initial.sql', '$migration_checksum')
ON CONFLICT (artifact_name) DO NOTHING;
"

if [ -f "$mailbox_migration_file" ]; then
  mailbox_migration_checksum=$(artifact_sha256 "$mailbox_migration_file")
  mailbox_recorded_checksum=$(psql_exec -A -t -c "SELECT sha256 FROM public.ltc_schema_artifact WHERE artifact_name='0002_email_mailbox_monitor.sql';" 2>/dev/null || true)
  if [ -z "$mailbox_recorded_checksum" ]; then
    psql_exec < "$mailbox_migration_file"
    psql_exec -c "
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256, applied_at)
VALUES ('0002_email_mailbox_monitor.sql', '$mailbox_migration_checksum', clock_timestamp())
ON CONFLICT (artifact_name) DO UPDATE
SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at;
"
  elif [ "$mailbox_recorded_checksum" != "$mailbox_migration_checksum" ]; then
    echo "mailbox monitor migration checksum drifted; create a new migration instead of editing 0002" >&2
    exit 1
  fi
fi

if [ -f "$mailbox_secret_migration_file" ]; then
  mailbox_secret_migration_checksum=$(artifact_sha256 "$mailbox_secret_migration_file")
  mailbox_secret_recorded_checksum=$(psql_exec -A -t -c "SELECT sha256 FROM public.ltc_schema_artifact WHERE artifact_name='0003_email_mailbox_monitor_secret_value.sql';" 2>/dev/null || true)
  if [ -z "$mailbox_secret_recorded_checksum" ]; then
    psql_exec < "$mailbox_secret_migration_file"
    psql_exec -c "
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256, applied_at)
VALUES ('0003_email_mailbox_monitor_secret_value.sql', '$mailbox_secret_migration_checksum', clock_timestamp())
ON CONFLICT (artifact_name) DO UPDATE
SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at;
"
  elif [ "$mailbox_secret_recorded_checksum" != "$mailbox_secret_migration_checksum" ]; then
    echo "mailbox secret migration checksum drifted; create a new migration instead of editing 0003" >&2
    exit 1
  fi
fi

# Apply additive migrations after the immutable v3.6 baseline. Each migration
# is recorded independently so rerunning database-init is idempotent.
for migration_path in db/migrations/*.sql; do
  migration_name=$(basename "$migration_path")
  if [ "$migration_name" = "0001_v3_6_initial.sql" ]; then
    continue
  fi
  migration_checksum=$(artifact_sha256 "$migration_path")
  applied_checksum=$(psql_exec -A -t -c "SELECT sha256 FROM public.ltc_schema_artifact WHERE artifact_name='$migration_name';" || true)
  if [ -z "$applied_checksum" ]; then
    psql_exec < "$migration_path"
    psql_exec -c "INSERT INTO public.ltc_schema_artifact (artifact_name, sha256) VALUES ('$migration_name', '$migration_checksum');"
  elif [ "$applied_checksum" != "$migration_checksum" ]; then
    echo "migration checksum drifted: $migration_name" >&2
    exit 1
  fi
done

psql_exec < "$seed_file"
psql_exec -c "
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256, applied_at)
VALUES ('0001_region_country_v5.sql', '$seed_checksum', clock_timestamp())
ON CONFLICT (artifact_name) DO UPDATE
SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at;
"

psql_exec < "$customer_operation_seed_file"
psql_exec -c "
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256, applied_at)
VALUES ('0002_customer_operation_demo.sql', '$customer_operation_seed_checksum', clock_timestamp())
ON CONFLICT (artifact_name) DO UPDATE
SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at;
"

psql_exec < "$lead_demo_seed_file"
psql_exec -c "
INSERT INTO public.ltc_schema_artifact (artifact_name, sha256, applied_at)
VALUES ('0003_lead_demo_leads.sql', '$lead_demo_seed_checksum', clock_timestamp())
ON CONFLICT (artifact_name) DO UPDATE
SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at;
"

catalog_shape=$(psql_exec -A -t -c "
SELECT
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ltc' AND c.relkind='r') || ':' ||
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ltc' AND c.relkind='v') || ':' ||
    (SELECT count(*) FROM ltc.ref_region_country) || ':' ||
    (SELECT count(DISTINCT region_code) FROM ltc.ref_region_country) || ':' ||
    (SELECT count(*) FROM ltc.lead_candidate);
")

catalog_view_count=$(printf '%s' "$catalog_shape" | cut -d: -f2)
catalog_country_count=$(printf '%s' "$catalog_shape" | cut -d: -f3)
catalog_region_count=$(printf '%s' "$catalog_shape" | cut -d: -f4)
catalog_candidate_count=$(printf '%s' "$catalog_shape" | cut -d: -f5)

if [ "$catalog_view_count" -ne 3 ] || \
   [ "$catalog_country_count" -ne 205 ] || \
   [ "$catalog_region_count" -ne 6 ] || \
   [ "$catalog_candidate_count" -lt 20 ]; then
  echo "unexpected database catalog shape: $catalog_shape" >&2
  exit 1
fi

echo "LTC v3.6 database initialized: PostgreSQL $server_version, catalog=$catalog_shape"
