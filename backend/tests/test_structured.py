"""Mini test/sample flow για το deterministic SQL retrieval πάνω στο schema
Περιληπτικού Σημειώματος.

Καλύπτει, πάνω σε in-memory SQLite fixture:
  - get_scores: lookup evaluation entry ανά person_id/period + field_scores +
    citations/retrieved_doc_ids.
  - compare_periods: σύγκριση δύο περιόδων του ίδιου ατόμου.
  - top_bottom_sections: top/bottom N αναλυτικά πεδία (field_scores) βάσει τιμής,
    με το ολιστικό πεδίο 141 εκτός κατάταξης και ξεχωριστά ως `overall`.
  - άδειο αποτέλεσμα -> valid StructuredResult με άδειο data, όχι exception.

Εκτελείται standalone: `python tests/test_structured.py`
"""

import os
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_helpers import remove_db  # noqa: E402

from app.db import repository  # noqa: E402
from app.db.database import SCHEMA_PATH, init_db  # noqa: E402
from app.models.evaluation import (  # noqa: E402
    CAREER_PERIOD,
    DutyEntry,
    EvaluationEntry,
    EvaluatorInfo,
    FieldScore,
)
from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.structured import (  # noqa: E402
    OVERALL_FIELD_CODE,
    compare_periods,
    get_promotions_table,
    get_scores,
    get_service_time_table,
    top_bottom_sections,
)

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
    {
        "rank": "ΣΗΜΑΙΟΦΟΡΟΣ",
        "decision_date": "27/03/2008",
        "decision": "4 Α - 2 ΔΑΒ ΓΙΑ ΤΟ ΕΤΟΣ 2008-09",
        "promotion_date": "05/07/2005",
    },
]

_SERVICE_TIME_ROWS = [
    {"subsection": "α", "label": "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ", "years": 23, "months": 0, "days": 10},
    {"subsection": "β", "label": "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ", "years": 13, "months": 4, "days": 8},
    {"subsection": "β", "label": "ΠΛΟΙΑ", "years": 12, "months": 11, "days": 7},
    {"subsection": "β", "label": "Αος ΜΗΧΑΝΙΚΟΣ", "years": 7, "months": 1, "days": 8},
]


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    return db_path


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
        duties=[DutyEntry(label="Κυβερνήτης", days=None)],
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


def test_get_scores_returns_entry_field_scores_citations_and_doc_ids():
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
    assert [c.model_dump() for c in result.citations] == [
        {"doc_id": "doc1", "page": 8, "section": "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ"}
    ]


def test_get_scores_empty_result_is_not_an_exception():
    conn = _make_conn()
    result = get_scores(conn, IsolationScope(person_id="missing", period="2025-01-01..2025-12-31"))

    assert result.data == {}
    assert result.citations == []
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
    assert [(c.doc_id, c.page) for c in result.citations] == [("doc-2024", 8), ("doc-2025", 8)]


def test_top_bottom_sections_ranks_numeric_field_scores():
    """Το προηγούμενο assertion ήταν `top_codes == ["141", "93"]`, δηλαδή
    κωδικοποιούσε το bug: το 141 κατατασσόταν σαν πεδίο επίδοσης. Τώρα βγαίνει
    από την κατάταξη και ελέγχεται χωριστά στα tests του `overall` παρακάτω."""
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
    assert top_codes == ["93", "91"]
    assert bottom_codes == ["91", "93"]
    # τα ΝΑΙ/ΟΧΙ πεδία δεν είναι αριθμητικά -> δεν κατατάσσονται
    assert "142α" not in top_codes + bottom_codes
    assert "142β" not in top_codes + bottom_codes


def test_top_bottom_sections_overall_field_is_returned_separately():
    """POSITIVE: όταν υπάρχει το 141, επιστρέφεται στο `overall` και ΔΕΝ
    εμφανίζεται ούτε στα top ούτε στα bottom."""
    conn = _make_conn()
    entry = _make_entry(
        "2025-01-01",
        96,
        [("141", 96), ("91", 95), ("93", 92), ("97", 90), ("142α", "ΝΑΙ")],
    )
    _seed_person(conn, "p1", entry, "doc1")

    result = top_bottom_sections(conn, IsolationScope(person_id="p1", period=entry.period), n=3)

    overall = result.data["overall"]
    assert overall is not None
    assert overall["field_code"] == OVERALL_FIELD_CODE
    assert overall["value"] == 96
    # ίδιο shape με τα στοιχεία των top/bottom
    assert set(overall) == set(result.data["top"][0])

    ranked_codes = [fs["field_code"] for fs in result.data["top"] + result.data["bottom"]]
    assert OVERALL_FIELD_CODE not in ranked_codes
    assert [fs["field_code"] for fs in result.data["top"]] == ["91", "93", "97"]
    assert [fs["field_code"] for fs in result.data["bottom"]] == ["97", "93", "91"]


