"""Mini test/sample flow για το POST /query/structured (Φάση 4).

Καλύπτει, πάνω σε temp file-based SQLite (ίδιο schema με production, 2
persons x 2 periods seeded):
  - σωστά scores για τον scoped person/period.
  - τα δεδομένα άλλου person δεν διαρρέουν ποτέ στην απάντηση.
  - γράφεται ακριβώς μία γραμμή audit_log με mode="structured".
  - μη έγκυρος συνδυασμός operation/πεδίων -> 422.

Εκτελείται standalone: `python tests/test_api_structured.py`
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.models.evaluation import SectionScore  # noqa: E402


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
    eval_id = repository.upsert_evaluation(conn, "p1", "2025", "A", "Καλή απόδοση.")
    repository.replace_scores(
        conn, eval_id, [SectionScore(section="Στοχοθεσία", score=4, comment=None)]
    )
    repository.upsert_document(conn, "doc-p1", "p1", "2025", "/docs/doc-p1.pdf", 2)

    repository.upsert_person(conn, "p2", "Ιωάννου Μαρία")
    eval_id2 = repository.upsert_evaluation(conn, "p2", "2025", "B", "Άριστη απόδοση.")
    repository.replace_scores(
        conn, eval_id2, [SectionScore(section="Στοχοθεσία", score=2, comment=None)]
    )
    repository.upsert_document(conn, "doc-p2", "p2", "2025", "/docs/doc-p2.pdf", 1)
    conn.commit()
    conn.close()
    return db_path


def _override_settings(db_path: Path) -> None:
    test_settings = Settings(_env_file=None, DB_PATH=db_path)
    app.dependency_overrides[get_settings] = lambda: test_settings


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _last_audit_row(db_path: Path) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row


def test_get_scores_scoped_to_person_and_period():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": "2025", "operation": "get_scores"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["data"]["gnmatefsi"] == "A"
        assert body["result"]["retrieved_doc_ids"] == ["doc-p1"]
        assert isinstance(body["audit_id"], int)
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_other_person_data_never_leaks():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": "2025", "operation": "get_scores"},
        )

        body = response.json()
        assert "doc-p2" not in body["result"]["retrieved_doc_ids"]
        assert body["result"]["data"]["gnmatefsi"] != "B"
        for section in body["result"]["data"]["sections"]:
            assert section["score"] != 2  # p2's score, must not appear for p1
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_audit_row_written_with_structured_mode():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": "2025", "operation": "top_bottom_sections", "n": 1},
        )
        audit_id = response.json()["audit_id"]

        row = _last_audit_row(db_path)
        assert row["id"] == audit_id
        assert row["mode"] == "structured"
        assert json.loads(row["retrieved_doc_ids"]) == ["doc-p1"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_invalid_operation_field_combo_is_422():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        # compare_periods χωρίς other_period -> μη έγκυρος συνδυασμός
        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": "2025", "operation": "compare_periods"},
        )

        assert response.status_code == 422
    finally:
        _clear_overrides()
        os.remove(db_path)


def run_all():
    tests = [
        test_get_scores_scoped_to_person_and_period,
        test_other_person_data_never_leaks,
        test_audit_row_written_with_structured_mode,
        test_invalid_operation_field_combo_is_422,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
