"""Mini test/sample flow για τον extractor (Περιληπτικό Σημείωμα).

Καλύπτει, σε ΣΥΝΘΕΤΙΚΟ κείμενο (καμία σχέση με πραγματικά δεδομένα):
  - A1: whitespace-tolerant label matching (κενά πριν το ":" και γύρω από "/").
  - A4: dual-format Ενότητα 7 — fallback θεσιακός (positional) parser για
    layout χωρίς labels (bare "Ε.Α."/"Σ.Α." anchors, όπως σε πραγματικά PDF).
  - A5: sections 1-5 χωρίς "|" — ομαδοποίηση διαδοχικών "label: value" γραμμών.

Εκτελείται standalone (χωρίς pytest): `python tests/test_extractor.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.extractor import (  # noqa: E402
    _field,
    _iter_pipe_rows,
    _parse_evaluation_entry_positional,
)


def test_field_matches_whitespace_before_colon():
    # Πραγματικό PDF: "Α.Γ.Μ. :" (κενό πριν το ":"), όχι "Α.Γ.Μ.:" όπως στο
    # synthetic corpus.
    text = "Α.Γ.Μ. :\nΜ-99999\n"
    assert _field(text, "Α.Γ.Μ.") == "Μ-99999"


def test_field_matches_whitespace_around_slash_in_composite_label():
    # Πραγματικό PDF: "Όπλο / Σώμα:" (κενά γύρω από "/"), το lookup γίνεται με
    # το synthetic-style label "Όπλο/Σώμα" (χωρίς κενά).
    text = "Όπλο / Σώμα:\nΜΗΧΑΝΙΚΟΣ / 05 (Σ.Ν.Δ)\n"
    assert _field(text, "Όπλο/Σώμα") == "ΜΗΧΑΝΙΚΟΣ / 05 (Σ.Ν.Δ)"


def test_iter_pipe_rows_without_pipe_groups_consecutive_label_value_lines():
    # Fallback χωρίς "|": κάθε πεδίο πίνακα σε ξεχωριστή γραμμή αντί για μία
    # γραμμή "label: value | label: value | ...".
    text = (
        "Βαθμός: ΥΠΟΠΛΟΙΑΡΧΟΣ\n"
        "Ημ/νία Απόφασης: 01/03/2020\n"
        "Απόφαση: Προακτέος\n"
        "Ημ/νία Προαγωγής: 15/03/2020\n"
        "\n"
        "Βαθμός: ΣΗΜΑΙΟΦΟΡΟΣ\n"
        "Ημ/νία Απόφασης: 01/03/2018\n"
    )

    rows = _iter_pipe_rows(text, "Βαθμός")

    assert len(rows) == 2, f"αναμένονταν 2 rows, βρέθηκαν {len(rows)}"
    assert rows[0]["Βαθμός"] == "ΥΠΟΠΛΟΙΑΡΧΟΣ"
    assert rows[0]["Απόφαση"] == "Προακτέος"
    assert rows[0]["Ημ/νία Προαγωγής"] == "15/03/2020"
    assert rows[1]["Βαθμός"] == "ΣΗΜΑΙΟΦΟΡΟΣ"
    assert "Απόφαση" not in rows[1]


def test_positional_parser_extracts_entry_from_anchor_based_layout():
    # Μιμείται το πραγματικό layout (βλ. debug dump πάνω στο ιδιωτικό PDF,
    # ΟΧΙ tracked): bare "Ε.Α." anchor, μετά ημερομηνία/"-"/ημερομηνία, μετά
    # "ΧΑΡΑΚΤΗΡΙΣΜΟΣ (βαθμός)" σε μία γραμμή (με λατινικό "E" — font
    # substitution σε πραγματικά PDF), μετά μονάδα/ρόλος χωρίς labels, μετά
    # "Αξιολογών:" + rank/name/role σε μία γραμμή, μετά bare ΠΕΔΙΟ κωδικοί.
    block_text = (
        "Ε.Α.\n"
        "01/01/2020\n-\n31/12/2020\n"
        "EΞΑΙΡΕΤΟΣ (97)\n"
        "ΣΥΝΘΕΤΙΚΗ ΜΟΝΑΔΑ\n-\nΚΥΒΕΡΝΗΤΗΣ\n"
        "180\n\n"
        "Αξιολογών:\nΠΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΔΙΟΙΚΗΤΗΣ\n\n"
        "141\nΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΓΙΑ ΤΟΝ ΚΑΤΕΧΟΜΕΝΟ ΒΑΘΜΟ\n95\n"
    )

    entry = _parse_evaluation_entry_positional("Ε.Α.", block_text, page=4)

    assert entry is not None
    assert entry.period_start.isoformat() == "2020-01-01"
    assert entry.period_end.isoformat() == "2020-12-31"
    assert entry.characterization == "ΕΞΑΙΡΕΤΟΣ", "λατινικό 'E' πρέπει να κανονικοποιηθεί σε ελληνικό 'Ε'"
    assert entry.score == 97
    assert entry.ea_type == "Ε.Α."
    assert entry.unit == "ΣΥΝΘΕΤΙΚΗ ΜΟΝΑΔΑ"
    assert entry.evaluator.rank == "ΠΧΟΣ"
    assert entry.evaluator.name == "ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ"
    assert entry.evaluator.role == "ΔΙΟΙΚΗΤΗΣ"
    assert entry.source_page == 4
    assert len(entry.field_scores) == 1
    assert entry.field_scores[0].field_code == "141"
    assert entry.field_scores[0].value == 95


def test_positional_parser_treats_bare_du_as_unit_not_characterization():
    # "ΔΥ" = "Διοίκηση Υποβρυχίων", ΜΟΝΑΔΑ, όχι χαρακτηρισμός (βλ.
    # private/prompts/B2_CHARACTERIZATION_FIX.md). Πραγματικά Σ.Α. blocks δεν
    # έχουν καθόλου γραμμή χαρακτηρισμού — bare "ΔΥ" μετά τις ημερομηνίες
    # είναι ήδη η μονάδα. Ο lookahead στο _parse_evaluation_entry_positional
    # δεν πρέπει να το καταναλώσει ως χαρακτηρισμό.
    block_text = (
        "Σ.Α.\n"
        "01/01/2019\n-\n10/01/2019\n"
        "ΔΥ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=4)

    assert entry is not None
    # MUTATION CHECK: αν ο lookahead αντιστραφεί σε unconditional consume
    # (παλιά συμπεριφορά), το "ΔΥ" θα καταναλωθεί ως characterization και
    # αυτό το assert θα σκάσει.
    assert entry.characterization is None, "'ΔΥ' είναι μονάδα, ΔΕΝ πρέπει να γίνει characterization"
    assert entry.score is None
    assert entry.unit == "ΔΥ"
    assert entry.ea_type == "Σ.Α."


def test_positional_parser_sa_with_unrecognized_token_accepted_as_unit():
    # Η απουσία χαρακτηρισμού επιτρέπεται ΜΟΝΟ για Σ.Α. (βλ.
    # private/prompts/B2_CHARACTERIZATION_FIX.md, Ε1) — 4/4 Σ.Α. blocks του
    # πραγματικού PDF δεν έχουν καθόλου γραμμή χαρακτηρισμού, άρα οποιοδήποτε
    # μη αναγνωρισμένο token εκεί είναι ήδη η μονάδα, ΟΧΙ επινοημένος
    # χαρακτηρισμός.
    block_text = (
        "Σ.Α.\n"
        "01/01/2019\n-\n10/01/2019\n"
        "ΑΓΝΩΣΤΟΣ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=4)

    assert entry is not None, "Σ.Α. χωρίς γνωστό χαρακτηρισμό δεν πρέπει να απορρίπτεται"
    # MUTATION CHECK: αν το `elif ea_type == "Ε.Α.":` guard αφαιρεθεί/αντιστραφεί
    # ώστε να ισχύει και για Σ.Α., η εγγραφή θα απορριφθεί (None) και αυτό θα σκάσει.
    assert entry.characterization is None
    assert entry.score is None
    assert entry.unit == "ΑΓΝΩΣΤΟΣ"


def test_positional_parser_ea_with_unrecognized_token_rejected():
    # Αντίθετα από Σ.Α., ΟΛΑ τα Ε.Α. blocks του πραγματικού PDF (32/32,
    # μετρημένο) ΕΧΟΥΝ γραμμή χαρακτηρισμού. Ένα μη αναγνωρισμένο token εκεί
    # είναι αλλοιωμένο/άγνωστο (OCR, ομόγραφο, τυπογραφικό) — αν γινόταν
    # δεκτό ως μονάδα θα μετατόπιζε σιωπηλά την πραγματική μονάδα προς
    # απώλεια (σιωπηλή παραμόρφωση). Η εγγραφή απορρίπτεται εξ ολοκλήρου.
    block_text = (
        "Ε.Α.\n"
        "01/01/2019\n-\n10/01/2019\n"
        "ΑΓΝΩΣΤΟΣ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Ε.Α.", block_text, page=4)

    # MUTATION CHECK: αν το `elif ea_type == "Ε.Α.":` guard αφαιρεθεί ώστε το
    # lookahead να δέχεται ΟΠΟΙΟΔΗΠΟΤΕ ea_type (παλιά υπερ-γενικευμένη
    # συμπεριφορά), αυτό το assert θα σκάσει (entry δεν θα είναι None).
    assert entry is None, "Ε.Α. με μη αναγνωρισμένο χαρακτηρισμό πρέπει να απορρίπτεται, ΟΧΙ να γίνεται μονάδα"


def test_positional_parser_still_rejects_invalid_period():
    # ΕΞΑΙΡΕΣΗ (private/prompts/B2_CHARACTERIZATION_FIX.md): το `return None`
    # για μη έγκυρη περίοδο ΔΕΝ αλλάζει με αυτό το fix — παραμένει η μόνη
    # περίπτωση όπου η θεσιακή εγγραφή απορρίπτεται εξ ολοκλήρου.
    block_text = (
        "Σ.Α.\n"
        "ΟΧΙ-ΗΜΕΡΟΜΗΝΙΑ\n-\n10/01/2019\n"
        "ΔΥ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=4)

    assert entry is None


def test_positional_parser_real_block_28_ke_palaskas():
    # Πραγματικό block #28 από το ιδιωτικό δείγμα PDF (ΟΧΙ tracked, βλ.
    # private/debug_raw_pages.txt γραμμές 1225-1233): Σ.Α. περίοδος χωρίς
    # γραμμή χαρακτηρισμού, μονάδα "ΚΕ ΠΑΛΑΣΚΑΣ" στη θέση [4]. Πριν το fix
    # αυτό το block απορριπτόταν σιωπηλά.
    block_text = (
        "Σ.Α.\n"
        "01/01/2009\n-\n09/04/2009\n"
        "ΚΕ ΠΑΛΑΣΚΑΣ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ (Μ) ΕΥΑΓΓΕΛΟΣ ΚΟΡΩΝΑΚΗΣ - ΔΙΕΥΘΥΝΤΗΣ ΣΠΟΥΔΩΝ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=7)

    assert entry is not None
    assert entry.period_start.isoformat() == "2009-01-01"
    assert entry.period_end.isoformat() == "2009-04-09"
    assert entry.characterization is None
    assert entry.score is None
    assert entry.unit == "ΚΕ ΠΑΛΑΣΚΑΣ"
    # Codepoint assertions: ελληνικά κεφαλαία (U+0391-U+03A9), ΟΧΙ λατινικά
    # ομόγραφα (π.χ. Latin "K" U+004B / "E" U+0045 αντί Greek "Κ" U+039A /
    # "Ε" U+0395).
    assert ord(entry.unit[0]) == 0x039A, "'Κ' πρέπει να είναι Greek Kappa U+039A"
    assert ord(entry.unit[1]) == 0x0395, "'Ε' πρέπει να είναι Greek Epsilon U+0395"
    assert entry.evaluator.name == "(Μ) ΕΥΑΓΓΕΛΟΣ ΚΟΡΩΝΑΚΗΣ"
    # Latin "M" U+004D vs Greek Mu "Μ" U+039C — homoglyph, εύκολο λάθος στο
    # ίδιο το test αν πληκτρολογηθεί με το λάθος alphabet.
    assert ord(entry.evaluator.name[1]) == 0x039C, "'Μ' πρέπει να είναι Greek Mu U+039C, όχι Latin M U+004D"


def test_positional_parser_real_block_33_fg_psara():
    # Πραγματικό block #33 από το ιδιωτικό δείγμα PDF (ΟΧΙ tracked, βλ.
    # private/debug_raw_pages.txt γραμμές 1298-1306): ίδιο μοτίβο, μονάδα
    # "ΦΓ ΨΑΡΑ". Πριν το fix απορριπτόταν σιωπηλά.
    block_text = (
        "Σ.Α.\n"
        "01/01/2007\n-\n25/01/2007\n"
        "ΦΓ ΨΑΡΑ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΤΗΛΕΜΑΧΟΣ ΠΟΥΛΗΣ - ΚΥΒΕΡΝΗΤΗΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=8)

    assert entry is not None
    assert entry.period_start.isoformat() == "2007-01-01"
    assert entry.period_end.isoformat() == "2007-01-25"
    assert entry.characterization is None
    assert entry.score is None
    assert entry.unit == "ΦΓ ΨΑΡΑ"
    assert ord(entry.unit[0]) == 0x03A6, "'Φ' πρέπει να είναι Greek Phi U+03A6"
    assert ord(entry.unit[1]) == 0x0393, "'Γ' πρέπει να είναι Greek Gamma U+0393"
    assert entry.evaluator.name == "ΤΗΛΕΜΑΧΟΣ ΠΟΥΛΗΣ"


def run_all():
    tests = [
        test_field_matches_whitespace_before_colon,
        test_field_matches_whitespace_around_slash_in_composite_label,
        test_iter_pipe_rows_without_pipe_groups_consecutive_label_value_lines,
        test_positional_parser_extracts_entry_from_anchor_based_layout,
        test_positional_parser_treats_bare_du_as_unit_not_characterization,
        test_positional_parser_sa_with_unrecognized_token_accepted_as_unit,
        test_positional_parser_ea_with_unrecognized_token_rejected,
        test_positional_parser_still_rejects_invalid_period,
        test_positional_parser_real_block_28_ke_palaskas,
        test_positional_parser_real_block_33_fg_psara,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
