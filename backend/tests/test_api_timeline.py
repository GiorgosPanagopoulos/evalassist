"""Tests για το GET /person/{person_id}/timeline.

Πάνω σε temp file-based SQLite (ίδιο schema με production), seeded με το
ακριβές σχήμα του Μ-01253 (36 περίοδοι: 32 Ε.Α. με score, 4 Σ.Α. χωρίς):
  - positive: 36 points, 32 με score, 4 null — και τα 4 null είναι Σ.Α.
  - positive: χρονολογική ταξινόμηση, doc_id + page ανά point, audit row
    με mode="structured" και τα retrieved doc_ids.
  - negative: άλλο person_id ΔΕΝ επιστρέφει δεδομένα του Μ-01253.
  - negative: κανένα Σ.Α. point δεν παίρνει τιμή από γειτονικό point.
  - negative: >1 έγγραφα για το ίδιο (person_id, period) -> ValueError/400,
    ποτέ σιωπηλό LIMIT 1.
Επιπλέον, αν υπάρχει η πραγματική ΒΔ (backend/data/evalassist.db), ο ίδιος
positive έλεγχος τρέχει και πάνω της.

Εκτελείται standalone: `PYTHONPATH=. python tests/test_api_timeline.py`
"""

import json
import os
import shutil
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
from app.models.evaluation import EvaluationEntry, EvaluatorInfo  # noqa: E402

PERSON = "Μ-01253"
OTHER_PERSON = "Μ-99999"
DOC_ID = "29b215931c674b6e"
REAL_DB = Path(__file__).resolve().parents[1] / "data" / "evalassist.db"

# (period_start, period_end, ea_type, score, source_page) — ίδιο σχήμα με τα
# 36 evaluations του Μ-01253 στην πραγματική ΒΔ. Σκόπιμα ΟΧΙ χρονολογικά
# ταξινομημένα εδώ, ώστε το test να ελέγχει ότι το endpoint ταξινομεί.
_PERIODS: list[tuple[str, str, str, int | None, int]] = [
    ("2024-01-01", "2024-07-02", "Ε.Α.", 100, 4),
    ("2023-06-15", "2023-12-31", "Ε.Α.", 100, 4),
    ("2023-01-01", "2023-06-14", "Ε.Α.", 100, 4),
    ("2022-05-21", "2022-12-31", "Ε.Α.", 100, 4),
    ("2022-01-01", "2022-05-20", "Ε.Α.", 100, 4),
    ("2021-06-11", "2021-12-31", "Ε.Α.", 100, 4),
    ("2021-01-01", "2021-06-10", "Ε.Α.", 100, 4),
    ("2020-07-14", "2020-12-31", "Ε.Α.", 100, 4),
    ("2019-09-27", "2020-07-13", "Ε.Α.", 99, 4),
    ("2019-09-17", "2019-09-26", "Σ.Α.", None, 4),
    ("2019-01-26", "2019-09-16", "Ε.Α.", 100, 4),
    ("2018-10-15", "2019-01-25", "Ε.Α.", 99, 4),
    ("2018-08-28", "2018-10-14", "Σ.Α.", None, 4),
    ("2018-01-01", "2018-08-27", "Ε.Α.", 100, 4),
    ("2017-01-01", "2017-12-31", "Ε.Α.", 100, 5),
    ("2016-01-01", "2016-12-31", "Ε.Α.", 100, 5),
    ("2015-09-02", "2015-12-31", "Ε.Α.", 100, 5),
    ("2015-01-01", "2015-09-01", "Ε.Α.", 100, 5),
    ("2014-01-01", "2014-12-31", "Ε.Α.", 100, 5),
    ("2013-08-28", "2013-12-31", "Ε.Α.", 100, 5),
    ("2013-01-01", "2013-08-27", "Ε.Α.", 96, 5),
    ("2012-09-14", "2012-12-31", "Ε.Α.", 93, 7),
    ("2012-01-01", "2012-09-13", "Ε.Α.", 96, 7),
    ("2011-06-21", "2011-12-31", "Ε.Α.", 95, 7),
    ("2011-01-01", "2011-06-20", "Ε.Α.", 100, 7),
    ("2010-05-17", "2010-12-31", "Ε.Α.", 100, 7),
    ("2010-01-01", "2010-05-16", "Ε.Α.", 100, 7),
    ("2009-04-10", "2009-04-10", "Ε.Α.", 100, 7),
    ("2009-01-01", "2009-04-09", "Σ.Α.", None, 7),
    ("2008-08-25", "2008-12-31", "Ε.Α.", 95, 7),
    ("2008-01-01", "2008-08-21", "Ε.Α.", 100, 7),
    ("2007-05-08", "2007-12-31", "Ε.Α.", 100, 8),
    ("2007-01-26", "2007-05-06", "Ε.Α.", 99, 8),
    ("2007-01-01", "2007-01-25", "Σ.Α.", None, 8),
    ("2006-01-01", "2006-12-31", "Ε.Α.", 100, 8),
    ("2005-07-05", "2005-12-31", "Ε.Α.", 98, 8),
]
assert len(_PERIODS) == 36
assert sum(1 for p in _PERIODS if p[2] == "Ε.Α.") == 32
assert sum(1 for p in _PERIODS if p[2] == "Σ.Α.") == 4


