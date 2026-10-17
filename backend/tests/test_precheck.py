"""Unit tests για το app.retrieval.precheck (ντετερμινιστικοί έλεγχοι πριν το
retrieval), πάνω σε temp SQLite με συνθετικά δεδομένα.

Συνθετικό fixture (ΟΧΙ οι περίοδοι του πραγματικού φακέλου):
  - X-00001: Ε.Α. ανά έτος 2006-2023, με το 2018 σπασμένο σε τρεις περιόδους
    (η τρίτη περνά στο 2019) + career document. field_scores σε μία περίοδο.
  - X-00002: 2010-2012 μόνο, για τον έλεγχο ότι το εύρος είναι ανά άτομο.

Καλύπτει:
  - επικύρωση period (υπαρκτή, career, ανύπαρκτη, περίοδος άλλου ατόμου).
  - πεδίο εκτός schema (trap 18 αυτούσιο), κανονικοποίηση κωδικών.
  - έτος εκτός εύρους (trap 17 αυτούσιο), έτος σε άλλη περίοδο, career.
  - ΓΝΩΣΤΟΣ ΠΕΡΙΟΡΙΣΜΟΣ κλειδωμένος: πτυχίο με έτος εκτός εύρους -> άρνηση.
  - regression ψευδών αρνήσεων: F01-F18 (test v2 του χρήστη, ήδη εκτελεσμένο
    στις 2026-10-09) και C1-C4, το καθένα με έγκυρη περίοδο για το έτος του.

Εκτελείται standalone: `python tests/test_precheck.py`
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_helpers import remove_db  # noqa: E402

from app.core.exceptions import InvalidPeriodError  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.models.evaluation import CAREER_PERIOD, FIELD_CODE_LABELS  # noqa: E402
from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.precheck import (  # noqa: E402
    RefusalReason,
    check_question,
    validate_period,
)

P1 = "X-00001"
P2 = "X-00002"
P1_2012 = "2012-01-01..2012-12-31"
P1_2013 = "2013-01-01..2013-12-31"
P1_2018_A = "2018-01-01..2018-06-30"
P1_2018_B = "2018-07-01..2018-09-30"
P1_2018_C = "2018-10-01..2019-01-31"
P2_2011 = "2011-02-01..2011-12-31"


def _p1_periods() -> list[tuple[str, str]]:
    periods = []
    for year in range(2006, 2024):
        if year == 2018:
            periods += [("2018-01-01", "2018-06-30"), ("2018-07-01", "2018-09-30"),
                        ("2018-10-01", "2019-01-31")]
        elif year == 2019:
            periods.append(("2019-02-01", "2019-12-31"))
        else:
            periods.append((f"{year}-01-01", f"{year}-12-31"))
    return periods


def _insert_person(conn, person_id: str, periods: list[tuple[str, str]]) -> None:
    conn.execute("INSERT INTO persons (person_id, name) VALUES (?, ?)", (person_id, "Συνθετικό"))
    for start, end in periods:
        period = f"{start}..{end}"
        conn.execute(
            "INSERT INTO evaluations (person_id, period, period_start, period_end, ea_type, "
            "unit, evaluator_name) VALUES (?, ?, ?, ?, 'Ε.Α.', 'ΜΟΝΑΔΑ', 'ΑΞΙΟΛΟΓΗΤΗΣ')",
            (person_id, period, start, end),
        )
        conn.execute(
            "INSERT INTO documents (doc_id, person_id, period, path) VALUES (?, ?, ?, ?)",
            (f"doc-{person_id}", person_id, period, "/synthetic.pdf"),
        )
    conn.execute(
        "INSERT INTO documents (doc_id, person_id, period, path) VALUES (?, ?, ?, ?)",
        (f"doc-{person_id}", person_id, CAREER_PERIOD, "/synthetic.pdf"),
    )


def _make_db() -> tuple[Path, sqlite3.Connection]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _insert_person(conn, P1, _p1_periods())
    _insert_person(conn, P2, [("2010-02-01", "2010-12-31"), ("2011-02-01", "2011-12-31"),
                              ("2012-02-01", "2012-11-30")])
    eval_id = conn.execute(
        "SELECT id FROM evaluations WHERE person_id = ? AND period = ?", (P1, P1_2018_A)
    ).fetchone()["id"]
    for code in ("141", "142α", "51"):
        conn.execute(
            "INSERT INTO field_scores (eval_id, field_code, value) VALUES (?, ?, '100')",
            (eval_id, code),
        )
    conn.commit()
    return db_path, conn


def _with_db(test):
    def wrapper():
        db_path, conn = _make_db()
        try:
            test(conn)
        finally:
            conn.close()
            remove_db(db_path)

    wrapper.__name__ = test.__name__
    return wrapper


def _check(conn, question: str, period: str, person_id: str = P1):
    return check_question(conn, IsolationScope(person_id=person_id, period=period), question)


# --- validate_period -------------------------------------------------------


@_with_db
def test_validate_period_accepts_existing_and_career(conn):
    validate_period(conn, P1, P1_2018_A)
    validate_period(conn, P1, CAREER_PERIOD)


@_with_db
def test_validate_period_rejects_unknown_period(conn):
    try:
        validate_period(conn, P1, "2030-01-01..2030-12-31")
    except InvalidPeriodError as exc:
        assert str(exc) == f"Η περίοδος «2030-01-01..2030-12-31» δεν υπάρχει στον φάκελο {P1}."
    else:
        raise AssertionError("αναμενόταν InvalidPeriodError")


@_with_db
def test_validate_period_rejects_other_persons_period_and_unknown_person(conn):
    # Η περίοδος υπάρχει στη βάση, αλλά για άλλο άτομο: δεν είναι έγκυρη για αυτό.
    validate_period(conn, P2, P2_2011)
    for person_id, period in ((P1, P2_2011), ("ghost", P1_2018_A)):
        try:
            validate_period(conn, person_id, period)
        except InvalidPeriodError:
            continue
        raise AssertionError(f"αναμενόταν InvalidPeriodError για {person_id}/{period}")


# --- κωδικός πεδίου ----------------------------------------------------------


@_with_db
def test_trap18_field_out_of_schema(conn):
    refusal = _check(conn, "Ποια είναι η βαθμολογία του στο πεδίο 200;", P1_2018_A)
    assert refusal is not None
    assert refusal.reason == RefusalReason.FIELD_OUT_OF_SCHEMA
    assert refusal.text.startswith("Το πεδίο 200 δεν υπάρχει στο έντυπο αξιολόγησης.")
    # η λίστα υπαρκτών πεδίων είναι όλο το schema, ταξινομημένο αριθμητικά
    listed = refusal.text.split("Υπάρχοντα πεδία: ")[1].rstrip(".").split(", ")
    assert set(listed) == set(FIELD_CODE_LABELS)
    assert listed[:2] == ["51", "62"] and listed[-3:] == ["141", "142α", "142β"]


@_with_db
def test_field_code_variants_inside_schema_pass(conn):
    for question in (
        "Τι λέει το πεδίο 142β;",
        "Τι λέει το ΠΕΔΙΟ 142Β;",
        "Τι λέει το πεδίο 142a;",  # λατινικό a -> α
        "Ποια είναι η τιμή του πεδίου 141;",
        "Το πεδίο 51 αφορά τι;",  # το "α" του "αφορά" δεν είναι suffix
        "Τι βαθμό πήρε στο 85;",  # χωρίς πρόθεμα: δεν αναγνωρίζεται ως κωδικός
    ):
        assert _check(conn, question, P1_2018_A) is None, question


@_with_db
def test_field_code_variants_outside_schema_refused(conn):
    for question, code in (
        ("Ποια είναι η τιμή του κωδικού πεδίου 143;", "143"),
        ("Τι λέει το πεδίο 142γ;", "142γ"),
        ("Τι λέει το πεδίο 2003;", "2003"),  # τετραψήφιο μετά από πρόθεμα: πεδίο, όχι έτος
    ):
        refusal = _check(conn, question, P1_2018_A)
        assert refusal is not None and refusal.reason == RefusalReason.FIELD_OUT_OF_SCHEMA, question
        assert refusal.text.startswith(f"Το πεδίο {code} δεν υπάρχει"), refusal.text


@_with_db
def test_field_code_in_db_but_not_in_labels_is_schema(conn):
    conn.execute(
        "INSERT INTO field_scores (eval_id, field_code, value) "
        "SELECT id, '99', '90' FROM evaluations WHERE period = ? AND person_id = ?",
        (P1_2012, P1),
    )
    assert _check(conn, "Τι λέει το πεδίο 99;", P1_2012) is None


@_with_db
def test_valid_field_absent_from_selected_period_is_not_refused(conn):
    # Σκόπιμα: τα field_scores λείπουν από τις περισσότερες περιόδους (Β6).
    assert _check(conn, "Τι λέει το πεδίο 85;", P1_2012) is None


# --- έτος ----------------------------------------------------------------------


@_with_db
def test_trap17_year_out_of_range(conn):
    refusal = _check(conn, "Τι έγραφε η έκθεση του 2003;", P1_2018_A)
    assert refusal is not None
    assert refusal.reason == RefusalReason.YEAR_OUT_OF_RANGE
    assert refusal.text == (
        "Δεν υπάρχει περίοδος αξιολόγησης για το 2003. "
        "Ο φάκελος καλύπτει 2006-01-01 έως 2023-12-31. "
        "Αν το ερώτημα αφορά πτυχία ή τοποθετήσεις, διατυπώστε το χωρίς έτος."
    )


@_with_db
def test_known_limitation_degree_year_outside_evaluations_is_refused(conn):
    # ΓΝΩΣΤΟΣ ΠΕΡΙΟΡΙΣΜΟΣ (βλ. docstring του app.retrieval.precheck): τα πτυχία
    # δεν έχουν πίνακα με ημερομηνίες στο SQLite, οπότε ένα έτος εκτός των
    # περιόδων αξιολόγησης απορρίπτεται ακόμη κι αν το ερώτημα είναι νόμιμο.
    # Αποδεκτή ψευδής άρνηση: το κείμενο δείχνει την παράκαμψη. Αν αυτό το
    # test αποτύχει, η συμπεριφορά άλλαξε: απόφαση, όχι σιωπηλή αλλαγή.
    refusal = _check(conn, "Τι πτυχίο απέκτησε το 2003;", P1_2018_A)
    assert refusal is not None
    assert refusal.reason == RefusalReason.YEAR_OUT_OF_RANGE
    assert "διατυπώστε το χωρίς έτος" in refusal.text


@_with_db
def test_year_in_other_period_redirects(conn):
    refusal = _check(conn, "Πότε προήχθη το 2013;", P1_2018_A)
    assert refusal is not None
    assert refusal.reason == RefusalReason.YEAR_OTHER_PERIOD
    assert refusal.text == (
        f"Το 2013 δεν ανήκει στην επιλεγμένη περίοδο {P1_2018_A}. "
        f"Περίοδοι που το περιέχουν: {P1_2013}. "
        "Για σύγκριση περιόδων ή για τον πίνακα προαγωγών χρησιμοποιήστε τη "
        "δομημένη αναζήτηση."
    )


@_with_db
def test_year_in_other_period_lists_all_containing_periods(conn):
    refusal = _check(conn, "Τι χαρακτηρισμό πήρε το 2018;", P1_2012)
    assert refusal is not None and refusal.reason == RefusalReason.YEAR_OTHER_PERIOD
    assert f"Περίοδοι που το περιέχουν: {P1_2018_A}, {P1_2018_B}, {P1_2018_C}." in refusal.text


@_with_db
def test_year_covered_by_selected_period_passes(conn):
    assert _check(conn, "Τι χαρακτηρισμό πήρε το 2018;", P1_2018_B) is None
    # περίοδος που περνά σε επόμενο έτος καλύπτει και τα δύο
    assert _check(conn, "Ποιος τον αξιολόγησε τον Ιανουάριο του 2019;", P1_2018_C) is None
    # ημερομηνίες σε μορφή εντύπου
    assert _check(conn, "Βαθμολογία για 01/07/2018 - 30/09/2018;", P1_2018_B) is None


@_with_db
def test_comparison_across_periods_redirects_in_semantic(conn):
    refusal = _check(conn, "Πώς συγκρίνεται το 2012 με το 2013;", P1_2012)
    assert refusal is not None and refusal.reason == RefusalReason.YEAR_OTHER_PERIOD
    assert refusal.text.startswith("Το 2013 δεν ανήκει")


@_with_db
def test_career_period_checks_only_range(conn):
    assert _check(conn, "Πότε προήχθη το 2013;", CAREER_PERIOD) is None
    refusal = _check(conn, "Τι έγραφε η έκθεση του 2003;", CAREER_PERIOD)
    assert refusal is not None and refusal.reason == RefusalReason.YEAR_OUT_OF_RANGE


@_with_db
def test_year_range_is_per_person(conn):
    # Το 2008 καλύπτεται για το X-00001 αλλά όχι για το X-00002.
    refusal = _check(conn, "Τι έγραφε η έκθεση του 2008;", P2_2011, person_id=P2)
    assert refusal is not None and refusal.reason == RefusalReason.YEAR_OUT_OF_RANGE
    assert "Ο φάκελος καλύπτει 2010-02-01 έως 2012-11-30." in refusal.text


@_with_db
def test_field_check_runs_before_year_check(conn):
    refusal = _check(conn, "Τι λέει το πεδίο 200 για το 2003;", P1_2018_A)
    assert refusal is not None and refusal.reason == RefusalReason.FIELD_OUT_OF_SCHEMA


# --- regression: καμία ψευδής άρνηση σε ερωτήματα γεγονότων ------------------

# Test v2 του χρήστη (F01-F18), εκτελεσμένο 2026-10-09. Κάθε ερώτημα με έγκυρη
# περίοδο που ταιριάζει στο έτος του (όσα δεν έχουν έτος: περίοδος 2018).
_FACT_QUESTIONS = [
    ("F01", "Τι χαρακτηρισμό πήρε στην τελευταία του έκθεση;", P1_2018_A),
    ("F02", "Ποια ήταν η πρόταση του αξιολογούντος για την κρίση του;", P1_2018_A),
    ("F03", "Κρίθηκε ποτέ μη προακτέος;", P1_2018_A),
    ("F04", "Σε ποια κρίση πήρε ΔΑΒ και από πόσα μέλη;", P1_2018_A),
    ("F05", "Τι γνώμη έγραψε ο γνωματεύων στην έκθεση του 2018?", P1_2018_A),
    ("F06", "Ο αξιολογητής τον χαρακτηρίζει κατάλληλο για Κυβερνήτη;", P1_2018_A),
    ("F07", "Αναφέρεται κάπου ότι είναι κατάλληλος για επιτελική θέση;", P1_2018_A),
    ("F08", "Ποια συνολική βαθμολογία πήρε το 2012;", P1_2012),
    ("F09", "Πόσες φορές πήρε χαρακτηρισμό ΕΞΑΙΡΕΤΟΣ;", P1_2018_A),
    ("F10", "Ποιος τον αξιολόγησε όταν ήταν Ανθυποπλοίαρχος;", P1_2018_A),
    ("F11", "Υπάρχει πειθαρχική ποινή στον φάκελο;", P1_2018_A),
    ("F12", "Ποια είναι η χαμηλότερη βαθμολογία που του έδωσε αξιολογητής;", P1_2018_A),
    ("F13", "Τι λέει το πεδίο 142β για το 2018;", P1_2018_A),
    ("F14", "Ποια ήταν η σύσταση του Κυβερνήτη στην έκθεση;", P1_2018_A),
    ("F15", "Πότε έγινε Υποπλοίαρχος;", P1_2018_A),
    ("F16", "Ειχε καθηκοντα Α μηχανικου;", P1_2018_A),
    ("F17", "Πόσες μέρες ήταν χωρίς καθήκοντα το 2018;", P1_2018_A),
    ("F18", "Τι γράφει για τη συνολική του εμφάνιση;", P1_2018_A),
    ("C1", "Ποιος ήταν ο χαρακτηρισμός του για την περίοδο 2018;", P1_2018_A),
    ("C2", "Σε ποια μονάδα υπηρετούσε το 2018;", P1_2018_A),
    ("C3", "Ποια ήταν η χαμηλότερη βαθμολογία του και πότε;", P1_2018_A),
    ("C4", "Ποιος τον αξιολόγησε το 2018;", P1_2018_A),
]


@_with_db
def test_no_false_refusals_on_fact_questions(conn):
    refused = [
        (qid, refusal.reason)
        for qid, question, period in _FACT_QUESTIONS
        if (refusal := _check(conn, question, period)) is not None
    ]
    assert refused == [], refused


def run_all():
    tests = [
        test_validate_period_accepts_existing_and_career,
        test_validate_period_rejects_unknown_period,
        test_validate_period_rejects_other_persons_period_and_unknown_person,
        test_trap18_field_out_of_schema,
        test_field_code_variants_inside_schema_pass,
        test_field_code_variants_outside_schema_refused,
        test_field_code_in_db_but_not_in_labels_is_schema,
        test_valid_field_absent_from_selected_period_is_not_refused,
        test_trap17_year_out_of_range,
        test_known_limitation_degree_year_outside_evaluations_is_refused,
        test_year_in_other_period_redirects,
        test_year_in_other_period_lists_all_containing_periods,
        test_year_covered_by_selected_period_passes,
        test_comparison_across_periods_redirects_in_semantic,
        test_career_period_checks_only_range,
        test_year_range_is_per_person,
        test_field_check_runs_before_year_check,
        test_no_false_refusals_on_fact_questions,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
