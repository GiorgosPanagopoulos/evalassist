"""Χτίζει τη βάση που παραδίδεται στον server από μια υπάρχουσα βάση ανάπτυξης.

Η νέα βάση δημιουργείται από το τρέχον schema (init_db) και παίρνει ΜΟΝΟ τους
πίνακες δεδομένων. Οι users, sessions, auth_log και audit_log μένουν άδειοι:
χρήστες, κωδικοί, ενεργά sessions και ιστορικό ερωτήσεων της μηχανής
ανάπτυξης δεν πηγαίνουν στον server. Ο πρώτος admin του server φτιάχνεται εκεί
με `python -m app.auth.create_admin`.

Η πηγή ανοίγει μόνο για ανάγνωση (SQLite mode=ro) και δεν αλλάζει. Το script
δεν τυπώνει περιεχόμενο, μόνο ονόματα πινάκων και πλήθος γραμμών. Αρνείται να
γράψει πάνω σε αρχείο που υπάρχει.

Χρήση (από τη ρίζα του repo, με το venv του backend):
    python deploy/build_deploy_db.py --source backend/data/evalassist.db --target <out.db>
"""

import argparse
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import init_db  # noqa: E402

# Με σειρά που σέβεται τα foreign keys (persons πρώτα, field_scores μετά τα evaluations).
DATA_TABLES = ("persons", "evaluations", "field_scores", "documents", "promotions", "service_time")
EMPTY_TABLES = ("users", "sessions", "auth_log", "audit_log")


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def build(source: Path, target: Path) -> dict[str, int]:
    """Επιστρέφει {πίνακας: γραμμές} της νέας βάσης. Σε οποιοδήποτε σφάλμα
    το μισοτελειωμένο target διαγράφεται."""
    source = source.resolve()
    target = target.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Δεν βρέθηκε η πηγή: {source}")
    if target.exists():
        raise FileExistsError(f"Το target υπάρχει ήδη, δεν γράφεται από πάνω: {target}")
    if target == source:
        raise ValueError("Πηγή και target είναι το ίδιο αρχείο.")

    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    try:
        init_db(target)
        dst = sqlite3.connect(target)
        try:
            dst.execute("PRAGMA foreign_keys = ON")
            for table in DATA_TABLES:
                columns = _columns(dst, table)
                missing = set(columns) - set(_columns(src, table))
                if missing:
                    raise ValueError(
                        f"Η πηγή δεν έχει τις στήλες {sorted(missing)} στον πίνακα {table}: "
                        "τρέξε πρώτα το migration στην πηγή (python -m app.db.database)."
                    )
                column_list = ", ".join(f'"{c}"' for c in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = src.execute(f'SELECT {column_list} FROM "{table}"').fetchall()
                dst.executemany(
                    f'INSERT INTO "{table}" ({column_list}) VALUES ({placeholders})', rows
                )
            violations = dst.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise sqlite3.IntegrityError(f"{len(violations)} παραβιάσεις foreign key")
            dst.commit()

            counts = {}
            for table in DATA_TABLES:
                counts[table] = _count(dst, table)
                if counts[table] != _count(src, table):
                    raise RuntimeError(f"Διαφορά πλήθους γραμμών στον πίνακα {table}")
            for table in EMPTY_TABLES:
                counts[table] = _count(dst, table)
                if counts[table] != 0:
                    raise RuntimeError(f"Ο πίνακας {table} δεν είναι άδειος")
        finally:
            dst.close()
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="βάση ανάπτυξης (μόνο ανάγνωση)")
    parser.add_argument("--target", type=Path, required=True, help="νέα βάση (δεν πρέπει να υπάρχει)")
    args = parser.parse_args(argv)
    try:
        counts = build(args.source, args.target)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for table, count in counts.items():
        print(f"{table}: {count}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
