"""Mini test/sample flow για το backend/app/core/audit.py (refactor step).

Καλύπτει, πάνω σε in-memory SQLite fixture (ίδιο schema με production):
  - write_audit + readback, με prompt_version.
  - write_audit + readback, χωρίς prompt_version (structured mode, nullable).
  - ts αφήνεται στο SQLite DEFAULT όταν δεν δίνεται ρητά.

Εκτελείται standalone: `python tests/test_audit.py`
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.audit import AuditEntry, write_audit  # noqa: E402
from app.db.database import SCHEMA_PATH  # noqa: E402


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def test_write_and_readback_with_prompt_version():
    conn = _make_conn()
    entry = AuditEntry(
        user="evaluator1",
        query="Πώς ήταν η στοχοθεσία;",
        retrieved_doc_ids=["doc1", "doc2"],
        mode="semantic",
        prompt_version="v1",
    )

    write_audit(conn, entry)
    conn.commit()

    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["user"] == "evaluator1"
    assert row["query"] == "Πώς ήταν η στοχοθεσία;"
    assert json.loads(row["retrieved_doc_ids"]) == ["doc1", "doc2"]
    assert row["mode"] == "semantic"
    assert row["prompt_version"] == "v1"
    assert row["ts"] is not None  # SQLite DEFAULT (datetime('now'))


def test_write_without_prompt_version_is_nullable():
    conn = _make_conn()
    entry = AuditEntry(
        user="evaluator2",
        query="Ποια η γνωμάτευση;",
        retrieved_doc_ids=[],
        mode="structured",
    )

    write_audit(conn, entry)
    conn.commit()

    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["prompt_version"] is None
    assert json.loads(row["retrieved_doc_ids"]) == []
    assert row["mode"] == "structured"


def run_all():
    tests = [
        test_write_and_readback_with_prompt_version,
        test_write_without_prompt_version_is_nullable,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
