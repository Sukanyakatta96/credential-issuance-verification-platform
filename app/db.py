import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

from .config import PROJECT_ROOT

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["APP_CONFIG"].database_path)
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction(db: sqlite3.Connection):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def migrate(db: sqlite3.Connection) -> list[str]:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migration (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {r["name"] for r in db.execute("SELECT name FROM schema_migration")}
    newly_applied = []
    for path in migration_files():
        if path.name in applied:
            continue
        db.executescript("BEGIN;\n" + path.read_text(encoding="utf-8") + "\nCOMMIT;")
        db.execute(
            "INSERT INTO schema_migration (name, applied_at) VALUES (?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
            (path.name,),
        )
        newly_applied.append(path.name)
    return newly_applied


def paginate(db, base_sql: str, params: list, page: int, page_size: int, order_by: str):
    total = db.execute(f"SELECT COUNT(*) FROM ({base_sql})", params).fetchone()[0]
    rows = db.execute(
        f"{base_sql} ORDER BY {order_by} LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
