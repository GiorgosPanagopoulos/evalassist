"""Mini test/sample flow για το append-only audit_log (Φάση 5, audit integrity).

Καλύπτει, πάνω σε temp file-based SQLite (ποτέ την πραγματική DB):
  - init_db σε καθαρή DB, write_audit περνάει και επιστρέφει id.
  - UPDATE/DELETE στο audit_log μπλοκάρονται από τα triggers (append-only).
  - η γραμμή επιβιώνει αναλλοίωτη μετά από μπλοκαρισμένα UPDATE/DELETE.
  - answer_text roundtrip με ελληνικό κείμενο που περιέχει εισαγωγικά.
  - migration path: DB χωρίς answer_text στήλη, init_db προσθέτει τη στήλη,
    διατηρεί την παλιά γραμμή, και ενεργοποιεί τα triggers.
  - migration refusal_reason: πάνω στο τρέχον schema της πραγματικής DB
    (με unsupported_ranks/answer_text, χωρίς refusal_reason) κρατά όλες τις
    γραμμές και τα triggers, και τρέχει δύο φορές χωρίς σφάλμα.

Εκτελείται standalone: `python tests/test_audit_integrity.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_helpers import remove_db  # noqa: E402

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
        remove_db(db_path)


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
        remove_db(db_path)


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
        remove_db(db_path)


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
        remove_db(db_path)


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
        remove_db(db_path)


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
        remove_db(db_path)


# Το schema του audit_log ακριβώς όπως είναι σήμερα στην πραγματική DB
# (`sqlite3 data/evalassist.db ".schema audit_log"`), πριν από το refusal_reason:
# οι unsupported_ranks/answer_text μπήκαν με ALTER ADD COLUMN, μαζί τα triggers.
_PRE_REFUSAL_REASON_SCHEMA = """
CREATE TABLE audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL DEFAULT (datetime('now')),
    user                TEXT NOT NULL,
    query               TEXT NOT NULL,
    retrieved_doc_ids   TEXT,
    mode                TEXT NOT NULL CHECK (mode IN ('structured', 'semantic')),
    prompt_version      TEXT
