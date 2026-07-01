"""Mini test/sample flow για τον config-driven chunker (Φάση 2).

Καλύπτει τις δύο διαδρομές:
  1. known-sections match: headers στο κείμενο που fuzzy-ταιριάζουν με το
     KNOWN_SECTIONS config (single source of truth στο evaluation.py) -
     επιβεβαιώνεται section/score ανίχνευση χωρίς hardcoded strings στον chunker.
  2. fallback: άγνωστο layout (καμία επικεφαλίδα δεν ταιριάζει) - επιβεβαιώνεται
     ότι ο chunker πέφτει σε structural (paragraph) chunking αντί να απορρίψει
     το έγγραφο, και ότι δεν χάνεται περιεχόμενο.

Εκτελείται standalone (χωρίς pytest): `python tests/test_chunker.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.chunker import PageText, chunk_by_section  # noqa: E402
from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402

DOC_ID = "test-doc-0001"


def test_known_sections_are_detected_via_fuzzy_match():
    # Σκόπιμα ελαφρά "θορυβώδεις" εκδοχές (κεφαλαία / τόνοι / μικρό typo) των
    # KNOWN_SECTIONS ονομάτων, ώστε να αποδεικνύεται fuzzy matching και όχι
    # exact-string σύγκριση.
    assert len(KNOWN_SECTIONS) >= 2
    section_a, section_b = KNOWN_SECTIONS[0], KNOWN_SECTIONS[1]
    noisy_a = section_a.upper()  # κεφαλαία -> normalization test
    noisy_b = section_b.replace("α", "α ").strip()  # μικρή "OCR θορυβώδης" παραλλαγή

    page_text = (
        f"{noisy_a}\n"
        f"Βαθμολογία: 4\n"
        "Ο εργαζόμενος πέτυχε τους στόχους του με συνέπεια.\n"
        "\n"
        f"{noisy_b}\n"
        "Σχόλιο αξιολογητή για την ενότητα.\n"
        "(5/5)\n"
    )
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks, "αναμένονταν chunks στη known-section διαδρομή"
    assert all(not c.fallback for c in chunks), "δεν αναμένεται fallback εδώ"

    sections_found = {c.section for c in chunks}
    assert section_a in sections_found, f"δεν εντοπίστηκε '{section_a}' μέσω fuzzy match"
    assert section_b in sections_found, f"δεν εντοπίστηκε '{section_b}' μέσω fuzzy match"

    scores_by_section = {c.section: c.score for c in chunks}
    assert scores_by_section[section_a] == 4
    assert scores_by_section[section_b] == 5

    for c in chunks:
        assert c.doc_id == DOC_ID
        assert c.page == 1


def test_unknown_layout_falls_back_to_structural_chunking_without_data_loss():
    # Κείμενο χωρίς καμία αναφορά σε KNOWN_SECTIONS -> δεν πρέπει να απορριφθεί
    # το έγγραφο, πρέπει να καλυφθεί ολόκληρο μέσω παραγράφων.
    paragraph_1 = "Γενικές παρατηρήσεις για την πορεία του έργου κατά το έτος."
    paragraph_2 = "Προτάσεις βελτίωσης για την επόμενη περίοδο αξιολόγησης."
    paragraph_3 = "Πρόσθετα σχόλια που δεν εντάσσονται σε συγκεκριμένη ενότητα."
    page_text = f"{paragraph_1}\n\n{paragraph_2}\n\n{paragraph_3}"
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks, "το fallback δεν πρέπει να απορρίψει το έγγραφο (μηδενικά chunks)"
    assert all(c.fallback for c in chunks), "αναμένονταν αποκλειστικά fallback chunks"
    assert all(c.section is None and c.score is None for c in chunks)

    # Μηδενική απώλεια περιεχομένου: κάθε παράγραφος εμφανίζεται ακέραιη σε
    # κάποιο chunk.
    joined = "\n".join(c.text for c in chunks)
    for paragraph in (paragraph_1, paragraph_2, paragraph_3):
        assert paragraph in joined


def test_partial_known_sections_do_not_trigger_fallback():
    # Αν έστω μία ενότητα αναγνωριστεί, η διαδρομή παραμένει "known", ακόμη κι
    # αν υπάρχει και άσχετο/άγνωστο κείμενο γύρω της.
    section = KNOWN_SECTIONS[0]
    page_text = f"Εισαγωγικό σχόλιο χωρίς ενότητα.\n{section}\nΒαθμολογία: 3\n"
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks
    assert not any(c.fallback for c in chunks)
    assert any(c.section == section and c.score == 3 for c in chunks)


def run_all():
    tests = [
        test_known_sections_are_detected_via_fuzzy_match,
        test_unknown_layout_falls_back_to_structural_chunking_without_data_loss,
        test_partial_known_sections_do_not_trigger_fallback,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
