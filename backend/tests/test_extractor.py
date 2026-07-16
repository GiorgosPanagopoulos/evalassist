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


def test_positional_parser_accepts_du_characterization():
    # Πραγματικό PDF: κάποιες Σ.Α. περίοδοι έχουν bare "ΔΥ" αντί για επίσημο
    # χαρακτηρισμό με βαθμό — "ΔΥ" είναι μέλος του CHARACTERIZATIONS (βλ.
    # models/evaluation.py), οπότε η εγγραφή καταγράφεται κανονικά με
    # score=None αντί να παραλειφθεί.
    block_text = (
        "Σ.Α.\n"
        "01/01/2019\n-\n10/01/2019\n"
        "ΔΥ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=4)

    assert entry is not None
    assert entry.characterization == "ΔΥ"
    assert entry.score is None
    assert entry.ea_type == "Σ.Α."


def test_positional_parser_skips_entry_without_valid_characterization():
    # Χαρακτηρισμός εκτός CHARACTERIZATIONS (πραγματικά άγνωστος, όχι "ΔΥ")
    # — δεν πρέπει να επινοηθεί τιμή, η εγγραφή παραλείπεται (None).
    block_text = (
        "Σ.Α.\n"
        "01/01/2019\n-\n10/01/2019\n"
        "ΑΓΝΩΣΤΟΣ\n-\n\n"
        "Αξιολογών:\nΑΝΤΧΟΣ   ΣΥΝΘΕΤΙΚΟ ΟΝΟΜΑ - ΕΠΙΣΤΟΛΕΑΣ\n\n"
    )

    entry = _parse_evaluation_entry_positional("Σ.Α.", block_text, page=4)

    assert entry is None


def run_all():
    tests = [
        test_field_matches_whitespace_before_colon,
        test_field_matches_whitespace_around_slash_in_composite_label,
        test_iter_pipe_rows_without_pipe_groups_consecutive_label_value_lines,
        test_positional_parser_extracts_entry_from_anchor_based_layout,
        test_positional_parser_accepts_du_characterization,
        test_positional_parser_skips_entry_without_valid_characterization,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