, unsupported_ranks TEXT, answer_text TEXT);
CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE is not allowed');
END;
CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE is not allowed');
END;
"""

_PRE_REFUSAL_REASON_ROWS = [
    ("u1", "q structured", '["doc1"]', "structured", None, None, '{"score": 95}'),
    ("u2", "q semantic", '["doc2"]', "semantic", "v3", '["Σμχος"]', "Απάντηση LLM."),
    ("u3", "Τι έγραφε η έκθεση του 2003;", "[]", "semantic", None, None, "Δεν υπάρχει περίοδος."),
]

_OLD_COLUMNS = (
    "id, ts, user, query, retrieved_doc_ids, mode, prompt_version, unsupported_ranks, answer_text"
)


def _make_pre_refusal_reason_db() -> Path:
    db_path = _make_temp_db_path()
    conn = sqlite3.connect(db_path)
    conn.executescript(_PRE_REFUSAL_REASON_SCHEMA)
    conn.executemany(
        "INSERT INTO audit_log (user, query, retrieved_doc_ids, mode, prompt_version, "
        "unsupported_ranks, answer_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        _PRE_REFUSAL_REASON_ROWS,
    )
    conn.commit()
    conn.close()
    return db_path


def _old_rows(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in conn.execute(f"SELECT {_OLD_COLUMNS} FROM audit_log ORDER BY id")]


def _trigger_sql(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(
        conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit_log'"
        ).fetchall()
    )


def test_migration_adds_refusal_reason_keeps_rows_and_triggers():
    db_path = _make_pre_refusal_reason_db()
    try:
        conn = sqlite3.connect(db_path)
        rows_before = _old_rows(conn)
        triggers_before = _trigger_sql(conn)
        conn.close()
        assert len(rows_before) == 3
        assert set(triggers_before) == {"audit_log_no_update", "audit_log_no_delete"}

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
        assert columns.count("refusal_reason") == 1
        assert _old_rows(conn) == rows_before
        null_count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE refusal_reason IS NULL"
        ).fetchone()[0]
        assert null_count == 3
        assert _trigger_sql(conn) == triggers_before

        for statement in (
            "UPDATE audit_log SET refusal_reason = 'year_out_of_range' WHERE id = 3",
            "UPDATE audit_log SET user = 'x' WHERE id = 1",
            "DELETE FROM audit_log WHERE id = 1",
        ):
            try:
                conn.execute(statement)
                assert False, f"expected '{statement}' to be blocked after migration"
            except sqlite3.DatabaseError as exc:
                assert "append-only" in str(exc)
        assert _old_rows(conn) == rows_before

        # Νέα γραμμή μετά το migration: ο κωδικός γράφεται verbatim ως TEXT.
        audit_id = write_audit(
            conn,
            AuditEntry(
                user="u4",
                query="q",
                retrieved_doc_ids=[],
                mode="semantic",
                refusal_reason="year_out_of_range",
            ),
        )
        conn.commit()
        value = conn.execute(
            "SELECT refusal_reason FROM audit_log WHERE id = ?", (audit_id,)
        ).fetchone()[0]
        conn.close()
        assert type(value) is str
        assert value == "year_out_of_range"
    finally:
        remove_db(db_path)


def test_migration_runs_twice_without_error():
    db_path = _make_pre_refusal_reason_db()
    try:
        init_db(db_path)
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        triggers = _trigger_sql(conn)
        conn.close()
        assert columns.count("refusal_reason") == 1
        assert count == 3
        assert set(triggers) == {"audit_log_no_update", "audit_log_no_delete"}
    finally:
        remove_db(db_path)


# Το schema του audit_log όπως είναι στην πραγματική ΒΔ πριν από το scope
# (με refusal_reason, χωρίς person_id/period/other_period), μαζί με τα triggers.
_PRE_SCOPE_SCHEMA = _PRE_REFUSAL_REASON_SCHEMA.replace(
    ", unsupported_ranks TEXT, answer_text TEXT);",
    ", unsupported_ranks TEXT, answer_text TEXT, refusal_reason TEXT);",
)
_SCOPE_COLUMNS = ("person_id", "period", "other_period")


def _make_pre_scope_db() -> Path:
    db_path = _make_temp_db_path()
    conn = sqlite3.connect(db_path)
    conn.executescript(_PRE_SCOPE_SCHEMA)
    conn.executemany(
        "INSERT INTO audit_log (user, query, retrieved_doc_ids, mode, prompt_version, "
        "unsupported_ranks, answer_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        _PRE_REFUSAL_REASON_ROWS,
    )
    conn.commit()
    conn.close()
    return db_path


def _all_rows(conn: sqlite3.Connection) -> list[tuple]:
    return [
        tuple(r)
        for r in conn.execute(f"SELECT {_OLD_COLUMNS}, refusal_reason FROM audit_log ORDER BY id")
    ]


def test_migration_adds_scope_columns_keeps_rows_and_triggers():
    db_path = _make_pre_scope_db()
    try:
        conn = sqlite3.connect(db_path)
        columns_before = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
        rows_before = _all_rows(conn)
        triggers_before = _trigger_sql(conn)
        conn.close()
        assert not set(_SCOPE_COLUMNS) & set(columns_before)
        assert len(rows_before) == 3

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
        assert columns == columns_before + list(_SCOPE_COLUMNS)
        assert _all_rows(conn) == rows_before
        # Καμία backfill: οι παλιές γραμμές μένουν NULL.
        not_null = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE "
            "person_id IS NOT NULL OR period IS NOT NULL OR other_period IS NOT NULL"
        ).fetchone()[0]
        assert not_null == 0
        assert _trigger_sql(conn) == triggers_before
        try:
            conn.execute("UPDATE audit_log SET period = 'x' WHERE id = 1")
            assert False, "expected UPDATE to be blocked after migration"
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)

        audit_id = write_audit(
            conn,
            AuditEntry(
                user="u4",
                query="q",
                retrieved_doc_ids=[],
                mode="structured",
                person_id="p1",
                period="2025-01-01..2025-12-31",
                other_period="2024-01-01..2024-12-31",
            ),
        )
        conn.commit()
        value = conn.execute(
            "SELECT person_id, period, other_period FROM audit_log WHERE id = ?", (audit_id,)
        ).fetchone()
        conn.close()
        assert value == ("p1", "2025-01-01..2025-12-31", "2024-01-01..2024-12-31")
    finally:
        remove_db(db_path)


def test_scope_migration_second_run_changes_nothing():
    db_path = _make_pre_scope_db()
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        schema_first = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE tbl_name = 'audit_log' ORDER BY name"
        ).fetchall()
        rows_first = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        conn.close()

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        schema_second = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE tbl_name = 'audit_log' ORDER BY name"
        ).fetchall()
        rows_second = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        conn.close()
        assert schema_second == schema_first
        assert rows_second == rows_first
    finally:
        remove_db(db_path)


def run_all():
    tests = [
        test_init_db_write_audit_returns_id,
        test_update_is_blocked,
        test_delete_is_blocked,
        test_row_survives_blocked_update_and_delete,
        test_answer_text_roundtrip_with_greek_quotes,
        test_migration_adds_answer_text_and_keeps_triggers,
        test_migration_adds_refusal_reason_keeps_rows_and_triggers,
        test_migration_runs_twice_without_error,
        test_migration_adds_scope_columns_keeps_rows_and_triggers,
        test_scope_migration_second_run_changes_nothing,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
