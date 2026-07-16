"""Mini test/sample flow για τον config-driven chunker (Περιληπτικό Σημείωμα).

Καλύπτει τις δύο διαδρομές:
  1. known-sections match: headers στο κείμενο που fuzzy-ταιριάζουν με το
     KNOWN_SECTIONS config (single source of truth στο app/models/evaluation.py) -
     επιβεβαιώνεται section detection χωρίς hardcoded strings στον chunker.
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
    assert len(KNOWN_SECTIONS) == 7
    section_a, section_b = KNOWN_SECTIONS[0], KNOWN_SECTIONS[2]
    noisy_a = section_a.lower()  # πεζά -> normalization test
    noisy_b = section_b.replace("Ε", "Ε ").strip()  # μικρή "OCR θορυβώδης" παραλλαγή

    page_text = (
        f"{noisy_a}\n"
        "Βαθμός: Πλωτάρχης | Ημ/νία Απόφασης: 01/03/2020 | Απόφαση: Προακτέος | "
        "Ημ/νία Προαγωγής: 15/03/2020\n"
        "\n"
        f"{noisy_b}\n"
        "Πτυχίο: Σχολή Ναυτικών Δοκίμων | Έτος: 2010 | Βαθμολογία: Λίαν Καλώς\n"
    )
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks, "αναμένονταν chunks στη known-section διαδρομή"
    assert all(not c.fallback for c in chunks), "δεν αναμένεται fallback εδώ"

    sections_found = {c.section for c in chunks}
    assert section_a in sections_found, f"δεν εντοπίστηκε '{section_a}' μέσω fuzzy match"
    assert section_b in sections_found, f"δεν εντοπίστηκε '{section_b}' μέσω fuzzy match"

    for c in chunks:
        assert c.doc_id == DOC_ID
        assert c.page == 1


def test_unknown_layout_falls_back_to_structural_chunking_without_data_loss():
    # Κείμενο χωρίς καμία αναφορά σε KNOWN_SECTIONS -> δεν πρέπει να απορριφθεί
    # το έγγραφο, πρέπει να καλυφθεί ολόκληρο μέσω παραγράφων.
    paragraph_1 = "Γενικές παρατηρήσεις για την πορεία της σταδιοδρομίας."
    paragraph_2 = "Προτάσεις για την επόμενη τοποθέτηση."
    paragraph_3 = "Πρόσθετα σχόλια που δεν εντάσσονται σε συγκεκριμένη ενότητα."
    page_text = f"{paragraph_1}\n\n{paragraph_2}\n\n{paragraph_3}"
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks, "το fallback δεν πρέπει να απορρίψει το έγγραφο (μηδενικά chunks)"
    assert all(c.fallback for c in chunks), "αναμένονταν αποκλειστικά fallback chunks"
    assert all(c.section is None for c in chunks)

    # Μηδενική απώλεια περιεχομένου: κάθε παράγραφος εμφανίζεται ακέραιη σε
    # κάποιο chunk.
    joined = "\n".join(c.text for c in chunks)
    for paragraph in (paragraph_1, paragraph_2, paragraph_3):
        assert paragraph in joined


def test_partial_known_sections_do_not_trigger_fallback():
    # Αν έστω μία ενότητα αναγνωριστεί, η διαδρομή παραμένει "known", ακόμη κι
    # αν υπάρχει και άσχετο/άγνωστο κείμενο γύρω της.
    section = KNOWN_SECTIONS[3]
    page_text = f"Εισαγωγικό σχόλιο χωρίς ενότητα.\n{section}\nΑ/Α: 1 | Μονάδα: Φ/Γ ΣΥΝΘΕΤΙΚΟ\n"
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert chunks
    assert not any(c.fallback for c in chunks)
    assert any(c.section == section for c in chunks)


def test_evaluation_section_spans_multiple_entries_in_one_chunk():
    # Η Ενότητα 7 (ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ) περιέχει πολλαπλές
    # περιόδους μέσα στο ίδιο section chunk· η διάσπασή τους σε entries
    # γίνεται στο extractor, όχι εδώ (ο chunker εντοπίζει μόνο section boundaries).
    section = KNOWN_SECTIONS[6]
    page_text = (
        f"{section}\n"
        "Περίοδος: 01/01/2023 - 31/12/2023\n"
        "Χαρακτηρισμός: ΕΞΑΙΡΕΤΟΣ (100)\n"
        "Περίοδος: 01/01/2024 - 30/06/2024\n"
        "Χαρακτηρισμός: ΛΙΑΝ ΚΑΛΟΣ (90)\n"
    )
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert len(chunks) == 1
    assert chunks[0].section == section
    assert "01/01/2023" in chunks[0].text
    assert "01/01/2024" in chunks[0].text


def test_page_without_header_inherits_active_section_from_previous_page():
    # Πραγματικό PDF layout: section header μόνο στην πρώτη σελίδα της
    # ενότητας· οι επόμενες σελίδες συνεχίζουν χωρίς επανάληψη του header
    # (αντίθετα με τη σύμβαση του synthetic generator). Χωρίς carry-forward,
    # το περιεχόμενο της 2ης σελίδας θα χανόταν εντελώς (Bug 2a).
    section = KNOWN_SECTIONS[6]
    page1_text = f"{section}\nΠερίοδος: 01/01/2023 - 31/12/2023\nΧαρακτηρισμός: ΕΞΑΙΡΕΤΟΣ (100)\n"
    page2_text = "Περίοδος: 01/01/2022 - 31/12/2022\nΧαρακτηρισμός: ΚΑΛΟΣ (70)\n"
    pages = [PageText(page=1, text=page1_text), PageText(page=2, text=page2_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert not any(c.fallback for c in chunks), "δεν αναμένεται fallback εδώ"
    page2_chunks = [c for c in chunks if c.page == 2]
    assert page2_chunks, "η σελίδα 2 (χωρίς header) δεν πρέπει να χαθεί"
    assert all(c.section == section for c in page2_chunks), (
        "η σελίδα 2 πρέπει να κληρονομήσει την ενεργή ενότητα της σελίδας 1"
    )
    assert "01/01/2022" in "\n".join(c.text for c in page2_chunks)


def test_legend_substring_does_not_trigger_false_positive_boundary():
    # Bug 2b: μια γραμμή-legend/σύνοψη ΜΕΣΑ σε μια ενότητα μπορεί να αναφέρει
    # (ως substring) το πλήρες title μιας ΑΛΛΗΣ ενότητας, χωρίς η ίδια να
    # είναι header γραμμή (δεν ξεκινά με αρίθμηση, ούτε είναι ολόκληρη η
    # γραμμή το title). Αυτό ΔΕΝ πρέπει να σπάσει το chunk σε ψευδές section.
    section = KNOWN_SECTIONS[6]
    other_title = KNOWN_SECTIONS[5]
    legend_line = f"Δείτε στην ενότητα {other_title} παραπάνω."
    page_text = (
        f"{section}\n"
        f"{legend_line}\n"
        "Περίοδος: 01/01/2023 - 31/12/2023\n"
        "Χαρακτηρισμός: ΕΞΑΙΡΕΤΟΣ (100)\n"
    )
    pages = [PageText(page=1, text=page_text)]

    chunks = chunk_by_section(pages, DOC_ID)

    assert len(chunks) == 1, (
        f"η γραμμή legend δεν πρέπει να σπάσει το chunk σε δεύτερο section, βρέθηκαν {len(chunks)}"
    )
    assert chunks[0].section == section
    assert legend_line in chunks[0].text
    assert "01/01/2023" in chunks[0].text


def run_all():
    tests = [
        test_known_sections_are_detected_via_fuzzy_match,
        test_unknown_layout_falls_back_to_structural_chunking_without_data_loss,
        test_partial_known_sections_do_not_trigger_fallback,
        test_evaluation_section_spans_multiple_entries_in_one_chunk,
        test_page_without_header_inherits_active_section_from_previous_page,
        test_legend_substring_does_not_trigger_false_positive_boundary,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
