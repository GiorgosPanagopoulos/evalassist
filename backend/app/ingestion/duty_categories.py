"""Γεωμετρική εξαγωγή της υποενότητας «γ. Ανά Κατηγορία Καθήκοντος» της
Ενότητας 2 (ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ) σε ServiceTimeEntry, για persistence
στον πίνακα service_time (SQLite) - ίδιο σκεπτικό με τα promotion_table.py
και service_time.py.

Η υποενότητα γ ΔΕΝ είναι εξαγώγιμη με text parsing (σε αντίθεση με τις α/β
στο app.ingestion.service_time): έχει τρεις επιπλέον στήλες (category, rank,
unit) στην ΙΔΙΑ οριζόντια θέση όπου σε άλλες σειρές βρίσκεται διαφορετικό
πεδίο - μόνο το x0 της κάθε λέξης το διακρίνει, όχι η σειρά εμφάνισης στο
κείμενο. Καθαρή γεωμετρική λύση πάνω σε PyMuPDF word tuples (x0, y0, x1, y1,
text), πριν από οποιαδήποτε ανασύνθεση σε γραμμές κειμένου.

Οι σταθερές (x-anchors, tolerance, footer threshold) προέρχονται από
μέτρηση επί του πραγματικού private/perilhptiko2018.pdf (ΑΓΜ Μ-01253,
σελίδες 1-2) και επαληθεύτηκαν να παράγουν ακριβώς τις 5 πραγματικές σειρές
πριν οριστικοποιηθεί το module.
"""

import logging
from pathlib import Path

import fitz  # PyMuPDF

from app.models.evaluation import ServiceTimeEntry

logger = logging.getLogger(__name__)

WordTuple = tuple[float, float, float, float, str]

# Ίδιος δείκτης υποενότητας γ με το text-based
# app.ingestion.service_time._SUBSECTION_C_PREFIX. Το "γ." δεν έχει
# τεκμηριωμένο πρόβλημα homoglyph στο PDF (σε αντίθεση με το "Μήνες"/"Mήνες"
# - βλ. MONTHS_LABEL_X παρακάτω), οπότε εδώ επιτρέπεται σύγκριση με string
# literal: χρησιμοποιείται ΜΟΝΟ για να εντοπιστεί ΠΟΥ ξεκινάει η ενότητα,
# ΠΟΤΕ για το parsing των ίδιων των σειρών δεδομένων (εκεί ισχύει αυστηρά
# x-position anchor, βλ. _row_to_entry).
_SUBSECTION_C_MARKER = "γ."

# Footer ("Εκτυπώθηκε από το χρήστη: ...") ξεκινάει y>=817 και στις δύο
# σελίδες του brief. Λέξεις σε ή κάτω από αυτό το y αγνοούνται.
FOOTER_Y = 817.0

# Κάθε λογική σειρά καταλαμβάνει δύο οπτικές γραμμές (τιμές/ετικέτες) με
# offset 2.39px· η απόσταση μεταξύ διαδοχικών σειρών είναι ~17px. Η ανοχή
# 3.0 (> 2.39, << 17) συγχωνεύει τις δύο οπτικές γραμμές μιας λογικής
# σειράς χωρίς να αλυσιδώνει διπλανές σειρές.
ROW_Y_TOLERANCE = 3.0

