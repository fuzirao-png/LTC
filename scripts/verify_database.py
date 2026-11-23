#!/usr/bin/env python3
"""Run the repository-local PostgreSQL 16 acceptance suite for LTC v3.6."""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "db/migrations"
SEED_SQL = ROOT / "db/seeds/0001_region_country_v5.sql"
INVARIANT_SQL = ROOT / "tests/integration/sql/001_core_invariants.sql"
CUSTOMER_ANALYSIS_SQL = ROOT / "tests/integration/sql/002_customer_analysis_flow.sql"
CUSTOMER_ANALYSIS_PY = ROOT / "tests/integration/verify_customer_analysis.py"


class AcceptanceFailure(RuntimeError):
    pass


def migration_files(directory: Path = MIGRATIONS_DIR) -> tuple[Path, ...]:
    return tuple(sorted(directory.glob("*.sql"), key=lambda path: path.name))


def expected_catalog_shape(migrations: tuple[Path, ...] | None = None) -> tuple[int, int]:
    table_names: set[str] = set()
    view_names: set[str] = set()
    for migration in migrations or migration_files():
        sql = migration.read_text(encoding="utf-8")
        table_names.update(
            re.findall(r"(?im)^CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+ltc\.([a-z_][a-z0-9_]*)", sql)
        )
        view_names.update(
            re.findall(r"(?im)^CREATE(?:\s+OR\s+REPLACE)?\s+VIEW\s+ltc\.([a-z_][a-z0-9_]*)", sql)
        )
    return len(table_names), len(view_names)