def test_top_bottom_sections_overall_is_none_when_field_absent():
    """NEGATIVE: χωρίς 141 το `overall` είναι None -- «δεν υπάρχει στην πηγή»,
    όχι κενό dict -- και η κατάταξη δουλεύει κανονικά με τα υπόλοιπα."""
    conn = _make_conn()
    entry = _make_entry(
        "2025-01-01",
        90,
        [("91", 95), ("93", 92), ("97", 90), ("142α", "ΝΑΙ")],
    )
    _seed_person(conn, "p1", entry, "doc1")

    result = top_bottom_sections(conn, IsolationScope(person_id="p1", period=entry.period), n=2)

    assert result.data["overall"] is None
    assert [fs["field_code"] for fs in result.data["top"]] == ["91", "93"]
    assert [fs["field_code"] for fs in result.data["bottom"]] == ["97", "93"]


def test_top_bottom_sections_low_overall_does_not_fall_into_bottom():
    """REGRESSION -- αυτό ακριβώς ήταν το bug: το 141 είναι ολιστική κρίση, όχι
    πεδίο επίδοσης, αλλά με χαμηλή τιμή κατατασσόταν σαν αδύναμο πεδίο. Εδώ το
    141 έχει τη ΧΑΜΗΛΟΤΕΡΗ τιμή όλων -- πρέπει να μείνει εκτός bottom."""
    conn = _make_conn()
    entry = _make_entry(
        "2025-01-01",
        70,
        [("141", 70), ("91", 95), ("93", 92), ("97", 90), ("96", 88)],
    )
    _seed_person(conn, "p1", entry, "doc1")

    result = top_bottom_sections(conn, IsolationScope(person_id="p1", period=entry.period), n=3)

    bottom_codes = [fs["field_code"] for fs in result.data["bottom"]]
    assert OVERALL_FIELD_CODE not in bottom_codes
    assert bottom_codes == ["96", "97", "93"]
    # δεν κρύβεται -- απλώς δεν είναι συγκρίσιμο
    assert result.data["overall"]["value"] == 70


def test_get_promotions_table_judged_for_chain():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
        repository.replace_promotions(conn, "p1", _PROMOTION_ROWS)
        repository.upsert_document(conn, "doc-career", "p1", CAREER_PERIOD, "/docs/doc-career.pdf", 8)
        conn.commit()

        scope = IsolationScope(person_id="p1", period=CAREER_PERIOD)
        result = get_promotions_table(conn, scope)
        conn.close()

        rows = {r["row_index"]: r for r in result.data["rows"]}
        assert rows[0]["rank"] == "ΥΠΟΠΛΟΙΑΡΧΟΣ"
        assert rows[0]["judged_for"] is None
        assert rows[1]["judged_for"] == "ΥΠΟΠΛΟΙΑΡΧΟΣ"
        assert rows[2]["judged_for"] == "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ"
        assert result.retrieved_doc_ids == ["doc-career"]
        assert [c.model_dump() for c in result.citations] == [
            {"doc_id": "doc-career", "page": None, "section": "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ"}
        ]
    finally:
        remove_db(db_path)


def test_get_promotions_table_empty_result_is_not_an_exception():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        result = get_promotions_table(conn, IsolationScope(person_id="missing", period=CAREER_PERIOD))
        conn.close()

        assert result.data["rows"] == []
        assert result.citations == []
        assert result.retrieved_doc_ids == []
    finally:
        remove_db(db_path)


def test_get_promotions_table_isolation_scope_no_cross_person_leak():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
        repository.replace_promotions(conn, "p1", _PROMOTION_ROWS)
        repository.upsert_document(conn, "doc-p1", "p1", CAREER_PERIOD, "/docs/doc-p1.pdf", 8)

        repository.upsert_person(conn, "p2", "Ιωάννου Μαρία")
        repository.replace_promotions(conn, "p2", _PROMOTION_ROWS[:1])
        repository.upsert_document(conn, "doc-p2", "p2", CAREER_PERIOD, "/docs/doc-p2.pdf", 8)
        conn.commit()

        result = get_promotions_table(conn, IsolationScope(person_id="p1", period=CAREER_PERIOD))
        conn.close()

        assert len(result.data["rows"]) == 3
        assert result.retrieved_doc_ids == ["doc-p1"]
        assert "doc-p2" not in result.retrieved_doc_ids
    finally:
        remove_db(db_path)


