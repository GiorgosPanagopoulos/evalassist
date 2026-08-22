"""Mini test/sample flow για το backend/app/ingestion/duties_positional.py
(_extract_block_duties - γεωμετρική εξαγωγή του πίνακα (ετικέτα, ημέρες)
της Ενότητας 7, θεσιακό/bare-anchor layout).

Fixture: αυτούσια PyMuPDF word tuples (x0, y0, x1, y1, text) από
private/perilhptiko2018.pdf (ΑΓΜ Μ-01253), όπως καταγράφηκαν με
`page.get_text("words")` πριν την υλοποίηση - όχι ξαναγραμμένα από μνήμη.
Το ίδιο το PDF είναι gitignored (private/) και δεν χρειάζεται εδώ: η pure
συνάρτηση _extract_block_duties δουλεύει πάνω σε word tuples ήδη scoped
στο εύρος ενός block, καμία εξάρτηση από fitz/PDF I/O.

Η μόνη εξαίρεση είναι το fixture "ετικέτα χωρίς αριθμό": δεν υπάρχει
τέτοια περίπτωση στα 36 πραγματικά blocks του δείγματος (μετρημένο) - το
fixture είναι το block 1 (σελ. 4, ΤΜΗΜΑΤΑΡΧΗΣ ΓΕΝ/Β3-V) ΧΩΡΙΣ το tuple
του "184", για να δοκιμαστεί ρητά η edge-case διακλάδωση (days=None).

Εκτελείται standalone: `PYTHONPATH=. python backend/tests/test_duties_positional.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.duties_positional import _extract_block_duties  # noqa: E402

# --- Block 1 πραγματικού PDF (σελ. 4, περίοδος 01/01/2024-02/07/2024):
# ΕΝΑ καθήκον, χωρίς wrap, με λέξη-συνέχεια στην ίδια οπτική γραμμή
# ("ΓΕΝ/Β3-V" μετά "ΤΜΗΜΑΤΑΡΧΗΣ") - ίδιο font-quirk y0 offset με τον
# αριθμό ημερών (βλ. docstring module). ---
BLOCK_1_ONE_DUTY = [
    (36.03, 5.91, 51.59, 13.91, "Ε.Α."),
    (66.34, 3.52, 106.37, 14.51, "01/01/2024"),
    (136.97, 3.52, 139.63, 14.51, "-"),
    (155.40, 3.52, 195.43, 14.51, "02/07/2024"),
    (214.15, 3.52, 258.97, 14.51, "EΞΑΙΡΕΤΟΣ"),
    (261.19, 5.91, 279.86, 13.91, "(100)"),
    (301.20, 5.91, 328.73, 13.91, "ΓΕΝ/Β3"),
    (400.13, 3.52, 402.79, 14.51, "-"),
    (418.56, 5.91, 479.50, 13.91, "ΤΜΗΜΑΤΑΡΧΗΣ"),
    (481.72, 3.52, 517.28, 14.51, "ΓΕΝ/Β3-V"),
    (524.11, 3.52, 537.46, 14.51, "184"),
]

# --- Block 6 πραγματικού PDF (σελ. 4, περίοδος 11/06/2021-31/12/2021):
# ΔΥΟ καθήκοντα, το πρώτο wrapped σε 3 γραμμές ("ΒΟΗΘΟΣ" / "ΠΡΟΙΣΤΑΜΕΝΟΥ" /
# "ΜΗΧΑΝΟΓΡΑΦΗΣΗΣ", gap +9.0 ανά γραμμή), το δεύτερο σε 2. ---
BLOCK_6_TWO_DUTIES = [
    (36.03, 230.27, 51.59, 238.27, "Ε.Α."),
    (66.34, 227.88, 106.37, 238.87, "11/06/2021"),
    (136.97, 227.88, 139.63, 238.87, "-"),
    (155.40, 227.88, 195.43, 238.87, "31/12/2021"),
    (214.15, 227.88, 258.97, 238.87, "EΞΑΙΡΕΤΟΣ"),
    (261.19, 230.27, 279.86, 238.27, "(100)"),
    (301.20, 230.27, 328.73, 238.27, "ΓΕΝ/Β3"),
    (400.13, 227.88, 402.79, 238.87, "-"),
    (418.56, 230.27, 453.29, 238.27, "ΒΟΗΘΟΣ"),
    (418.56, 239.27, 482.62, 247.27, "ΠΡΟΙΣΤΑΜΕΝΟΥ"),
    (418.56, 248.27, 496.57, 256.27, "ΜΗΧΑΝΟΓΡΑΦΗΣΗΣ"),
    (524.11, 227.88, 537.46, 238.87, "112"),
    (418.56, 261.23, 482.23, 269.23, "ΠΡΟΙΣΤΑΜΕΝΟΣ"),
    (418.56, 270.23, 496.57, 278.23, "ΜΗΧΑΝΟΓΡΑΦΗΣΗΣ"),
    (526.28, 258.84, 535.17, 269.83, "92"),
]

# --- Απόσπασμα block 9 πραγματικού PDF (σελ. 4, περίοδος
# 27/09/2019-13/07/2020): ΜΙΑ ετικέτα wrapped με συντομογραφία "ΕΒ"
# ("ΒΟΗΘΟΣ ΑΞΙΩΜΑΤΙΚΟΥ" + wrap "ΕΒ") - ΜΗΝ φιλτράρεις με βάση το μήκος. ---
BLOCK_9_WRAPPED_ABBREVIATION = [
    (36.03, 422.29, 51.59, 430.29, "Ε.Α."),
    (66.34, 419.90, 106.37, 430.89, "27/09/2019"),
    (136.97, 419.90, 139.63, 430.89, "-"),
    (155.40, 419.90, 195.43, 430.89, "13/07/2020"),
    (418.56, 510.27, 453.29, 518.27, "ΒΟΗΘΟΣ"),
    (455.51, 510.27, 510.26, 518.27, "ΑΞΙΩΜΑΤΙΚΟΥ"),
    (418.56, 519.27, 429.23, 527.27, "ΕΒ"),
    (524.11, 507.88, 537.46, 518.87, "161"),
]

# --- Block 28 πραγματικού PDF (σελ. 7, περίοδος 10/04/2009-10/04/2009):
# μονοήμερη παρουσίαση, ΚΑΝΕΝΑ καθήκον - ΕΓΚΥΡΟ, όχι σφάλμα. ---
BLOCK_28_EMPTY = [
    (36.03, 670.91, 51.59, 678.91, "Ε.Α."),
    (66.34, 668.52, 106.37, 679.51, "10/04/2009"),
    (136.97, 668.52, 139.63, 679.51, "-"),
    (155.40, 668.52, 195.43, 679.51, "10/04/2009"),
    (214.15, 668.52, 219.49, 679.51, "E"),
    (219.48, 670.91, 279.86, 678.91, "ΞΑΙΡΕΤΟΣ (100)"),
    (301.20, 670.91, 347.93, 678.91, "ΥΒ ΠΟΝΤΟΣ"),
    (400.13, 668.52, 402.79, 679.51, "-"),
]

# --- Block 1 ΧΩΡΙΣ το tuple του "184" (συνθετικό edge-case, βλ. docstring
# πάνω-πάνω): ετικέτα χωρίς αντίστοιχο αριθμό ημερών. ---
BLOCK_1_LABEL_WITHOUT_NUMBER = [w for w in BLOCK_1_ONE_DUTY if w[4] != "184"]


def test_one_duty_same_line_continuation():
    entries = _extract_block_duties(BLOCK_1_ONE_DUTY)
    assert entries == [("ΤΜΗΜΑΤΑΡΧΗΣ ΓΕΝ/Β3-V", 184)]


def test_two_duties_first_wrapped_three_lines():
    entries = _extract_block_duties(BLOCK_6_TWO_DUTIES)
    assert entries == [
        ("ΒΟΗΘΟΣ ΠΡΟΙΣΤΑΜΕΝΟΥ ΜΗΧΑΝΟΓΡΑΦΗΣΗΣ", 112),
        ("ΠΡΟΙΣΤΑΜΕΝΟΣ ΜΗΧΑΝΟΓΡΑΦΗΣΗΣ", 92),
    ]


def test_wrapped_label_with_abbreviation_not_filtered_by_length():
    entries = _extract_block_duties(BLOCK_9_WRAPPED_ABBREVIATION)
    assert entries == [("ΒΟΗΘΟΣ ΑΞΙΩΜΑΤΙΚΟΥ ΕΒ", 161)]
    # codepoint assertion: το "ΕΒ" είναι ελληνικά κεφαλαία (Ε=U+0395, Β=U+0392),
    # όχι λατινικά ομόγραφα (E=U+0045, B=U+0042) - critical για μη-φιλτράρισμα.
    label = entries[0][0]
    abbrev = label.split()[-1]
    assert abbrev == "ΕΒ"
    assert [ord(c) for c in abbrev] == [0x395, 0x392]


def test_empty_block_returns_empty_list_not_exception():
    assert _extract_block_duties(BLOCK_28_EMPTY) == []


def test_label_without_number_gives_none_not_exception():
    entries = _extract_block_duties(BLOCK_1_LABEL_WITHOUT_NUMBER)
    assert entries == [("ΤΜΗΜΑΤΑΡΧΗΣ ΓΕΝ/Β3-V", None)]


def test_empty_words_returns_empty_list():
    assert _extract_block_duties([]) == []


def test_unit_and_characterization_words_not_mistaken_for_labels():
    # Το "ΓΕΝ/Β3" (μονάδα, x0=301.20) και το "EΞΑΙΡΕΤΟΣ (100)" (χαρακτηρισμός,
    # x0=214.15) δεν πρέπει ποτέ να καταλήξουν σε ΞΕΧΩΡΙΣΤΟ label - μόνο η
    # στήλη x0~418.56 παράγει ετικέτες. Ακριβώς ΕΝΑ label αναμένεται εδώ.
    entries = _extract_block_duties(BLOCK_1_ONE_DUTY)
    assert len(entries) == 1
    assert entries[0][0] == "ΤΜΗΜΑΤΑΡΧΗΣ ΓΕΝ/Β3-V"
    assert "EΞΑΙΡΕΤΟΣ" not in entries[0][0]


def run_all():
    tests = [
        test_one_duty_same_line_continuation,
        test_two_duties_first_wrapped_three_lines,
        test_wrapped_label_with_abbreviation_not_filtered_by_length,
        test_empty_block_returns_empty_list_not_exception,
        test_label_without_number_gives_none_not_exception,
        test_empty_words_returns_empty_list,
        test_unit_and_characterization_words_not_mistaken_for_labels,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