# Column x0-ranges, μετρημένες στις 5 πραγματικές σειρές του brief. Τα όρια
# μπαίνουν στο μέσο μεταξύ διαδοχικών anchors ώστε να αντέχουν τη φυσική
# διακύμανση πλάτους λέξης (π.χ. category/unit είναι πολυλεκτικά).
CATEGORY_X: tuple[float, float] = (30.0, 130.0)  # anchor 36.03
RANK_X: tuple[float, float] = (130.0, 185.0)  # anchor 135.24, OPTIONAL - λείπει νόμιμα σε 2/5 σειρές
UNIT_X: tuple[float, float] = (185.0, 300.0)  # anchor 189.10
YEARS_VALUE_X: tuple[float, float] = (300.0, 340.0)  # anchor c 307.5, center-aligned
YEARS_LABEL_X: tuple[float, float] = (340.0, 380.0)  # "Έτη" x0=343.11, ΑΠΟΡΡΙΠΤΕΤΑΙ με x-range
MONTHS_VALUE_X: tuple[float, float] = (380.0, 415.0)  # anchor c 392.56, center-aligned
# "Mήνες"/"Μήνες" x0=423.82 - στο πραγματικό PDF εμφανίζεται με ΛΑΤΙΝΙΚΟ M
# (U+004D), μικτό με το ελληνικό Μ (U+039C) που χρησιμοποιεί η υποενότητα β
# στο ΙΔΙΟ έγγραφο. ΑΠΟΡΡΙΠΤΕΤΑΙ αυστηρά με x-range, ΠΟΤΕ με σύγκριση
# κειμένου.
MONTHS_LABEL_X: tuple[float, float] = (415.0, 460.0)
DAYS_VALUE_X: tuple[float, float] = (460.0, 500.0)  # anchor c 477.6, center-aligned
DAYS_LABEL_X: tuple[float, float] = (500.0, 540.0)  # "Ημέρες" x0=507.20, ΑΠΟΡΡΙΠΤΕΤΑΙ με x-range


