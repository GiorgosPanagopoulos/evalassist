"""End-to-end mini test/sample flow για το ingestion pipeline πάνω στο schema
Περιληπτικού Σημειώματος.

Καλύπτει, πάνω σε 2 dummy (born-digital, όχι σαρωμένα) PDF:
  - known-sections διαδρομή: δομημένη εξαγωγή SummaryNote (person, evaluation
    entry, field_scores) + section chunking, με period = 'YYYY-MM-DD..YYYY-MM-DD'
    για το evaluation entry και period='career' για τις υπόλοιπες ενότητες.
  - fallback διαδρομή: άγνωστο layout για τις ενότητες (η ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ
    παραμένει parseable ανεξάρτητα, βλ. app.ingestion.extractor) -> structural
    chunking, μηδενική απώλεια περιεχομένου, καμία evaluation entry.
  - idempotent re-ingestion: re-run του ίδιου PDF δεν διπλασιάζει ούτε τις
    SQLite εγγραφές, ούτε τα ChromaDB chunks.

Χρησιμοποιεί FakeEmbedder (deterministic, χωρίς ML) αντί για το πραγματικό
BAAI/bge-m3, ώστε το test να τρέχει γρήγορα και χωρίς εξάρτηση από download
μοντέλου ~2GB· η πραγματική `Embedder` (app.ingestion.embedder) χρησιμοποιεί
το ίδιο `.embed()` interface, οπότε αντικαθίσταται 1-προς-1 σε πραγματική χρήση.

Εκτελείται standalone: `python tests/test_ingestion_pipeline.py`
"""

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402

from app.db.database import get_connection, init_db  # noqa: E402
from app.ingestion.pipeline import CAREER_PERIOD, run_ingestion  # noqa: E402
from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402

_GREEK_FONT_CANDIDATES = [
    # macOS
    str(Path.home() / "Library" / "Fonts" / "DejaVuSans.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    # Windows
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
]

_env_font = os.environ.get("EVALASSIST_TEST_FONT")
if _env_font:
    _GREEK_FONT_CANDIDATES.insert(0, _env_font)


class FakeEmbedder:
    """Deterministic stand-in για το BAAI/bge-m3 embedding model (test-only)."""

    DIM = 16

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([b / 255.0 for b in digest[: self.DIM]])
        return vectors


def _greek_font() -> str:
    for candidate in _GREEK_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Δεν βρέθηκε γραμματοσειρά με ελληνικά γλυφή για τη δημιουργία dummy PDF. "
        "Ορίστε EVALASSIST_TEST_FONT με το path μιας γραμματοσειράς που έχει ελληνικά γλυφή."
    )


def _make_pdf(path: Path, text: str) -> None:
    font_path = _greek_font()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(50, 50, 545, 792),
        text,
        fontsize=8,
        fontname="F0",
        fontfile=font_path,
    )
    doc.save(path)
    doc.close()


ENTRY_PERIOD = "2023-01-01..2023-12-31"

KNOWN_SECTION_DOC_TEXT = f"""ΑΔΙΑΒΑΘΜΗΤΟ - ΣΥΝΘΕΤΙΚΑ ΔΕΔΟΜΕΝΑ
ΠΕΡΙΛΗΠΤΙΚΟ ΣΗΜΕΙΩΜΑ

Υπηρεσία: ΓΕΝΙΚΟ ΕΠΙΤΕΛΕΙΟ ΝΑΥΤΙΚΟΥ
Α.Γ.Μ.: Μ-00001
Ημερομηνία: 01/07/2025

ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ
Ονοματεπώνυμο: Παπαδόπουλος Γιώργος
Βαθμός: Πλωτάρχης

{KNOWN_SECTIONS[0]}
Βαθμός: Πλωτάρχης | Ημ/νία Απόφασης: 01/03/2020 | Απόφαση: Προακτέος | Ημ/νία Προαγωγής: 15/03/2020

{KNOWN_SECTIONS[2]}
Πτυχίο: Σχολή Ναυτικών Δοκίμων | Έτος: 2010 | Βαθμολογία: Λίαν Καλώς

{KNOWN_SECTIONS[6]}
Περίοδος: 01/01/2023 - 31/12/2023
Τύπος: Ε.Α.
Βαθμός: Πλωτάρχης
Χαρακτηρισμός: ΕΞΑΙΡΕΤΟΣ (95)
Μονάδα: Φ/Γ ΣΥΝΘΕΤΙΚΟ
Καθήκοντα: Κυβερνήτης, Επόπτης
Αξιολογών: Πλοίαρχος, Ιωάννης Καραγιάννης, Διοικητής
ΠΕΔΙΟ: 141 | ΠΕΡΙΓΡΑΦΗ: Γενική Ικανότητα | ΒΑΘΜΟΛΟΓΙΑ: 95
Ελαττώματα: Κανένα
Σημειώσεις Αξιολογούντος: Πολύ καλή συνολική απόδοση κατά τη διάρκεια της περιόδου.
"""