def test_get_service_time_table_rows_and_citations():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
        repository.replace_service_time(conn, "p1", _SERVICE_TIME_ROWS)
        repository.upsert_document(conn, "doc-career", "p1", CAREER_PERIOD, "/docs/doc-career.pdf", 8)
        conn.commit()

        result = get_service_time_table(conn, IsolationScope(person_id="p1", period=CAREER_PERIOD))
        conn.close()

        assert len(result.data["rows"]) == 4
        assert result.data["rows"][0] == {
            "row_index": 0,
            "subsection": "α",
            "label": "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ",
            "years": 23,
            "months": 0,
            "days": 10,
        }
        assert [c.model_dump() for c in result.citations] == [
            {"doc_id": "doc-career", "page": None, "section": "ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ"}
        ]
        assert result.retrieved_doc_ids == ["doc-career"]
    finally:
        remove_db(db_path)


def test_get_service_time_table_empty_result_is_not_an_exception():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        result = get_service_time_table(conn, IsolationScope(person_id="missing", period=CAREER_PERIOD))
        conn.close()

        assert result.data["rows"] == []
        assert result.citations == []
        assert result.retrieved_doc_ids == []
    finally:
        remove_db(db_path)


# --- citations: doc_id/page/section μόνο από τη DB ----------------------------


def _seed_entry_with_page(
    conn, person_id: str, start: str, doc_id: str, page: int
) -> EvaluationEntry:
    entry = _make_entry(start, 90, [("141", 90), ("91", 80), ("93", 70)])
    entry.source_page = page
    _seed_person(conn, person_id, entry, doc_id)
    return entry


def test_citations_page_comes_from_source_page_per_operation():
    """POSITIVE: γνωστές τιμές στη DB (διαφορετική σελίδα ανά περίοδο) ->
    ακριβώς αυτές στα citations κάθε period-scoped operation."""
    conn = _make_conn()
    a = _seed_entry_with_page(conn, "p1", "2012-01-01", "doc-a", 7)
    b = _seed_entry_with_page(conn, "p1", "2013-01-01", "doc-b", 5)

    scores = get_scores(conn, IsolationScope(person_id="p1", period=a.period))
    assert [(c.doc_id, c.page) for c in scores.citations] == [("doc-a", 7)]

    top_bottom = top_bottom_sections(conn, IsolationScope(person_id="p1", period=b.period))
    assert [(c.doc_id, c.page) for c in top_bottom.citations] == [("doc-b", 5)]

    compared = compare_periods(conn, "p1", b.period, a.period)
    assert [(c.doc_id, c.page) for c in compared.citations] == [("doc-b", 5), ("doc-a", 7)]


def test_null_source_page_stays_null_in_citation():
    """NEGATIVE: source_page NULL στη DB -> page None, όχι 0 ούτε εικασία."""
    conn = _make_conn()
    entry = _seed_entry_with_page(conn, "p1", "2012-01-01", "doc-a", 7)
    conn.execute("UPDATE evaluations SET source_page = NULL WHERE person_id = 'p1'")
    conn.commit()

    result = get_scores(conn, IsolationScope(person_id="p1", period=entry.period))

    assert [(c.doc_id, c.page) for c in result.citations] == [("doc-a", None)]


def _insert_duplicate_document(conn, person_id: str, period: str) -> None:
    # Δεύτερο έγγραφο για ίδιο (person_id, period) — το PK είναι (doc_id, period).
    conn.execute(
        "INSERT INTO documents (doc_id, person_id, period, path, page_count) "
        "VALUES ('duplicate-doc', ?, ?, '/docs/dup.pdf', 1)",
        (person_id, period),
    )
    conn.commit()


def _assert_value_error(fn, *needles: str) -> None:
    try:
        fn()
    except ValueError as exc:
        for needle in needles:
            assert needle in str(exc), str(exc)
    else:
        raise AssertionError("αναμενόταν ValueError, όχι σιωπηλό LIMIT 1")


