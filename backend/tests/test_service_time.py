"""Mini test/sample flow για το backend/app/ingestion/service_time.py
(parse_service_time_rows - structured extraction Ενότητας 2) και το
backend/app/db/repository.py (replace_service_time).

Fixture: το πραγματικό κείμενο chunk της Ενότητας 2 (section="ΣΥΝΟΛΙΚΟΣ
ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ", page=1), αυτούσιο repr από τη ChromaDB όπως δόθηκε στο
prompt - όχι ξαναγραμμένο από μνήμη.

Εκτελείται standalone: `python tests/test_service_time.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.service_time as service_time  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.ingestion.service_time import parse_service_time_rows  # noqa: E402

# Αυτούσιο repr από το prompt - chunk section "ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ",
# page 1.
FIXTURE = (
    "2. - ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ\n\n"
    "α.  ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ (Έως 27/09/2024)\n23\nΈτη\n0\nΜήνες\n10\nΗμέρες\n\n"
    "β.  Ανά Σταδιοδρομική Κατηγορία\n\n"
    "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ\n13\nΈτη\n4\nΜήνες\n8\nΗμέρες\n\n"
    "ΠΛΟΙΑ\n12\nΈτη\n11\nΜήνες\n7\nΗμέρες\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ ΟΛΟΚΛΗΡΩΣΗΣ ΠΡΟΣΟΝΤΩΝ\n0\nΈτη\n0\nΜήνες\n0\nΗμέρες\n\n"
    "Αος ΜΗΧΑΝΙΚΟΣ\n7\nΈτη\n1\nΜήνες\n8\nΗμέρες\n\n"
    "γ.  Ανά Κατηγορία Καθήκοντος\n\n"
    "Εκτυπώθηκε από το χρήστη: B3VE\\e.siatis\nΣελίδα 1 από 8\n(ΑΓΜ: Μ-01253)"
)

# Το ΠΡΑΓΜΑΤΙΚΟ δεύτερο chunk της ίδιας ενότητας (σελ.2, υποενότητα γ),
# αυτούσιο repr από τη ChromaDB. Περιέχει ΕΓΚΥΡΕΣ εξάδες τιμών
# αριθμός/Έτη/αριθμός/Μήνες/αριθμός/Ημέρες - ο parser τις αγνοεί επειδή
# λείπει ο header 'α.', όχι επειδή οι τιμές είναι αναγνώσιμες. Οι σειρές
# αυτές έχουν επιπλέον rank + unit πριν τις τιμές (εκτός scope, ξεχωριστό PR).
PAGE_2_CHUNK = (
    "Α ΜΗΧΑΝΙΚΟΣ\nΑΝΘΧΟΣ\nΥΒ ΑΜΦΙΤΡΙΤΗ\n2\nΈτη\n1\nΜήνες\n24\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΠΧΟΣ\nΥΒ ΠΑΠΑΝΙΚΟΛΗΣ\n2\nΈτη\n12\nΜήνες\n3\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΒ ΠΡΩΤΕΥΣ\n0\nΈτη\n9\nΜήνες\n21\nΗμέρες"
)


def test_alpha_single_entry():
    rows = parse_service_time_rows(FIXTURE)
    alpha_rows = [r for r in rows if r["subsection"] == "α"]
    assert len(alpha_rows) == 1
    assert alpha_rows[0] == {
        "subsection": "α",
        "label": "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ",
        "years": 23,
        "months": 0,
        "days": 10,
    }


def test_beta_three_entries_without_qualification_date():
    rows = parse_service_time_rows(FIXTURE)
    beta_rows = [r for r in rows if r["subsection"] == "β"]
    assert len(beta_rows) == 3
    assert beta_rows[0] == {
        "subsection": "β",
        "label": "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ",
        "years": 13,
        "months": 4,
        "days": 8,
    }
    assert beta_rows[1] == {
        "subsection": "β",
        "label": "ΠΛΟΙΑ",
        "years": 12,
        "months": 11,
        "days": 7,
    }
    assert beta_rows[2] == {
        "subsection": "β",
        "label": "Αος ΜΗΧΑΝΙΚΟΣ",
        "years": 7,
        "months": 1,
        "days": 8,
    }


def test_qualification_date_entry_never_appears():
    rows = parse_service_time_rows(FIXTURE)
    labels = [r["label"] for r in rows]
    assert "ΗΜΕΡΟΜΗΝΙΑ ΟΛΟΚΛΗΡΩΣΗΣ ΠΡΟΣΟΝΤΩΝ" not in labels
    assert len(rows) == 4  # 1 (α) + 3 (β), όχι 5


def test_text_without_header_returns_empty_list():
    text = "Κάποιο άσχετο κείμενο χωρίς κανένα από τα γνωστά labels.\nΤέλος."
    assert parse_service_time_rows(text) == []


def test_page_2_chunk_returns_empty_list():
    assert parse_service_time_rows(PAGE_2_CHUNK) == []


def test_failsafe_exception_returns_empty_list_not_raise():
    original = service_time._parse_values

    def _boom(_value_lines):
        raise RuntimeError("forced failure for test")

    service_time._parse_values = _boom
    try:
        result = parse_service_time_rows(FIXTURE)
    finally:
        service_time._parse_values = original
    assert result == []


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    return db_path


def test_replace_service_time_twice_same_row_count():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")

        rows = parse_service_time_rows(FIXTURE)
        repository.replace_service_time(conn, "p1", rows)
        conn.commit()
        count_first = conn.execute(
            "SELECT COUNT(*) AS c FROM service_time WHERE person_id = ?", ("p1",)
        ).fetchone()["c"]

        repository.replace_service_time(conn, "p1", rows)
        conn.commit()
        count_second = conn.execute(
            "SELECT COUNT(*) AS c FROM service_time WHERE person_id = ?", ("p1",)
        ).fetchone()["c"]

        conn.close()
        assert count_first == 4
        assert count_second == 4
    finally:
        db_path.unlink(missing_ok=True)


def test_row_index_continuous_and_ordered():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")

        rows = parse_service_time_rows(FIXTURE)
        repository.replace_service_time(conn, "p1", rows)
        conn.commit()

        db_rows = conn.execute(
            "SELECT row_index, label FROM service_time WHERE person_id = ? ORDER BY row_index",
            ("p1",),
        ).fetchall()
        conn.close()

        assert [r["row_index"] for r in db_rows] == [0, 1, 2, 3]
        assert [r["label"] for r in db_rows] == [
            "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ",
            "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ",
            "ΠΛΟΙΑ",
            "Αος ΜΗΧΑΝΙΚΟΣ",
        ]
    finally:
        db_path.unlink(missing_ok=True)


def test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes():
    # Κωδικοσημείο-έλεγχος ομογράφων στα ίδια τα test data: το πρώτο γράμμα
    # κάθε label πρέπει να είναι πραγματικό ελληνικό κεφαλαίο, όχι οπτικά
    # όμοιο λατινικό.
    rows = parse_service_time_rows(FIXTURE)
    beta_rows = [r for r in rows if r["subsection"] == "β"]
    assert ord(beta_rows[0]["label"][0]) == 0x3A3  # ΕΛΛΗΝΙΚΟ κεφαλαίο Σ, όχι λατινικό S
    assert ord(beta_rows[1]["label"][0]) == 0x3A0  # ΕΛΛΗΝΙΚΟ κεφαλαίο Π, όχι λατινικό P


def test_get_service_time_reader_orders_by_row_index():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repository.upsert_person(conn, "p1", "Παπαδόπουλος Γιώργος")

        rows = parse_service_time_rows(FIXTURE)
        repository.replace_service_time(conn, "p1", rows)
        conn.commit()

        result = repository.get_service_time(conn, "p1")
        conn.close()

        assert [r["row_index"] for r in result] == [0, 1, 2, 3]
        assert [r["label"] for r in result] == [
            "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ",
            "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ",
            "ΠΛΟΙΑ",
            "Αος ΜΗΧΑΝΙΚΟΣ",
        ]
        assert result[0]["years"] == 23
        assert result[0]["months"] == 0
        assert result[0]["days"] == 10
    finally:
        db_path.unlink(missing_ok=True)


def test_get_service_time_reader_empty_for_unknown_person():
    db_path = _make_temp_db()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        result = repository.get_service_time(conn, "missing")
        conn.close()
        assert result == []
    finally:
        db_path.unlink(missing_ok=True)


def run_all():
    tests = [
        test_alpha_single_entry,
        test_beta_three_entries_without_qualification_date,
        test_qualification_date_entry_never_appears,
        test_text_without_header_returns_empty_list,
        test_page_2_chunk_returns_empty_list,
        test_failsafe_exception_returns_empty_list_not_raise,
        test_replace_service_time_twice_same_row_count,
        test_row_index_continuous_and_ordered,
        test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes,
        test_get_service_time_reader_orders_by_row_index,
        test_get_service_time_reader_empty_for_unknown_person,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