FALLBACK_DOC_TEXT = """ΑΔΙΑΒΑΘΜΗΤΟ - ΣΥΝΘΕΤΙΚΑ ΔΕΔΟΜΕΝΑ
ΠΕΡΙΛΗΠΤΙΚΟ ΣΗΜΕΙΩΜΑ

Υπηρεσία: ΓΕΝΙΚΟ ΕΠΙΤΕΛΕΙΟ ΝΑΥΤΙΚΟΥ
Α.Γ.Μ.: Μ-00002
Ημερομηνία: 01/07/2025

ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ
Ονοματεπώνυμο: Κωνσταντίνου Μαρία

Γενικές παρατηρήσεις για την πορεία της σταδιοδρομίας κατά το έτος.

Προτάσεις για την επόμενη τοποθέτηση.

Πρόσθετα σχόλια που δεν εντάσσονται σε συγκεκριμένη ενότητα.
"""


def run_all():
    tmp_dir = Path(tempfile.mkdtemp(prefix="evalassist_ingestion_test_"))
    try:
        db_path = tmp_dir / "test.db"
        chroma_dir = tmp_dir / "chroma"
        embedder = FakeEmbedder()

        doc_a_path = tmp_dir / "known_sections.pdf"
        doc_b_path = tmp_dir / "fallback.pdf"
        _make_pdf(doc_a_path, KNOWN_SECTION_DOC_TEXT)
        _make_pdf(doc_b_path, FALLBACK_DOC_TEXT)

        # --- known-sections διαδρομή ---
        result_a = run_ingestion(
            doc_a_path, embedder=embedder, db_path=db_path, chroma_dir=chroma_dir
        )
        assert not result_a.fallback_used, "δεν αναμένονταν fallback στο doc_a"
        assert result_a.person_id == "Μ-00001"
        assert result_a.summary_note.person.name == "Παπαδόπουλος Γιώργος"
        assert len(result_a.summary_note.evaluations) == 1
        entry = result_a.summary_note.evaluations[0]
        assert entry.period == ENTRY_PERIOD
        assert entry.characterization == "ΕΞΑΙΡΕΤΟΣ"
        assert entry.score == 95
        assert entry.field_scores and entry.field_scores[0].field_code == "141"
        assert set(result_a.periods) == {ENTRY_PERIOD, CAREER_PERIOD}
        print(f"OK  known-sections extraction: {result_a.doc_id}, chunks={result_a.chunk_count}")

        _assert_sqlite_state(
            db_path,
            person_id=result_a.person_id,
            period=ENTRY_PERIOD,
            expect_evaluation=True,
            expected_field_scores=1,
        )
        _assert_chroma_state(chroma_dir, doc_id=result_a.doc_id, expect_min_count=2)
        print("OK  known-sections SQLite + ChromaDB persistence")

        # --- fallback διαδρομή (άγνωστο section layout, header παραμένει parseable) ---
        result_b = run_ingestion(
            doc_b_path, embedder=embedder, db_path=db_path, chroma_dir=chroma_dir
        )
        assert result_b.fallback_used, "αναμένονταν fallback στο doc_b (άγνωστο section layout)"
        assert result_b.person_id == "Μ-00002"
        assert result_b.summary_note.person.name == "Κωνσταντίνου Μαρία"
        assert result_b.summary_note.evaluations == [], (
            "δεν αναμένονταν evaluation entries στο fallback doc"
        )
        print(f"OK  fallback extraction: {result_b.doc_id}, chunks={result_b.chunk_count}")

        _assert_sqlite_state(
            db_path, person_id=result_b.person_id, period=None, expect_evaluation=False,
            expected_field_scores=0,
        )
        _assert_chroma_state(chroma_dir, doc_id=result_b.doc_id, expect_min_count=1)
        _assert_no_content_loss(
            chroma_dir,
            doc_id=result_b.doc_id,
            expected_substrings=[
                "Α.Γ.Μ.: Μ-00002",
                "Γενικές παρατηρήσεις για την πορεία της σταδιοδρομίας",
                "Προτάσεις για την επόμενη τοποθέτηση",
                "Πρόσθετα σχόλια που δεν εντάσσονται σε συγκεκριμένη ενότητα",
            ],
        )
        print("OK  fallback SQLite + ChromaDB persistence (zero content loss)")

        # --- idempotency: re-run του ίδιου PDF ---
        result_a2 = run_ingestion(
            doc_a_path, embedder=embedder, db_path=db_path, chroma_dir=chroma_dir
        )
        assert result_a2.doc_id == result_a.doc_id, "doc_id πρέπει να είναι ντετερμινιστικό"
        _assert_sqlite_state(
            db_path,
            person_id=result_a.person_id,
            period=ENTRY_PERIOD,
            expect_evaluation=True,
            expected_field_scores=1,  # όχι 2 -> replace, όχι append
        )
        _assert_chroma_state(
            chroma_dir, doc_id=result_a.doc_id, expect_min_count=2, exact_count=result_a.chunk_count
        )
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            persons_count = conn.execute(
                "SELECT COUNT(*) AS n FROM persons WHERE person_id = ?", (result_a.person_id,)
            ).fetchone()["n"]
            assert persons_count == 1, (
                f"idempotency: αναμένονταν 1 person row, βρέθηκαν {persons_count}"
            )
        print("OK  idempotent re-ingestion (SQLite + ChromaDB δεν διπλασιάστηκαν)")

        print("\nΌλα τα tests πέρασαν.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _assert_sqlite_state(
    db_path: Path,
    person_id: str,
    period: str | None,
    expect_evaluation: bool,
    expected_field_scores: int,
) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if not expect_evaluation:
            eval_count = conn.execute(
                "SELECT COUNT(*) AS n FROM evaluations WHERE person_id = ?", (person_id,)
            ).fetchone()["n"]
            assert eval_count == 0, f"δεν αναμένονταν evaluations, βρέθηκαν {eval_count}"
            return

        eval_rows = conn.execute(
            "SELECT id FROM evaluations WHERE person_id = ? AND period = ?",
            (person_id, period),
        ).fetchall()
        assert len(eval_rows) == 1, f"αναμένονταν 1 evaluation row, βρέθηκαν {len(eval_rows)}"
        eval_id = eval_rows[0]["id"]
        fs_count = conn.execute(
            "SELECT COUNT(*) AS n FROM field_scores WHERE eval_id = ?", (eval_id,)
        ).fetchone()["n"]
        assert fs_count == expected_field_scores, (
            f"αναμένονταν {expected_field_scores} field_scores, βρέθηκαν {fs_count}"
        )
    finally:
        conn.close()


