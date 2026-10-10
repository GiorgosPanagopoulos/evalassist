"""Tests for verify.py. Synthetic data only.

Run: PYTHONPATH=. python evals/spikes/extractive/test_verify.py
"""

import sys
import traceback
import unicodedata

from evals.spikes.extractive.verify import (
    Excerpt,
    locate_normalize,
    unique_displays,
    verify_quote,
)

PERIOD = "2001-01-01..2001-12-31"

# Greek letters used below, spelled out by codepoint.
GR_E = "\u0395"  # GREEK CAPITAL LETTER EPSILON
GR_E_TONOS = "\u0388"  # GREEK CAPITAL LETTER EPSILON WITH TONOS
COMB_ACUTE = "\u0301"  # COMBINING ACUTE ACCENT
LAT_E = "E"  # LATIN CAPITAL LETTER E
FINAL_SIGMA = "ς"
SIGMA = "Σ"

EXCELLENT = "ΕΞΑΙΡΕΤΟΣ (100)"
VERY_GOOD = "ΛΙΑΝ ΚΑΛΟΣ"


def cps(s: str) -> list[str]:
    return [f"U+{ord(c):04X}" for c in s]


def assert_greek_letters(s: str) -> None:
    for c in s:
        if c.isalpha():
            assert 0x0370 <= ord(c) <= 0x03FF, f"non-Greek letter {c!r} {cps(c)} in {s!r}"


def ex(body: str, period: str = PERIOD, doc_id: str = "DOC", page: int = 1) -> Excerpt:
    return Excerpt(body=body, period=period, doc_id=doc_id, page=page, section="SEC")


# --- codepoints of the test literals -------------------------------------


def test_codepoints_of_literals():
    assert_greek_letters(EXCELLENT)
    assert_greek_letters(VERY_GOOD)
    assert cps(EXCELLENT[:2]) == ["U+0395", "U+039E"]
    assert cps(GR_E) == ["U+0395"]
    assert cps(GR_E_TONOS) == ["U+0388"]
    assert cps(LAT_E) == ["U+0045"]
    assert unicodedata.normalize("NFD", GR_E_TONOS) == GR_E + COMB_ACUTE
    assert "ς".upper() == SIGMA and "ς" == FINAL_SIGMA


# --- positive ------------------------------------------------------------


def test_exact_quote():
    r = verify_quote(1, EXCELLENT, [ex(f"ΧΑΡΑΚΤΗΡΙΣΜΟΣ: {EXCELLENT}")])
    assert r.verified and r.reason is None
    assert r.quote_text == EXCELLENT


def test_accent_case_whitespace_variation():
    body = "ΒΑΘΜΟΣ:   ΛΙΑΝ\n  ΚΑΛΟΣ\nΤΕΛΟΣ"
    quote = "λίαν καλός"
    assert cps(quote)[1] == "U+03AF"  # iota with tonos
    assert quote[-1] == FINAL_SIGMA
    r = verify_quote(1, quote, [ex(body)])
    assert r.verified, r
    assert r.quote_text == "ΛΙΑΝ\n  ΚΑΛΟΣ"  # chunk characters, not the quote's


def test_precomposed_quote_vs_decomposed_body():
    body = GR_E + COMB_ACUTE + "ΤΟΣ 2001"
    quote = GR_E_TONOS + "τος 2001"
    assert cps(body[:2]) == ["U+0395", "U+0301"]
    assert cps(quote[:1]) == ["U+0388"]
    r = verify_quote(1, quote, [ex(body)])
    assert r.verified, r
    assert r.quote_text == body  # combining mark kept in quote_text


def test_latin_homoglyph_in_quote():
    quote = LAT_E + EXCELLENT[1:]
    assert cps(quote[:1]) == ["U+0045"]
    assert_greek_letters(quote[1:])
    r = verify_quote(1, quote, [ex(EXCELLENT)])
    assert r.verified, r
    assert r.quote_text == EXCELLENT
    assert cps(r.quote_text[:1]) == ["U+0395"]


def test_latin_homoglyph_in_body():
    body = LAT_E + EXCELLENT[1:]
    r = verify_quote(1, EXCELLENT, [ex(body)])
    assert r.verified, r
    assert cps(r.quote_text[:1]) == ["U+0045"]


def test_short_two_word_quote():
    r = verify_quote(1, VERY_GOOD, [ex(f"ΧΑΡΑΚΤΗΡΙΣΜΟΣ: {VERY_GOOD}\nΑΛΛΟ")])
    assert r.verified, r
    assert r.quote_text == VERY_GOOD


def test_word_inside_phrase_on_boundary_passes():
    r = verify_quote(1, "ΚΑΛΟΣ", [ex(VERY_GOOD)])
    assert r.verified, r


def test_one_to_many_upper_mapping():
    # upper() can change length; the map must still give the original span.
    r = verify_quote(1, "STRASSE", [ex("X STRAßE Y")])
    assert r.verified, r
    assert r.quote_text == "STRAßE"


