"""PostgreSQL persistence for customer analysis aggregates.

Transaction model (v3.6):
    transaction() — public context manager for the Application Layer.
        Opens a connection, yields it, commits on clean exit, rollback on
        exception.  Multi-statement write methods accept an optional ``_conn``
        keyword so the Application Layer can coordinate the boundary when
        several repository calls must be atomic.

    Convenience helpers (_execute_one / _execute_all / _execute_none) use
    _connection() internally and commit, so they are safe for single-statement
    operations.

    Write methods WITHOUT a caller-provided _conn manage their own transaction
    so existing single-call usage stays backwards-compatible.

Optimistic locking:
    Every UPSERT includes ``WHERE version = $expected``.  When 0 rows are
    affected a VersionConflictError is raised so the domain layer's
    ``patch()`` check is backed by the database.

Row locking:
    find_run_by_input uses SELECT ... FOR UPDATE to prevent duplicate-run races.
    save_report locks the current report row before superseding.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from datetime import datetime
from typing import Any, Callable, Iterator
from uuid import UUID

from ltc.modules.customer_analysis.domain.errors import (
    InvalidStateError,
    VersionConflictError,
)
from ltc.modules.customer_analysis.domain.models import (
    AnalysisReport,
    AnalysisRun,
    AnalysisSuggestion,
    CustomerProfile,
    MeddpiccDimension,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class PostgresCustomerAnalysisRepository:
    """Strict DB-API repository for the v3.6 customer-analysis tables."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    # ------------------------------------------------------------------
    # Transaction boundaries
    # ------------------------------------------------------------------
    # Two layers:
    #   transaction()  — public, for the Application Layer to coordinate
    #                    multi-call units of work.  Yields the connection;
    #                    commits on clean exit, rollback on exception.
    #   _connection()  — internal helper.  Opens a new connection; commit
    #                    on clean exit, rollback on exception.  Used by the
    #                    convenience query helpers and by single-statement
    #                    write methods that do NOT receive an explicit _conn.

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Public: yield a connection; commit on clean exit, rollback on error.

        Use this from the Application Layer to wrap several repository calls
        in a single atomic unit::

            with repo.transaction() as conn:
                repo.save_run(run, _conn=conn)
                repo.save_report(report, _conn=conn)
        """
        connection = self._connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        """Internal: open connection, commit on clean exit, rollback on error."""
        connection = self._connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            raise
        finally:
            connection.close()

    # ----------------------------------------------------------------
    # Convenience query helpers (use _connection so each query is a
    # self-contained unit — the caller doesn't need to manage a connection).
    # ----------------------------------------------------------------

    def _execute_one(self, query: str, params: tuple[Any, ...] = (), *, _conn: Any = None) -> Any:
        conn = _conn
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
            try:
                cur = conn.cursor()
                cur.execute(query, params)
                return cur.fetchone()
            finally:
                conn_ctx.__exit__(None, None, None)
        else:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchone()

    def _execute_all(self, query: str, params: tuple[Any, ...] = (), *, _conn: Any = None) -> list[Any]:
        conn = _conn
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
            try:
                cur = conn.cursor()
                cur.execute(query, params)
                return cur.fetchall()
            finally:
                conn_ctx.__exit__(None, None, None)
        else:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchall()

    def _execute_none(self, query: str, params: tuple[Any, ...] = (), *, _conn: Any = None) -> None:
        conn = _conn
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
            try:
                cur = conn.cursor()
                cur.execute(query, params)
            finally:
                conn_ctx.__exit__(None, None, None)
        else:
            cur = conn.cursor()
            cur.execute(query, params)

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _json(value: Any) -> Any:
        try:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        except ImportError:
            return json.dumps(value, ensure_ascii=False, default=str)

    # ==================================================================
    # Customer Profile
    # ==================================================================

    _PROFILE_SELECT = """SELECT company_id, company_type, region_text, employee_scale,
        business_model, esim_scenario, coverage, estimated_usage, integration,
        compliance, budget_text, decision_maker_text, decision_maker_contact_id,
        decision_cycle_text, completeness_score, missing_fields, extra_payload,
        field_provenance, source_summary, last_enriched_at, version, updated_by,
        updated_at FROM ltc.customer_profile"""

    def get_profile(self, company_id: UUID) -> CustomerProfile | None:
        row = self._execute_one(
            self._PROFILE_SELECT + " WHERE company_id=%s", (company_id,),
        )
        return self._profile_from_row(row) if row else None

    def save_profile(self, profile: CustomerProfile, *, _conn: Any = None) -> None:
        """Upsert with optimistic-lock guard."""
        if _conn is None:
            with self._connection() as conn:
                self.save_profile(profile, _conn=conn)
            return

        prev_version = profile.version - 1
        conn = _conn
        cur = conn.cursor()
        cur.execute(
                """INSERT INTO ltc.customer_profile (
                company_id, company_type, region_text, employee_scale, business_model,
                esim_scenario, coverage, estimated_usage, integration, compliance,
                budget_text, decision_maker_text, decision_maker_contact_id,
                decision_cycle_text, completeness_score, missing_fields, extra_payload,
                field_provenance, source_summary, last_enriched_at, version, updated_by,
                updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_id) DO UPDATE SET
                company_type=EXCLUDED.company_type, region_text=EXCLUDED.region_text,
                employee_scale=EXCLUDED.employee_scale, business_model=EXCLUDED.business_model,
                esim_scenario=EXCLUDED.esim_scenario, coverage=EXCLUDED.coverage,
                estimated_usage=EXCLUDED.estimated_usage, integration=EXCLUDED.integration,
                compliance=EXCLUDED.compliance, budget_text=EXCLUDED.budget_text,
                decision_maker_text=EXCLUDED.decision_maker_text,
                decision_maker_contact_id=EXCLUDED.decision_maker_contact_id,
                decision_cycle_text=EXCLUDED.decision_cycle_text,
                completeness_score=EXCLUDED.completeness_score,
                missing_fields=EXCLUDED.missing_fields, extra_payload=EXCLUDED.extra_payload,
                field_provenance=EXCLUDED.field_provenance,
                source_summary=EXCLUDED.source_summary,
                last_enriched_at=EXCLUDED.last_enriched_at, version=EXCLUDED.version,
                updated_by=EXCLUDED.updated_by, updated_at=EXCLUDED.updated_at
                WHERE ltc.customer_profile.version = %s""",
                (
                    profile.company_id, profile.company_type, profile.region_text,
                    profile.employee_scale, profile.business_model, profile.esim_scenario,
                    profile.coverage, profile.estimated_usage, profile.integration,
                    profile.compliance, profile.budget_text, profile.decision_maker_text,
                    profile.decision_maker_contact_id, profile.decision_cycle_text,
                    profile.completeness_score, list(profile.missing_fields),
                    self._json(profile.extra_payload), self._json(profile.field_provenance),
                    profile.source_summary, profile.last_enriched_at, profile.version,
                    profile.updated_by, profile.updated_at,
                    prev_version,
                ),
        )
        if cur.rowcount == 0:
            raise VersionConflictError(
                f"profile version {prev_version} was modified concurrently"
            )

    @staticmethod
    def _profile_from_row(row: Any) -> CustomerProfile:
        return CustomerProfile(
            company_id=row[0], company_type=row[1], region_text=row[2],
            employee_scale=row[3], business_model=row[4], esim_scenario=row[5],
            coverage=row[6], estimated_usage=row[7], integration=row[8],
            compliance=row[9], budget_text=row[10], decision_maker_text=row[11],
            decision_maker_contact_id=row[12], decision_cycle_text=row[13],
            completeness_score=float(row[14] or 0), missing_fields=tuple(row[15] or ()),
            extra_payload=PostgresCustomerAnalysisRepository._safe_dict(row[16]),
            field_provenance=PostgresCustomerAnalysisRepository._safe_dict(row[17]),
            source_summary=row[18], last_enriched_at=row[19], version=int(row[20] or 0),
            updated_by=row[21], updated_at=row[22],
        )

    # ==================================================================
    # MEDDPICC Dimensions
    # ==================================================================

    _DIM_SELECT = """SELECT company_id, dimension_code, level, status, summary, payload,
        evidence_refs, version, updated_by, updated_at
        FROM ltc.customer_meddpicc_dimension"""

    def list_meddpicc(self, company_id: UUID) -> list[MeddpiccDimension]:
        rows = self._execute_all(
            self._DIM_SELECT + " WHERE company_id=%s ORDER BY dimension_code",
            (company_id,),
        )
        return [self._dimension_from_row(row) for row in rows]

    def get_meddpicc_dimension(
        self, company_id: UUID, dimension_code: str
    ) -> MeddpiccDimension | None:
        row = self._execute_one(
            self._DIM_SELECT + " WHERE company_id=%s AND dimension_code=%s",
            (company_id, dimension_code),
        )
        return self._dimension_from_row(row) if row else None

    def save_meddpicc_dimension(self, dimension: MeddpiccDimension, *, _conn: Any = None) -> None:
        """Upsert with optimistic-lock guard."""
        prev_version = dimension.version - 1
        conn = _conn
        conn_ctx = None
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ltc.customer_meddpicc_dimension (
                company_id, dimension_code, level, status, summary, payload,
                evidence_refs, version, updated_by, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (company_id, dimension_code) DO UPDATE SET
                level=EXCLUDED.level, status=EXCLUDED.status, summary=EXCLUDED.summary,
                payload=EXCLUDED.payload, evidence_refs=EXCLUDED.evidence_refs,
                version=EXCLUDED.version, updated_by=EXCLUDED.updated_by,
                updated_at=EXCLUDED.updated_at
                WHERE ltc.customer_meddpicc_dimension.version = %s""",
                (
                    dimension.company_id, dimension.dimension_code, dimension.level,
                    dimension.status, dimension.summary, self._json(dimension.payload),
                    self._json(list(dimension.evidence_refs)), dimension.version,
                    dimension.updated_by, dimension.updated_at,
                    prev_version,
                ),
            )
            if cur.rowcount == 0:
                raise VersionConflictError(
                    f"MEDDPICC {dimension.dimension_code} version {prev_version} "
                    f"was modified concurrently"
                )
        finally:
            if conn_ctx is not None:
                conn_ctx.__exit__(None, None, None)

    @staticmethod
    def _dimension_from_row(row: Any) -> MeddpiccDimension:
        payload = PostgresCustomerAnalysisRepository._safe_dict(row[5])
        return MeddpiccDimension(
            company_id=row[0], dimension_code=row[1], level=row[2], status=row[3],
            summary=row[4], payload=payload, evidence_refs=tuple(row[6] or ()),
            evidence_state=str(payload.get("evidence_state") or "missing"),
            customer_fact_status=str(payload.get("customer_fact_status") or "unconfirmed"),
            version=int(row[7] or 0), updated_by=row[8], updated_at=row[9],
        )

    # ==================================================================
    # Analysis Run
    # ==================================================================

    _RUN_SELECT = """SELECT run.analysis_run_id, run.company_id, run.lead_id,
        run.source_candidate_id, run.icp_assessment_id, run.scale_assessment_id,
        run.current_job_id, run.report_type, run.trigger_type, run.status,
        run.input_hash, run.prompt_version, run.schema_version, run.model_name,
        run.profile_version, run.meddpicc_revision, run.engagement_cutoff_at,
        run.input_snapshot, run.token_usage, run.cost_amount, run.cost_currency,
        run.cost_status, run.error_code, run.error_message, run.created_by,
        run.created_at, run.triggered_at, run.trigger_context,
        run.superseded_by_run_id, run.started_at, run.completed_at, run.version,
        report.report_id
        FROM ltc.analysis_run run LEFT JOIN ltc.analysis_report report
        ON report.analysis_run_id=run.analysis_run_id"""

    def get_run(self, run_id: UUID) -> AnalysisRun | None:
        row = self._execute_one(
            self._RUN_SELECT + " WHERE run.analysis_run_id=%s", (run_id,),
        )
        return self._run_from_row(row) if row else None

    def get_run_by_job_id(self, job_id: UUID) -> AnalysisRun | None:
        row = self._execute_one(
            self._RUN_SELECT
            + " WHERE run.current_job_id=%s ORDER BY run.created_at DESC LIMIT 1",
            (job_id,),
        )
        return self._run_from_row(row) if row else None

    def find_run_by_input(
        self, company_id: UUID, report_type: str, input_hash: str
    ) -> AnalysisRun | None:
        """Lock the latest matching row to prevent duplicate-run races."""
        row = self._execute_one(
            """SELECT run.analysis_run_id, run.company_id, run.current_job_id,
               run.report_type, run.trigger_type, run.status,
               run.input_hash, run.prompt_version, run.schema_version, run.model_name,
               run.profile_version, run.meddpicc_revision, run.engagement_cutoff_at,
               run.input_snapshot, run.token_usage, run.cost_amount, run.cost_currency,
               run.cost_status, run.error_code, run.error_message, run.created_by,
               run.created_at, run.started_at, run.completed_at, run.version,
               NULL AS report_id
               FROM ltc.analysis_run run
               WHERE run.company_id=%s AND run.report_type=%s AND run.input_hash=%s
               ORDER BY run.created_at DESC LIMIT 1 FOR UPDATE""",
            (company_id, report_type, input_hash),
        )
        return self._run_from_row(row) if row else None

    def find_recent_run(
        self,
        company_id: UUID,
        report_type: str,
        *,
        since_at: datetime,
    ) -> AnalysisRun | None:
        row = self._execute_one(
            """SELECT run.analysis_run_id, run.company_id, run.current_job_id,
               run.report_type, run.trigger_type, run.status,
               run.input_hash, run.prompt_version, run.schema_version, run.model_name,
               run.profile_version, run.meddpicc_revision, run.engagement_cutoff_at,
               run.input_snapshot, run.token_usage, run.cost_amount, run.cost_currency,
               run.cost_status, run.error_code, run.error_message, run.created_by,
               run.created_at, run.triggered_at, run.trigger_context,
               run.superseded_by_run_id, run.started_at, run.completed_at, run.version,
               NULL AS report_id
               FROM ltc.analysis_run run
               WHERE run.company_id=%s AND run.report_type=%s
                 AND run.triggered_at >= %s
               ORDER BY run.triggered_at DESC, run.created_at DESC
               LIMIT 1""",
            (company_id, report_type, since_at),
        )
        return self._run_from_row(row) if row else None

    def save_run(self, run: AnalysisRun, *, _conn: Any = None) -> None:
        """Insert/update the analysis_run row with optimistic-lock guard.

        Lineage data (lead_id, source_candidate_id, icp_assessment_id,
        scale_assessment_id) is read from ltc.sales_lead via the
        AnalysisContextPort.  If the caller has not pre-resolved them, the
        run will be saved with NULL lineage columns.

        The *job* row is NOT created here — that responsibility belongs to
        the AnalysisJobPort adapter.
        """
        prev_version = run.version - 1
        conn = _conn
        conn_ctx = None
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ltc.analysis_run (
                analysis_run_id, company_id, lead_id, source_candidate_id,
                icp_assessment_id, scale_assessment_id, current_job_id, report_type,
                trigger_type, status, input_hash, prompt_version, schema_version,
                model_name, profile_version, meddpicc_revision, engagement_cutoff_at,
                input_snapshot, token_usage, cost_amount, cost_currency, cost_status,
                error_code, error_message, created_by, created_at, triggered_at,
                trigger_context, superseded_by_run_id, started_at,
                completed_at, version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (analysis_run_id) DO UPDATE SET
                status=EXCLUDED.status, current_job_id=EXCLUDED.current_job_id,
                token_usage=EXCLUDED.token_usage, cost_amount=EXCLUDED.cost_amount,
                cost_currency=EXCLUDED.cost_currency, cost_status=EXCLUDED.cost_status,
                engagement_cutoff_at=EXCLUDED.engagement_cutoff_at,
                triggered_at=EXCLUDED.triggered_at,
                trigger_context=EXCLUDED.trigger_context,
                superseded_by_run_id=EXCLUDED.superseded_by_run_id,
                error_code=EXCLUDED.error_code, error_message=EXCLUDED.error_message,
                started_at=EXCLUDED.started_at, completed_at=EXCLUDED.completed_at,
                version=EXCLUDED.version
                WHERE ltc.analysis_run.version = %s""",
                (
                    run.run_id, run.company_id, None, None, None, None,
                    run.current_job_id, run.report_type, run.trigger_type, run.status,
                    run.input_hash, run.prompt_version, run.schema_version,
                    run.model_name, run.profile_version, run.meddpicc_revision,
                    run.engagement_cutoff_at,
                    self._json(run.input_snapshot),
                    self._json({}),  # token_usage — updated by worker on completion
                    None,  # cost_amount
                    "USD",
                    "unknown",
                    run.error_code, run.error_message, None,  # created_by
                    run.created_at, run.triggered_at, self._json(run.trigger_context),
                    run.superseded_by_run_id, run.started_at, run.completed_at, run.version,
                    prev_version,
                ),
            )
            if cur.rowcount == 0:
                raise VersionConflictError(
                    f"analysis run version {prev_version} was modified concurrently"
                )
        finally:
            if conn_ctx is not None:
                conn_ctx.__exit__(None, None, None)

    def count_runs_by_status(self) -> dict[str, int]:
        rows = self._execute_all(
            "SELECT status, COUNT(*) FROM ltc.analysis_run GROUP BY status",
        )
        return {str(row[0]): int(row[1]) for row in rows}

    @staticmethod
    def _safe_dict(value: Any) -> dict[str, Any]:
        """Convert a value to dict regardless of whether it's a dict, JSON string, or None."""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            import json as _json
            try:
                return _json.loads(value)
            except (_json.JSONDecodeError, TypeError):
                return {}
        try:
            return dict(value)
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _run_from_row(row: Any) -> AnalysisRun:
        # Auto-detect row format by column count:
        # 33 cols = from _RUN_SELECT (used by get_run, get_run_by_job_id)
        # 29 cols = from find_run_by_input / find_recent_run
        n = len(row)
        if n >= 33:
            # 33-column format: [0]run_id [1]company_id [...extra cols...] [6]job_id ...
            return AnalysisRun(
                run_id=row[0], company_id=row[1], current_job_id=row[6],
                report_type=row[7], trigger_type=row[8], status=row[9],
                input_hash=row[10], prompt_version=row[11], schema_version=row[12],
                model_name=row[13], profile_version=int(row[14] or 0),
                meddpicc_revision=row[15],
                engagement_cutoff_at=row[16],
                input_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[17]),
                error_code=row[22], error_message=row[23],
                created_at=row[25], triggered_at=row[26],
                trigger_context=PostgresCustomerAnalysisRepository._safe_dict(row[27]),
                superseded_by_run_id=row[28],
                started_at=row[29], completed_at=row[30],
                version=int(row[31] or 0), report_id=row[32],
            )
        else:
            # 29-column format from find_run_by_input / find_recent_run
            return AnalysisRun(
                run_id=row[0], company_id=row[1], current_job_id=row[2],
                report_type=row[3], trigger_type=row[4], status=row[5],
                input_hash=row[6], prompt_version=row[7], schema_version=row[8],
                model_name=row[9], profile_version=int(row[10] or 0),
                meddpicc_revision=row[11],
                engagement_cutoff_at=row[12],
                input_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[13]),
                error_code=row[18], error_message=row[19],
                created_at=row[21], triggered_at=row[22],
                trigger_context=PostgresCustomerAnalysisRepository._safe_dict(row[23]),
                superseded_by_run_id=row[24],
                started_at=row[25], completed_at=row[26],
                version=int(row[27] or 0), report_id=row[28],
            )

    # ==================================================================
    # Analysis Report
    # ==================================================================

    _REPORT_SELECT = """SELECT ar.report_id, ar.company_id, ar.analysis_run_id,
        ar.report_type, ar.version_no, ar.schema_version, ar.summary,
        ar.health_grade, ar.intention_level, ar.confidence,
        ar.section_confidence, ar.low_confidence_sections, ar.data_sources,
        ar.evidence_refs, ar.profile_snapshot, ar.meddpicc_snapshot,
        ar.icp_snapshot, ar.scale_snapshot, ar.report_payload,
        ar.sales_guide_payload, ar.generated_by, ar.model_name,
        ar.content_source, run.input_hash, ar.generated_at, ar.superseded_at
        FROM ltc.analysis_report ar JOIN ltc.analysis_run run
        ON run.analysis_run_id=ar.analysis_run_id"""

    @classmethod
    def _report_select(cls) -> str:
        return cls._REPORT_SELECT

    def next_report_version(self, company_id: UUID, report_type: str) -> int:
        row = self._execute_one(
            """SELECT COALESCE(MAX(version_no), 0)+1 FROM ltc.analysis_report
            WHERE company_id=%s AND report_type=%s""",
            (company_id, report_type),
        )
        return int(row[0])

    def save_report(self, report: AnalysisReport, *, _conn: Any = None) -> None:
        """Supersede old current report then insert new, in one transaction.

        Uses FOR UPDATE on the current report row to prevent concurrent
        supersede races.
        """
        conn = _conn
        conn_ctx = None
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
        try:
            cur = conn.cursor()
            # Lock the current row so concurrent supersedes serialize
            cur.execute(
                """SELECT report_id FROM ltc.analysis_report
                WHERE company_id=%s AND report_type=%s AND superseded_at IS NULL
                FOR UPDATE""",
                (report.company_id, report.report_type),
            )
            cur.execute(
                """UPDATE ltc.analysis_report SET superseded_at=clock_timestamp()
                WHERE company_id=%s AND report_type=%s AND superseded_at IS NULL
                AND report_id<>%s""",
                (report.company_id, report.report_type, report.report_id),
            )
            cur.execute(
                """INSERT INTO ltc.analysis_report (
                report_id, company_id, analysis_run_id, report_type, version_no,
                schema_version, summary, health_grade, intention_level, confidence,
                section_confidence, low_confidence_sections, data_sources, evidence_refs,
                profile_snapshot, meddpicc_snapshot, icp_snapshot, scale_snapshot,
                report_payload, sales_guide_payload, generated_by, model_name,
                content_source, generated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s)""",
                (
                    report.report_id, report.company_id, report.analysis_run_id,
                    report.report_type, report.version_no, report.schema_version,
                    report.summary, report.health_grade, report.intention_level,
                    report.confidence, self._json(report.section_confidence),
                    list(report.low_confidence_sections),
                    self._json(list(report.data_sources)),
                    self._json(list(report.evidence_refs)),
                    self._json(report.profile_snapshot),
                    self._json(report.meddpicc_snapshot), self._json(report.icp_snapshot),
                    self._json(report.scale_snapshot), self._json(report.report_payload),
                    self._json(report.sales_guide_payload), report.generated_by,
                    report.model_name, report.content_source, report.generated_at,
                ),
            )
        finally:
            if conn_ctx is not None:
                conn_ctx.__exit__(None, None, None)

    def get_report(self, report_id: UUID) -> AnalysisReport | None:
        row = self._execute_one(
            self._REPORT_SELECT + " WHERE ar.report_id=%s", (report_id,),
        )
        return self._report_from_row(row) if row else None

    def get_current_report(
        self, company_id: UUID, report_type: str = "customer_analysis"
    ) -> AnalysisReport | None:
        row = self._execute_one(
            self._REPORT_SELECT
            + " WHERE ar.company_id=%s AND ar.report_type=%s "
            + "AND ar.superseded_at IS NULL ORDER BY ar.version_no DESC LIMIT 1",
            (company_id, report_type),
        )
        return self._report_from_row(row) if row else None

    def list_reports(
        self, company_id: UUID, *, limit: int, cursor: str | None
    ) -> tuple[list[AnalysisReport], str | None]:
        offset = int(cursor or 0)
        rows = self._execute_all(
            self._REPORT_SELECT
            + " WHERE ar.company_id=%s AND ar.report_type='customer_analysis' "
            + "ORDER BY ar.version_no DESC LIMIT %s OFFSET %s",
            (company_id, limit + 1, offset),
        )
        page = rows[:limit]
        next_cursor = str(offset + limit) if len(rows) > limit else None
        return [self._report_from_row(row) for row in page], next_cursor

    @staticmethod
    def _report_from_row(row: Any) -> AnalysisReport:
        return AnalysisReport(
            report_id=row[0], company_id=row[1], analysis_run_id=row[2],
            report_type=row[3], version_no=int(row[4]), schema_version=row[5],
            summary=row[6], health_grade=row[7], intention_level=row[8],
            confidence=float(row[9]) if row[9] is not None else None,
            section_confidence=PostgresCustomerAnalysisRepository._safe_dict(row[10]),
            low_confidence_sections=tuple(row[11] or ()),
            data_sources=tuple(row[12] or ()), evidence_refs=tuple(row[13] or ()),
            profile_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[14]), meddpicc_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[15]),
            icp_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[16]), scale_snapshot=PostgresCustomerAnalysisRepository._safe_dict(row[17]),
            report_payload=PostgresCustomerAnalysisRepository._safe_dict(row[18]), sales_guide_payload=PostgresCustomerAnalysisRepository._safe_dict(row[19]),
            generated_by=row[20], model_name=row[21], content_source=row[22],
            input_hash=row[23], generated_at=row[24], superseded_at=row[25],
        )

    # ==================================================================
    # Analysis Suggestion
    # ==================================================================

    _SUGGESTION_SELECT = """SELECT suggestion_id, company_id, report_id, target_type,
        dimension_code, target_path, target_version_at_creation,
        current_value_snapshot, proposed_value, evidence_refs, confidence, status,
        reviewed_by, reviewed_at, review_note, created_at, version
        FROM ltc.analysis_suggestion"""

    def save_suggestion(self, suggestion: AnalysisSuggestion, *, _conn: Any = None) -> None:
        """Upsert with optimistic-lock guard."""
        prev_version = suggestion.version - 1
        conn = _conn
        conn_ctx = None
        if conn is None:
            conn_ctx = self._connection()
            conn = conn_ctx.__enter__()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ltc.analysis_suggestion (
                suggestion_id, company_id, report_id, target_type, dimension_code,
                target_path, target_version_at_creation, current_value_snapshot,
                proposed_value, evidence_refs, confidence, status, reviewed_by,
                reviewed_at, review_note, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (suggestion_id) DO UPDATE SET status=EXCLUDED.status,
                reviewed_by=EXCLUDED.reviewed_by, reviewed_at=EXCLUDED.reviewed_at,
                review_note=EXCLUDED.review_note,
                version=ltc.analysis_suggestion.version + 1
                WHERE ltc.analysis_suggestion.suggestion_id = %s
                  AND ltc.analysis_suggestion.version = %s""",
                (
                    suggestion.suggestion_id, suggestion.company_id, suggestion.report_id,
                    suggestion.target_type, suggestion.dimension_code,
                    suggestion.target_path, suggestion.target_version_at_creation,
                    self._json(suggestion.current_value_snapshot),
                    self._json(suggestion.proposed_value),
                    self._json(list(suggestion.evidence_refs)), suggestion.confidence,
                    suggestion.status, suggestion.reviewed_by, suggestion.reviewed_at,
                    suggestion.review_note, suggestion.created_at,
                    suggestion.suggestion_id,
                    prev_version,
                ),
            )
            if cur.rowcount == 0:
                raise VersionConflictError(
                    f"suggestion version {prev_version} was modified concurrently"
                )
        finally:
            if conn_ctx is not None:
                conn_ctx.__exit__(None, None, None)

    def get_suggestion(self, suggestion_id: UUID) -> AnalysisSuggestion | None:
        row = self._execute_one(
            self._SUGGESTION_SELECT + " WHERE suggestion_id=%s", (suggestion_id,),
        )
        return self._suggestion_from_row(row) if row else None

    def list_suggestions(
        self, company_id: UUID, *, status: str = "pending"
    ) -> list[AnalysisSuggestion]:
        rows = self._execute_all(
            self._SUGGESTION_SELECT
            + " WHERE company_id=%s AND status=%s ORDER BY created_at",
            (company_id, status),
        )
        return [self._suggestion_from_row(row) for row in rows]

    @staticmethod
    def _suggestion_from_row(row: Any) -> AnalysisSuggestion:
        return AnalysisSuggestion(
            suggestion_id=row[0], company_id=row[1], report_id=row[2],
            target_type=row[3], dimension_code=row[4], target_path=row[5],
            target_version_at_creation=int(row[6]), current_value_snapshot=row[7],
            proposed_value=row[8], evidence_refs=tuple(row[9] or ()),
            confidence=float(row[10]) if row[10] is not None else None,
            status=row[11], reviewed_by=row[12], reviewed_at=row[13],
            review_note=row[14], created_at=row[15], version=int(row[16] or 0),
        )
