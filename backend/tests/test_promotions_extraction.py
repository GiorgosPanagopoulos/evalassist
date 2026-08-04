"""Mini test/sample flow για το backend/app/ingestion/promotion_table.py
(parse_promotion_rows - structured extraction) και το
backend/app/db/repository.py (replace_promotions).

Fixture: το ίδιο πραγματικό κείμενο chunk της Ενότητας 1 (section="ΚΡΙΣΕΙΣ
ΠΡΟΑΓΩΓΩΝ", page=1) με το tests/test_promotion_table.py. Επαληθεύτηκε
εμπειρικά ότι ταιριάζει τιμή προς τιμή με το πραγματικό chunk της ChromaDB
(collection evaluation_chunks, doc_id 29b215931c674b6e).

Εκτελείται standalone: `python tests/test_promotions_extraction.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.promotion_table as promotion_table  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.ingestion.promotion_table import (  # noqa: E402
    annotate_promotion_table,
    parse_promotion_rows,
)

# Αυτούσιο repr από private/debug_krisis_chunktext.txt - chunk 0, section
# "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ", page 1. Ίδιο fixture με tests/test_promotion_table.py.
FIXTURE = (
    "1. - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ (Ημερομηνία Τελευταίας Προαγωγής: 05/07/2019)\n\n"
    "ΒΑΘΜΟΣ\nΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ\nΑΠΟΦΑΣΗ\nΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ\n\n"
    "ΥΠΟΠΛΟΙΑΡΧΟΣ\n08/04/2019\nΠΕ ΠΑΜΨΗΦΕΙ (04/08/04/2019) ΓΙΑ ΤΟ ΕΤΟΣ 2019-\n2020\n05/07/2013\n\n"
    "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ\n02/04/2013\nΠΕ ΠΑΜΨΗΦΕΙ (02//02/04/2013) ΓΙΑ ΤΟ ΕΤΟΣ 2013-\n2014\n05/07/2008\n\n"
    "ΣΗΜΑΙΟΦΟΡΟΣ\n27/03/2008\n4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09\n05/07/2005"
)


def test_parse_valid_table_produces_correct_dicts_in_order():
    rows = parse_promotion_rows(FIXTURE)
    assert len(rows) == 3

    assert rows[0] == {
        "rank": "ΥΠΟΠΛΟΙΑΡΧΟΣ",
        "decision_date": "08/04/2019",
        "decision": "ΠΕ ΠΑΜΨΗΦΕΙ (04/08/04/2019) ΓΙΑ ΤΟ ΕΤΟΣ 2019-2020",
        "promotion_date": "05/07/2013",
    }
    assert rows[1] == {
        "rank": "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ",
        "decision_date": "02/04/2013",
        "decision": "ΠΕ ΠΑΜΨΗΦΕΙ (02//02/04/2013) ΓΙΑ ΤΟ ΕΤΟΣ 2013-2014",
        "promotion_date": "05/07/2008",
    }
    assert rows[2] == {
        "rank": "ΣΗΜΑΙΟΦΟΡΟΣ",
        "decision_date": "27/03/2008",
        "decision": "4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09",
        "promotion_date": "05/07/2005",
    }
    for row in rows:
        for value in row.values():
            assert isinstance(value, str)


def test_text_without_header_returns_empty_list():
    text = "Κάποιο άσχετο κείμενο χωρίς κανένα από τα γνωστά labels.\nΤέλος."
    assert parse_promotion_rows(text) == []


def test_already_annotated_text_does_not_produce_duplicates():
    # Το ίδιο κείμενο, ήδη περασμένο από annotate_promotion_table: κάθε
    # σειρά είναι πλέον μία γραμμή "ΒΑΘΜΟΣ: X | ..." αντί για ομάδα 4+
    # γραμμών - parse_promotion_rows δεν πρέπει να την ξαναδιαβάσει ως νέα
    # σειρά (idempotency prefix + <4 γραμμές ανά ομάδα).
    annotated = annotate_promotion_table(FIXTURE)
    assert parse_promotion_rows(annotated) == []


def test_failsafe_exception_returns_empty_list_not_raise():
    original = promotion_table._merge_decision_lines

    def _boom(_decision_lines):
        raise RuntimeError("forced failure for test")

    promotion_table._merge_decision_lines = _boom
    try:
        result = parse_promotion_rows(FIXTURE)
    finally:
        promotion_table._merge_decision_lines = original
    assert result == []


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    return db_path


def test_replace_promotions_twice_same_row_count():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")

        rows = parse_promotion_rows(FIXTURE)
        repository.replace_promotions(conn, "p1", rows)
        conn.commit()
        count_first = conn.execute(
            "SELECT COUNT(*) AS c FROM promotions WHERE person_id = ?", ("p1",)
        ).fetchone()["c"]

        repository.replace_promotions(conn, "p1", rows)
        conn.commit()
        count_second = conn.execute(
            "SELECT COUNT(*) AS c FROM promotions WHERE person_id = ?", ("p1",)
        ).fetchone()["c"]

        conn.close()
        assert count_first == 3
        assert count_second == 3
    finally:
        db_path.unlink(missing_ok=True)


def test_row_index_continuous_and_ordered():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")

        rows = parse_promotion_rows(FIXTURE)
        repository.replace_promotions(conn, "p1", rows)
        conn.commit()

        db_rows = conn.execute(
            "SELECT row_index, rank FROM promotions WHERE person_id = ? ORDER BY row_index",
            ("p1",),
        ).fetchall()
        conn.close()

        assert [r["row_index"] for r in db_rows] == [0, 1, 2]
        assert [r["rank"] for r in db_rows] == [
            "ΥΠΟΠΛΟΙΑΡΧΟΣ",
            "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ",
            "ΣΗΜΑΙΟΦΟΡΟΣ",
        ]
    finally:
        db_path.unlink(missing_ok=True)


def test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes():
    # Κωδικοσημείο-έλεγχος ομογράφων στα ίδια τα test data: το πρώτο
    # γράμμα κάθε βαθμού πρέπει να είναι πραγματικό ελληνικό κεφαλαίο, όχι
    # οπτικά όμοιο λατινικό (π.χ. Υ=U+03A5, όχι Y=U+0059).
    rows = parse_promotion_rows(FIXTURE)
    assert ord(rows[0]["rank"][0]) == 0x3A5  # ΕΛΛΗΝΙΚΟ κεφαλαίο Υ, όχι λατινικό Y (0x59)
    assert ord(rows[1]["rank"][0]) == 0x391  # ΕΛΛΗΝΙΚΟ κεφαλαίο Α, όχι λατινικό A (0x41)
    assert ord(rows[2]["rank"][0]) == 0x3A3  # ΕΛΛΗΝΙΚΟ κεφαλαίο Σ, όχι λατινικό S/Sigma-lookalike


def run_all():
    tests = [
        test_parse_valid_table_produces_correct_dicts_in_order,
        test_text_without_header_returns_empty_list,
        test_already_annotated_text_does_not_produce_duplicates,
        test_failsafe_exception_returns_empty_list_not_raise,
        test_replace_promotions_twice_same_row_count,
        test_row_index_continuous_and_ordered,
        test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