def test_quote_surrounding_spaces_stripped():
    r = verify_quote(1, "  ΛΙΑΝ ΚΑΛΟΣ \n", [ex(VERY_GOOD)])
    assert r.verified, r


def test_date_exact_passes():
    r = verify_quote(1, "05/07/2005", [ex("ΗΜΕΡΟΜΗΝΙΑ 05/07/2005")])
    assert r.verified, r


# --- negative ------------------------------------------------------------


def test_text_not_present():
    r = verify_quote(1, "ΜΕΤΡΙΟΣ", [ex(EXCELLENT)])
    assert not r.verified and r.reason == "not_found"
    assert r.quote_text is None and r.displays == []


def test_text_in_other_excerpt():
    excerpts = [ex(EXCELLENT), ex(VERY_GOOD)]
    r = verify_quote(1, VERY_GOOD, excerpts)
    assert not r.verified and r.reason == "wrong_excerpt"
    assert r.found_in == [2]


def test_quote_from_header():
    # The body handed to verify has no headers (section 2.1).
    raw = f"[ΕΝΟΤΗΤΑ: ΤΟΠΟΘΕΤΗΣΕΙΣ]\n\n{EXCELLENT}"
    body = raw.split("\n\n", 1)[1]
    for quote in ("ΤΟΠΟΘΕΤΗΣΕΙΣ", "[ΕΝΟΤΗΤΑ: ΤΟΠΟΘΕΤΗΣΕΙΣ]", "ΕΝΟΤΗΤΑ"):
        r = verify_quote(1, quote, [ex(body)])
        assert not r.verified and r.reason == "not_found", (quote, r)


def test_half_word():
    r = verify_quote(1, "ΑΛΟΣ", [ex(VERY_GOOD)])
    assert not r.verified and r.reason == "partial_token"
    r = verify_quote(1, "ΟΣ (100)", [ex(EXCELLENT)])
    assert not r.verified and r.reason == "partial_token"
    r = verify_quote(1, "ΛΙΑΝ ΚΑΛ", [ex(VERY_GOOD)])
    assert not r.verified and r.reason == "partial_token"


def test_digit_inside_number():
    r = verify_quote(1, "10", [ex(EXCELLENT)])
    assert not r.verified and r.reason == "partial_token", r
    r = verify_quote(1, "9", [ex("ΒΑΘΜΟΣ 93")])
    assert not r.verified and r.reason == "partial_token", r


def test_negation_on_previous_line_is_displayed():
    # Whole-body display keeps a negation that ends the previous line.
    body = "ΓΝΩΜΗ ΑΞΙΟΛΟΓΗΤΗ: ΔΕΝ\nΣΥΝΙΣΤΑΤΑΙ ΓΙΑ ΠΡΟΑΓΩΓΗ\nΤΕΛΟΣ"
    r = verify_quote(1, "ΣΥΝΙΣΤΑΤΑΙ ΓΙΑ ΠΡΟΑΓΩΓΗ", [ex(body)])
    assert r.verified, r
    [d] = r.displays
    assert d.display_text == body and "ΔΕΝ" in d.display_text
    assert r.quote_text == "ΣΥΝΙΣΤΑΤΑΙ ΓΙΑ ΠΡΟΑΓΩΓΗ"  # the selection still omits it


def test_known_limit_integer_part_of_decimal():
    # KNOWN LIMITATION, documented, not fixed: "," is not alnum, so "93"
    # passes the token boundary inside "93,5".
    body = "ΒΑΘΜΟΣ 93,5\nΑΛΛΟ"
    r = verify_quote(1, "93", [ex(body)])
    assert r.verified, r
    assert r.quote_text == "93"
    assert [d.display_text for d in r.displays] == [body]
    assert r.displays[0].highlights == [(7, 9)]


def test_empty_and_symbol_only_quote():
    for quote in ("", "   ", "\n", "-", "( )", "/"):
        r = verify_quote(1, quote, [ex("- ( ) / Χ")])
        assert not r.verified and r.reason == "no_alnum", (quote, r)


def test_excerpt_index_out_of_range():
    excerpts = [ex(EXCELLENT), ex(VERY_GOOD)]
    for n in (0, -1, 3, 99):
        r = verify_quote(n, EXCELLENT, excerpts)
        assert not r.verified and r.reason == "bad_excerpt_index", (n, r)


def test_excerpt_index_wrong_type_raises():
    for n in ("1", 1.0, True, None):
        try:
            verify_quote(n, EXCELLENT, [ex(EXCELLENT)])
        except TypeError:
            continue
        raise AssertionError(f"no TypeError for {n!r}")


def test_date_with_changed_separator():
    body = "ΗΜΕΡΟΜΗΝΙΑ 05/07/2005\nΑΠΟΦΑΣΗ (18/27-3-08)"
    for quote in ("05.07.2005", "05-07-2005", "05072005", "18.27-3-08", "18/27/3/08"):
        r = verify_quote(1, quote, [ex(body)])
        assert not r.verified and r.reason == "not_found", (quote, r)


