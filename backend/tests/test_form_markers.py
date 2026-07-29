"""Mini test/sample flow για το backend/app/ingestion/form_markers.py
(μαρκάρισμα κενών υποπεδίων Ενότητας 5 - ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ).

Fixtures βασισμένα στο πραγματικό κείμενο chunk της Ενότητας 5 (επιβεβαιωμένο
από ChromaDB), με fake Α.Γ.Μ. (Μ-00000, Μ = ΕΛΛΗΝΙΚΟ κεφαλαίο U+039C, ΟΧΙ
λατινικό M) αντί για πραγματικό.

Εκτελείται standalone: `python tests/test_form_markers.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.form_markers import annotate_empty_section5_subfields  # noqa: E402

MARKER = "ΟΥΔΕΝ ΚΑΤΑΧΩΡΗΜΕΝΟ"

_HEALTH_TAIL = "δ.   Κατάσταση Υγείας\n\nΗΜΕΡΟΜΗΝΙΑ:\n03/04/2019\nΓΝΩΜΑΤΕΥΣΗ:\nΙκανός\nΗΜΕΡΕΣ ΑΔΕΙΑΣ:\n5\n"

_ALL_EMPTY = (
    "5. - ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ ή ΜΗ ΓΙΑ ΠΡΟΑΓΩΓΗ ΚΑΤ' ΕΚΛΟΓΗΝ\n\n"
    "α.  Παραπομπές σε συμβούλια - Αποφάσεις συμβουλίων\n\n"
    "β.  Δίκες - Αποφάσεις Δικαστηρίων (Πολιτικών - Στρατοδικείων)\n\n"
    "γ.   Ποινές\n\n"
    "(1)   Συνήθεις - Πειθαρχικές\n\n"
    "(2)   Για Σοβαρά Παραπτώματα\n\n"
    "(3)   Πρόσκαιρη Παύση\n\n" + _HEALTH_TAIL
)


def test_all_empty_marks_leaves_and_container():
    result = annotate_empty_section5_subfields(_ALL_EMPTY)
    assert result.count(MARKER) == 6  # α, β, γ, (1), (2), (3)
    # ο marker δένεται στην ΙΔΙΑ γραμμή με το label ("ετικέτα: ΟΥΔΕΝ
    # ΚΑΤΑΧΩΡΗΜΕΝΟ"), όχι σε δική του παράγραφο - αλλιώς μένει η θεσιακή
    # αμφισημία που θέλουμε να λύσουμε.
    assert f"γ.   Ποινές: {MARKER}" in result
    assert f"(1)   Συνήθεις - Πειθαρχικές: {MARKER}" in result
    assert "ΗΜΕΡΟΜΗΝΙΑ:\n03/04/2019" in result
    assert "ΓΝΩΜΑΤΕΥΣΗ:\nΙκανός" in result
    # το boundary "δ." δεν μαρκάρεται - κανένας marker ανάμεσα σε αυτό και
    # την πρώτη τιμή του
    tail_idx = result.index("δ.   Κατάσταση Υγείας")
    date_idx = result.index("ΗΜΕΡΟΜΗΝΙΑ:")
    assert MARKER not in result[tail_idx:date_idx]


def test_one_child_has_value_not_marked_container_not_marked():
    text = _ALL_EMPTY.replace(
        "(2)   Για Σοβαρά Παραπτώματα\n\n(3)",
        "(2)   Για Σοβαρά Παραπτώματα\n\nΠαράπτωμα Α\n\n(3)",
    )
    result = annotate_empty_section5_subfields(text)
    assert result.count(MARKER) == 4  # α, β, (1), (3) - όχι το (2), όχι το γ
    assert "Παράπτωμα Α" in result
    two_idx = result.index("(2)   Για Σοβαρά Παραπτώματα")
    three_idx = result.index("(3)   Πρόσκαιρη Παύση")
    assert MARKER not in result[two_idx:three_idx]
    container_idx = result.index("γ.   Ποινές")
    one_idx = result.index("(1)   Συνήθεις - Πειθαρχικές")
    assert MARKER not in result[container_idx:one_idx]


def test_container_has_own_value_children_empty_not_marked():
    text = _ALL_EMPTY.replace(
        "γ.   Ποινές\n\n(1)",
        "γ.   Ποινές\n\nΒΛ. ΣΗΜΕΙΩΣΗ\n\n(1)",
    )
    result = annotate_empty_section5_subfields(text)
    assert result.count(MARKER) == 5  # α, β, (1), (2), (3) - όχι το γ
    assert "ΒΛ. ΣΗΜΕΙΩΣΗ" in result
    container_idx = result.index("γ.   Ποινές")
    one_idx = result.index("(1)   Συνήθεις - Πειθαρχικές")
    assert MARKER not in result[container_idx:one_idx]
    assert result[container_idx:one_idx].count("ΒΛ. ΣΗΜΕΙΩΣΗ") == 1


def test_health_section_with_values_byte_identical():
    assert annotate_empty_section5_subfields(_HEALTH_TAIL) == _HEALTH_TAIL


def test_no_known_labels_byte_identical():
    text = "Κάποιο άσχετο κείμενο χωρίς κανένα από τα γνωστά labels.\nΤέλος."
    assert annotate_empty_section5_subfields(text) == text


def test_variant_single_space_spacing_matches():
    text = (
        "α. Παραπομπές σε συμβούλια - Αποφάσεις συμβουλίων\n\n"
        "β. Δίκες - Αποφάσεις Δικαστηρίων (Πολιτικών - Στρατοδικείων)\n\n"
        "γ. Ποινές\n\n"
        "(1) Συνήθεις - Πειθαρχικές\n\n"
        "(2) Για Σοβαρά Παραπτώματα\n\n"
        "(3) Πρόσκαιρη Παύση\n\n"
        "δ. Κατάσταση Υγείας\n\nΗΜΕΡΟΜΗΝΙΑ:\n01/01/2020\n"
    )
    result = annotate_empty_section5_subfields(text)
    assert result.count(MARKER) == 6


def test_idempotency_second_pass_does_not_duplicate_markers():
    once = annotate_empty_section5_subfields(_ALL_EMPTY)
    twice = annotate_empty_section5_subfields(once)
    assert once == twice
    assert twice.count(MARKER) == 6


def test_fake_agm_uses_greek_capital_mu_not_latin():
    assert ord("Μ") == 0x39C  # ΕΛΛΗΝΙΚΟ κεφαλαίο Μ, όχι λατινικό M (0x4D)
    text = "Α.Γ.Μ.: Μ-00000\n\n" + _ALL_EMPTY
    result = annotate_empty_section5_subfields(text)
    assert "Μ-00000" in result
    assert ord(result[result.index("Μ-00000")]) == 0x39C


def run_all():
    tests = [
        test_all_empty_marks_leaves_and_container,
        test_one_child_has_value_not_marked_container_not_marked,
        test_container_has_own_value_children_empty_not_marked,
        test_health_section_with_values_byte_identical,
        test_no_known_labels_byte_identical,
        test_variant_single_space_spacing_matches,
        test_idempotency_second_pass_does_not_duplicate_markers,
        test_fake_agm_uses_greek_capital_mu_not_latin,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
