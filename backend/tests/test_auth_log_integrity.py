"""auth_log append-only: UPDATE και DELETE μπλοκάρονται από τα triggers του
schema.sql (ίδιο μοτίβο με το audit_log, βλ. test_audit_integrity.py).

Εκτελείται standalone: `python tests/test_auth_log_integrity.py`
"""

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.service import AuthEvent, log_event  # noqa: E402
from app.db.database import get_connection, init_db  # noqa: E402


def _db_with_one_row() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    conn = get_connection(db_path)
    log_event(
        conn, datetime(2026, 1, 1, tzinfo=timezone.utc), AuthEvent.LOGIN_FAIL, username="synthetic"
    )
    conn.commit()
    conn.close()
    return db_path


def _expect_abort(db_path: Path, sql: str, message: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql)
        conn.commit()
    except sqlite3.IntegrityError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError(f"Το '{sql}' δεν μπλοκαρίστηκε")
    finally:
        conn.close()


def test_update_is_blocked():
    db_path = _db_with_one_row()
    try:
        _expect_abort(db_path, "UPDATE auth_log SET event = 'login_ok'", "UPDATE is not allowed")
    finally:
        os.remove(db_path)


def test_delete_is_blocked():
    db_path = _db_with_one_row()
    try:
        _expect_abort(db_path, "DELETE FROM auth_log", "DELETE is not allowed")
    finally:
        os.remove(db_path)


def test_row_survives_blocked_update_and_delete():
    db_path = _db_with_one_row()
    try:
        for sql in ("UPDATE auth_log SET username = 'x'", "DELETE FROM auth_log"):
            _expect_abort(db_path, sql, "not allowed")
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT event, username FROM auth_log").fetchall()
        finally:
            conn.close()
        assert rows == [("login_fail", "synthetic")]
    finally:
        os.remove(db_path)


def test_init_db_twice_keeps_triggers():
    db_path = _db_with_one_row()
    try:
        init_db(db_path)
        _expect_abort(db_path, "DELETE FROM auth_log", "DELETE is not allowed")
    finally:
        os.remove(db_path)


def run_all():
    tests = [
        test_update_is_blocked,
        test_delete_is_blocked,
        test_row_survives_blocked_update_and_delete,
        test_init_db_twice_keeps_triggers,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
