"""Regression test για την ΡΗΤΗ διόρθωση του CHUNK_SPLIT_FIX: το
`run_ingestion` (pipeline.py) πρέπει να κάνει ΜΙΑ ΜΟΝΟ κλήση section-detection
(`chunk_by_section_unsplit`) και να παράγει τις δύο όψεις (unsplit για τον
extractor, split για το Chroma path) πάνω στο ΙΔΙΟ αντικείμενο - όχι δύο
ανεξάρτητες κλήσεις detection που θα μπορούσαν να αποκλίνουν (βλ.
private/prompts/CHUNK_SPLIT_FIX.md, η ρητή διόρθωση του χρήστη μετά το HARD
STOP #1).

Monkeypatches `chunk_by_section_unsplit`/`extract_summary_note` μέσα στο
namespace του pipeline module ώστε να μετρήσει (α) πόσες φορές καλείται το
detection, (β) αν ο extractor λαμβάνει ΤΟ ΙΔΙΟ list object (by identity, `is`)
που επέστρεψε η detection call - όχι ένα δεύτερο, ανεξάρτητα υπολογισμένο.
Δεν χρειάζεται πραγματικό PDF: το `parse_pdf` επίσης monkeypatch-άρεται.

Εκτελείται standalone (χωρίς pytest): `python tests/test_pipeline_single_detection_call.py`
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import dataclass  # noqa: E402

import fitz  # noqa: E402

import app.ingestion.pipeline as pipeline  # noqa: E402
from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402


@dataclass(frozen=True)
class _FakeParsedPage:
    page: int
    text: str


class _FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 1.0] for _ in texts]


_DOC_TEXT = f"""ΑΔΙΑΒΑΘΜΗΤΟ - ΣΥΝΘΕΤΙΚΑ ΔΕΔΟΜΕΝΑ
ΠΕΡΙΛΗΠΤΙΚΟ ΣΗΜΕΙΩΜΑ

Υπηρεσία: ΓΕΝΙΚΟ ΕΠΙΤΕΛΕΙΟ ΝΑΥΤΙΚΟΥ
Α.Γ.Μ.: Μ-00099
Ημερομηνία: 01/07/2025

ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ
Ονοματεπώνυμο: Δοκιμαστικός Χρήστος

{KNOWN_SECTIONS[6]}
Περίοδος: 01/01/2023 - 31/12/2023
Τύπος: Ε.Α.
Χαρακτηρισμός: ΕΞΑΙΡΕΤΟΣ (95)
Αξιολογών: Πλοίαρχος, Ιωάννης Καραγιάννης, Διοικητής
"""


def _run_with_instrumentation():
    """Τρέχει run_ingestion με monkeypatched parse_pdf/chunk_by_section_unsplit/
    extract_summary_note, επιστρέφει (result, call_log) όπου call_log
    καταγράφει # κλήσεων detection και identity του section_chunks object
    που έλαβε ο extractor."""
    call_log = {"unsplit_calls": 0, "unsplit_result_id": None, "extractor_received_id": None}

    original_unsplit = pipeline.chunk_by_section_unsplit
    original_extract = pipeline.extract_summary_note

    def spy_unsplit(pages, doc_id):
        call_log["unsplit_calls"] += 1
        result = original_unsplit(pages, doc_id)
        call_log["unsplit_result_id"] = id(result)
        return result

    def spy_extract(full_text, section_chunks):
        call_log["extractor_received_id"] = id(section_chunks)
        return original_extract(full_text, section_chunks)

    pipeline.chunk_by_section_unsplit = spy_unsplit
    pipeline.extract_summary_note = spy_extract
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="evalassist_wiring_test_"))
        try:
            pdf_path = tmp_dir / "dummy.pdf"
            # Πραγματικό (έστω κενό) PDF, ΟΧΙ raw bytes: το
            # extract_duty_categories_from_pdf (καλείται μέσα στο
            # run_ingestion) ανοίγει το ΙΔΙΟ pdf_path ανεξάρτητα με fitz -
            # raw bytes θα προκαλούσαν θορυβώδες (αν και harmless, caught)
            # FzErrorFormat traceback σε κάθε τρέξιμο του test.
            _blank_doc = fitz.open()
            _blank_doc.new_page()
            _blank_doc.save(pdf_path)
            _blank_doc.close()
            original_parse_pdf = pipeline.parse_pdf
            pipeline.parse_pdf = lambda _path: [_FakeParsedPage(page=1, text=_DOC_TEXT)]
            try:
                result = pipeline.run_ingestion(
                    pdf_path,
                    embedder=_FakeEmbedder(),
                    db_path=tmp_dir / "test.db",
                    chroma_dir=tmp_dir / "chroma",
                )
            finally:
                pipeline.parse_pdf = original_parse_pdf
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)
    finally:
        pipeline.chunk_by_section_unsplit = original_unsplit
        pipeline.extract_summary_note = original_extract

    return result, call_log


def test_chunk_by_section_unsplit_called_exactly_once():
    # Η ρητή διόρθωση του χρήστη: ΟΧΙ διπλή κλήση section-detection. Δύο
    # ανεξάρτητες κλήσεις θα μπορούσαν να αποκλίνουν αν το κείμενο/state
    # άλλαζε ανάμεσά τους.
    _, call_log = _run_with_instrumentation()
    assert call_log["unsplit_calls"] == 1, (
        f"αναμενόταν ΑΚΡΙΒΩΣ 1 κλήση chunk_by_section_unsplit, "
        f"βρέθηκαν {call_log['unsplit_calls']}"
    )


def test_extractor_receives_same_object_as_detection_returned():
    # Ο extractor πρέπει να λάβει το ΙΔΙΟ object (by identity) που επέστρεψε
    # η μοναδική detection call - όχι ένα δεύτερο list με ίδιο περιεχόμενο
    # αλλά διαφορετική ταυτότητα (που θα σήμαινε κρυφή δεύτερη κλήση/αντιγραφή).
    _, call_log = _run_with_instrumentation()
    assert call_log["unsplit_result_id"] is not None
    assert call_log["extractor_received_id"] == call_log["unsplit_result_id"], (
        "ο extractor έλαβε section_chunks με ΔΙΑΦΟΡΕΤΙΚΗ ταυτότητα από αυτό που "
        "επέστρεψε το chunk_by_section_unsplit - πιθανή απόκλιση των δύο όψεων"
    )


def test_pipeline_still_produces_correct_evaluation():
    # Sanity: η instrumentation δεν έσπασε το ίδιο το pipeline αποτέλεσμα.
    result, _ = _run_with_instrumentation()
    assert result.person_id == "Μ-00099"
    assert len(result.summary_note.evaluations) == 1
    assert result.summary_note.evaluations[0].characterization == "ΕΞΑΙΡΕΤΟΣ"


def run_all():
    tests = [
        test_chunk_by_section_unsplit_called_exactly_once,
        test_extractor_receives_same_object_as_detection_returned,
        test_pipeline_still_produces_correct_evaluation,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