def _in_range(x0: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= x0 < bounds[1]


def _cluster_rows(words: list[WordTuple]) -> list[list[WordTuple]]:
    """Ομαδοποιεί λέξεις σε λογικές σειρές βάσει y0 (ανοχή ROW_Y_TOLERANCE).

    Κάθε ομάδα μετράει την ανοχή ως προς το ΕΛΑΧΙΣΤΟ y0 της (όχι transitively
    ως προς την προηγούμενη λέξη), ώστε άσχετες γειτονικές οπτικές γραμμές
    αλλού στη σελίδα (π.χ. πυκνά multi-line πεδία σε άλλες ενότητες) να μην
    αλυσιδώνονται σε μία τεχνητά μεγάλη ομάδα."""
    ordered = sorted(words, key=lambda w: w[1])
    rows: list[list[WordTuple]] = []
    for word in ordered:
        # rows[-1][0] είναι το ελάχιστο y0 της τρέχουσας ομάδας ΜΟΝΟ επειδή
        # το ordered είναι sorted κατά y0 παραπάνω - η σύγκριση προϋποθέτει
        # αυτό το sort.
        if rows and word[1] - rows[-1][0][1] <= ROW_Y_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def _row_to_entry(row: list[WordTuple]) -> ServiceTimeEntry | None:
    """Χτίζει μία ServiceTimeEntry από μία ομάδα λέξεων της ίδιας λογικής
    σειράς, αποκλειστικά βάσει x0 buckets.

    Επιστρέφει None αν λείπει category ή οποιαδήποτε από τις τρεις τιμές
    (years/months/days) - η ομάδα απορρίπτεται σιωπηλά ως μη-δεδομένα
    (π.χ. ο ίδιος ο header 'γ.', footer, ή άσχετο περιεχόμενο άλλης
    ενότητας στην ίδια σελίδα που τυχαίνει να μοιράζεται τις στήλες
    category/unit)."""
    category_words: list[tuple[float, str]] = []
    rank_words: list[tuple[float, str]] = []
    unit_words: list[tuple[float, str]] = []
    years_val = months_val = days_val = None

    for x0, _y0, _x1, _y1, text in row:
        stripped = text.strip()
        if not stripped:
            continue
        if _in_range(x0, CATEGORY_X):
            category_words.append((x0, stripped))
        elif _in_range(x0, RANK_X):
            rank_words.append((x0, stripped))
        elif _in_range(x0, UNIT_X):
            unit_words.append((x0, stripped))
        elif _in_range(x0, YEARS_VALUE_X) and stripped.isdigit():
            years_val = int(stripped)
        elif _in_range(x0, MONTHS_VALUE_X) and stripped.isdigit():
            months_val = int(stripped)
        elif _in_range(x0, DAYS_VALUE_X) and stripped.isdigit():
            days_val = int(stripped)
        # YEARS_LABEL_X / MONTHS_LABEL_X / DAYS_LABEL_X και οτιδήποτε άλλο
        # εκτός εύρους απορρίπτονται σιωπηλά εδώ - ετικέτες μονάδας
        # (Έτη/Μήνες/Ημέρες), όχι δεδομένα.

    if not category_words or years_val is None or months_val is None or days_val is None:
        return None

    category = " ".join(text for _, text in sorted(category_words))
    rank = " ".join(text for _, text in sorted(rank_words)) or None
    unit = " ".join(text for _, text in sorted(unit_words)) or None
    return ServiceTimeEntry(
        category=category, rank=rank, unit=unit, years=years_val, months=months_val, days=days_val
    )


def extract_duty_category_rows(words: list[WordTuple]) -> list[ServiceTimeEntry]:
    """Pure γεωμετρική εξαγωγή. Δέχεται ΗΔΗ scoped λίστα από PyMuPDF word
    tuples (x0, y0, x1, y1, text) - τις λέξεις της σελίδας που ακολουθεί
    αμέσως τον header 'γ.' (βλ. extract_duty_categories_from_pdf για το πώς
    επιλέγεται αυτή η σελίδα). Καμία εξάρτηση από fitz/PDF I/O εδώ - καθαρή
    συνάρτηση, testable με χειρόγραφα tuples χωρίς πραγματικό PDF.

    Fail-safe: καμία εξαίρεση δεν διαφεύγει, [] + logged warning σε κάθε
    αποτυχία επεξεργασίας."""
    try:
        filtered = [w for w in words if w[1] < FOOTER_Y]
        rows = _cluster_rows(filtered)
        entries: list[ServiceTimeEntry] = []
        for row in rows:
            entry = _row_to_entry(row)
            if entry is not None:
                entries.append(entry)
        return entries
    except Exception:
        logger.warning(
            "extract_duty_category_rows: αποτυχία επεξεργασίας, επιστροφή κενής λίστας",
            exc_info=True,
        )
        return []


def _find_header_page(doc: "fitz.Document") -> int | None:
    """Εντοπίζει τη σελίδα (0-indexed) που περιέχει τον header 'γ. Ανά
    Κατηγορία Καθήκοντος'. Η υποενότητα γ ξεκινά ΠΑΝΤΑ στην επόμενη σελίδα
    (μετρημένο: ο header είναι η τελευταία γραμμή περιεχομένου της σελίδας
    του, μηδέν σειρές δεδομένων από κάτω του στην ίδια σελίδα)."""
    for index in range(doc.page_count):
        words = doc[index].get_text("words")
        rows = _cluster_rows([(w[0], w[1], w[2], w[3], w[4]) for w in words if w[1] < FOOTER_Y])
        for row in rows:
            first_word = min(row, key=lambda w: w[0])
            if first_word[4].strip() == _SUBSECTION_C_MARKER and _in_range(first_word[0], CATEGORY_X):
                return index
    return None


def extract_duty_categories_from_pdf(pdf_path: Path) -> list[ServiceTimeEntry]:
    """Λεπτό wrapper γύρω από το extract_duty_category_rows: ανοίγει/κλείνει
    το PDF μόνο του με try/finally (ίδιο ownership pattern με
    app.ingestion.parser.parse_pdf - κανένα PyMuPDF page object δεν
    διαφεύγει αυτής της συνάρτησης), εντοπίζει τη σελίδα του header 'γ.' και
    περνάει τις λέξεις της ΕΠΟΜΕΝΗΣ σελίδας στην pure συνάρτηση.

    Fail-safe: καμία εξαίρεση δεν διαφεύγει (άνοιγμα PDF, ανάγνωση σελίδας),
    [] + logged warning. Επίσης [] αν δεν βρεθεί ο header, ή αν ο header
    είναι στην τελευταία σελίδα του PDF (καμία επόμενη σελίδα να διαβαστεί)."""
    try:
        doc = fitz.open(pdf_path)
        try:
            header_page = _find_header_page(doc)
            if header_page is None or header_page + 1 >= doc.page_count:
                return []
            words = doc[header_page + 1].get_text("words")
            word_tuples: list[WordTuple] = [(w[0], w[1], w[2], w[3], w[4]) for w in words]
        finally:
            doc.close()
    except Exception:
        logger.warning(
            "extract_duty_categories_from_pdf: αποτυχία ανοίγματος/ανάγνωσης PDF, "
            "επιστροφή κενής λίστας",
            exc_info=True,
        )
        return []
    return extract_duty_category_rows(word_tuples)
