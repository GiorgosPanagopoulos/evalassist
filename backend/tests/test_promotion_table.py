"""Mini test/sample flow για το backend/app/ingestion/promotion_table.py
(επισήμανση στηλών πίνακα Ενότητας 1 - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ).

Fixture: το πραγματικό κείμενο chunk της Ενότητας 1 (section="ΚΡΙΣΕΙΣ
ΠΡΟΑΓΩΓΩΝ", page=1, 373 chars), αντιγραμμένο αυτούσιο από το repr στο
private/debug_krisis_chunktext.txt - όχι ξαναγραμμένο από μνήμη.

Εκτελείται standalone: `python tests/test_promotion_table.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.promotion_table as promotion_table  # noqa: E402
from app.ingestion.promotion_table import annotate_promotion_table  # noqa: E402

_HEADER_LINE = "1. - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ (Ημερομηνία Τελευταίας Προαγωγής: 05/07/2019)"

# Αυτούσιο repr από private/debug_krisis_chunktext.txt - chunk 0, section
# "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ", page 1.
FIXTURE = (
    "1. - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ (Ημερομηνία Τελευταίας Προαγωγής: 05/07/2019)\n\n"
    "ΒΑΘΜΟΣ\nΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ\nΑΠΟΦΑΣΗ\nΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ\n\n"
    "ΥΠΟΠΛΟΙΑΡΧΟΣ\n08/04/2019\nΠΕ ΠΑΜΨΗΦΕΙ (04/08/04/2019) ΓΙΑ ΤΟ ΕΤΟΣ 2019-\n2020\n05/07/2013\n\n"
    "ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ\n02/04/2013\nΠΕ ΠΑΜΨΗΦΕΙ (02//02/04/2013) ΓΙΑ ΤΟ ΕΤΟΣ 2013-\n2014\n05/07/2008\n\n"
    "ΣΗΜΑΙΟΦΟΡΟΣ\n27/03/2008\n4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09\n05/07/2005"
)


def test_happy_path_all_three_rows_produced_correctly():
    result = annotate_promotion_table(FIXTURE)
    assert (
        "ΒΑΘΜΟΣ: ΥΠΟΠΛΟΙΑΡΧΟΣ | ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ: 08/04/2019 | "
        "ΑΠΟΦΑΣΗ: ΠΕ ΠΑΜΨΗΦΕΙ (04/08/04/2019) ΓΙΑ ΤΟ ΕΤΟΣ 2019-2020 | "
        "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 05/07/2013"
    ) in result
    assert (
        "ΒΑΘΜΟΣ: ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ | ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ: 02/04/2013 | "
        "ΑΠΟΦΑΣΗ: ΠΕ ΠΑΜΨΗΦΕΙ (02//02/04/2013) ΓΙΑ ΤΟ ΕΤΟΣ 2013-2014 | "
        "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 05/07/2008"
    ) in result
    assert (
        "ΒΑΘΜΟΣ: ΣΗΜΑΙΟΦΟΡΟΣ | ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ: 27/03/2008 | "
        "ΑΠΟΦΑΣΗ: 4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09 | "
        "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 05/07/2005"
    ) in result


def test_wrapped_year_lands_in_apofasi_not_proagogi():
    result = annotate_promotion_table(FIXTURE)
    row = next(line for line in result.split("\n") if line.startswith("ΒΑΘΜΟΣ: ΥΠΟΠΛΟΙΑΡΧΟΣ"))
    assert "ΑΠΟΦΑΣΗ: ΠΕ ΠΑΜΨΗΦΕΙ (04/08/04/2019) ΓΙΑ ΤΟ ΕΤΟΣ 2019-2020" in row
    assert "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 2020" not in row
    assert "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 05/07/2013" in row

    row2 = next(
        line for line in result.split("\n") if line.startswith("ΒΑΘΜΟΣ: ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ")
    )
    assert "ΑΠΟΦΑΣΗ: ΠΕ ΠΑΜΨΗΦΕΙ (02//02/04/2013) ΓΙΑ ΤΟ ΕΤΟΣ 2013-2014" in row2
    assert "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 2014" not in row2


def test_four_line_group_without_wrap():
    result = annotate_promotion_table(FIXTURE)
    assert (
        "ΒΑΘΜΟΣ: ΣΗΜΑΙΟΦΟΡΟΣ | ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ: 27/03/2008 | "
        "ΑΠΟΦΑΣΗ: 4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09 | "
        "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: 05/07/2005"
    ) in result


def test_text_without_headers_is_byte_identical():
    text = "Κάποιο άσχετο κείμενο χωρίς κανένα από τα γνωστά labels.\nΤέλος."
    assert annotate_promotion_table(text) == text


def test_group_of_three_lines_stays_unchanged():
    # Αφαιρεί τη γραμμή ΑΠΟΦΑΣΗ από την ομάδα ΣΗΜΑΙΟΦΟΡΟΣ -> 3 μη κενές
    # γραμμές, άγνωστη δομή, δεν μαντεύουμε.
    text = FIXTURE.replace(
        "ΣΗΜΑΙΟΦΟΡΟΣ\n27/03/2008\n4 Α - 2 ΔΑΒ(18/27-3-08)ΓΙΑ ΤΟ ΈΤΟΣ 2008-09\n05/07/2005",
        "ΣΗΜΑΙΟΦΟΡΟΣ\n27/03/2008\n05/07/2005",
    )
    result = annotate_promotion_table(text)
    assert "ΣΗΜΑΙΟΦΟΡΟΣ\n27/03/2008\n05/07/2005" in result
    assert "ΒΑΘΜΟΣ: ΣΗΜΑΙΟΦΟΡΟΣ" not in result
    # οι άλλες δύο ομάδες (4+ γραμμές) παραμένουν κανονικά επεξεργασμένες
    assert "ΒΑΘΜΟΣ: ΥΠΟΠΛΟΙΑΡΧΟΣ" in result
    assert "ΒΑΘΜΟΣ: ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ" in result


def test_idempotency_second_pass_does_not_change_result():
    once = annotate_promotion_table(FIXTURE)
    twice = annotate_promotion_table(once)
    assert once == twice


def test_header_line_remains_untouched():
    result = annotate_promotion_table(FIXTURE)
    assert _HEADER_LINE in result
    assert result.startswith(_HEADER_LINE)


def test_exception_path_returns_input_unchanged():
    original = promotion_table._merge_decision_lines

    def _boom(_decision_lines):
        raise RuntimeError("forced failure for test")

    promotion_table._merge_decision_lines = _boom
    try:
        result = annotate_promotion_table(FIXTURE)
    finally:
        promotion_table._merge_decision_lines = original
    assert result == FIXTURE


def test_header_labels_use_real_greek_codepoints_not_latin_lookalikes():
    from app.ingestion.promotion_table import _HEADER_LABELS

    assert _HEADER_LABELS[0] == "ΒΑΘΜΟΣ"
    assert ord(_HEADER_LABELS[0][0]) == 0x392  # ΕΛΛΗΝΙΚΟ κεφαλαίο Β, όχι λατινικό B (0x42)
    assert _HEADER_LABELS[1] == "ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ"
    assert ord(_HEADER_LABELS[1][0]) == 0x397  # ΕΛΛΗΝΙΚΟ κεφαλαίο Η, όχι λατινικό H (0x48)
    assert _HEADER_LABELS[2] == "ΑΠΟΦΑΣΗ"
    assert ord(_HEADER_LABELS[2][0]) == 0x391  # ΕΛΛΗΝΙΚΟ κεφαλαίο Α, όχι λατινικό A (0x41)
    assert _HEADER_LABELS[3] == "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ"


def run_all():
    tests = [
        test_happy_path_all_three_rows_produced_correctly,
        test_wrapped_year_lands_in_apofasi_not_proagogi,
        test_four_line_group_without_wrap,
        test_text_without_headers_is_byte_identical,
        test_group_of_three_lines_stays_unchanged,
        test_idempotency_second_pass_does_not_change_result,
        test_header_line_remains_untouched,
        test_exception_path_returns_input_unchanged,
        test_header_labels_use_real_greek_codepoints_not_latin_lookalikes,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