def _assert_chroma_state(
    chroma_dir: Path,
    doc_id: str,
    expect_min_count: int,
    exact_count: int | None = None,
) -> None:
    from app.ingestion.vectorstore import get_collection

    collection = get_collection(chroma_dir)
    result = collection.get(where={"doc_id": doc_id})
    ids = result["ids"]
    if exact_count is not None:
        assert len(ids) == exact_count, (
            f"doc_id={doc_id}: αναμένονταν {exact_count} chunks (idempotent re-run), βρέθηκαν {len(ids)}"
        )
    else:
        assert len(ids) >= expect_min_count, (
            f"doc_id={doc_id}: αναμένονταν >= {expect_min_count} chunks, βρέθηκαν {len(ids)}"
        )
    for metadata in result["metadatas"]:
        assert metadata["doc_id"] == doc_id
        for key in ("person_id", "person_name", "period", "section", "score", "page"):
            assert key in metadata, f"metadata λείπει το κλειδί {key!r}"


def _assert_no_content_loss(chroma_dir: Path, doc_id: str, expected_substrings: list[str]) -> None:
    from app.ingestion.vectorstore import get_collection

    collection = get_collection(chroma_dir)
    result = collection.get(where={"doc_id": doc_id})
    joined = "\n".join(result["documents"])
    for substring in expected_substrings:
        assert substring in joined, f"περιεχόμενο χάθηκε στο fallback chunking: {substring!r}"


if __name__ == "__main__":
    run_all()