def run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        raise AcceptanceFailure(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class PostgresContainer:
    def __init__(self, image: str, keep: bool) -> None:
        suffix = uuid.uuid4().hex[:10]
        self.name = f"ltc-v36-acceptance-{suffix}"
        self.image = image
        self.keep = keep
        self.database = "ltc_acceptance"
        self.password = secrets.token_urlsafe(24)

    def start(self) -> None:
        run(
            [
                "docker",
                "run",
                "--name",
                self.name,
                "-e",
                f"POSTGRES_PASSWORD={self.password}",
                "-e",
                f"POSTGRES_DB={self.database}",
                "-d",
                self.image,
            ]
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = run(
                [
                    "docker",
                    "exec",
                    self.name,
                    "pg_isready",
                    "-U",
                    "postgres",
                    "-d",
                    self.database,
                ],
                check=False,
            )
            if ready.returncode == 0:
                return
            time.sleep(1)
        logs = run(["docker", "logs", self.name], check=False)
        raise AcceptanceFailure(f"PostgreSQL did not become ready:\n{logs.stdout}\n{logs.stderr}")

    def cleanup(self) -> None:
        if self.keep:
            print(f"[keep] disposable container retained: {self.name}")
            return
        run(["docker", "rm", "-f", self.name], check=False)

    def copy(self, source: Path, destination: str) -> None:
        run(["docker", "cp", str(source), f"{self.name}:{destination}"])

    def exec(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run(["docker", "exec", self.name, *args], check=check)

    def psql(
        self,
        sql: str,
        *,
        database: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.exec(
            [
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                database or self.database,
                "-c",
                sql,
            ],
            check=check,
        )

    def psql_file(self, source: Path, remote_name: str) -> None:
        destination = f"/tmp/{remote_name}"
        self.copy(source, destination)
        self.exec(
            [
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                self.database,
                "-f",
                destination,
            ]
        )

    def scalar(self, sql: str, *, database: str | None = None) -> str:
        result = self.exec(
            [
                "psql",
                "-X",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                database or self.database,
                "-c",
                sql,
            ]
        )
        return result.stdout.strip()


def assert_catalog(container: PostgresContainer) -> None:
    expected_tables, expected_views = expected_catalog_shape()
    sql = rf"""
DO $$
DECLARE
    table_count integer;
    view_count integer;
    invalid_constraint_count integer;
    invalid_index_count integer;
    missing_critical_trigger_count integer;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ltc' AND c.relkind = 'r';

    SELECT COUNT(*) INTO view_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ltc' AND c.relkind = 'v';

    SELECT COUNT(*) INTO invalid_constraint_count
    FROM pg_constraint con
    JOIN pg_namespace n ON n.oid = con.connamespace
    WHERE n.nspname = 'ltc' AND NOT con.convalidated;

    SELECT COUNT(*) INTO invalid_index_count
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ltc' AND NOT i.indisvalid;

    SELECT COUNT(*) INTO missing_critical_trigger_count
    FROM unnest(ARRAY[
        'trg_user_account_status_transition',
        'ct_sales_lead_assignment_consistency_on_lead',
        'ct_sales_lead_assignment_consistency_on_assignment',
        'ct_user_assignment_consistency',
        'trg_lead_assignment_no_hard_delete',
        'trg_lead_stage_transition_no_hard_delete',
        'trg_analysis_report_immutable',
        'trg_analysis_report_no_hard_delete'
    ]) AS required(trigger_name)
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger t
        WHERE t.tgname = required.trigger_name AND NOT t.tgisinternal
    );

    IF table_count <> {expected_tables} THEN
        RAISE EXCEPTION 'expected {expected_tables} tables, got %', table_count;
    END IF;
    IF view_count <> {expected_views} THEN
        RAISE EXCEPTION 'expected {expected_views} views, got %', view_count;
    END IF;
    IF invalid_constraint_count <> 0 OR invalid_index_count <> 0 THEN
        RAISE EXCEPTION 'invalid catalog objects: constraints=%, indexes=%',
            invalid_constraint_count, invalid_index_count;
    END IF;
    IF missing_critical_trigger_count <> 0 THEN
        RAISE EXCEPTION 'missing % critical triggers', missing_critical_trigger_count;
    END IF;
END;
$$;
"""
    container.psql(sql)

    reference_shape = container.scalar(
        "SELECT count(*) || ':' || count(DISTINCT region_code) || ':' || "
        "count(DISTINCT country_code) || ':' || min(data_version) "
        "FROM ltc.ref_region_country;"
    )
    if reference_shape != "205:6:205:region-country-v5":
        raise AcceptanceFailure(f"unexpected reference seed shape: {reference_shape}")


def assert_job_concurrency(container: PostgresContainer) -> None:
    concurrency_key = f"acceptance:job:{uuid.uuid4()}"

    def insert_job(job_id: str) -> subprocess.CompletedProcess[str]:
        sql = (
            "BEGIN; "
            "INSERT INTO ltc.job "
            "(job_id, job_type, queue_name, concurrency_key, status, payload) VALUES "
            f"('{job_id}', 'acceptance', 'acceptance', '{concurrency_key}', 'queued', '{{}}'::jsonb); "
            "SELECT pg_sleep(0.75); COMMIT;"
        )
        return container.psql(sql, check=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(insert_job, [str(uuid.uuid4()), str(uuid.uuid4())])
        )

    successes = [result for result in results if result.returncode == 0]
    failures = [result for result in results if result.returncode != 0]
    if len(successes) != 1 or len(failures) != 1:
        raise AcceptanceFailure(
            "active job concurrency gate did not produce exactly one winner: "
            f"return_codes={[result.returncode for result in results]}"
        )
    failure_text = f"{failures[0].stdout}\n{failures[0].stderr}".lower()
    if "duplicate key value" not in failure_text:
        raise AcceptanceFailure(f"unexpected concurrency failure:\n{failure_text}")


def assert_claim_concurrency(container: PostgresContainer) -> None:
    lead_id = "00000000-0000-0000-0000-000000000802"
    sales_id = "00000000-0000-0000-0000-000000000102"
    assigned_by = "00000000-0000-0000-0000-000000000101"
    assigned_at = "2026-07-20T00:02:00Z"

    container.psql(
        "BEGIN; "
        "UPDATE ltc.lead_assignment SET status='released', ended_at=clock_timestamp() "
        f"WHERE lead_id='{lead_id}' AND status='active'; "
        "UPDATE ltc.sales_lead SET allocation_status='claimable', "
        "current_owner_user_id=NULL, current_assignment_started_at=NULL, sla_due_at=NULL "
        f"WHERE lead_id='{lead_id}'; COMMIT;"
    )

    def claim(assignment_id: str) -> subprocess.CompletedProcess[str]:
        sql = (
            "BEGIN; "
            "UPDATE ltc.sales_lead SET allocation_status='claimed', "
            f"current_owner_user_id='{sales_id}', "
            f"current_assignment_started_at='{assigned_at}', "
            "sla_due_at='2099-01-01T00:00:00Z' "
            f"WHERE lead_id='{lead_id}' AND allocation_status='claimable'; "
            "INSERT INTO ltc.lead_assignment "
            "(assignment_id, lead_id, assignee_user_id, assigned_by, assignment_type, "
            "status, assigned_at, sla_due_at) VALUES "
            f"('{assignment_id}', '{lead_id}', '{sales_id}', '{assigned_by}', "
            f"'claim', 'active', '{assigned_at}', '2099-01-01T00:00:00Z'); "
            "SELECT pg_sleep(0.75); COMMIT;"
        )
        return container.psql(sql, check=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, [str(uuid.uuid4()), str(uuid.uuid4())]))

    successes = [result for result in results if result.returncode == 0]
    failures = [result for result in results if result.returncode != 0]
    if len(successes) != 1 or len(failures) != 1:
        raise AcceptanceFailure(
            "claim concurrency gate did not produce exactly one winner: "
            f"return_codes={[result.returncode for result in results]}"
        )
    if "duplicate key value" not in f"{failures[0].stdout}\n{failures[0].stderr}".lower():
        raise AcceptanceFailure("claim loser did not fail on the active-assignment uniqueness gate")

    shape = container.scalar(
        "SELECT sl.allocation_status || ':' || count(la.assignment_id) || ':' || "
        "count(la.assignment_id) FILTER (WHERE la.assignee_user_id=sl.current_owner_user_id "
        "AND la.assigned_at=sl.current_assignment_started_at) "
        "FROM ltc.sales_lead sl "
        "JOIN ltc.lead_assignment la ON la.lead_id=sl.lead_id AND la.status='active' "
        f"WHERE sl.lead_id='{lead_id}' GROUP BY sl.lead_id;"
    )
    if shape != "claimed:1:1":
        raise AcceptanceFailure(f"claim concurrency left an invalid final shape: {shape}")


def assert_backup_restore(container: PostgresContainer) -> None:
    restored_database = "ltc_restore"
    source_shape = container.scalar(
        "SELECT "
        "(SELECT count(*) FROM ltc.ref_region_country) || ':' || "
        "(SELECT count(*) FROM ltc.sales_lead) || ':' || "
        "(SELECT count(*) FROM ltc.lead_assignment) || ':' || "
        "(SELECT count(*) FROM ltc.job);"
    )
    container.exec(
        [
            "pg_dump",
            "-U",
            "postgres",
            "-d",
            container.database,
            "-Fc",
            "-f",
            "/tmp/ltc_acceptance.dump",
        ]
    )
    container.exec(["createdb", "-U", "postgres", restored_database])
    container.exec(
        [
            "pg_restore",
            "--exit-on-error",
            "-U",
            "postgres",
            "-d",
            restored_database,
            "/tmp/ltc_acceptance.dump",
        ]
    )
    restored_shape = container.scalar(
        "SELECT "
        "(SELECT count(*) FROM ltc.ref_region_country) || ':' || "
        "(SELECT count(*) FROM ltc.sales_lead) || ':' || "
        "(SELECT count(*) FROM ltc.lead_assignment) || ':' || "
        "(SELECT count(*) FROM ltc.job);",
        database=restored_database,
    )
    if source_shape != restored_shape:
        raise AcceptanceFailure(
            f"backup/restore row-count mismatch: source={source_shape}, restored={restored_shape}"
        )


def validate_files() -> None:
    migrations = migration_files()
    if not migrations:
        raise AcceptanceFailure(f"no database migrations found in {MIGRATIONS_DIR}")
    missing = [path for path in (SEED_SQL, INVARIANT_SQL, CUSTOMER_ANALYSIS_SQL, CUSTOMER_ANALYSIS_PY) if not path.is_file()]
    if missing:
        raise AcceptanceFailure(f"missing acceptance inputs: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument("--keep-container", action="store_true")
    args = parser.parse_args()

    validate_files()
    run(["docker", "info"])

    container = PostgresContainer(args.image, args.keep_container)
    api_image: str | None = None
    try:
        print(f"[1/9] starting disposable PostgreSQL: {args.image}")
        container.start()
        version = container.scalar("SHOW server_version;")
        if not version.startswith("16."):
            raise AcceptanceFailure(f"PostgreSQL 16 required, got {version}")

        migrations = migration_files()
        print(f"[2/9] applying full empty-database migration chain ({len(migrations)} files)")
        for index, migration in enumerate(migrations, start=1):
            container.psql_file(migration, f"001_migration_{index:03d}.sql")

        print("[3/9] applying region-country v5 seed twice (idempotency)")
        container.psql_file(SEED_SQL, "002_region_seed.sql")
        container.psql_file(SEED_SQL, "002_region_seed.sql")
        assert_catalog(container)

        print("[4/9] running state, JSON, history, and view invariants")
        container.psql_file(INVARIANT_SQL, "003_core_invariants.sql")

        print("[5/9] running customer-analysis persistence and restart-read flow")
        container.psql_file(CUSTOMER_ANALYSIS_SQL, "004_customer_analysis_flow.sql")
        api_image = f"ltc-customer-analysis-acceptance:{uuid.uuid4().hex[:10]}"
        run(["docker", "build", "--target", "runtime", "-t", api_image, str(ROOT / "apps/api")])
        application_container = f"ltc-customer-analysis-check-{uuid.uuid4().hex[:10]}"
        try:
            run([
                "docker", "create", "--name", application_container,
                "--network", f"container:{container.name}",
                "--entrypoint", "python", api_image,
                "/tmp/verify_customer_analysis.py", container.database, container.password,
            ])
            run([
                "docker", "cp", str(CUSTOMER_ANALYSIS_PY),
                f"{application_container}:/tmp/verify_customer_analysis.py",
            ])
            application_result = run(["docker", "start", "--attach", application_container])
        finally:
            run(["docker", "rm", "-f", application_container], check=False)
        success_marker = "customer-analysis application persistence flow passed"
        if success_marker not in application_result.stdout:
            raise AcceptanceFailure(
                "customer-analysis application flow completed without success marker\n"
                f"stdout:\n{application_result.stdout}\nstderr:\n{application_result.stderr}"
            )
        print(success_marker)
        run(["docker", "image", "rm", api_image], check=False)
        api_image = None

        print("[6/9] running two-session active-job concurrency test")
        assert_job_concurrency(container)

        print("[7/9] running two-session lead-claim concurrency test")
        assert_claim_concurrency(container)

        print("[8/9] validating full logical backup and restore")
        assert_backup_restore(container)

        print("[9/9] rechecking source catalog after runtime tests")
        assert_catalog(container)
        print(f"PASS: LTC v3.6 database acceptance on PostgreSQL {version}")
        return 0
    except AcceptanceFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        if api_image is not None:
            run(["docker", "image", "rm", api_image], check=False)
        container.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
