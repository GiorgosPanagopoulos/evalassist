"""Mini test/sample flow για το POST /query/structured πάνω στο schema
Περιληπτικού Σημειώματος.

Καλύπτει, πάνω σε temp file-based SQLite (ίδιο schema με production, 2
persons x 1 evaluation period seeded):
  - σωστά στοιχεία για τον scoped person/period.
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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.models.evaluation import (  # noqa: E402
    CAREER_PERIOD,
    DutyEntry,
    EvaluationEntry,
    EvaluatorInfo,
    FieldScore,
)

PERIOD = "2025-01-01..2025-12-31"

_PROMOTION_ROWS = [
    {
        "rank": "ΥΠΟΠΛΟΙΑΡΧΟΣ",
        "decision_date": "08/04/2019",
        "decision": "ΠΕ ΠΑΜΨΗΦΕΙ ΓΙΑ ΤΟ ΕΤΟΣ 2019-2020",
        "promotion_date": "05/07/2013",
    },
    {
        "rank": "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ",
        "decision_date": "02/04/2013",
        "decision": "ΠΕ ΠΑΜΨΗΦΕΙ ΓΙΑ ΤΟ ΕΤΟΣ 2013-2014",
        "promotion_date": "05/07/2008",
    },
]


def _entry(score: int, characterization: str) -> EvaluationEntry:
    return EvaluationEntry(
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        characterization=characterization,
        score=score,
        ea_type="Ε.Α.",
        unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
        duties=[DutyEntry(label="Κυβερνήτης", days=None)],
        rank_at_time="Πλωτάρχης",
        evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Ιωάννης Καραγιάννης", role="Διοικητής"),
        gnomatevon=None,
        defects=None,
        evaluator_notes="Καλή απόδοση.",
        gnomatevon_notes=None,
        field_scores=[FieldScore(field_code="141", value=score)],
        source_page=8,
    )


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
    entry1 = _entry(score=96, characterization="ΕΞΑΙΡΕΤΟΣ")
    eval_id = repository.upsert_evaluation(conn, "p1", entry1)
    repository.replace_field_scores(conn, eval_id, entry1.field_scores)
    repository.upsert_document(conn, "doc-p1", "p1", entry1.period, "/docs/doc-p1.pdf", 8)
    repository.replace_promotions(conn, "p1", _PROMOTION_ROWS)
    repository.upsert_document(conn, "doc-p1-career", "p1", CAREER_PERIOD, "/docs/doc-p1-career.pdf", 8)

    repository.upsert_person(conn, "p2", "Ιωάννου Μαρία")
    entry2 = _entry(score=55, characterization="ΜΕΤΡΙΟΣ")
    eval_id2 = repository.upsert_evaluation(conn, "p2", entry2)
    repository.replace_field_scores(conn, eval_id2, entry2.field_scores)
    repository.upsert_document(conn, "doc-p2", "p2", entry2.period, "/docs/doc-p2.pdf", 8)
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
            json={"person_id": "p1", "period": PERIOD, "operation": "get_scores"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["data"]["characterization"] == "ΕΞΑΙΡΕΤΟΣ"
        assert body["result"]["data"]["score"] == 96
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
            json={"person_id": "p1", "period": PERIOD, "operation": "get_scores"},
        )

        body = response.json()
        assert "doc-p2" not in body["result"]["retrieved_doc_ids"]
        assert body["result"]["data"]["score"] != 55  # p2's score, must not appear for p1
        assert body["result"]["data"]["characterization"] != "ΜΕΤΡΙΟΣ"
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
            json={"person_id": "p1", "period": PERIOD, "operation": "top_bottom_sections", "n": 1},
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
            json={"person_id": "p1", "period": PERIOD, "operation": "compare_periods"},
        )

        assert response.status_code == 422
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_get_promotions_table_returns_judged_for_and_career_doc_ids():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": PERIOD, "operation": "get_promotions_table"},
        )

        assert response.status_code == 200
        body = response.json()
        rows = {r["row_index"]: r for r in body["result"]["data"]["rows"]}
        assert rows[0]["judged_for"] is None
        assert rows[1]["judged_for"] == "ΥΠΟΠΛΟΙΑΡΧΟΣ"
        assert body["result"]["retrieved_doc_ids"] == ["doc-p1-career"]
        # career-wide: το doc-p1 (scoped στο evaluation period) δεν εμφανίζεται εδώ
        assert "doc-p1" not in body["result"]["retrieved_doc_ids"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_get_promotions_table_other_person_data_never_leaks():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p2", "period": PERIOD, "operation": "get_promotions_table"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["data"]["rows"] == []
        assert body["result"]["retrieved_doc_ids"] == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_get_promotions_table_writes_audit_row():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": PERIOD, "operation": "get_promotions_table"},
        )
        audit_id = response.json()["audit_id"]

        row = _last_audit_row(db_path)
        assert row["id"] == audit_id
        assert row["mode"] == "structured"
        assert json.loads(row["retrieved_doc_ids"]) == ["doc-p1-career"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_get_service_time_table_empty_result_is_200_not_error():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={"person_id": "p1", "period": PERIOD, "operation": "get_service_time_table"},
        )

        assert response.status_code == 200
        assert response.json()["result"]["data"]["rows"] == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_promotions_table_operation_rejects_other_period():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.post(
            "/query/structured",
            json={
                "person_id": "p1",
                "period": PERIOD,
                "operation": "get_promotions_table",
                "other_period": "2024-01-01..2024-12-31",
            },
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
        test_get_promotions_table_returns_judged_for_and_career_doc_ids,
        test_get_promotions_table_other_person_data_never_leaks,
        test_get_promotions_table_writes_audit_row,
        test_get_service_time_table_empty_result_is_200_not_error,
        test_promotions_table_operation_rejects_other_period,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
