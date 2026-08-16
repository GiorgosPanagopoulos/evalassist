import re
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
    if columns and "answer_text" not in columns:
        conn.execute("ALTER TABLE audit_log ADD COLUMN answer_text TEXT")


def _migrate_service_time_check(conn: sqlite3.Connection) -> None:
    """DBs δημιουργημένες πριν την υποενότητα γ (Ανά Κατηγορία Καθήκοντος,
    βλ. app.ingestion.duty_categories) έχουν CHECK (subsection IN ('α','β'))
    ήδη αποθηκευμένο στο sqlite_master. Το SQLite ΔΕΝ υποστηρίζει ALTER
    TABLE για CHECK constraints - η μόνη λύση είναι DROP + recreate (το
    recreate γίνεται αμέσως μετά, από το CREATE TABLE IF NOT EXISTS του
    schema.sql).

    Το DROP εδώ είναι lossless: το service_time είναι πλήρως παράγωγος
    πίνακας - γεμίζει εξ ολοκλήρου από delete-then-insert σε κάθε
    ingestion (repository.replace_service_time), μηδέν ανθρωπογενή
    δεδομένα, σε αντίθεση με το audit_log που είναι append-only ιστορικό
    και ΔΕΝ αγγίζεται εδώ. ΑΠΑΙΤΕΙΤΑΙ re-ingestion των PDF μετά από αυτό το
    migration ώστε να ξαναγεμίσει ο πίνακας."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'service_time'"
    ).fetchone()
    if row is None:
        return
    existing_sql = row[0]
    if existing_sql is not None and "γ" not in existing_sql:
        conn.execute("DROP TABLE service_time")


_EVALUATIONS_COLUMNS = (
    "id, person_id, period, period_start, period_end, ea_type, characterization, "
    "score, unit, duties, rank_at_time, evaluator_rank, evaluator_name, evaluator_role, "
    "gnomatevon_rank, gnomatevon_name, gnomatevon_role, defects, evaluator_notes, "
    "gnomatevon_notes, source_page, created_at"
)

_EVALUATIONS_NOT_NULL_RE = re.compile(r"characterization\s+TEXT\s+NOT\s+NULL")


def _migrate_evaluations_characterization_nullable(conn: sqlite3.Connection) -> None:
    """DBs δημιουργημένες πριν αφαιρεθεί το ψευδεπίγραφο "ΔΥ" χαρακτηρισμό
    (βλ. app.models.evaluation.CHARACTERIZATIONS) έχουν
    `characterization TEXT NOT NULL` ήδη αποθηκευμένο στο sqlite_master. Το
    SQLite ΔΕΝ υποστηρίζει ALTER TABLE για DROP NOT NULL.

    Σε αντίθεση με το `_migrate_service_time_check`, το `evaluations` ΔΕΝ
    είναι παράγωγος πίνακας: `upsert_evaluation` κάνει ON CONFLICT DO
    UPDATE (όχι delete-then-insert), το `field_scores.eval_id` αναφέρεται
    στα `evaluations.id`, και το `created_at` είναι ανθρωπογενές ιστορικό.
    Άρα table rebuild με ρητή αντιγραφή όλων των γραμμών/στηλών (id και
    created_at ΣΥΜΠΕΡΙΛΑΜΒΑΝΟΝΤΑΙ), όχι DROP+recreate."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'evaluations'"
    ).fetchone()
    if row is None or row[0] is None or not _EVALUATIONS_NOT_NULL_RE.search(row[0]):
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        """
        CREATE TABLE evaluations_new (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id           TEXT NOT NULL REFERENCES persons(person_id),
            period              TEXT NOT NULL,
            period_start        TEXT NOT NULL,
            period_end          TEXT NOT NULL,
            ea_type             TEXT NOT NULL CHECK (ea_type IN ('Ε.Α.', 'Σ.Α.')),
            characterization    TEXT,
            score               INTEGER CHECK (score IS NULL OR score BETWEEN 0 AND 100),
            unit                TEXT NOT NULL,
            duties              TEXT,
            rank_at_time        TEXT,
            evaluator_rank      TEXT,
            evaluator_name      TEXT NOT NULL,
            evaluator_role      TEXT,
            gnomatevon_rank     TEXT,
            gnomatevon_name     TEXT,
            gnomatevon_role     TEXT,
            defects             TEXT,
            evaluator_notes     TEXT,
            gnomatevon_notes    TEXT,
            source_page         INTEGER,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (person_id, period)
        )
        """
    )
    conn.execute(
        f"INSERT INTO evaluations_new ({_EVALUATIONS_COLUMNS}) "
        f"SELECT {_EVALUATIONS_COLUMNS} FROM evaluations"
    )
    conn.execute("DROP TABLE evaluations")
    conn.execute("ALTER TABLE evaluations_new RENAME TO evaluations")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evaluations_person_period "
        "ON evaluations(person_id, period)"
    )
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(
            f"PRAGMA foreign_key_check βρήκε παραβιάσεις μετά το evaluations rebuild: {violations}"
        )
    conn.execute("PRAGMA foreign_keys = ON")


def init_db(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        _migrate_service_time_check(conn)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_audit_log(conn)
        _migrate_evaluations_characterization_nullable(conn)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
