"""Mini test για το KNOWN_SECTIONS (app/models/evaluation.py).

Κλειδώνει ότι κάθε section header του KNOWN_SECTIONS βρίσκεται αυτούσιο
μέσα στο πραγματικό κείμενο του PDF. Το section 5 γράφεται στο έγγραφο με
ΠΕΖΟ ήτα (U+03AE), όχι κεφαλαίο (U+0389): literal find() απέτυχε σιωπηλά
και το section δεν εντοπιζόταν ποτέ.

Τα headers γράφονται με ρητά \\uXXXX escapes στο κρίσιμο σημείο ώστε να
μην υπάρχει οπτική αμφιβολία ποιος χαρακτήρας ελέγχεται.

Εκτελείται standalone: `python tests/test_known_sections.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402

_GREEK_ETA_TONOS = "\u03ae"  # ή πεζό με τόνο - όπως στο πραγματικό PDF
_GREEK_ETA_CAPITAL_TONOS = "\u0389"  # Ή κεφαλαίο με τόνο - ΔΕΝ υπάρχει στο PDF

# Αυτούσιες (repr-verified) γραμμές επικεφαλίδων από το perilhptiko2018.pdf.
_REAL_HEADER_LINES = [
    "1. - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ",
    "2. - ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ",
    "3. - ΚΑΤΕΧΟΜΕΝΑ ΠΤΥΧΙΑ",
    "4. - ΤΟΠΟΘΕΤΗΣΕΙΣ",
    "5. - ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ " + _GREEK_ETA_TONOS
    + " ΜΗ ΓΙΑ ΠΡΟΑΓΩΓΗ ΚΑΤ' ΕΚΛΟΓΗΝ",
    "6. - ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΣΤΟΝ ΚΑΤΕΧΟΜΕΝΟ ΒΑΘΜΟ",
    "7. - ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ",
]

_FULL_TEXT = "\n\n".join(_REAL_HEADER_LINES)


def test_all_sections_found_in_real_text() -> None:
    missing = [s for s in KNOWN_SECTIONS if _FULL_TEXT.find(s) == -1]
    assert not missing, f"sections not found: {missing}"


def test_section_count() -> None:
    assert len(KNOWN_SECTIONS) == 7, len(KNOWN_SECTIONS)


def test_section_5_uses_lowercase_eta() -> None:
    section_5 = KNOWN_SECTIONS[4]
    assert _GREEK_ETA_TONOS in section_5, repr(section_5)
    assert _GREEK_ETA_CAPITAL_TONOS not in section_5, repr(section_5)


if __name__ == "__main__":
    test_all_sections_found_in_real_text()
    test_section_count()
    test_section_5_uses_lowercase_eta()
    print("OK - all KNOWN_SECTIONS tests passed")
