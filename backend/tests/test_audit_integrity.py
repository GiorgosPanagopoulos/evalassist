"""Mini test/sample flow για το append-only audit_log (Φάση 5, audit integrity).

Καλύπτει, πάνω σε temp file-based SQLite (ποτέ την πραγματική DB):
  - init_db σε καθαρή DB, write_audit περνάει και επιστρέφει id.
  - UPDATE/DELETE στο audit_log μπλοκάρονται από τα triggers (append-only).
  - η γραμμή επιβιώνει αναλλοίωτη μετά από μπλοκαρισμένα UPDATE/DELETE.
  - answer_text roundtrip με ελληνικό κείμενο που περιέχει εισαγωγικά.
  - migration path: DB χωρίς answer_text στήλη, init_db προσθέτει τη στήλη,
    διατηρεί την παλιά γραμμή, και ενεργοποιεί τα triggers.

Εκτελείται standalone: `python tests/test_audit_integrity.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.audit import AuditEntry, write_audit  # noqa: E402
from app.db.database import init_db  # noqa: E402


def _make_temp_db_path() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Path(path)


def test_init_db_write_audit_returns_id():
    db_path = _make_temp_db_path()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        entry = AuditEntry(
            user="evaluator1",
            query="Ποια η στοχοθεσία;",
            retrieved_doc_ids=["doc1"],
            mode="semantic",
            answer_text="Η στοχοθεσία ήταν ικανοποιητική.",
        )
        audit_id = write_audit(conn, entry)
        conn.commit()
        conn.close()
        assert isinstance(audit_id, int)
        assert audit_id == 1
    finally:
        os.remove(db_path)


def test_update_is_blocked():
    db_path = _make_temp_db_path()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        entry = AuditEntry(user="u1", query="q1", retrieved_doc_ids=[], mode="structured")
        write_audit(conn, entry)
        conn.commit()

        try:
            conn.execute("UPDATE audit_log SET user = 'x' WHERE id = 1")
            assert False, "expected UPDATE to be blocked"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        conn.close()
    finally:
        os.remove(db_path)


def test_delete_is_blocked():
    db_path = _make_temp_db_path()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        entry = AuditEntry(user="u1", query="q1", retrieved_doc_ids=[], mode="structured")
        write_audit(conn, entry)
        conn.commit()

        try:
            conn.execute("DELETE FROM audit_log WHERE id = 1")
            assert False, "expected DELETE to be blocked"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        conn.close()
    finally:
        os.remove(db_path)


def test_row_survives_blocked_update_and_delete():
    db_path = _make_temp_db_path()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        entry = AuditEntry(
            user="evaluator2",
            query="Ποια η γνωμάτευση;",
            retrieved_doc_ids=["doc9"],
            mode="structured",
            answer_text="ΕΞΑΙΡΕΤΟΣ",
        )
        write_audit(conn, entry)
        conn.commit()

        for statement in (
            "UPDATE audit_log SET user = 'x' WHERE id = 1",
            "DELETE FROM audit_log WHERE id = 1",
        ):
            try:
                conn.execute(statement)
                assert False, f"expected '{statement}' to be blocked"
            except sqlite3.DatabaseError:
                pass

        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM audit_log WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row["user"] == "evaluator2"
        assert row["query"] == "Ποια η γνωμάτευση;"
        assert row["answer_text"] == "ΕΞΑΙΡΕΤΟΣ"
    finally:
        os.remove(db_path)


def test_answer_text_roundtrip_with_greek_quotes():
    db_path = _make_temp_db_path()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        answer = 'Ο χαρακτηρισμός ήταν «ΕΞΑΙΡΕΤΟΣ» με σχόλιο "καλή απόδοση".'
        entry = AuditEntry(
            user="evaluator3",
            query="Ποιος ο χαρακτηρισμός;",
            retrieved_doc_ids=["doc1"],
            mode="semantic",
            answer_text=answer,
        )
        audit_id = write_audit(conn, entry)
        conn.commit()

        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT answer_text FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
        conn.close()
        assert row["answer_text"] == answer
    finally:
        os.remove(db_path)


def test_migration_adds_answer_text_and_keeps_triggers():
    db_path = _make_temp_db_path()
    try:
        # Χτίζουμε χειροκίνητα ένα audit_log του παλιού schema (μόνο τις
        # παλιές στήλες, χωρίς answer_text, χωρίς triggers), σαν να προήλθε
        # από DB πριν από αυτή την αλλαγή.
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE audit_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                  TEXT NOT NULL DEFAULT (datetime('now')),
                user                TEXT NOT NULL,
                query               TEXT NOT NULL,
                retrieved_doc_ids   TEXT,
                mode                TEXT NOT NULL CHECK (mode IN ('structured', 'semantic')),
                prompt_version      TEXT,
                unsupported_ranks   TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO audit_log (user, query, retrieved_doc_ids, mode)
            VALUES (?, ?, ?, ?)
            """,
            ("old_user", "old_query", "[]", "structured"),
        )
        conn.commit()
        conn.close()

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_log)")}
        assert "answer_text" in columns

        old_row = conn.execute("SELECT * FROM audit_log WHERE user = 'old_user'").fetchone()
        assert old_row is not None
        assert old_row["query"] == "old_query"
        assert old_row["answer_text"] is None

        try:
            conn.execute("DELETE FROM audit_log WHERE user = 'old_user'")
            assert False, "expected DELETE to be blocked after migration"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        conn.close()
    finally:
        os.remove(db_path)


def run_all():
    tests = [
        test_init_db_write_audit_returns_id,
        test_update_is_blocked,
        test_delete_is_blocked,
        test_row_survives_blocked_update_and_delete,
        test_answer_text_roundtrip_with_greek_quotes,
        test_migration_adds_answer_text_and_keeps_triggers,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