def _entry(start: str, end: str, ea_type: str, score: int | None, page: int) -> EvaluationEntry:
    return EvaluationEntry(
        period_start=date.fromisoformat(start),
        period_end=date.fromisoformat(end),
        characterization="ΕΞΑΙΡΕΤΟΣ" if score is not None else None,
        score=score,
        ea_type=ea_type,
        unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
        evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Ιωάννης Καραγιάννης", role="Διοικητής"),
        source_page=page,
    )


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repository.upsert_person(conn, PERSON, "Παπαδόπουλος Γιώργος")
    for start, end, ea_type, score, page in _PERIODS:
        entry = _entry(start, end, ea_type, score, page)
        repository.upsert_evaluation(conn, PERSON, entry)
        repository.upsert_document(conn, DOC_ID, PERSON, entry.period, "/docs/m-01253.pdf", 12)

    repository.upsert_person(conn, OTHER_PERSON, "Ιωάννου Μαρία")
    other = _entry("2025-01-01", "2025-12-31", "Ε.Α.", 55, 3)
    repository.upsert_evaluation(conn, OTHER_PERSON, other)
    repository.upsert_document(conn, "doc-other", OTHER_PERSON, other.period, "/docs/other.pdf", 3)
    conn.commit()
    conn.close()
    return db_path


def _override_settings(db_path: Path) -> None:
    test_settings = Settings(_env_file=None, DB_PATH=db_path)
    app.dependency_overrides[get_settings] = lambda: test_settings


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _audit_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    conn.close()
    return rows


def _assert_m01253_shape(points: list[dict]) -> None:
    assert len(points) == 36, len(points)
    scored = [p for p in points if p["score"] is not None]
    unscored = [p for p in points if p["score"] is None]
    assert len(scored) == 32, len(scored)
    assert len(unscored) == 4, len(unscored)
    # Και τα 4 null points είναι Σ.Α. — και αντίστροφα, κανένα Ε.Α. δεν είναι null.
    assert all(p["kind"] == "Σ.Α." for p in unscored), [p["kind"] for p in unscored]
    assert all(p["kind"] == "Ε.Α." for p in scored)
    # Χρονολογική ταξινόμηση.
    starts = [p["period_start"] for p in points]
    assert starts == sorted(starts)
    # Κάθε point έχει doc_id + page + section.
    for p in points:
        assert p["doc_id"] == DOC_ID
        assert isinstance(p["page"], int)
        assert p["section"] == "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ"


