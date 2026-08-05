"""Mini test/sample flow για το query-routing heuristic (Φάση B2).

route_query(question) επιστρέφει "structured" hint ΜΟΝΟ όταν το ερώτημα
περιέχει ΤΑΥΤΟΧΡΟΝΑ μια βαθμολογική λέξη (βαθμ*/score/"πόσο πήρε"/
"αξιολογήθηκε με") ΚΑΙ αναφορά (fuzzy/case-insensitive) σε μία από τις 7
KNOWN_SECTIONS. Καθαρά advisory: δεν αλλάζει mode μόνο του.

Εκτελείται standalone: `python tests/test_routing.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.routing import route_query  # noqa: E402


def test_score_keyword_plus_exact_section_returns_structured():
    question = "Ποιος ήταν ο βαθμός στη Γενική Ικανότητα στον Κατεχόμενο Βαθμό;"
    assert route_query(question) == "structured"


def test_poso_pire_phrase_plus_section_returns_structured():
    question = "Πόσο πήρε στη Συνολική Εμφάνιση - Χαρακτηρισμός;"
    assert route_query(question) == "structured"


def test_axiologithike_me_phrase_plus_section_returns_structured():
    question = "Πώς αξιολογήθηκε με βάση τις Τοποθετήσεις;"
    assert route_query(question) == "structured"


def test_fuzzy_section_match_with_different_word_ending_returns_structured():
    # "Κρίσεις Προαγωγής" (γεν. ενικού) vs KNOWN_SECTIONS "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ"
    # (γεν. πληθυντικού) -> δεν ταιριάζει ως substring, πρέπει να πιάσει το
    # fuzzy (SequenceMatcher) fallback.
    question = "Βαθμολογήθηκε καλά στις Κρίσεις Προαγωγής;"
    assert route_query(question) == "structured"


def test_no_score_keyword_returns_none():
    question = "Ποια είναι η διεύθυνση κατοικίας του;"
    assert route_query(question) is None


def test_score_keyword_without_known_section_returns_none():
    question = "Πόσο βαθμολογήθηκε συνολικά;"
    assert route_query(question) is None


def test_known_section_without_score_keyword_returns_none():
    question = "Πες μου για τις Τοποθετήσεις του."
    assert route_query(question) is None


def test_score_word_english_without_known_section_returns_none():
    question = "What's the score for delivery?"
    assert route_query(question) is None


def test_promoted_keyword_without_score_keyword_or_section_returns_structured():
    # δεύτερο ανεξάρτητο σκέλος: "προήχθη" ταιριάζει σε "προηχθ" μετά το
    # normalize, χωρίς καμία βαθμολογική λέξη ή γνωστή ενότητα.
    question = "Πότε προήχθη σε Υποπλοίαρχο;"
    assert route_query(question) == "structured"


def test_promotion_noun_keyword_returns_structured():
    question = "Ποια ήταν η προαγωγή του το 2019;"
    assert route_query(question) == "structured"


def test_judged_keyword_returns_structured():
    question = "Πότε κρίθηκε τελευταία φορά;"
    assert route_query(question) == "structured"


def test_service_time_keyword_returns_structured():
    # normalize αφαιρεί τόνους αλλά όχι πτώσεις: "χρόνο υπηρεσίας" (αιτιατική)
    # ταιριάζει στο στέλεχος "χρονο υπηρεσιας".
    question = "Δείξε μου τον χρόνο υπηρεσίας του."
    assert route_query(question) == "structured"


def test_service_at_sea_keyword_returns_structured():
    question = "Πόση υπηρεσία θαλάσσης έχει;"
    assert route_query(question) == "structured"


def test_unrelated_question_still_returns_none():
    # μη-regression: το δεύτερο σκέλος δεν πυροδοτεί για άσχετα ερωτήματα.
    question = "Ποια είναι η διεύθυνση κατοικίας του;"
    assert route_query(question) is None


def run_all():
    tests = [
        test_score_keyword_plus_exact_section_returns_structured,
        test_poso_pire_phrase_plus_section_returns_structured,
        test_axiologithike_me_phrase_plus_section_returns_structured,
        test_fuzzy_section_match_with_different_word_ending_returns_structured,
        test_no_score_keyword_returns_none,
        test_score_keyword_without_known_section_returns_none,
        test_known_section_without_score_keyword_returns_none,
        test_score_word_english_without_known_section_returns_none,
        test_promoted_keyword_without_score_keyword_or_section_returns_structured,
        test_promotion_noun_keyword_returns_structured,
        test_judged_keyword_returns_structured,
        test_service_time_keyword_returns_structured,
        test_service_at_sea_keyword_returns_structured,
        test_unrelated_question_still_returns_none,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