def test_multiple_documents_for_same_period_is_error_not_limit_1():
    conn = _make_conn()
    entry = _seed_entry_with_page(conn, "p1", "2012-01-01", "doc-a", 7)
    other = _seed_entry_with_page(conn, "p1", "2013-01-01", "doc-b", 5)
    _insert_duplicate_document(conn, "p1", entry.period)
    repository.replace_promotions(conn, "p1", _PROMOTION_ROWS)
    repository.replace_service_time(conn, "p1", _SERVICE_TIME_ROWS)
    repository.upsert_document(conn, "doc-a", "p1", CAREER_PERIOD, "/docs/doc-a.pdf", 8)
    _insert_duplicate_document(conn, "p1", CAREER_PERIOD)

    scope = IsolationScope(person_id="p1", period=entry.period)
    career = IsolationScope(person_id="p1", period=CAREER_PERIOD)
    _assert_value_error(lambda: get_scores(conn, scope), entry.period, "doc-a", "duplicate-doc")
    _assert_value_error(lambda: top_bottom_sections(conn, scope), entry.period)
    _assert_value_error(
        lambda: compare_periods(conn, "p1", other.period, entry.period), entry.period
    )
    _assert_value_error(lambda: get_promotions_table(conn, career), CAREER_PERIOD)
    _assert_value_error(lambda: get_service_time_table(conn, career), CAREER_PERIOD)

    # Το διπλό έγγραφο μιας ΑΛΛΗΣ περιόδου δεν μπλοκάρει την ερώτηση αυτής.
    unaffected = get_scores(conn, IsolationScope(person_id="p1", period=other.period))
    assert [(c.doc_id, c.page) for c in unaffected.citations] == [("doc-b", 5)]


def test_data_without_document_is_error_not_uncited():
    """Δεδομένα χωρίς έγγραφο στο scope δεν έχουν προέλευση: σφάλμα, ποτέ
    απάντηση χωρίς citation."""
    conn = _make_conn()
    repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")
    repository.replace_promotions(conn, "p1", _PROMOTION_ROWS)
    conn.commit()

    _assert_value_error(
        lambda: get_promotions_table(conn, IsolationScope(person_id="p1", period=CAREER_PERIOD)),
        "Κανένα έγγραφο",
    )


def test_citations_only_contain_requested_person_doc_ids():
    conn = _make_conn()
    entry = _seed_entry_with_page(conn, "p1", "2012-01-01", "doc-p1", 7)
    _seed_entry_with_page(conn, "p2", "2012-01-01", "doc-p2", 3)
    for person_id, doc_id in (("p1", "doc-p1"), ("p2", "doc-p2")):
        repository.replace_promotions(conn, person_id, _PROMOTION_ROWS)
        repository.replace_service_time(conn, person_id, _SERVICE_TIME_ROWS)
        repository.upsert_document(conn, doc_id, person_id, CAREER_PERIOD, f"/docs/{doc_id}.pdf", 8)
    conn.commit()

    scope = IsolationScope(person_id="p1", period=entry.period)
    career = IsolationScope(person_id="p1", period=CAREER_PERIOD)
    results = [
        get_scores(conn, scope),
        top_bottom_sections(conn, scope),
        compare_periods(conn, "p1", entry.period, entry.period),
        get_promotions_table(conn, career),
        get_service_time_table(conn, career),
    ]
    for result in results:
        assert result.citations
        assert {c.doc_id for c in result.citations} == {"doc-p1"}


def run_all():
    tests = [
        test_get_scores_returns_entry_field_scores_citations_and_doc_ids,
        test_get_scores_empty_result_is_not_an_exception,
        test_compare_periods,
        test_top_bottom_sections_ranks_numeric_field_scores,
        test_top_bottom_sections_overall_field_is_returned_separately,
        test_top_bottom_sections_overall_is_none_when_field_absent,
        test_top_bottom_sections_low_overall_does_not_fall_into_bottom,
        test_get_promotions_table_judged_for_chain,
        test_get_promotions_table_empty_result_is_not_an_exception,
        test_get_promotions_table_isolation_scope_no_cross_person_leak,
        test_get_service_time_table_rows_and_citations,
        test_get_service_time_table_empty_result_is_not_an_exception,
        test_citations_page_comes_from_source_page_per_operation,
        test_null_source_page_stays_null_in_citation,
        test_multiple_documents_for_same_period_is_error_not_limit_1,
        test_data_without_document_is_error_not_uncited,
        test_citations_only_contain_requested_person_doc_ids,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
