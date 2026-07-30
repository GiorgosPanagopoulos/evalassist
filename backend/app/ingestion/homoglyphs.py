"""Κανονικοποίηση ελληνικών ομογράφων (homoglyphs) στο κείμενο chunks, πριν
την αποθήκευση στη ChromaDB.

Πλαίσιο: το πραγματικό PDF περιέχει tokens όπου κάποιοι ελληνικοί χαρακτήρες
έχουν αντικατασταθεί από τα οπτικά ταυτόσημα λατινικά τους (π.χ. "EΞΑΙΡΕΤΟΣ"
με λατινικό "E") λόγω font substitution στο σύστημα που παρήγαγε το αρχείο.
Χωρίς κανονικοποίηση, το structured path (extractor.py, που ήδη κάνει αυτή
την αντιστοίχιση σε ΕΝΑ σημείο - βλ. _parse_characterization_token) και το
semantic path (κείμενο chunk στο Chroma) βλέπουν διαφορετικές μορφές του
ίδιου δεδομένου.

Ο πίνακας μετάφρασης LATIN_TO_GREEK_UPPER ζει εδώ ως single source of truth·
το extractor.py τον κάνει import (βλ. εκεί για το _LATIN_TO_GREEK_UPPER alias,
backward compat).

Καθαρό module: μόνο stdlib (re + logging), καμία εξάρτηση από άλλα modules
του ingestion.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Ίδιος πίνακας με το (πρώην) extractor._LATIN_TO_GREEK_UPPER - μόνο κεφαλαία,
# μόνο τα λατινικά γράμματα που έχουν οπτικά ταυτόσημο ελληνικό αντίστοιχο.
LATIN_TO_GREEK_UPPER = str.maketrans(
    {
        "A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ",
        "M": "Μ", "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "Y": "Υ", "X": "Χ",
    }
)

_WHITESPACE_RE = re.compile(r"(\s+)")

_LATIN_MIN, _LATIN_MAX = 0x41, 0x7A
_GREEK_MIN, _GREEK_MAX = 0x370, 0x3FF


def _has_latin(token: str) -> bool:
    return any(_LATIN_MIN <= ord(ch) <= _LATIN_MAX for ch in token)


def _greek_count(token: str) -> int:
    return sum(1 for ch in token if _GREEK_MIN <= ord(ch) <= _GREEK_MAX)


def _normalize_token(token: str) -> str:
    if not token or not _has_latin(token):
        return token
    greek_count = _greek_count(token)
    if greek_count == 0:
        return token
    # όρος 3: γνήσια πλειοψηφία ελληνικών χαρακτήρων ΚΑΙ αμιγώς αλφαβητικό
    # token - προστατεύει νόμιμα mixed tokens (κωδικοί μονάδων, ημερομηνίες
    # σήματος) που περιέχουν ψηφία, κάθετο ή παρενθέσεις.
    if not (token.isalpha() and greek_count * 2 > len(token)):
        return token
    return token.translate(LATIN_TO_GREEK_UPPER)


def normalize_greek_homoglyphs(text: str) -> str:
    """Αντικαθιστά, ανά token (whitespace-split, με διατήρηση της αρχικής
    μορφοποίησης), τους λατινικούς χαρακτήρες που είναι στην πραγματικότητα
    ελληνικοί (font substitution) με το ελληνικό τους αντίστοιχο.

    Normalize μόνο αν, για το token: (1) περιέχει τουλάχιστον έναν λατινικό
    χαρακτήρα, (2) περιέχει τουλάχιστον έναν ελληνικό χαρακτήρα, (3) είναι
    αμιγώς αλφαβητικό ΚΑΙ οι ελληνικοί χαρακτήρες αποτελούν γνήσια πλειοψηφία.
    Αλλιώς το token επιστρέφεται αυτούσιο.

    Idempotent: δεύτερη εφαρμογή πάνω στο αποτέλεσμα δεν αλλάζει τίποτα.

    Σε οποιοδήποτε σφάλμα επιστρέφεται το text αυτούσιο, με καταγραφή -
    καμία σιωπηλή αποτυχία σε σύστημα με audit trail (βλ. αντίστοιχο pattern
    στο form_markers.annotate_empty_section5_subfields)."""
    try:
        return _normalize(text)
    except Exception:
        logger.warning(
            "normalize_greek_homoglyphs: αποτυχία επεξεργασίας, επιστροφή text αυτούσιο",
            exc_info=True,
        )
        return text


def _normalize(text: str) -> str:
    parts = _WHITESPACE_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _normalize_token(parts[i])
    return "".join(parts)