def test_timeline_returns_36_points_32_scored_4_null_all_sa():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.get(f"/person/{PERSON}/timeline")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["result"]["person_id"] == PERSON
        _assert_m01253_shape(body["result"]["points"])
        assert body["result"]["retrieved_doc_ids"] == [DOC_ID]
        assert isinstance(body["audit_id"], int)

        # Οι τιμές είναι το evaluations.score αυτούσιο.
        by_period = {p["period"]: p for p in body["result"]["points"]}
        assert by_period["2012-09-14..2012-12-31"]["score"] == 93
        assert by_period["2005-07-05..2005-12-31"]["score"] == 98
        assert by_period["2012-09-14..2012-12-31"]["page"] == 7
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_timeline_writes_one_audit_row_with_structured_mode():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.get(f"/person/{PERSON}/timeline", headers={"X-User": "tester"})
        assert response.status_code == 200

        rows = _audit_rows(db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == response.json()["audit_id"]
        assert row["mode"] == "structured"
        assert row["user"] == "tester"
        assert json.loads(row["retrieved_doc_ids"]) == [DOC_ID]
        assert json.loads(row["query"])["person_id"] == PERSON
        assert row["prompt_version"] is None
        assert len(json.loads(row["answer_text"])) == 36
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_other_person_never_gets_m01253_data():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.get(f"/person/{OTHER_PERSON}/timeline")

        assert response.status_code == 200
        body = response.json()
        points = body["result"]["points"]
        assert len(points) == 1
        assert points[0]["score"] == 55
        assert points[0]["doc_id"] == "doc-other"
        assert DOC_ID not in body["result"]["retrieved_doc_ids"]
        assert DOC_ID not in response.text
        assert "2012-09-14..2012-12-31" not in response.text

        # Άγνωστο person_id: άδεια λίστα, όχι διαρροή — και πάλι audit row.
        response = client.get("/person/Μ-00000/timeline")
        assert response.status_code == 200
        assert response.json()["result"]["points"] == []
        assert response.json()["result"]["retrieved_doc_ids"] == []
        assert DOC_ID not in response.text
        assert len(_audit_rows(db_path)) == 2
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_sa_points_never_take_value_from_neighbours():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        points = client.get(f"/person/{PERSON}/timeline").json()["result"]["points"]

        sa_indices = [i for i, p in enumerate(points) if p["kind"] == "Σ.Α."]
        assert len(sa_indices) == 4
        for i in sa_indices:
            assert points[i]["score"] is None, points[i]
            # Και οι δύο γείτονες έχουν score· το Σ.Α. δεν πήρε κανέναν από αυτούς
            # (ούτε μέσο όρο τους).
            prev_score = points[i - 1]["score"]
            next_score = points[i + 1]["score"]
            assert prev_score is not None and next_score is not None
            assert points[i]["score"] not in (prev_score, next_score, (prev_score + next_score) / 2)

        # Το JSON έχει κυριολεκτικά null, όχι 0 ή "".
        raw = client.get(f"/person/{PERSON}/timeline").text
        assert '"score":null' in raw.replace(" ", "")
        assert '"score":0' not in raw.replace(" ", "")
        assert '"score":""' not in raw.replace(" ", "")
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_multiple_documents_for_same_period_is_error_not_limit_1():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        # Δεύτερο έγγραφο για ίδιο (person_id, period) — το PK είναι (doc_id, period).
        conn.execute(
            "INSERT INTO documents (doc_id, person_id, period, path, page_count) "
            "VALUES (?, ?, ?, ?, ?)",
            ("duplicate-doc", PERSON, "2012-09-14..2012-12-31", "/docs/dup.pdf", 1),
        )
        conn.commit()
        conn.close()

        _override_settings(db_path)
        client = TestClient(app)

        response = client.get(f"/person/{PERSON}/timeline")

        assert response.status_code == 400, response.text
        assert "2012-09-14..2012-12-31" in response.json()["detail"]
        # Error path: audit row γράφεται και πάλι, με άδεια doc_ids.
        rows = _audit_rows(db_path)
        assert len(rows) == 1
        assert rows[0]["mode"] == "structured"
        assert json.loads(rows[0]["retrieved_doc_ids"]) == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_real_db_m01253_if_present():
    if not REAL_DB.exists():
        print(f"SKIP (no real DB at {REAL_DB})")
        return
    # Αντίγραφο: το endpoint γράφει audit_log, δεν θέλουμε test rows στην
    # πραγματική ΒΔ.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    shutil.copyfile(REAL_DB, db_path)
    try:
        _override_settings(db_path)
        client = TestClient(app)
        response = client.get(f"/person/{PERSON}/timeline")
        assert response.status_code == 200, response.text
        _assert_m01253_shape(response.json()["result"]["points"])
    finally:
        _clear_overrides()
        os.remove(db_path)


def run_all():
    tests = [
        test_timeline_returns_36_points_32_scored_4_null_all_sa,
        test_timeline_writes_one_audit_row_with_structured_mode,
        test_other_person_never_gets_m01253_data,
        test_sa_points_never_take_value_from_neighbours,
        test_multiple_documents_for_same_period_is_error_not_limit_1,
        test_real_db_m01253_if_present,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
