"""A recording DB-API double.

It exists so the SQL this package sends can be asserted on without a database: the
statements, the parameters, and the fact that no caller-supplied value is ever formatted
into a statement. It answers queries from a scripted list rather than executing them, so
it proves nothing about whether PostgreSQL accepts the SQL -- that is what
`test_postgres_integration.py` is for.
"""

from contextlib import contextmanager
from typing import Any


class FakeCursor:
    def __init__(self, connection: "FakeConnection"):
        self._connection = connection
        self._rows: list[tuple[Any, ...]] = []
        self.closed = False

    def execute(self, sql: str, params: Any = None) -> None:
        self._connection.statements.append((sql, params))
        self._rows = self._connection.rows_for(sql)

    def executemany(self, sql: str, seq: Any) -> None:
        rows = list(seq)
        self._connection.statements.append((sql, rows))
        self._connection.batches.append((sql, rows))
        self._rows = []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    """Answers each `execute` with the first scripted response whose key it contains."""

    def __init__(self, responses: list[tuple[str, list[tuple[Any, ...]]]] | None = None):
        self.responses = responses or []
        self.statements: list[tuple[str, Any]] = []
        self.batches: list[tuple[str, list[Any]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.cursors: list[FakeCursor] = []

    def rows_for(self, sql: str) -> list[tuple[Any, ...]]:
        for key, rows in self.responses:
            if key in sql:
                return rows
        return []

    def cursor(self) -> FakeCursor:
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def executed(self) -> list[str]:
        return [sql for sql, _ in self.statements]

    def parameters_for(self, key: str) -> Any:
        """The parameters of the first statement containing `key`."""
        for sql, params in self.statements:
            if key in sql:
                return params
        raise AssertionError(f"no statement contained {key!r}")


def factory(connection: FakeConnection):
    """A `ConnectionFactory` that hands out the same connection every time."""

    @contextmanager
    def connect():
        yield connection

    return connect
