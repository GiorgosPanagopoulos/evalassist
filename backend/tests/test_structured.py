"""Mini test/sample flow για το deterministic SQL retrieval πάνω στο schema
Περιληπτικού Σημειώματος.

Καλύπτει, πάνω σε in-memory SQLite fixture:
  - get_scores: lookup evaluation entry ανά person_id/period + field_scores +
    sources/retrieved_doc_ids.
  - compare_periods: σύγκριση δύο περιόδων του ίδιου ατόμου.
  - top_bottom_sections: top/bottom N αναλυτικά πεδία (field_scores) βάσει τιμής.
  - άδειο αποτέλεσμα -> valid StructuredResult με άδειο data, όχι exception.

Εκτελείται standalone: `python tests/test_structured.py`
"""

import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import repository  # noqa: E402
from app.db.database import SCHEMA_PATH  # noqa: E402
from app.models.evaluation import EvaluationEntry, EvaluatorInfo, FieldScore  # noqa: E402
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


def _make_entry(period_start: str, score: int, field_scores: list[tuple[str, object]]) -> EvaluationEntry:
    year = int(period_start.split("-")[0])
    return EvaluationEntry(
        period_start=date.fromisoformat(period_start),
        period_end=date(year, 12, 31),
        characterization="ΕΞΑΙΡΕΤΟΣ",
        score=score,
        ea_type="Ε.Α.",
        unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
        duties=["Κυβερνήτης"],
        rank_at_time="Πλωτάρχης",
        evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Ιωάννης Καραγιάννης", role="Διοικητής"),
        gnomatevon=None,
        defects=None,
        evaluator_notes="Καλή απόδοση.",
        gnomatevon_notes=None,
        field_scores=[FieldScore(field_code=code, value=value) for code, value in field_scores],
        source_page=8,
    )


def _seed_person(
    conn: sqlite3.Connection,
    person_id: str,
    entry: EvaluationEntry,
    doc_id: str,
) -> None:
    repository.upsert_person(conn, person_id, "Παπαδόπουλος Γιώργος")
    eval_id = repository.upsert_evaluation(conn, person_id, entry)
    repository.replace_field_scores(conn, eval_id, entry.field_scores)
    repository.upsert_document(conn, doc_id, person_id, entry.period, f"/docs/{doc_id}.pdf", 8)
    conn.commit()


def test_get_scores_returns_entry_field_scores_sources_and_doc_ids():
    conn = _make_conn()
    entry = _make_entry("2025-01-01", 96, [("141", 96), ("91", 95), ("142α", "ΝΑΙ")])
    _seed_person(conn, "p1", entry, "doc1")

    result = get_scores(conn, IsolationScope(person_id="p1", period=entry.period))

    assert result.mode == "structured"
    assert result.data["characterization"] == "ΕΞΑΙΡΕΤΟΣ"
    assert result.data["score"] == 96
    assert {(fs["field_code"], fs["value"]) for fs in result.data["field_scores"]} == {
        ("141", 96),
        ("91", 95),
        ("142α", "ΝΑΙ"),
    }
    assert result.retrieved_doc_ids == ["doc1"]
    assert all(src["doc_id"] == "doc1" for src in result.sources)


def test_get_scores_empty_result_is_not_an_exception():
    conn = _make_conn()
    result = get_scores(conn, IsolationScope(person_id="missing", period="2025-01-01..2025-12-31"))

    assert result.data == {}
    assert result.sources == []
    assert result.retrieved_doc_ids == []


def test_compare_periods():
    conn = _make_conn()
    entry_2024 = _make_entry("2024-01-01", 80, [("141", 80)])
    entry_2025 = _make_entry("2025-01-01", 95, [("141", 95)])
    _seed_person(conn, "p1", entry_2024, "doc-2024")
    _seed_person(conn, "p1", entry_2025, "doc-2025")

    result = compare_periods(conn, "p1", entry_2024.period, entry_2025.period)

    assert result.data["entry_a"]["score"] == 80
    assert result.data["entry_b"]["score"] == 95
    assert set(result.retrieved_doc_ids) == {"doc-2024", "doc-2025"}


def test_top_bottom_sections_ranks_numeric_field_scores():
    conn = _make_conn()
    entry = _make_entry(
        "2025-01-01",
        90,
        [("141", 90), ("91", 40), ("93", 70), ("142α", "ΝΑΙ"), ("142β", "ΟΧΙ")],
    )
    _seed_person(conn, "p1", entry, "doc1")

    result = top_bottom_sections(conn, IsolationScope(person_id="p1", period=entry.period), n=2)

    top_codes = [fs["field_code"] for fs in result.data["top"]]
    bottom_codes = [fs["field_code"] for fs in result.data["bottom"]]
    assert top_codes == ["141", "93"]
    assert bottom_codes == ["91", "93"]
    # τα ΝΑΙ/ΟΧΙ πεδία δεν είναι αριθμητικά -> δεν κατατάσσονται
    assert "142α" not in top_codes + bottom_codes
    assert "142β" not in top_codes + bottom_codes


def run_all():
    tests = [
        test_get_scores_returns_entry_field_scores_sources_and_doc_ids,
        test_get_scores_empty_result_is_not_an_exception,
        test_compare_periods,
        test_top_bottom_sections_ranks_numeric_field_scores,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
