"""Mini test/sample flow για το backend/app/ingestion/duty_categories.py
(extract_duty_category_rows - γεωμετρική εξαγωγή της υποενότητας γ. Ανά
Κατηγορία Καθήκοντος της Ενότητας 2).

Fixture: αυτούσια PyMuPDF word tuples (x0, y0, x1, y1, text) από
private/perilhptiko2018.pdf σελίδα 2 (ΑΓΜ Μ-01253), όπως καταγράφηκαν στο
recon πριν την υλοποίηση - όχι ξαναγραμμένα από μνήμη. Το ίδιο το PDF είναι
gitignored (private/) και δεν χρειάζεται εδώ: η pure συνάρτηση δουλεύει
πάνω σε word tuples, καμία εξάρτηση από fitz/PDF I/O.

Εκτελείται standalone: `python tests/test_duty_categories.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.duty_categories as duty_categories  # noqa: E402
from app.ingestion.duty_categories import (  # noqa: E402
    _DUTY_LABEL_PREFIX,
    extract_duty_category_rows,
    label_duty_category_rows,
)

# Αυτούσια word tuples (x0, y0, x1, y1, text) - σελίδα 2, οι 5 πραγματικές
# σειρές της υποενότητας γ. Σειρά εμφάνισης στο PDF, ΟΧΙ ταξινομημένα.
WORDS_PAGE_2 = [
    # --- σειρά 1: Α ΜΗΧΑΝΙΚΟΣ / ΑΝΘΧΟΣ / ΥΒ ΑΜΦΙΤΡΙΤΗ / 2-1-24 ---
    (36.03, 7.93, 41.36, 15.93, "Α"),
    (43.59, 7.93, 91.20, 15.93, "ΜΗΧΑΝΙΚΟΣ"),
    (135.24, 7.93, 169.08, 15.93, "ΑΝΘΧΟΣ"),
    (189.10, 7.93, 199.77, 15.93, "ΥΒ"),
    (201.99, 7.93, 245.71, 15.93, "ΑΜΦΙΤΡΙΤΗ"),
    (305.31, 5.54, 309.75, 16.53, "2"),
    (343.11, 7.93, 356.99, 15.93, "Έτη"),
    (390.34, 5.54, 394.79, 16.53, "1"),
    (423.82, 5.54, 446.39, 16.53, "Mήνες"),  # ΛΑΤΙΝΙΚΟ M, εντός εγγράφου
    (473.14, 5.54, 482.03, 16.53, "24"),
    (507.20, 7.93, 533.12, 15.93, "Ημέρες"),
    # --- σειρά 2: Α ΜΗΧΑΝΙΚΟΣ / ΥΠΧΟΣ / ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ / 2-12-3 ---
    (36.03, 24.92, 41.36, 32.92, "Α"),
    (43.59, 24.92, 91.20, 32.92, "ΜΗΧΑΝΙΚΟΣ"),
    (135.24, 24.92, 162.86, 32.92, "ΥΠΧΟΣ"),
    (189.10, 24.92, 199.77, 32.92, "ΥΒ"),
    (201.99, 24.92, 259.83, 32.92, "ΠΑΠΑΝΙΚΟΛΗΣ"),
    (305.31, 22.53, 309.75, 33.52, "2"),
    (343.11, 24.92, 356.99, 32.92, "Έτη"),
    (388.11, 22.53, 397.00, 33.52, "12"),
    (423.82, 22.53, 446.39, 33.52, "Mήνες"),
    (475.37, 22.53, 479.82, 33.52, "3"),
    (507.20, 24.92, 533.12, 32.92, "Ημέρες"),
    # --- σειρά 3: Α ΜΗΧΑΝΙΚΟΣ / ΥΠΧΟΣ / ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ / 1-1-6 ---
    (36.03, 41.91, 41.36, 49.91, "Α"),
    (43.59, 41.91, 91.20, 49.91, "ΜΗΧΑΝΙΚΟΣ"),
    (135.24, 41.91, 162.86, 49.91, "ΥΠΧΟΣ"),
    (189.10, 41.91, 199.77, 49.91, "ΥΒ"),
    (201.99, 41.91, 259.83, 49.91, "ΠΑΠΑΝΙΚΟΛΗΣ"),
    (305.31, 39.52, 309.75, 50.51, "1"),
    (343.11, 41.91, 356.99, 49.91, "Έτη"),
    (390.34, 39.52, 394.79, 50.51, "1"),
    (423.82, 39.52, 446.39, 50.51, "Mήνες"),
    (475.37, 39.52, 479.82, 50.51, "6"),
    (507.20, 41.91, 533.12, 49.91, "Ημέρες"),
    # --- σειρά 4: Α ΜΗΧΑΝΙΚΟΣ / (rank λείπει) / ΥΒ ΠΡΩΤΕΥΣ / 0-0-28 ---
    (36.03, 58.91, 41.36, 66.91, "Α"),
    (43.59, 58.91, 91.20, 66.91, "ΜΗΧΑΝΙΚΟΣ"),
    (189.10, 58.91, 199.77, 66.91, "ΥΒ"),
    (201.99, 58.91, 239.59, 66.91, "ΠΡΩΤΕΥΣ"),
    (305.31, 56.52, 309.75, 67.51, "0"),
    (343.11, 58.91, 356.99, 66.91, "Έτη"),
    (390.34, 56.52, 394.79, 67.51, "0"),
    (423.82, 56.52, 446.39, 67.51, "Mήνες"),
    (473.14, 56.52, 482.03, 67.51, "28"),
    (507.20, 58.91, 533.12, 66.91, "Ημέρες"),
    # --- σειρά 5: Α ΜΗΧΑΝΙΚΟΣ / (rank λείπει) / ΥΒ ΠΡΩΤΕΥΣ / 0-9-21 ---
    (36.03, 75.97, 41.36, 83.97, "Α"),
    (43.59, 75.97, 91.20, 83.97, "ΜΗΧΑΝΙΚΟΣ"),
    (189.10, 75.97, 199.77, 83.97, "ΥΒ"),
    (201.99, 75.97, 239.59, 83.97, "ΠΡΩΤΕΥΣ"),
    (305.31, 73.58, 309.75, 84.57, "0"),
    (343.11, 75.97, 356.99, 83.97, "Έτη"),
    (390.34, 73.58, 394.79, 84.57, "9"),
    (423.82, 73.58, 446.39, 84.57, "Mήνες"),
    (473.14, 73.58, 482.03, 84.57, "21"),
    (507.20, 75.97, 533.12, 83.97, "Ημέρες"),
    # --- footer, στην ίδια σελίδα, πρέπει να αγνοηθεί (y >= 817) ---
    (19.03, 819.92, 61.38, 826.92, "Εκτυπώθηκε"),
    (63.32, 819.92, 77.27, 826.92, "από"),
    (513.77, 819.92, 517.66, 826.92, "1"),  # ψηφίο σε στήλη category, όχι δεδομένα
]


def test_five_real_rows_exact():
    entries = extract_duty_category_rows(WORDS_PAGE_2)
    assert len(entries) == 5
    assert [(e.category, e.rank, e.unit, e.years, e.months, e.days) for e in entries] == [
        ("Α ΜΗΧΑΝΙΚΟΣ", "ΑΝΘΧΟΣ", "ΥΒ ΑΜΦΙΤΡΙΤΗ", 2, 1, 24),
        ("Α ΜΗΧΑΝΙΚΟΣ", "ΥΠΧΟΣ", "ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ", 2, 12, 3),
        ("Α ΜΗΧΑΝΙΚΟΣ", "ΥΠΧΟΣ", "ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ", 1, 1, 6),
        ("Α ΜΗΧΑΝΙΚΟΣ", None, "ΥΒ ΠΡΩΤΕΥΣ", 0, 0, 28),
        ("Α ΜΗΧΑΝΙΚΟΣ", None, "ΥΒ ΠΡΩΤΕΥΣ", 0, 9, 21),
    ]


def test_missing_rank_is_none_not_empty_string():
    entries = extract_duty_category_rows(WORDS_PAGE_2)
    assert entries[3].rank is None
    assert entries[4].rank is None
    # rank λείπει, unit/category όχι - η απουσία δεν έσπασε τη γειτονική στήλη
    assert entries[3].unit == "ΥΒ ΠΡΩΤΕΥΣ"
    assert entries[3].category == "Α ΜΗΧΑΝΙΚΟΣ"


def test_unit_labels_rejected_by_x_range_not_text():
    entries = extract_duty_category_rows(WORDS_PAGE_2)
    for entry in entries:
        for field in (entry.category, entry.rank, entry.unit):
            assert field is None or "Έτη" not in field
            assert field is None or "Mήνες" not in field
            assert field is None or "Ημέρες" not in field


def test_footer_rows_excluded():
    entries = extract_duty_category_rows(WORDS_PAGE_2)
    # Το ψηφίο footer "1" (y=819.92) δεν πρέπει να παράξει 6η σειρά.
    assert len(entries) == 5


def test_empty_words_returns_empty_list():
    assert extract_duty_category_rows([]) == []


def test_row_without_values_is_dropped():
    # Μόνο category, καμία τιμή στις στήλες years/months/days - όπως ο
    # ίδιος ο header 'γ. Ανά Κατηγορία Καθήκοντος' που δεν έχει δεδομένα
    # από κάτω του στην ίδια σελίδα.
    header_like = [
        (36.03, 795.03, 42.70, 803.03, "γ."),
        (47.15, 795.03, 62.29, 803.03, "Ανά"),
        (64.51, 795.03, 105.09, 803.03, "Κατηγορία"),
        (107.31, 795.03, 153.64, 803.03, "Καθήκοντος"),
    ]
    assert extract_duty_category_rows(header_like) == []


def test_failsafe_exception_returns_empty_list_not_raise():
    original = duty_categories._row_to_entry

    def _boom(_row):
        raise RuntimeError("forced failure for test")

    duty_categories._row_to_entry = _boom
    try:
        result = extract_duty_category_rows(WORDS_PAGE_2)
    finally:
        duty_categories._row_to_entry = original
    assert result == []


# Αυτούσιο repr από private/debug_duty_categories_page2_chunktext.txt -
# indexed_text (μετά normalize_greek_homoglyphs) του chunk σελίδας 2, ΠΡΙΝ
# από labeling. Ίδιο πρόσωπο/PDF με τα WORDS_PAGE_2 παραπάνω, ίδιες 5
# εγγραφές, στη μορφή που πράγματι παράγει parser._extract_text_blocks (ένα
# token ανά γραμμή, κενή γραμμή ανάμεσα σε εγγραφές) - όχι ξαναγραμμένο από
# μνήμη/εικασία.
#
# Το "12 Μήνες" στη 2η εγγραφή ΕΙΝΑΙ η πραγματική τιμή του εντύπου, όχι
# σφάλμα parsing - επαληθεύτηκε γεωμετρικά (token 12@x=388, ακριβώς στη
# στήλη μηνών). Μην το "διορθώσεις" σε <12.
PAGE2_TEXT = (
    "Α ΜΗΧΑΝΙΚΟΣ\nΑΝΘΧΟΣ\nΥΒ ΑΜΦΙΤΡΙΤΗ\n2\nΈτη\n1\nΜήνες\n24\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΠΧΟΣ\nΥΒ ΠΑΠΑΝΙΚΟΛΗΣ\n2\nΈτη\n12\nΜήνες\n3\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΠΧΟΣ\nΥΒ ΠΑΠΑΝΙΚΟΛΗΣ\n1\nΈτη\n1\nΜήνες\n6\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΒ ΠΡΩΤΕΥΣ\n0\nΈτη\n0\nΜήνες\n28\nΗμέρες\n\n"
    "Α ΜΗΧΑΝΙΚΟΣ\nΥΒ ΠΡΩΤΕΥΣ\n0\nΈτη\n9\nΜήνες\n21\nΗμέρες"
)

ENTRIES = extract_duty_category_rows(WORDS_PAGE_2)


def test_label_happy_path_all_five_rows_labeled():
    result = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    assert result.count(_DUTY_LABEL_PREFIX) == 5
    assert (
        "ΚΑΘΗΚΟΝ: Α ΜΗΧΑΝΙΚΟΣ | ΒΑΘΜΟΣ: ΑΝΘΧΟΣ | ΜΟΝΑΔΑ: ΥΒ ΑΜΦΙΤΡΙΤΗ | "
        "ΔΙΑΡΚΕΙΑ: 2 Έτη 1 Μήνες 24 Ημέρες"
    ) in result
    assert (
        "ΚΑΘΗΚΟΝ: Α ΜΗΧΑΝΙΚΟΣ | ΒΑΘΜΟΣ: ΥΠΧΟΣ | ΜΟΝΑΔΑ: ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ | "
        "ΔΙΑΡΚΕΙΑ: 2 Έτη 12 Μήνες 3 Ημέρες"
    ) in result


def test_label_missing_rank_uses_no_value_marker():
    result = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    assert (
        "ΚΑΘΗΚΟΝ: Α ΜΗΧΑΝΙΚΟΣ | ΒΑΘΜΟΣ: ΟΥΔΕΝ ΚΑΤΑΧΩΡΗΜΕΝΟ | ΜΟΝΑΔΑ: ΥΒ ΠΡΩΤΕΥΣ | "
        "ΔΙΑΡΚΕΙΑ: 0 Έτη 0 Μήνες 28 Ημέρες"
    ) in result
    assert (
        "ΚΑΘΗΚΟΝ: Α ΜΗΧΑΝΙΚΟΣ | ΒΑΘΜΟΣ: ΟΥΔΕΝ ΚΑΤΑΧΩΡΗΜΕΝΟ | ΜΟΝΑΔΑ: ΥΒ ΠΡΩΤΕΥΣ | "
        "ΔΙΑΡΚΕΙΑ: 0 Έτη 9 Μήνες 21 Ημέρες"
    ) in result


def test_label_replaces_bare_lines_not_appends():
    # ΑΝΤΙΚΑΤΑΣΤΑΣΗ όχι ΠΡΟΣΘΗΚΗ: η μονάδα δεν πρέπει να εμφανίζεται δύο
    # φορές (μία γυμνή + μία μέσα στη labeled γραμμή).
    result = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    assert result.count("ΥΒ ΑΜΦΙΤΡΙΤΗ") == 1
    assert result.count("ΥΒ ΠΑΠΑΝΙΚΟΛΗΣ") == 2  # δύο ΔΙΑΦΟΡΕΤΙΚΕΣ εγγραφές, όχι διπλασιασμός της ίδιας


def test_label_all_or_nothing_one_bad_entry_blocks_all():
    # entries[0] αντικαθίσταται με μια εκδοχή που ΔΕΝ ταιριάζει στο κείμενο
    # (days=999 δεν υπάρχει) - ΚΑΜΙΑ από τις 5 πρέπει να αλλάξει, ούτε οι
    # 4 έγκυρες.
    bad_entry = ENTRIES[0].model_copy(update={"days": 999})
    corrupted = [bad_entry] + ENTRIES[1:]
    result = label_duty_category_rows(PAGE2_TEXT, corrupted)
    assert result == PAGE2_TEXT
    assert _DUTY_LABEL_PREFIX not in result


def test_label_idempotency_second_pass_does_not_change_result():
    once = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    twice = label_duty_category_rows(once, ENTRIES)
    assert once == twice


def test_label_guard_and_format_share_single_prefix_constant():
    once = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    first_line = once.split("\n", 1)[0]
    assert first_line.startswith(_DUTY_LABEL_PREFIX)
    # το guard ελέγχει ΤΗΝ ΙΔΙΑ σταθερά που παράγει η μορφοποίηση - κείμενο
    # χτισμένο με το import, όχι με ξαναγραμμένο literal στο test.
    already_labeled = f"{_DUTY_LABEL_PREFIX} sentinel\n" + PAGE2_TEXT
    assert label_duty_category_rows(already_labeled, ENTRIES) == already_labeled


def test_label_months_output_uses_greek_mu_not_latin():
    once = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    assert "Μήνες" in once
    idx = once.index("Μήνες")
    assert ord(once[idx]) == 0x39C  # ΕΛΛΗΝΙΚΟ κεφαλαίο Μ, όχι λατινικό M (0x4D)
    assert "Mήνες" not in once  # λατινικό M δεν πρέπει να διαφύγει στην έξοδο


def test_label_empty_entries_returns_text_unchanged():
    assert label_duty_category_rows(PAGE2_TEXT, []) == PAGE2_TEXT


def test_label_no_matching_entries_returns_text_unchanged():
    # entries ΜΗ κενό αλλά ΚΑΜΙΑ εγγραφή δεν εμφανίζεται στο text - όπως το
    # chunk σελ.1 α/β, όπου η υποενότητα γ δεν υπάρχει καν στο κείμενο.
    # failed == len(spans): no-op (logger.debug), όχι warning.
    page1_text = "Α ΝΑΥΤΙΚΟΣ\nΑΤΤΑΣΕ\n1\nΈτη\n2\nΜήνες\n3\nΗμέρες"
    assert label_duty_category_rows(page1_text, ENTRIES) == page1_text


def test_label_failsafe_exception_returns_text_unchanged():
    original = duty_categories._entry_raw_span

    def _boom(_entry):
        raise RuntimeError("forced failure for test")

    duty_categories._entry_raw_span = _boom
    try:
        result = label_duty_category_rows(PAGE2_TEXT, ENTRIES)
    finally:
        duty_categories._entry_raw_span = original
    assert result == PAGE2_TEXT


def run_all():
    tests = [
        test_five_real_rows_exact,
        test_missing_rank_is_none_not_empty_string,
        test_unit_labels_rejected_by_x_range_not_text,
        test_footer_rows_excluded,
        test_empty_words_returns_empty_list,
        test_row_without_values_is_dropped,
        test_failsafe_exception_returns_empty_list_not_raise,
        test_label_happy_path_all_five_rows_labeled,
        test_label_missing_rank_uses_no_value_marker,
        test_label_replaces_bare_lines_not_appends,
        test_label_all_or_nothing_one_bad_entry_blocks_all,
        test_label_idempotency_second_pass_does_not_change_result,
        test_label_guard_and_format_share_single_prefix_constant,
        test_label_months_output_uses_greek_mu_not_latin,
        test_label_empty_entries_returns_text_unchanged,
        test_label_no_matching_entries_returns_text_unchanged,
        test_label_failsafe_exception_returns_text_unchanged,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
