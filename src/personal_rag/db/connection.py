"""How this package talks to PostgreSQL.

The datastore is reached through a *connection factory* rather than a driver import, for
two reasons. Section 7 requires ingestion and query to run in different processes with
different connection lifetimes -- a short-lived Cloud Run Job connection and a pooled
Cloud Run Service connection -- and only the caller knows which it has. And keeping the
driver out of the module means the SQL can be unit tested against a recording double,
so the query shapes are covered without a database.

Everything here speaks DB-API 2.0 with `pyformat` parameters (`%(name)s`), which is what
both `psycopg` 3 and `psycopg2` provide.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

# A factory returns a context manager that yields a connection and releases it on exit.
# `psycopg.connect` and `psycopg_pool.ConnectionPool.connection` both satisfy this.
ConnectionFactory = Callable[[], AbstractContextManager[Any]]


@contextmanager
def transaction(connect: ConnectionFactory) -> Iterator[Any]:
    """Yield a cursor inside one transaction, committing only if the body succeeds.

    Every write path in this package is a single transaction, so a failed ingestion run
    cannot leave a half-staged document behind and a failed activation cannot leave the
    pointer disagreeing with the run table.
    """
    with connect() as connection:
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()


def psycopg_factory(conninfo: str, **kwargs: Any) -> ConnectionFactory:
    """A factory that opens one `psycopg` connection per transaction.

    Suitable for the indexer job. A long-running query service should pass
    `psycopg_pool.ConnectionPool(...).connection` instead so connections are reused.
    """

    def connect() -> AbstractContextManager[Any]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "psycopg is required to reach PostgreSQL; install the 'postgres' extra "
                "(uv sync --extra postgres)"
            ) from exc
        return psycopg.connect(conninfo, **kwargs)

    return connect
