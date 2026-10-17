"""Κοινά βοηθητικά για τις προσωρινές SQLite βάσεις των standalone tests.

Δεν είναι test_*.py: το loop του CI (backend/tests/test_*.py) δεν το τρέχει
μόνο του."""

from pathlib import Path


def remove_db(db_path: Path | str) -> None:
    """Σβήνει τη βάση μαζί με τα -wal/-shm του WAL mode, όσα υπάρχουν."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
