"""Synchronous PostgreSQL pool and unit-of-work primitive.

Business modules own their repositories and SQL. This platform layer owns only
connection lifecycle, health probing, and transaction boundaries.
"""

from __future__ import annotations

from contextlib import contextmanager
import sys
from typing import Iterator

from psycopg import Connection, Error
from psycopg_pool import ConnectionPool, PoolTimeout

from ltc.platform.config import AppSettings


class DatabaseUnavailableError(RuntimeError):
    """Raised when a request cannot acquire or use a PostgreSQL connection."""


class PostgresDatabase:
    def __init__(self, settings: AppSettings) -> None:
        self._timeout_seconds = settings.database_pool_timeout_seconds
        self._pool = ConnectionPool(
            conninfo=settings.database_dsn,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            timeout=settings.database_pool_timeout_seconds,
            open=False,
        )
        self._opened = False

    def open(self) -> None:
        if self._opened:
            return
        try:
            self._pool.open(wait=True, timeout=self._timeout_seconds)
        except (Error, PoolTimeout) as exc:
            raise DatabaseUnavailableError("PostgreSQL connection pool could not start") from exc
        self._opened = True

    def close(self) -> None:
        if not self._opened:
            return
        self._pool.close()
        self._opened = False

    def ping(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1")
        except (Error, PoolTimeout) as exc:
            raise DatabaseUnavailableError("PostgreSQL is unavailable") from exc

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Yield one database transaction; commit or rollback as one UoW."""
        try:
            with self._connection() as connection:
                with connection.transaction():
                    yield connection
        except (Error, PoolTimeout) as exc:
            raise DatabaseUnavailableError("PostgreSQL transaction failed") from exc

    @contextmanager
    def advisory_lock(self, key: int) -> Iterator[tuple[Connection, bool]]:
        """Pin one physical connection while holding a session advisory lock."""
        with self._connection() as connection:
            with connection.transaction():
                acquired = bool(connection.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0])
            try:
                yield connection, acquired
            finally:
                if acquired:
                    with connection.transaction():
                        connection.execute("SELECT pg_advisory_unlock(%s)", (key,))

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        if not self._opened:
            raise DatabaseUnavailableError("PostgreSQL pool is not started")
        pool_context = None
        try:
            pool_context = self._pool.connection(timeout=self._timeout_seconds)
            connection = pool_context.__enter__()
        except (Error, PoolTimeout) as exc:
            raise DatabaseUnavailableError("PostgreSQL connection could not be acquired") from exc
        try:
            yield connection
        finally:
            if pool_context is not None:
                pool_context.__exit__(*sys.exc_info())
