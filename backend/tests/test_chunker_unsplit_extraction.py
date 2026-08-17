"""Regression tests για το CHUNK_SPLIT_FIX: ο extractor πρέπει να διαβάζει το
UNSPLIT section-detection αποτέλεσμα (`chunker.chunk_by_section_unsplit`), όχι
το split/overlap output του `chunker.chunk_by_section` (retrieval-oriented,
Chroma path) — αλλιώς το 45-96 char overlap του sub-splitter (chunker.py:44,
RecursiveCharacterTextSplitter chunk_size=1000/chunk_overlap=100) εμφανίζεται
διπλό μέσα στο δομημένο κείμενο (βλ. private/prompts/CHUNK_SPLIT_FIX.md).

Το κείμενο παρακάτω (~2000 chars, ξεπερνά το MAX_CHUNK_CHARS=1500) είναι
κατασκευασμένο ώστε το πραγματικό `RecursiveCharacterTextSplitter` να βάλει
ΟΛΟΚΛΗΡΟ ένα bare "Σ.Α." positional block (entry2) μέσα στο overlap παράθυρο
ανάμεσα σε δύο sub-chunks -> αν ο extractor διάβαζε το split output, το block
θα εμφανιζόταν ΔΥΟ φορές (φάντασμα εγγραφή). Το ακριβές μήκος filler
(pad_lines) βρέθηκε εμπειρικά (βλ. αναζήτηση στο recon) - όχι τυχαίο.

Κάθε test τρέχει ΚΑΙ το FIXED path (extract_summary_note με unsplit chunks)
ΚΑΙ το BROKEN path (extract_summary_note με split chunks, προσομοιώνοντας
την ΠΑΛΙΑ καλωδίωση πριν το fix) πάνω στο ΙΔΙΟ κείμενο, ώστε κάθε assertion
να αποδεικνύεται μη-κενή: αν κάποιος αναστρέψει το fix (ξαναδώσει split
chunks στον extractor), το ίδιο test θα έσκαγε.

Εκτελείται standalone (χωρίς pytest): `python tests/test_chunker_unsplit_extraction.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.chunker import (  # noqa: E402
    MAX_CHUNK_CHARS,
    PageText,
    chunk_by_section,
    chunk_by_section_unsplit,
    split_long_chunks,
)
from app.ingestion.extractor import extract_summary_note  # noqa: E402
from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402

DOC_ID = "test-doc-chunk-split-fix"
_SECTION = KNOWN_SECTIONS[6]  # ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ

# --- Σενάριο: 3 πραγματικές (bare-anchor, positional) εγγραφές σε 2 σελίδες.
# entry2 είναι σκόπιμα το ΕΛΑΧΙΣΤΟ έγκυρο Σ.Α. block (anchor + 2 ημερομηνίες,
# χωρίς χαρακτηρισμό/μονάδα/αξιολογητή) ώστε -αν διπλασιαστεί μέσω overlap-
# ΚΑΙ τα δύο αντίγραφα να παραμείνουν ανεξάρτητα valid (δεν απορρίπτονται από
# το date-validation guard όπως θα συνέβαινε με ένα truncated fragment).
_ENTRY_A = (
    "Ε.Α.\n01/01/2021\n-\n31/12/2021\nΕΞΑΙΡΕΤΟΣ (97)\n\n"
    "Αξιολογών:\nΠΧΟΣ ΠΡΩΤΟΣ - ΔΙΟΙΚΗΤΗΣ\n\n"
)
_FILLER_LINE = "Σημείωση αξιολόγησης σχετική με απόδοση."
_LEADING_FILLER = (_FILLER_LINE + "\n") * 22  # βρέθηκε εμπειρικά: γεμίζει piece0 ακριβώς
_ENTRY_2 = "Σ.Α.\n01/01/2019\n-\n10/01/2019\n"
_TRAILING_FILLER = (_FILLER_LINE + "\n") * 25
_ENTRY_3 = "Σ.Α.\n01/06/2016\n-\n30/06/2016\n"

_PAGE1_TEXT = f"{_SECTION}\n{_ENTRY_A}"
_PAGE2_TEXT = _LEADING_FILLER + _ENTRY_2 + _TRAILING_FILLER + _ENTRY_3


def _build_pages() -> list[PageText]:
    return [PageText(page=1, text=_PAGE1_TEXT), PageText(page=2, text=_PAGE2_TEXT)]


def _fixed_and_broken_notes():
    """Επιστρέφει (note_fixed, note_broken): το FIXED τρέχει extract_summary_note
    πάνω στο unsplit αποτέλεσμα (η πραγματική καλωδίωση μετά το fix)· το
    BROKEN πάνω στο split αποτέλεσμα (η ΠΑΛΙΑ καλωδίωση, πριν το fix)."""
    pages = _build_pages()
    unsplit = chunk_by_section_unsplit(pages, DOC_ID)
    split = split_long_chunks(unsplit)
    full_text = "\n".join(p.text for p in pages)
    note_fixed, raw_fixed = extract_summary_note(full_text, unsplit)
    note_broken, raw_broken = extract_summary_note(full_text, split)
    return note_fixed, raw_fixed, note_broken, raw_broken, unsplit, split


def test_setup_sanity_page2_actually_exceeds_max_chunk_chars_and_splits():
    # Προϋπόθεση του σεναρίου: η σελίδα 2 πρέπει να ξεπερνά το
    # MAX_CHUNK_CHARS ώστε ο sub-splitter να ενεργοποιείται πραγματικά (κάτι
    # που ΔΕΝ συμβαίνει σε κανένα υπάρχον fixture, βλ. test_chunker.py).
    pages = _build_pages()
    unsplit = chunk_by_section_unsplit(pages, DOC_ID)
    page2_chunk = next(c for c in unsplit if c.page == 2)
    assert len(page2_chunk.text) > MAX_CHUNK_CHARS, (
        f"το fixture πρέπει να ξεπερνά MAX_CHUNK_CHARS={MAX_CHUNK_CHARS}, "
        f"βρέθηκε {len(page2_chunk.text)} - το test δεν θα ασκούσε το sub-split path"
    )
    split_pieces = split_long_chunks(unsplit)
    assert len(split_pieces) > len(unsplit), "ο sub-splitter δεν έσπασε τη σελίδα 2 - το σενάριο δεν ισχύει πια"
    # Το ίδιο το _ENTRY_2 (πλήρες, valid block) πρέπει να εμφανίζεται σε
    # ΔΥΟ διαφορετικά split pieces - αλλιώς το engineered overlap δεν πιάνει
    # πια το anchor (π.χ. αν αλλάξει ο langchain splitter version/behavior).
    pieces_with_entry2 = [p for p in split_pieces if _ENTRY_2 in p.text]
    assert len(pieces_with_entry2) == 2, (
        f"το fixture βασίζεται σε _ENTRY_2 duplicated σε ακριβώς 2 split pieces, "
        f"βρέθηκε σε {len(pieces_with_entry2)} - re-tune το filler αν αυτό σπάσει"
    )


def test_t1_extractor_sees_no_duplicate_block_with_unsplit_chunks():
    # T1: ο extractor (FIXED path) ΔΕΝ πρέπει να δει το _ENTRY_2 duplicated -
    # κάθε raw_text πρέπει να περιέχει το block ΑΚΡΙΒΩΣ μία φορά.
    note_fixed, raw_fixed, _, _, _, _ = _fixed_and_broken_notes()
    assert len(raw_fixed) == 3, f"αναμένονταν 3 raw evaluation texts, βρέθηκαν {len(raw_fixed)}"
    entry2_occurrences = sum(raw.count("Σ.Α.\n01/01/2019") for raw in raw_fixed)
    assert entry2_occurrences == 1, (
        f"το entry2 anchor+date πρέπει να εμφανίζεται ΑΚΡΙΒΩΣ μία φορά στα raw_texts, "
        f"βρέθηκε {entry2_occurrences} φορές (overlap contamination)"
    )
    # MUTATION CHECK: το ΙΔΙΟ κείμενο μέσω του BROKEN (split) path πρέπει να
    # ΔΕΙΞΕΙ τη μόλυνση - αλλιώς η παραπάνω assertion θα ήταν αληθής ούτως ή
    # άλλως (vacuous), ανεξάρτητα από το αν διαβάζουμε unsplit ή split.
    _, _, _, raw_broken, _, _ = _fixed_and_broken_notes()
    entry2_occurrences_broken = sum(raw.count("Σ.Α.\n01/01/2019") for raw in raw_broken)
    assert entry2_occurrences_broken == 2, (
        "MUTATION CHECK ΑΠΕΤΥΧΕ: το BROKEN (split-fed) path έπρεπε να δείξει "
        f"2 occurrences του entry2 anchor (η μόλυνση που το fix αποτρέπει), βρέθηκαν "
        f"{entry2_occurrences_broken} - το fixture δεν αποδεικνύει πλέον τίποτα"
    )


def test_t2_chroma_path_still_has_overlapping_sub_chunks():
    # T2 (αρνητικός έλεγχος): το split_long_chunks (τροφοδοτεί το Chroma
    # path στο pipeline.py) ΔΕΝ πρέπει να αλλάξει - το overlap ΠΑΡΑΜΕΝΕΙ. Αν
    # κάποιος "διορθώσει" αφαιρώντας το overlap παντού (λάθος fix, ρητά
    # απαγορευμένο από το brief), αυτό το test πρέπει να σκάσει.
    pages = _build_pages()
    unsplit = chunk_by_section_unsplit(pages, DOC_ID)
    split_pieces = split_long_chunks(unsplit)
    pieces_with_entry2 = [p.text for p in split_pieces if _ENTRY_2 in p.text]
    assert len(pieces_with_entry2) == 2, (
        "το Chroma-bound split output πρέπει να ΕΞΑΚΟΛΟΥΘΕΙ να περιέχει το "
        f"overlap (_ENTRY_2 σε 2 pieces), βρέθηκε σε {len(pieces_with_entry2)} - "
        "το retrieval overlap αφαιρέθηκε, αυτό ΔΕΝ έπρεπε να συμβεί"
    )
    # chunk_by_section (public, αμετάβλητο API) πρέπει να παράγει ΑΚΡΙΒΩΣ το
    # ίδιο split αποτέλεσμα - regression guard για το εσωτερικό refactor.
    assert chunk_by_section(pages, DOC_ID) == split_pieces, (
        "chunk_by_section(pages, doc_id) πρέπει να παραμένει == "
        "split_long_chunks(chunk_by_section_unsplit(pages, doc_id)) μετά το refactor"
    )


def test_t3_anchor_safety_extractor_produces_exactly_n_blocks_not_ghost():
    # T3: bare "Σ.Α." (entry2) πέφτει μέσα στο overlap παράθυρο δύο
    # sub-chunks (επιβεβαιωμένο στο setup-sanity test). Ο FIXED path πρέπει
    # να παράγει ΑΚΡΙΒΩΣ 3 evaluation entries (entryA, entry2, entry3), ΟΧΙ
    # 4 (φάντασμα duplicate του entry2).
    note_fixed, _, note_broken, _, _, _ = _fixed_and_broken_notes()

    assert len(note_fixed.evaluations) == 3, (
        f"FIXED path: αναμένονταν 3 evaluations (N, όχι N+1 φάντασμα), "
        f"βρέθηκαν {len(note_fixed.evaluations)}"
    )
    periods_fixed = [e.period for e in note_fixed.evaluations]
    assert len(periods_fixed) == len(set(periods_fixed)), (
        f"FIXED path: δύο evaluations με ΤΗΝ ΙΔΙΑ περίοδο -> ghost duplicate, {periods_fixed}"
    )

    # MUTATION CHECK: το BROKEN (split-fed, παλιά καλωδίωση) path πάνω στο
    # ΙΔΙΟ κείμενο ΠΡΕΠΕΙ να παράγει το φάντασμα (4, όχι 3) - αλλιώς η
    # assertion του FIXED path παραπάνω δεν αποδεικνύει τίποτα.
    assert len(note_broken.evaluations) == 4, (
        "MUTATION CHECK ΑΠΕΤΥΧΕ: το BROKEN (split-fed) path έπρεπε να παράγει "
        f"το φάντασμα (4 evaluations), βρέθηκαν {len(note_broken.evaluations)} - "
        "το fixture δεν αποδεικνύει πλέον το anchor-safety issue"
    )
    periods_broken = [e.period for e in note_broken.evaluations]
    assert periods_broken.count("2019-01-01..2019-01-10") == 2, (
        f"MUTATION CHECK: το BROKEN path έπρεπε να διπλασιάσει ΣΥΓΚΕΚΡΙΜΕΝΑ την "
        f"περίοδο του entry2 (2019-01-01..2019-01-10), periods={periods_broken}"
    )


def test_t4_source_page_unchanged_per_entry():
    # T4: το source_page κάθε entry πρέπει να αντιστοιχεί στη σωστή αρχική
    # σελίδα, ανεξάρτητα από το ότι η σελίδα 2 έχει πλέον ΕΝΑ (unsplit)
    # chunk αντί για πολλά sub-chunks.
    note_fixed, _, _, _, _, _ = _fixed_and_broken_notes()
    assert len(note_fixed.evaluations) == 3
    entry_a, entry_2, entry_3 = note_fixed.evaluations
    assert entry_a.source_page == 1, f"entryA (σελ.1) πρέπει να έχει source_page=1, βρέθηκε {entry_a.source_page}"
    assert entry_2.source_page == 2, f"entry2 (σελ.2) πρέπει να έχει source_page=2, βρέθηκε {entry_2.source_page}"
    assert entry_3.source_page == 2, f"entry3 (σελ.2) πρέπει να έχει source_page=2, βρέθηκε {entry_3.source_page}"

    # MUTATION CHECK: αν η σελίδα ήταν λάθος υπολογισμένη (π.χ. αν
    # _page_for_offset έσπαγε λόγω του unsplit μεγέθους), θα περιμέναμε
    # τουλάχιστον ΕΝΑ entry με λάθος σελίδα - ελέγχουμε ρητά ότι ΚΑΝΕΝΑ δεν
    # έχει σελίδα εκτός {1, 2}.
    assert {entry_a.source_page, entry_2.source_page, entry_3.source_page} <= {1, 2}


def run_all():
    tests = [
        test_setup_sanity_page2_actually_exceeds_max_chunk_chars_and_splits,
        test_t1_extractor_sees_no_duplicate_block_with_unsplit_chunks,
        test_t2_chroma_path_still_has_overlapping_sub_chunks,
        test_t3_anchor_safety_extractor_produces_exactly_n_blocks_not_ghost,
        test_t4_source_page_unchanged_per_entry,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
