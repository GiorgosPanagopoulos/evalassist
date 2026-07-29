"""Mini test/sample flow για το backend/app/retrieval/rank_validator.py
(Φάση 1 rank validator, logging only).

Καλύπτει το πραγματικό incident (ΠΧΗΣ στο context, "Υπλγού" στην απάντηση)
καθώς και substring traps, κλίση, τονισμό και συντομογραφίες.

Εκτελείται standalone: `python tests/test_rank_validator.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.rank_validator import find_unsupported_ranks  # noqa: E402


def test_same_rank_in_answer_and_context_not_flagged():
    answer = "Ο αξιολογούμενος ήταν ΥΠΟΛΟΧΑΓΟΣ κατά την περίοδο."
    context = "[doc1 σελ.1 - Στοχοθεσία]\nΟ ΥΠΟΛΟΧΑΓΟΣ Παπαδόπουλος..."
    assert find_unsupported_ranks(answer, context) == []


def test_different_rank_in_context_is_flagged():
    answer = "Ο αξιολογούμενος ήταν ΥΠΟΛΟΧΑΓΟΣ."
    context = "[doc1 σελ.1 - Στοχοθεσία]\nΟ ΛΟΧΑΓΟΣ Παπαδόπουλος..."
    assert find_unsupported_ranks(answer, context) == ["ΥΠΟΛΟΧΑΓΟΣ"]


def test_abbreviation_in_context_full_form_in_answer_not_flagged():
    answer = "με βαθμό Πλωτάρχη"
    context = "ΑΞΙΟΛΟΓΩΝ ΠΧΗΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == []


def test_inflection_not_flagged():
    answer = "ο Υπλγού ανέφερε ότι"
    context = "ο ΥΠΛΓΟΣ ανέφερε ότι"
    assert find_unsupported_ranks(answer, context) == []


def test_accented_vs_unaccented_not_flagged():
    answer = "με βαθμό Υπλγού"
    context = "με βαθμό ΥΠΛΓΟΥ"
    assert find_unsupported_ranks(answer, context) == []


def test_ypoploiarchos_answer_ploiarchos_context_flagged_substring_trap():
    answer = "Ο ΥΠΟΠΛΟΙΑΡΧΟΣ ανέλαβε καθήκοντα."
    context = "Ο ΠΛΟΙΑΡΧΟΣ ανέλαβε καθήκοντα."
    assert find_unsupported_ranks(answer, context) == ["ΥΠΟΠΛΟΙΑΡΧΟΣ"]


def test_apchos_context_ploiarchos_answer_flagged_substring_trap():
    """Το ΠΧΟΣ (ΠΛΟΙΑΡΧΟΣ) είναι substring του ΑΠΧΟΣ (ΑΡΧΙΠΛΟΙΑΡΧΟΣ)· η
    longest-stem-first ταξινόμηση πρέπει να αποδώσει το ΑΠΧΟΣ αποκλειστικά
    στον ΑΡΧΙΠΛΟΙΑΡΧΟ, όχι στον Πλοίαρχο."""
    answer = "Ο Πλοίαρχος υπέγραψε."
    context = "ΑΠΧΟΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΠΛΟΙΑΡΧΟΣ"]


def test_pchos_context_archiploiarchos_answer_flagged_substring_trap_reverse():
    """Αντίστροφο του παραπάνω: context με ΠΧΟΣ (ΠΛΟΙΑΡΧΟΣ) δεν πρέπει να
    τεκμηριώνει τον Αρχιπλοίαρχο."""
    answer = "Ο Αρχιπλοίαρχος ενέκρινε."
    context = "ΠΧΟΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΑΡΧΙΠΛΟΙΑΡΧΟΣ"]


def test_ypnchos_context_navarchos_answer_flagged_substring_trap():
    """Το ΝΧΟΣ (ΝΑΥΑΡΧΟΣ) είναι substring του ΥΠΝΧΟΣ (ΥΠΟΝΑΥΑΡΧΟΣ)· το
    context δεν πρέπει να τεκμηριώνει τον Ναύαρχο."""
    answer = "Ο Ναύαρχος επιθεώρησε τη μονάδα."
    context = "ΥΠΝΧΟΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΝΑΥΑΡΧΟΣ"]


def test_anthchos_context_antinavarchos_answer_flagged_near_miss():
    """Το ΑΝΧΟΣ (ΑΝΤΙΝΑΥΑΡΧΟΣ) και το ΑΝΘΧΟΣ (ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ) διαφέρουν
    κατά ένα γράμμα (Θ) και ΔΕΝ πρέπει να συγχέονται."""
    answer = "Ο Αντιναύαρχος υπέγραψε την έκθεση."
    context = "ΑΝΘΧΟΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΑΝΤΙΝΑΥΑΡΧΟΣ"]


def test_pchis_context_ploiarchos_answer_flagged_different_rank():
    """Το ΠΧΗΣ (ΠΛΩΤΑΡΧΗΣ) και το ΠΧΟΣ (ΠΛΟΙΑΡΧΟΣ) είναι διαφορετικοί
    βαθμοί ίδιου μήκους· δεν πρέπει να ταυτίζονται."""
    answer = "Ο Πλοίαρχος υπέγραψε την έκθεση."
    context = "ΑΞΙΟΛΟΓΩΝ ΠΧΗΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΠΛΟΙΑΡΧΟΣ"]


def test_real_incident_pchis_context_yplgoy_answer_flagged():
    answer = "με βαθμό Υπλγού"
    context = "ΑΞΙΟΛΟΓΩΝ ΠΧΗΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΥΠΟΛΟΧΑΓΟΣ"]


def test_no_ranks_anywhere_returns_empty_list():
    answer = "Η στοχοθεσία ολοκληρώθηκε επιτυχώς."
    context = "Δεν υπάρχουν σχετικές παρατηρήσεις."
    assert find_unsupported_ranks(answer, context) == []


def test_abbreviation_accusative_form_is_flagged():
    """Το πραγματικό περιστατικό του audit #109: η αιτιατική συντομογραφία
    (ΠΧΟ) δεν έπιανε τίποτα πριν την κοπή του τελικού Σ."""
    answer = "ΠΧΟ ΝΙΚΟΛΑΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ Ν. ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΠΛΟΙΑΡΧΟΣ"]


def test_abbreviation_genitive_form_is_flagged():
    answer = "ΠΧΟΥ ΠΑΠΑΔΟΠΟΥΛΟΥ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΠΛΟΙΑΡΧΟΣ"]


def test_abbreviation_accusative_matches_same_rank_in_context():
    """Κρίσιμο: η αιτιατική στην απάντηση δεν πρέπει να παράγει false
    positive όταν το context έχει την ίδια συντομογραφία σε ονομαστική."""
    answer = "ΠΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΟΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == []


def test_anthchos_accusative_flagged():
    answer = "ΑΝΘΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΑΝΘΥΠΟΠΛΟΙΑΡΧΟΣ"]


def test_ypchos_accusative_flagged():
    answer = "ΥΠΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΥΠΟΠΛΟΙΑΡΧΟΣ"]


def test_apchos_not_matched_by_shortened_pchos_stem():
    """Substring trap μετά την κοπή: το κομμένο ΠΧΟ (ΠΛΟΙΑΡΧΟΣ) δεν πρέπει
    να πιάνει μέσα στο ΑΠΧΟ (ΑΡΧΙΠΛΟΙΑΡΧΟΣ)."""
    answer = "ΑΠΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    result = find_unsupported_ranks(answer, context)
    assert result == ["ΑΡΧΙΠΛΟΙΑΡΧΟΣ"]
    assert "ΠΛΟΙΑΡΧΟΣ" not in result


def test_anpchos_accusative_not_confused_with_pchos():
    answer = "ΑΝΠΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΑΝΤΙΠΛΟΙΑΡΧΟΣ"]


def test_ypnchos_accusative_not_confused_with_nchos():
    answer = "ΥΠΝΧΟ ΠΑΠΑΔΟΠΟΥΛΟ"
    context = "ΠΧΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ"
    assert find_unsupported_ranks(answer, context) == ["ΥΠΟΝΑΥΑΡΧΟΣ"]


def test_greek_words_do_not_trigger_shortened_stems():
    """Regression guard: μετά την κοπή τα stems είναι κοντύτερα· δεν πρέπει
    να ματσάρουν μέσα σε κανονικές ελληνικές λέξεις."""
    answer = "Η σχολή ήταν πλήρης και ο χρόνος επαρκής για την εκπαίδευση"
    context = ""
    assert find_unsupported_ranks(answer, context) == []


def run_all():
    tests = [
        test_same_rank_in_answer_and_context_not_flagged,
        test_different_rank_in_context_is_flagged,
        test_abbreviation_in_context_full_form_in_answer_not_flagged,
        test_inflection_not_flagged,
        test_accented_vs_unaccented_not_flagged,
        test_ypoploiarchos_answer_ploiarchos_context_flagged_substring_trap,
        test_apchos_context_ploiarchos_answer_flagged_substring_trap,
        test_pchos_context_archiploiarchos_answer_flagged_substring_trap_reverse,
        test_ypnchos_context_navarchos_answer_flagged_substring_trap,
        test_anthchos_context_antinavarchos_answer_flagged_near_miss,
        test_pchis_context_ploiarchos_answer_flagged_different_rank,
        test_real_incident_pchis_context_yplgoy_answer_flagged,
        test_no_ranks_anywhere_returns_empty_list,
        test_abbreviation_accusative_form_is_flagged,
        test_abbreviation_genitive_form_is_flagged,
        test_abbreviation_accusative_matches_same_rank_in_context,
        test_anthchos_accusative_flagged,
        test_ypchos_accusative_flagged,
        test_apchos_not_matched_by_shortened_pchos_stem,
        test_anpchos_accusative_not_confused_with_pchos,
        test_ypnchos_accusative_not_confused_with_nchos,
        test_greek_words_do_not_trigger_shortened_stems,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
