"""Mini test/sample flow για το _parse_health / _iter_health_entries
(structured extraction Ενότητας 5 / δ. Κατάσταση Υγείας, βλ.
app.ingestion.extractor). PR C — _parse_health (βλ. private/prompts/
PR_C_PARSE_HEALTH.md).

Το sample text παρακάτω αναπαράγει ΔΟΜΙΚΑ το πραγματικό layout (βλ. recon:
labels που σπάνε σε γραμμές, footer θόρυβος ΜΕΣΑ σε εγγραφή λόγω page break,
τερματισμός στο "ε.  Ευαρέσκειες") αλλά είναι πλήρως ανωνυμοποιημένο: καμία
πραγματική ημερομηνία, ΑΓΜ, username ή γνωμάτευση — όλα ΔΟΚΙΜΑΣΤΙΚΑ/ΣΥΝΘΕΤΙΚΑ.
ΔΕΝ διαβάζει τίποτα από private/.

Εκτελείται standalone (χωρίς pytest): `python tests/test_parse_health.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.extractor as extractor  # noqa: E402
from app.ingestion.extractor import _iter_health_entries, _parse_health  # noqa: E402

# Ανωνυμοποιημένο, δομικά ισοδύναμο με το πραγματικό section 5 (5 εγγραφές,
# footer ΜΕΣΑ στην 1η εγγραφή λόγω page break, κενή ΠΕΡΙΓΡΑΦΗ στην 1η,
# ΓΝΩΜΑΤΕΥΣΗ σε αλφαριθμητική ΚΑΙ σκέτη αριθμητική μορφή, μη-αριθμητικό
# ΗΜΕΡΕΣ ΑΔΕΙΑΣ στη 2η, τερματισμός στο "ε.  Ευαρέσκειες").
FIXTURE = (
    "5. - ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ ή ΜΗ ΓΙΑ ΠΡΟΑΓΩΓΗ ΚΑΤ' ΕΚΛΟΓΗΝ\n\n"
    "α.  Παραπομπές σε συμβούλια - Αποφάσεις συμβουλίων\n\n"
    "β.  Δίκες - Αποφάσεις Δικαστηρίων (Πολιτικών - Στρατοδικείων)\n\n"
    "γ.   Ποινές\n\n"
    "δ.   Κατάσταση Υγείας\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n01/01/2020\nΓΝΩΜΑΤΕΥΣΗ\n:\nΑΒΓ/111111ΤΕΣΤ20\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 5\n\n"
    "Εκτυπώθηκε από το χρήστη: XXXX\\anon.user\nΣελίδα 2 από 8\n(ΑΓΜ: Χ-00000)\n"
    "ΠΕΡΙΓΡΑΦΗ :\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n02/02/2020\nΓΝΩΜΑΤΕΥΣΗ\n:\n1234\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: ΑΓΝΩΣΤΟ\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΔΟΚΙΜΑΣΤΙΚΗ ΠΕΡΙΓΡΑΦΗ ΔΥΟ\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n03/03/2020\nΓΝΩΜΑΤΕΥΣΗ\n:\nΔΕΖ/222222ΤΕΣΤ20\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 4\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΔΟΚΙΜΑΣΤΙΚΗ ΠΕΡΙΓΡΑΦΗ ΤΡΙΑ\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n04/04/2020\nΓΝΩΜΑΤΕΥΣΗ\n:\n5678\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 10\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΔΟΚΙΜΑΣΤΙΚΗ ΠΕΡΙΓΡΑΦΗ ΤΕΣΣΕΡΑ\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ:\n05/05/2020\nΓΝΩΜΑΤΕΥΣΗ\n:\nΗΘΙ/333333ΤΕΣΤ20\nΗΜΕΡΕΣ ΑΔΕΙΑΣ\n\n: 20\n\n"
    "ΠΕΡΙΓΡΑΦΗ :\nΔΟΚΙΜΑΣΤΙΚΗ ΠΕΡΙΓΡΑΦΗ ΠΕΝΤΕ\n\n"
    "ε.  Ευαρέσκειες\n\n"
    "ΗΜΕΡΟΜΗΝΙΑ: 06/06/2020 ΘΑ ΑΓΝΟΗΘΕΙ ΓΙΑΤΙ ΕΙΝΑΙ ΜΕΤΑ ΤΟ ΟΡΙΟ ΤΗΣ ΕΝΟΤΗΤΑΣ\n"
)


def test_five_entries_parsed():
    entries = _iter_health_entries(FIXTURE)
    assert len(entries) == 5, f"αναμένονταν 5 εγγραφές, βρέθηκαν {len(entries)}"


def test_first_entry_empty_description():
    entries = _iter_health_entries(FIXTURE)
    assert entries[0]["ΠΕΡΙΓΡΑΦΗ"] == ""
    health = _parse_health(FIXTURE)
    assert health[0].description == ""


def test_footer_between_leave_days_and_description_is_not_captured():
    # Το footer ("Εκτυπώθηκε από το χρήστη: ...") εμφανίζεται ΜΕΣΑ στην 1η
    # εγγραφή (page break ανάμεσα σε ΗΜΕΡΕΣ ΑΔΕΙΑΣ και ΠΕΡΙΓΡΑΦΗ). WHITELIST
    # φίλτρο σημαίνει: (α) η τιμή ΗΜΕΡΕΣ ΑΔΕΙΑΣ παραμένει καθαρή "5", ΔΕΝ
    # καταπίνει το footer, (β) καμία τιμή δεν περιέχει το footer κείμενο,
    # (γ) το dict έχει ΜΟΝΟ τα 4 whitelisted keys — ποτέ "Εκτυπώθηκε από το
    # χρήστη" σαν ξεχωριστό πεδίο.
    entries = _iter_health_entries(FIXTURE)
    first = entries[0]
    assert first["ΗΜΕΡΕΣ ΑΔΕΙΑΣ"] == "5"
    assert set(first.keys()) == {"ΗΜΕΡΟΜΗΝΙΑ", "ΓΝΩΜΑΤΕΥΣΗ", "ΗΜΕΡΕΣ ΑΔΕΙΑΣ", "ΠΕΡΙΓΡΑΦΗ"}
    for value in first.values():
        assert "Εκτυπώθηκε" not in value
        assert "χρήστη" not in value
        assert "Χ-00000" not in value

    health = _parse_health(FIXTURE)
    assert health[0].leave_days == 5
    assert health[0].leave_days_raw == "5"


def test_terminates_at_section_end_not_end_of_text():
    entries = _iter_health_entries(FIXTURE)
    assert len(entries) == 5
    dates = [e["ΗΜΕΡΟΜΗΝΙΑ"] for e in entries]
    assert "06/06/2020" not in dates
    # Καμία τιμή δεν πρέπει να περιέχει το κείμενο μετά το boundary.
    for entry in entries:
        for value in entry.values():
            assert "ΑΓΝΟΗΘΕΙ" not in value


def test_gnomatevsi_alphanumeric_form():
    health = _parse_health(FIXTURE)
    assert health[0].opinion_ref == "ΑΒΓ/111111ΤΕΣΤ20"
    assert isinstance(health[0].opinion_ref, str)


def test_gnomatevsi_numeric_form_stays_str_not_normalized():
    health = _parse_health(FIXTURE)
    assert health[1].opinion_ref == "1234"
    assert isinstance(health[1].opinion_ref, str)


def test_non_numeric_leave_days_returns_none_with_raw_preserved():
    health = _parse_health(FIXTURE)
    second = health[1]
    assert second.leave_days is None
    assert second.leave_days_raw == "ΑΓΝΩΣΤΟ"


def test_all_five_dates_parsed_as_dates():
    health = _parse_health(FIXTURE)
    import datetime

    assert [h.date for h in health] == [
        datetime.date(2020, 1, 1),
        datetime.date(2020, 2, 2),
        datetime.date(2020, 3, 3),
        datetime.date(2020, 4, 4),
        datetime.date(2020, 5, 5),
    ]


def test_health_entry_has_no_category_field():
    health = _parse_health(FIXTURE)
    assert not hasattr(health[0], "category")


def test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes():
    # Κωδικοσημείο-έλεγχος ομογράφων στα ίδια τα test data/labels.
    for label in ("ΗΜΕΡΟΜΗΝΙΑ", "ΓΝΩΜΑΤΕΥΣΗ", "ΗΜΕΡΕΣ ΑΔΕΙΑΣ", "ΠΕΡΙΓΡΑΦΗ"):
        assert 0x0391 <= ord(label[0]) <= 0x03A9, f"{label!r} δεν ξεκινά με Greek Capital"
    assert ord("ε") == 0x03B5  # Greek small epsilon, όχι λατινικό "e"
    assert ord("Ευαρέσκειες"[0]) == 0x0395  # Greek capital epsilon


def test_whitelist_filter_catches_mutation():
    # Mutation check: σπάει το whitelist (προσθέτει το footer label στη
    # λίστα ΕΠΙΤΡΕΠΟΜΕΝΩΝ πεδίων, ό,τι θα συνέβαινε με blacklist φιλτράρισμα
    # αντί για whitelist) και επιβεβαιώνει ότι ΤΟ ΙΔΙΟ test-body πιάνει τη
    # διαρροή. Runtime monkeypatch (όχι εγγραφή σε αρχείο) — restore σε finally.
    original_labels = extractor._HEALTH_LABELS
    extractor._HEALTH_LABELS = original_labels + ["Εκτυπώθηκε από το χρήστη"]
    try:
        entries = extractor._iter_health_entries(FIXTURE)
        first = entries[0]
        assert "Εκτυπώθηκε από το χρήστη" in first
        leaked = first["Εκτυπώθηκε από το χρήστη"]
        assert leaked != "", "mutation ΔΕΝ έπιασε: το footer έπρεπε να διέρρευσε ως πεδίο"
    finally:
        extractor._HEALTH_LABELS = original_labels

    # Restore επιβεβαιωμένο: ξαναγυρνάει στην καθαρή συμπεριφορά.
    entries_after_restore = _iter_health_entries(FIXTURE)
    assert set(entries_after_restore[0].keys()) == {
        "ΗΜΕΡΟΜΗΝΙΑ", "ΓΝΩΜΑΤΕΥΣΗ", "ΗΜΕΡΕΣ ΑΔΕΙΑΣ", "ΠΕΡΙΓΡΑΦΗ",
    }


def run_all():
    tests = [
        test_five_entries_parsed,
        test_first_entry_empty_description,
        test_footer_between_leave_days_and_description_is_not_captured,
        test_terminates_at_section_end_not_end_of_text,
        test_gnomatevsi_alphanumeric_form,
        test_gnomatevsi_numeric_form_stays_str_not_normalized,
        test_non_numeric_leave_days_returns_none_with_raw_preserved,
        test_all_five_dates_parsed_as_dates,
        test_health_entry_has_no_category_field,
        test_greek_test_data_uses_real_greek_codepoints_not_latin_lookalikes,
        test_whitelist_filter_catches_mutation,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
