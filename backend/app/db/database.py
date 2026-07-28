import sqlite3
from pathlib import Path

from app.core.config import get_settings

DB_PATH = get_settings().DB_PATH
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_audit_log(conn: sqlite3.Connection) -> None:
    """Migration-safe προσθήκη στηλών σε DBs που δημιουργήθηκαν πριν από αυτές
    (CREATE TABLE IF NOT EXISTS δεν αλλάζει υπάρχοντα schema)."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_log)")}
    if columns and "prompt_version" not in columns:
        conn.execute("ALTER TABLE audit_log ADD COLUMN prompt_version TEXT")
    if columns and "unsupported_ranks" not in columns:
        conn.execute("ALTER TABLE audit_log ADD COLUMN unsupported_ranks TEXT")


def init_db(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_audit_log(conn)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
