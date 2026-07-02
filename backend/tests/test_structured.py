"""Mini test/sample flow για το deterministic SQL retrieval (Φάση 3).

Καλύπτει, πάνω σε in-memory SQLite fixture:
  - get_scores: lookup βαθμολογιών ανά person_id/period + sources/retrieved_doc_ids.
  - compare_periods: σύγκριση δύο περιόδων του ίδιου ατόμου.
  - top_bottom_sections: top/bottom N τομείς βάσει score.
  - άδειο αποτέλεσμα -> valid StructuredResult με άδειο data, όχι exception.

Εκτελείται standalone: `python tests/test_structured.py`
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import repository  # noqa: E402
from app.db.database import SCHEMA_PATH  # noqa: E402
from app.models.evaluation import SectionScore  # noqa: E402
from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.structured import (  # noqa: E402
    compare_periods,
    get_scores,
    top_bottom_sections,
)


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def _seed_person(conn: sqlite3.Connection, person_id: str, period: str, sections: list[tuple[str, int]], doc_id: str) -> None:
    repository.upsert_person(conn, person_id, "Παπαδόπουλος Γιώργος")
    eval_id = repository.upsert_evaluation(conn, person_id, period, "A", "Καλή απόδοση.")
    repository.replace_scores(
        conn, eval_id, [SectionScore(section=s, score=sc, comment=None) for s, sc in sections]
    )
    repository.upsert_document(conn, doc_id, person_id, period, f"/docs/{doc_id}.pdf", 3)
    conn.commit()


def test_get_scores_returns_sections_sources_and_doc_ids():
    conn = _make_conn()
    _seed_person(
        conn,
        "p1",
        "2025",
        [("Στοχοθεσία", 4), ("Ηγετική Ικανότητα", 5)],
        "doc1",
    )

    result = get_scores(conn, IsolationScope(person_id="p1", period="2025"))

    assert result.mode == "structured"
    assert result.data["gnmatefsi"] == "A"
    assert len(result.data["sections"]) == 2
    assert {s["section"] for s in result.data["sections"]} == {"Στοχοθεσία", "Ηγετική Ικανότητα"}
    assert result.retrieved_doc_ids == ["doc1"]
    assert all(src["doc_id"] == "doc1" for src in result.sources)


def test_get_scores_empty_result_is_not_an_exception():
    conn = _make_conn()
    result = get_scores(conn, IsolationScope(person_id="missing", period="2025"))

    assert result.data == {}
    assert result.sources == []
    assert result.retrieved_doc_ids == []


def test_compare_periods():
    conn = _make_conn()
    _seed_person(conn, "p1", "2024", [("Στοχοθεσία", 3)], "doc-2024")
    _seed_person(conn, "p1", "2025", [("Στοχοθεσία", 5)], "doc-2025")

    result = compare_periods(conn, "p1", "2024", "2025")

    assert result.data["sections_a"][0]["score"] == 3
    assert result.data["sections_b"][0]["score"] == 5
    assert set(result.retrieved_doc_ids) == {"doc-2024", "doc-2025"}


def test_top_bottom_sections():
    conn = _make_conn()
    sections = [
        ("Στοχοθεσία", 5),
        ("Ηγετική Ικανότητα", 4),
        ("Επαγγελματική Επάρκεια", 1),
        ("Συνεργασία και Ομαδικότητα", 2),
    ]
    _seed_person(conn, "p1", "2025", sections, "doc1")

    result = top_bottom_sections(conn, IsolationScope(person_id="p1", period="2025"), n=2)

    top_names = [s["section"] for s in result.data["top"]]
    bottom_names = [s["section"] for s in result.data["bottom"]]
    assert top_names == ["Στοχοθεσία", "Ηγετική Ικανότητα"]
    assert bottom_names == ["Επαγγελματική Επάρκεια", "Συνεργασία και Ομαδικότητα"]


def run_all():
    tests = [
        test_get_scores_returns_sections_sources_and_doc_ids,
        test_get_scores_empty_result_is_not_an_exception,
        test_compare_periods,
        test_top_bottom_sections,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
