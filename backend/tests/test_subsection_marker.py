"""Mini test/sample flow για το backend/app/ingestion/subsection_marker.py
(marker συνέχειας υποενότητας α./β./γ./δ./ε. πάνω από page break).

Fixtures βασισμένα στο πραγματικό κείμενο chunks του
private/perilhptiko2018.pdf (επιβεβαιωμένο μέσω repr() σε πραγματικό
ingestion run):
- career_chunks[1] (:36, σελ.1, ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ) τελειώνει με
  header "γ.  Ανά Κατηγορία Καθήκοντος" (ΔΥΟ κενά).
- career_chunks[2] (:37, σελ.2, ΙΔΙΟ section) δεν έχει κανέναν header -
  expected marker: "γ.  Ανά Κατηγορία Καθήκοντος" (ΟΧΙ "β.").
- career_chunks[5] (:40, σελ.2, ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ) περιέχει α./β./
  γ./δ. με δικούς του headers - δεν χρειάζεται marker, τελευταίος header
  "δ.   Κατάσταση Υγείας" (ΤΡΙΑ κενά).
- career_chunks[6] (:41, σελ.3, ΙΔΙΟ section) ΑΡΧΙΖΕΙ με ορφανές γραμμές
  (χωρίς header) αλλά ΤΕΛΕΙΩΝΕΙ με "ε.  Ευαρέσκειες" - expected marker
  "δ.   Κατάσταση Υγείας" ΠΑΡΟΛΟ που το chunk περιέχει (στο τέλος) δικό του
  header: ο κανόνας είναι θεσιακός (πρώτη γραμμή), όχι "chunk περιέχει
  οπουδήποτε έναν header".

Εκτελείται standalone: `python tests/test_subsection_marker.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.subsection_marker import (  # noqa: E402
    _MARKER_PREFIX,
    _annotate,
    annotate_subsection_continuation,
    resolve_subsection_carryforward,
)

_SECTION_2 = "ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ"
_SECTION_3 = "ΚΑΤΕΧΟΜΕΝΑ ΠΤΥΧΙΑ"
_SECTION_5 = "ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ"
_SECTION_6 = "ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΣΤΟΝ ΚΑΤΕΧΟΜΕΝΟ ΒΑΘΜΟ"

# Αυτούσιο (repr-verified) κείμενο career_chunks[1] (:36, σελ.1).
_CHUNK_36 = (
    "2. - ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ\n\n"
    "α.  ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ (Έως 27/09/2024)\n23\nΈτη\n0\nΜήνες\n10\nΗμέρες\n\n"
    "β.  Ανά Σταδιοδρομική Κατηγορία\n\n"
    "ΣΥΝΟΛΙΚΗ ΥΠΗΡΕΣΙΑ ΘΑΛΑΣΣΑΣ\n13\nΈτη\n4\nMήνες\n8\nΗμέρες\n\n"
    "ΠΛΟΙΑ\n12\nΈτη\n11\nMήνες\n7\nΗμέρες\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ ΟΛΟΚΛΗΡΩΣΗΣ ΠΡΟΣΟΝΤΩΝ\n0\nΈτη\n0\nMήνες\n0\nΗμέρες\n\n"
    "Αος ΜΗΧΑΝΙΚΟΣ\n7\nΈτη\n1\nMήνες\n8\nΗμέρες\n\n"
    "γ.  Ανά Κατηγορία Καθήκοντος\n\n"
    "Εκτυπώθηκε από το χρήστη: B3VE\\e.siatis\nΣελίδα 1 από 8\n(ΑΓΜ: Μ-01253)"
)

# Αυτούσιο (repr-verified) κείμενο career_chunks[2] (:37, σελ.2, ΙΔΙΟ section).
_CHUNK_37 = (
    "Α ΜΗΧΑΝΙΚΟΣ ΑΝΘΧΟΣ ΥΒ ΑΜΦΙΤΡΙΤΗ\n2\nΈτη\n1\nMήνες\n24\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ ΥΠΧΟΣ ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ\n2\nΈτη\n12\nMήνες\n3\nΗμέρες"
)

_EXPECTED_HEADER_37 = "γ.  Ανά Κατηγορία Καθήκοντος"

# Αυτούσιο (repr-verified) κείμενο career_chunks[5] (:40, σελ.2).
_CHUNK_40 = (
    "5. - ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ ή ΜΗ ΓΙΑ ΠΡΟΑΓΩΓΗ ΚΑΤ' ΕΚΛΟΓΗΝ\n\n"
    "α.  Παραπομπές σε συμβούλια - Αποφάσεις συμβουλίων\n\n"
    "β.  Δίκες - Αποφάσεις Δικαστηρίων (Πολιτικών - Στρατοδικείων)\n\n"
    "γ.   Ποινές\n\n"
    "(1)   Συνήθεις - Πειθαρχικές\n\n"
    "(2)   Για Σοβαρά Παραπτώματα\n\n"
    "(3)   Πρόσκαιρη Παύση\n\n"
    "δ.   Κατάσταση Υγείας\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n03/04/2019\nΓΝΩΜΑΤΕΥΣΗ\n:\nΝΝΑ/030815ΖΑΠΡ19\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 3\n\n"
    "Εκτυπώθηκε από το χρήστη: B3VE\\e.siatis\nΣελίδα 2 από 8\n(ΑΓΜ: Μ-01253)"
)

# Αυτούσιο (repr-verified) κείμενο career_chunks[6] (:41, σελ.3, ΙΔΙΟ section
# με :40) - ΑΡΧΙΖΕΙ ορφανό, ΤΕΛΕΙΩΝΕΙ με δικό του header "ε.  Ευαρέσκειες".
_CHUNK_41 = (
    "ΠΕΡΙΓΡΑΦΗ :\n\nΗΜΕΡΟΜΗΝΙΑ:\n19/12/2018\nΓΝΩΜΑΤΕΥΣΗ\n:\nΝΝΑ/201116ΖΔΕΚ18\n"
    "ΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 3\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΟΙΚΟΙ ΝΟΣΗΛΕΙΑΣ\n\nΗΜΕΡΟΜΗΝΙΑ:\n20/07/2017\nΓΝΩΜΑΤΕΥΣΗ\n:\n"
    "ΝΝΑ/210723JUL17\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 2\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΣύνδρομο προσομοιάζων με λοιμώδη μονοπυρήνωση - εμπύρετη φαρυγγοαμυγδαλίτιδα.\n\n"
    "ε.  Ευαρέσκειες"
)

_EXPECTED_HEADER_41 = "δ.   Κατάσταση Υγείας"


def test_carryforward_over_multiple_chunks_real_data():
    """career_chunks[1..2] (:36 -> :37), αυτούσια δεδομένα εγγράφου: το :37
    δεν έχει δικό του header, ο τελευταίος που είδαμε στο :36 είναι γ. (όχι
    β.) - ρητός έλεγχος της διόρθωσης."""
    result = resolve_subsection_carryforward(
        [_CHUNK_36, _CHUNK_37], [_SECTION_2, _SECTION_2]
    )
    assert result[0] is None  # το :36 έχει τους δικούς του headers
    assert result[1] == _EXPECTED_HEADER_37
    assert result[1] != "β.  Ανά Σταδιοδρομική Κατηγορία"


def test_carryforward_survives_across_intervening_chunks_no_header():
    """Το carry-forward πρέπει να επιβιώνει έως 5 σελίδες πάνω από ενδιάμεσα
    chunks του ΙΔΙΟΥ section χωρίς κανέναν δικό τους header."""
    texts = [_CHUNK_36, "Ουδέν νέο περιεχόμενο.", "Ακόμα ουδέν.", _CHUNK_37]
    sections = [_SECTION_2, _SECTION_2, _SECTION_2, _SECTION_2]
    result = resolve_subsection_carryforward(texts, sections)
    assert result == [None, _EXPECTED_HEADER_37, _EXPECTED_HEADER_37, _EXPECTED_HEADER_37]


def test_reset_on_top_level_section_change():
    result = resolve_subsection_carryforward(
        [_CHUNK_36, "Ξεκινά νέα ενότητα χωρίς κανένα header."],
        [_SECTION_2, _SECTION_3],
    )
    assert result[1] is None


def test_chunk_with_own_header_at_start_not_marked():
    """career_chunks[5] (:40): έχει δικούς του headers α./β./γ./δ. -> None,
    ΑΝΕΞΑΡΤΗΤΑ από το ότι προηγείται (υποθετικά) ενεργός carry."""
    result = resolve_subsection_carryforward(
        [_CHUNK_36, _CHUNK_40], [_SECTION_2, _SECTION_5]
    )
    assert result[1] is None


def test_positional_not_contains_any_real_data_case():
    """career_chunks[6] (:41): ΑΡΧΙΖΕΙ ορφανό, marker = δ. (από :40),
    ΠΑΡΟΛΟ που περιέχει (στο τέλος) δικό του header "ε. Ευαρέσκειες". Ένας
    "chunk περιέχει οπουδήποτε header -> None" κανόνας θα έδινε λάθος None
    εδώ - αυτό είναι το ρητό test για τη θεσιακή (πρώτη γραμμή) εκδοχή."""
    result = resolve_subsection_carryforward(
        [_CHUNK_40, _CHUNK_41], [_SECTION_5, _SECTION_5]
    )
    assert result[0] is None
    assert result[1] == _EXPECTED_HEADER_41
    assert "ε.  Ευαρέσκειες" in _CHUNK_41  # sanity: το header υπάρχει, απλά όχι στην αρχή


def test_active_header_updates_to_last_found_even_when_not_at_start():
    """Μετά το :41 (που έχει ε. στο τέλος, όχι στην αρχή), ένα επόμενο chunk
    ΙΔΙΟΥ section πρέπει να κληρονομήσει ε., όχι δ. - το ε. δεν βρίσκεται
    στην αρχή του :41 άρα δεν μαρκάρει το :41 ως self-contained, αλλά
    ενημερώνει τον ενεργό header για ό,τι ΕΠΕΤΑΙ."""
    result = resolve_subsection_carryforward(
        [_CHUNK_40, _CHUNK_41, "Συνέχεια χωρίς κανένα δικό της header."],
        [_SECTION_5, _SECTION_5, _SECTION_5],
    )
    assert result[2] == "ε.  Ευαρέσκειες"


def test_chunk_with_own_header_reachable_mid_first_line_not_matched_as_start():
    text = "Κάποια εισαγωγική γραμμή χωρίς header.\nα. Τίτλος\nΠεριεχόμενο."
    result = resolve_subsection_carryforward([_CHUNK_36, text], [_SECTION_2, _SECTION_2])
    # η πρώτη μη-κενή γραμμή ΔΕΝ είναι header -> κληρονομεί το ενεργό (γ.)
    assert result[1] == _EXPECTED_HEADER_37


def test_multiple_spaces_after_period_recognized_as_header():
    text = "γ.   Ποινές\n\nΠεριεχόμενο."
    result = resolve_subsection_carryforward([text], [_SECTION_5])
    assert result[0] is None  # η ίδια η πρώτη γραμμή είναι header


def test_ea_sa_capital_letters_not_treated_as_subsection_header():
    """Ε.Α. / Σ.Α. είναι ΚΕΦΑΛΑΙΑ - δεν πρέπει να πιάνονται από [α-ε]."""
    text = "Ε.Α.\n01/01/2024\n-\n02/07/2024\nΕΞΑΙΡΕΤΟΣ (100)"
    result = resolve_subsection_carryforward([_CHUNK_36, text], [_SECTION_2, _SECTION_2])
    assert result[1] == _EXPECTED_HEADER_37  # όχι None - το Ε.Α. δεν "έσβησε" το carry


def test_annotate_prepends_marker_with_blank_line():
    result = annotate_subsection_continuation("κείμενο", "δ. Κατάσταση Υγείας")
    assert result == "[ΣΥΝΕΧΕΙΑ ΥΠΟΕΝΟΤΗΤΑΣ: δ. Κατάσταση Υγείας]\n\nκείμενο"


def test_annotate_none_title_returns_unchanged():
    assert annotate_subsection_continuation("κείμενο", None) == "κείμενο"


def test_annotate_idempotency_second_pass_does_not_duplicate():
    once = annotate_subsection_continuation("κείμενο", "δ. Κατάσταση Υγείας")
    twice = annotate_subsection_continuation(once, "δ. Κατάσταση Υγείας")
    assert once == twice
    assert twice.count("[ΣΥΝΕΧΕΙΑ ΥΠΟΕΝΟΤΗΤΑΣ:") == 1


def test_annotate_marker_derived_from_single_source_of_truth():
    """_MARKER_PREFIX και το f-string στο _annotate πρέπει να παράγουν τον
    ΙΔΙΟ prefix - αλλιώς το idempotency guard (text.startswith(_MARKER_PREFIX))
    αποτυγχάνει σιωπηλά και ο marker διπλασιάζεται σε re-ingestion."""
    once = _annotate("X", "T")
    assert once.startswith(_MARKER_PREFIX) is True
    assert _annotate(once, "T") == once


def test_annotate_exception_path_returns_text_unchanged():
    class _Hostile:
        def __str__(self):
            raise RuntimeError("boom")

    result = annotate_subsection_continuation("κείμενο", _Hostile())  # type: ignore[arg-type]
    assert result == "κείμενο"


def run_all():
    tests = [
        test_carryforward_over_multiple_chunks_real_data,
        test_carryforward_survives_across_intervening_chunks_no_header,
        test_reset_on_top_level_section_change,
        test_chunk_with_own_header_at_start_not_marked,
        test_positional_not_contains_any_real_data_case,
        test_active_header_updates_to_last_found_even_when_not_at_start,
        test_chunk_with_own_header_reachable_mid_first_line_not_matched_as_start,
        test_multiple_spaces_after_period_recognized_as_header,
        test_ea_sa_capital_letters_not_treated_as_subsection_header,
        test_annotate_prepends_marker_with_blank_line,
        test_annotate_none_title_returns_unchanged,
        test_annotate_idempotency_second_pass_does_not_duplicate,
        test_annotate_marker_derived_from_single_source_of_truth,
        test_annotate_exception_path_returns_text_unchanged,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
