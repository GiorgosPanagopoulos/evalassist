"""CLI app.auth.create_admin: init_db πρώτα, getpass δύο φορές, ελάχιστο
μήκος 12, ο κωδικός δεν εμφανίζεται ποτέ σε output ή στη βάση.

Εκτελείται standalone: `python tests/test_create_admin.py`
"""

import io
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_helpers import remove_db  # noqa: E402

from app.auth.create_admin import main  # noqa: E402
from app.auth.passwords import verify_password  # noqa: E402

PASSWORD = "synthetic-admin-pass"


def _fresh_path() -> Path:
    # Ανύπαρκτο αρχείο: το CLI πρέπει να φτιάξει μόνο του το σχήμα (init_db).
    directory = tempfile.mkdtemp()
    return Path(directory) / "fresh.db"


def _run(db_path: Path, username: str, passwords: list[str]) -> tuple[int, str]:
    answers = iter(passwords)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(
            db_path, input_fn=lambda _prompt: username, getpass_fn=lambda _prompt: next(answers)
        )
    return code, out.getvalue() + err.getvalue()


def _users(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()


def _cleanup(db_path: Path) -> None:
    remove_db(db_path)
    os.rmdir(db_path.parent)


def test_creates_admin_on_fresh_db_without_leaking_password():
    db_path = _fresh_path()
    try:
        code, output = _run(db_path, "Root", [PASSWORD, PASSWORD])
        assert code == 0, output
        assert PASSWORD not in output
        users = _users(db_path)
        assert len(users) == 1
        user = users[0]
        assert user["username"] == "root" and user["role"] == "admin"
        assert user["must_change_pw"] == 0 and user["is_active"] == 1
        assert PASSWORD not in user["password_hash"]
        assert verify_password(PASSWORD, user["password_hash"])

        conn = sqlite3.connect(db_path)
        try:
            log = conn.execute("SELECT event, username, detail FROM auth_log").fetchall()
        finally:
            conn.close()
        assert log == [("admin_bootstrap", "root", None)]
    finally:
        _cleanup(db_path)


def test_rejects_short_password():
    db_path = _fresh_path()
    try:
        code, output = _run(db_path, "root", ["short-pass1", "short-pass1"])
        assert code == 1
        assert "12" in output and "short-pass1" not in output
        assert _users(db_path) == []
    finally:
        _cleanup(db_path)


def test_rejects_mismatched_confirmation():
    db_path = _fresh_path()
    try:
        code, output = _run(db_path, "root", [PASSWORD, PASSWORD + "x"])
        assert code == 1
        assert PASSWORD not in output
        assert _users(db_path) == []
    finally:
        _cleanup(db_path)


def test_rejects_duplicate_and_invalid_username():
    db_path = _fresh_path()
    try:
        assert _run(db_path, "root", [PASSWORD, PASSWORD])[0] == 0
        assert _run(db_path, "root", [PASSWORD, PASSWORD])[0] == 1
        assert _run(db_path, "a b", [PASSWORD, PASSWORD])[0] == 1
        assert len(_users(db_path)) == 1
    finally:
        _cleanup(db_path)


def run_all():
    tests = [
        test_creates_admin_on_fresh_db_without_leaking_password,
        test_rejects_short_password,
        test_rejects_mismatched_confirmation,
        test_rejects_duplicate_and_invalid_username,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
