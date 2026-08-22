"""Mini test/sample flow για /persons, /persons/{id}/periods, /health (Φάση 4).

Εκτελείται standalone: `python tests/test_api_meta.py`
"""

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
from app.models.evaluation import DutyEntry, EvaluationEntry, EvaluatorInfo  # noqa: E402


def _entry(year: int) -> EvaluationEntry:
    return EvaluationEntry(
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        characterization="ΕΞΑΙΡΕΤΟΣ",
        score=90,
        ea_type="Ε.Α.",
        unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
        duties=[DutyEntry(label="Κυβερνήτης", days=None)],
        rank_at_time="Πλωτάρχης",
        evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Ιωάννης Καραγιάννης", role="Διοικητής"),
        gnomatevon=None,
        defects=None,
        evaluator_notes="Καλή απόδοση.",
        gnomatevon_notes=None,
        field_scores=[],
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
    repository.upsert_evaluation(conn, "p1", _entry(2024))
    repository.upsert_evaluation(conn, "p1", _entry(2025))
    repository.upsert_person(conn, "p2", "Ιωάννου Μαρία")
    repository.upsert_evaluation(conn, "p2", _entry(2025))
    conn.commit()
    conn.close()
    return db_path


def _override_settings(db_path: Path, ollama_url: str | None = None) -> None:
    kwargs = {"DB_PATH": db_path}
    if ollama_url is not None:
        kwargs["OLLAMA_URL"] = ollama_url
    test_settings = Settings(_env_file=None, **kwargs)
    app.dependency_overrides[get_settings] = lambda: test_settings


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_list_persons():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.get("/persons")

        assert response.status_code == 200
        person_ids = {p["person_id"] for p in response.json()}
        assert person_ids == {"p1", "p2"}
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_list_periods_for_person():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        client = TestClient(app)

        response = client.get("/persons/p1/periods")

        assert response.status_code == 200
        assert response.json() == [_entry(2024).period, _entry(2025).period]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_health_reports_ollama_unreachable_on_dead_port():
    db_path = _make_temp_db()
    try:
        # port 1 δεν έχει listener -> connection refused, γρήγορο fail
        _override_settings(db_path, ollama_url="http://127.0.0.1:1")
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["ollama_reachable"] is False
    finally:
        _clear_overrides()
        os.remove(db_path)


def run_all():
    tests = [
        test_list_persons,
        test_list_periods_for_person,
        test_health_reports_ollama_unreachable_on_dead_port,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
