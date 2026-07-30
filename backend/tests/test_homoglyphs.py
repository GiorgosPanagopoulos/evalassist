"""Mini test/sample flow για το backend/app/ingestion/homoglyphs.py
(κανονικοποίηση ελληνικών ομογράφων στο κείμενο chunks).

Τα ελληνικά string literals που περιέχουν τους υπό εξέταση χαρακτήρες
(λατινικό εναντίον ελληνικού Ε και Μ) γράφονται με ρητά \\uXXXX escapes,
ώστε να μην υπάρχει καμία οπτική αμφιβολία ποιος χαρακτήρας ελέγχεται.

Εκτελείται standalone: `python tests/test_homoglyphs.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.homoglyphs import (  # noqa: E402
    LATIN_TO_GREEK_UPPER,
    normalize_greek_homoglyphs,
)

# Ρητά codepoints για τους χαρακτήρες που κρίνονται - καμία αμφιβολία ποιο
# γράμμα (λατινικό ή ελληνικό) υπάρχει σε κάθε literal παρακάτω.
_LATIN_E = "E"  # E λατινικό
_GREEK_EPSILON = "Ε"  # Ε ελληνικό κεφαλαίο έψιλον
_LATIN_M = "M"  # M λατινικό
_GREEK_MU = "Μ"  # Μ ελληνικό κεφαλαίο μυ
_LATIN_I = "I"  # I λατινικό
_GREEK_IOTA = "Ι"  # Ι ελληνικό κεφαλαίο γιώτα
_LATIN_P = "P"  # P λατινικό
_GREEK_RHO = "Ρ"  # Ρ ελληνικό κεφαλαίο ρω

# --- 4 πραγματικά προβληματικά tokens (μία διαφορετική corrupted θέση το
# καθένα, γνήσια πλειοψηφία ελληνικών χαρακτήρων ώστε να περνούν τον όρο 3) ---

# "EΞΑΙΡΕΤΟΣ" με λατινικό "E" (το ίδιο παράδειγμα με το σχόλιο στο extractor.py)
_TOKEN_EXAIRETOS_BROKEN = _LATIN_E + "ΞΑΙΡΕΤΟΣ"
_TOKEN_EXAIRETOS_FIXED = _GREEK_EPSILON + "ΞΑΙΡΕΤΟΣ"

# "ΛΙΑΝ" με λατινικό "I"
_TOKEN_LIAN_BROKEN = "Λ" + _LATIN_I + "ΑΝ"
_TOKEN_LIAN_FIXED = "Λ" + _GREEK_IOTA + "ΑΝ"

# "ΜΕΤΡΙΟΣ" με λατινικό "M"
_TOKEN_METRIOS_BROKEN = _LATIN_M + "ΕΤΡΙΟΣ"
_TOKEN_METRIOS_FIXED = _GREEK_MU + "ΕΤΡΙΟΣ"

# "ΧΑΡΑΚΤΗΡΙΣΜΟΣ" με λατινικό "P" (αντί για Ρ)
_TOKEN_XARAKTIRISMOS_BROKEN = "ΧΑ" + _LATIN_P + "ΑΚΤΗΡΙΣΜΟΣ"
_TOKEN_XARAKTIRISMOS_FIXED = "ΧΑ" + _GREEK_RHO + "ΑΚΤΗΡΙΣΜΟΣ"

# --- 3 νόμιμα mixed tokens (κωδικός μονάδας / ημερομηνία σήματος): περιέχουν
# λατινικό ΚΑΙ ελληνικό χαρακτήρα, αλλά ψηφίο/κάθετο/παρένθεση -> isalpha()
# False -> ο όρος 3 αποτρέπει το normalize. ---

# κωδικός μονάδας με ψηφία
_UNIT_CODE_WITH_DIGITS = _LATIN_M + "Τ105"  # π.χ. "MΤ105"
# ημερομηνία σήματος με κάθετο
_SIGNAL_DATE_WITH_SLASH = _LATIN_E + "Ξ/19"  # π.χ. "EΞ/19"
# συντομογραφία με παρενθέσεις
_ABBREVIATION_WITH_PARENS = "(" + _LATIN_E + "Ξ)"  # π.χ. "(EΞ)"


def test_codepoints_are_the_expected_latin_and_greek_letters():
    assert ord(_LATIN_E) == 0x45
    assert ord(_GREEK_EPSILON) == 0x395
    assert ord(_LATIN_M) == 0x4D
    assert ord(_GREEK_MU) == 0x39C


def test_exairetos_broken_normalizes():
    assert normalize_greek_homoglyphs(_TOKEN_EXAIRETOS_BROKEN) == _TOKEN_EXAIRETOS_FIXED


def test_lian_broken_normalizes():
    assert normalize_greek_homoglyphs(_TOKEN_LIAN_BROKEN) == _TOKEN_LIAN_FIXED


def test_metrios_broken_normalizes():
    assert normalize_greek_homoglyphs(_TOKEN_METRIOS_BROKEN) == _TOKEN_METRIOS_FIXED


def test_xaraktirismos_broken_normalizes():
    assert normalize_greek_homoglyphs(_TOKEN_XARAKTIRISMOS_BROKEN) == _TOKEN_XARAKTIRISMOS_FIXED


def test_unit_code_with_digits_untouched():
    assert normalize_greek_homoglyphs(_UNIT_CODE_WITH_DIGITS) == _UNIT_CODE_WITH_DIGITS


def test_signal_date_with_slash_untouched():
    assert normalize_greek_homoglyphs(_SIGNAL_DATE_WITH_SLASH) == _SIGNAL_DATE_WITH_SLASH


def test_abbreviation_with_parens_untouched():
    assert normalize_greek_homoglyphs(_ABBREVIATION_WITH_PARENS) == _ABBREVIATION_WITH_PARENS


def test_idempotency_second_pass_does_not_change_result():
    once = normalize_greek_homoglyphs(_TOKEN_EXAIRETOS_BROKEN)
    twice = normalize_greek_homoglyphs(once)
    assert once == twice
    assert twice == _TOKEN_EXAIRETOS_FIXED


def test_idempotency_on_untouched_mixed_tokens():
    once = normalize_greek_homoglyphs(_UNIT_CODE_WITH_DIGITS)
    twice = normalize_greek_homoglyphs(once)
    assert once == twice


def test_pure_greek_text_unchanged():
    text = "Ο ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΤΗΣΕ ΜΕ ΖΗΛΟ."
    assert normalize_greek_homoglyphs(text) == text


def test_pure_latin_text_unchanged():
    text = "The evaluation report was filed on time."
    assert normalize_greek_homoglyphs(text) == text


def test_whitespace_and_newlines_preserved_exactly():
    text = (
        "Α.Γ.Μ.:\t"
        + _TOKEN_EXAIRETOS_BROKEN
        + "\n\n  "
        + _TOKEN_METRIOS_BROKEN
        + "  \n"
    )
    expected = (
        "Α.Γ.Μ.:\t"
        + _TOKEN_EXAIRETOS_FIXED
        + "\n\n  "
        + _TOKEN_METRIOS_FIXED
        + "  \n"
    )
    assert normalize_greek_homoglyphs(text) == expected


def test_translation_table_covers_expected_letters():
    # str.maketrans μετατρέπει τα keys σε ordinals - το table είναι int -> str
    assert LATIN_TO_GREEK_UPPER[ord(_LATIN_E)] == _GREEK_EPSILON
    assert LATIN_TO_GREEK_UPPER[ord(_LATIN_M)] == _GREEK_MU
    assert _TOKEN_EXAIRETOS_BROKEN.translate(LATIN_TO_GREEK_UPPER) == _TOKEN_EXAIRETOS_FIXED


def run_all():
    tests = [
        test_codepoints_are_the_expected_latin_and_greek_letters,
        test_exairetos_broken_normalizes,
        test_lian_broken_normalizes,
        test_metrios_broken_normalizes,
        test_xaraktirismos_broken_normalizes,
        test_unit_code_with_digits_untouched,
        test_signal_date_with_slash_untouched,
        test_abbreviation_with_parens_untouched,
        test_idempotency_second_pass_does_not_change_result,
        test_idempotency_on_untouched_mixed_tokens,
        test_pure_greek_text_unchanged,
        test_pure_latin_text_unchanged,
        test_whitespace_and_newlines_preserved_exactly,
        test_translation_table_covers_expected_letters,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
