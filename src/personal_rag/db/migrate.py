"""Forward-only schema migrations.

Numbered `.sql` files in `migrations/` are applied in filename order and recorded in
`schema_migrations`, so applying twice is a no-op and a partially migrated database
reports which step it stopped at. There is no down-migration: an index is a rebuildable
artifact (section 3), so recovering from a bad schema change means rebuilding, not
reversing.

`schema.sql` is the same DDL concatenated for humans and for tooling that wants one file.
It is generated from these migrations by `render_schema`, and a test asserts the checked
in copy still matches -- otherwise the two drift and the wrong one gets deployed.
"""

from pathlib import Path

from .connection import ConnectionFactory, transaction

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
SCHEMA_FILE = Path(__file__).parent / "schema.sql"

SCHEMA_HEADER = (
    "-- Generated from personal_rag/db/migrations by personal_rag.db.migrate.render_schema.\n"
    "-- Do not edit by hand: add a migration and regenerate.\n"
)

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(128) PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def migration_files() -> list[Path]:
    """Every migration, in the order it must be applied."""
    return sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))


def render_schema() -> str:
    """The full schema as one script, for bootstrapping a fresh database."""
    parts = [SCHEMA_HEADER]
    parts.extend(path.read_text(encoding="utf-8").strip() + "\n" for path in migration_files())
    return "\n".join(parts)


def applied_versions(connect: ConnectionFactory) -> set[str]:
    with transaction(connect) as cursor:
        cursor.execute(_MIGRATIONS_TABLE)
        cursor.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}


def apply_migrations(connect: ConnectionFactory) -> list[str]:
    """Apply every pending migration, returning the versions applied by this call.

    Each migration runs in its own transaction together with the row that records it, so
    a migration and the claim that it ran cannot disagree.
    """
    already = applied_versions(connect)
    applied: list[str] = []
    for path in migration_files():
        version = path.stem
        if version in already:
            continue
        with transaction(connect) as cursor:
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%(version)s)",
                {"version": version},
            )
        applied.append(version)
    return applied


def write_schema_file() -> Path:
    """Regenerate the checked in `schema.sql` after adding a migration.

    Newlines are pinned to LF so regenerating on Windows does not rewrite every line and
    make the drift test in `test_postgres_index.py` compare against a churned file.
    """
    with SCHEMA_FILE.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_schema())
    return SCHEMA_FILE


if __name__ == "__main__":  # pragma: no cover - developer convenience
    print(f"wrote {write_schema_file()}")