def test_dash_variants_not_normalized():
    body = "4 Α - 2 ΔΑΒ"
    assert cps(body[4]) == ["U+002D"]
    for quote in ("4 Α \u2013 2 ΔΑΒ", "4 Α \u2014 2 ΔΑΒ"):
        r = verify_quote(1, quote, [ex(body)])
        assert not r.verified and r.reason == "not_found", (quote, r)


def test_wrapping_quotes_and_ellipsis_rejected():
    for quote in (f"«{VERY_GOOD}»", f'"{VERY_GOOD}"', "ΛΙΑΝ ... ΚΑΛΟΣ", "ΛΙΑΝ\u2026"):
        r = verify_quote(1, quote, [ex(VERY_GOOD)])
        assert not r.verified and r.reason == "not_found", (quote, r)


def test_hyphenation_join_rejected_but_space_passes():
    body = "ΓΙΑ ΤΟ ΕΤΟΣ 2019-\n2020"
    r = verify_quote(1, "2019-2020", [ex(body)])
    assert not r.verified and r.reason == "not_found"
    r = verify_quote(1, "2019- 2020", [ex(body)])
    assert r.verified, r
    assert r.displays[0].display_text == body  # match spans two lines


# --- display -------------------------------------------------------------


def test_display_text_is_whole_body_not_quote():
    body = f"ΑΛΛΗ ΓΡΑΜΜΗ\nΧΑΡΑΚΤΗΡΙΣΜΟΣ: {EXCELLENT}\nΤΕΛΟΣ"
    quote = "εξαίρετος (100)"
    r = verify_quote(1, quote, [ex(body)])
    assert r.verified, r
    [d] = r.displays
    assert d.display_text == body
    assert d.display_text != quote and quote not in d.display_text
    assert d.period == PERIOD and d.doc_id == "DOC" and d.page == 1
    [(s, e)] = d.highlights
    assert d.display_text[s:e] == r.quote_text == EXCELLENT


def test_display_is_whole_body_for_any_period():
    body = "ΣΗΜΑΙΟΦΟΡΟΣ\n01/01/2001\n4 Α - 2 ΔΑΒ\n02/02/2001"
    for period in ("career", PERIOD):
        r = verify_quote(1, "4 Α - 2 ΔΑΒ", [ex(body, period=period)])
        assert r.verified, r
        [d] = r.displays
        assert d.display_text == body and d.period == period
        [(s, e)] = d.highlights
        assert d.display_text[s:e] == "4 Α - 2 ΔΑΒ"


def test_all_match_positions_returned():
    body = f"2001: {EXCELLENT}\n2002: {EXCELLENT}\n2003: {EXCELLENT}"
    r = verify_quote(1, EXCELLENT, [ex(body)])
    assert r.verified, r
    assert len(r.positions) == 3
    assert [body[s:e] for s, e in r.positions] == [EXCELLENT] * 3
    [d] = r.displays
    assert d.display_text == body
    assert d.highlights == r.positions
    assert [d.display_text[s:e] for s, e in d.highlights] == [EXCELLENT] * 3


def test_positions_on_same_line_all_highlighted():
    body = "ΚΑΛΟΣ ΚΑΙ ΚΑΛΟΣ\nΑΛΛΟ"
    r = verify_quote(1, "ΚΑΛΟΣ", [ex(body)])
    [d] = r.displays
    assert d.display_text == body and d.highlights == [(0, 5), (10, 15)]


def test_invalid_boundary_positions_skipped():
    body = "ΚΑΚΑΛΟΣ\nΚΑΛΟΣ"
    r = verify_quote(1, "ΚΑΛΟΣ", [ex(body)])
    assert r.verified and r.positions == [(8, 13)]
    assert r.displays[0].display_text == body
    assert r.displays[0].highlights == [(8, 13)]


def test_unique_displays_merge_highlights():
    body = f"Α: {VERY_GOOD}\nΒ"
    excerpts = [ex(body), ex(body, page=2)]
    r1 = verify_quote(1, VERY_GOOD, excerpts)
    r2 = verify_quote(1, "ΚΑΛΟΣ", excerpts)
    r3 = verify_quote(1, VERY_GOOD, excerpts)
    r4 = verify_quote(2, "ΛΙΑΝ", excerpts)
    displays = unique_displays([r1, r2, r3, r4])
    assert [(d.page, d.highlights) for d in displays] == [(1, [(3, 13), (8, 13)]), (2, [(3, 7)])]


def test_normalizer_keeps_punctuation():
    assert locate_normalize("Ε.Α. 05/07") == "Ε.Α. 05/07"
    assert locate_normalize("ά\tβ\u00a0\u2009γ") == "Α Β Γ"


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
