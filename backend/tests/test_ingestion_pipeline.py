"""End-to-end mini test/sample flow για το ingestion pipeline της Φάσης 2.

Καλύπτει, πάνω σε 2 dummy (born-digital, όχι σαρωμένα) PDF:
  - known-sections διαδρομή: δομημένη εξαγωγή + section/score chunking.
  - fallback διαδρομή: άγνωστο layout -> structural chunking, μηδενική
    απώλεια περιεχομένου.
  - idempotent re-ingestion: re-run του ίδιου PDF δεν διπλασιάζει ούτε τις
    SQLite εγγραφές, ούτε τα ChromaDB chunks.

Χρησιμοποιεί FakeEmbedder (deterministic, χωρίς ML) αντί για το πραγματικό
BAAI/bge-m3, ώστε το test να τρέχει γρήγορα και χωρίς εξάρτηση από download
μοντέλου ~2GB· η πραγματική `Embedder` (app.ingestion.embedder) χρησιμοποιεί
το ίδιο `.embed()` interface, οπότε αντικαθίσταται 1-προς-1 σε πραγματική χρήση.

Εκτελείται standalone: `python tests/test_ingestion_pipeline.py`
"""

import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402

from app.db.database import get_connection, init_db  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402
from app.models.evaluation import KNOWN_SECTIONS  # noqa: E402

_GREEK_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


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
    raise RuntimeError("Δεν βρέθηκε γραμματοσειρά με ελληνικά γλυφή για τη δημιουργία dummy PDF")


def _make_pdf(path: Path, text: str) -> None:
    font_path = _greek_font()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(50, 50, 545, 792),
        text,
        fontsize=11,
        fontname="F0",
        fontfile=font_path,
    )
    doc.save(path)
    doc.close()


KNOWN_SECTION_DOC_TEXT = f"""Ονοματεπώνυμο: Παπαδόπουλος Γιώργος
Περίοδος Αξιολόγησης: 2025
Γνωμάτευση: Α

{KNOWN_SECTIONS[0]}
Βαθμολογία: 4
Ο εργαζόμενος πέτυχε τους στόχους του με συνέπεια.

{KNOWN_SECTIONS[1]}
Σχόλιο αξιολογητή για την ενότητα.
(5/5)

Συνολικό Σχόλιο: Πολύ καλή συνολική απόδοση κατά τη διάρκεια της περιόδου.
"""

FALLBACK_DOC_TEXT = """Ονοματεπώνυμο: Κωνσταντίνου Μαρία
Περίοδος Αξιολόγησης: 2025
Γνωμάτευση: Β

Γενικές παρατηρήσεις για την πορεία του έργου κατά το έτος.

Προτάσεις βελτίωσης για την επόμενη περίοδο αξιολόγησης.

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
        assert result_a.chunk_count == 2, (
            f"αναμένονταν 2 known-section chunks, βρέθηκαν {result_a.chunk_count}"
        )
        assert len(result_a.report.sections) == 2
        assert result_a.report.gnmatefsi == "A"
        assert result_a.report.person_name == "Παπαδόπουλος Γιώργος"
        print(f"OK  known-sections extraction: {result_a.doc_id}, chunks={result_a.chunk_count}")

        _assert_sqlite_state(
            db_path,
            person_id=result_a.person_id,
            period=result_a.period,
            expected_evaluations=1,
            expected_scores=2,
        )
        _assert_chroma_state(
            chroma_dir,
            doc_id=result_a.doc_id,
            expected_count=2,
            expect_fallback=False,
        )
        print("OK  known-sections SQLite + ChromaDB persistence")

        # --- fallback διαδρομή ---
        result_b = run_ingestion(
            doc_b_path, embedder=embedder, db_path=db_path, chroma_dir=chroma_dir
        )
        assert result_b.fallback_used, "αναμένονταν fallback στο doc_b (άγνωστο layout)"
        # 4 blocks: το header (3 γραμμές με τα scalar labels) + 3 παράγραφοι σώματος.
        assert result_b.chunk_count == 4, (
            f"αναμένονταν 4 παραγράφους, βρέθηκαν {result_b.chunk_count}"
        )
        assert result_b.report.sections == [], "δεν αναμένονταν structured scores στο fallback doc"
        assert result_b.report.gnmatefsi == "B"
        print(f"OK  fallback extraction: {result_b.doc_id}, chunks={result_b.chunk_count}")

        _assert_sqlite_state(
            db_path,
            person_id=result_b.person_id,
            period=result_b.period,
            expected_evaluations=1,
            expected_scores=0,
        )
        _assert_chroma_state(
            chroma_dir,
            doc_id=result_b.doc_id,
            expected_count=4,
            expect_fallback=True,
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
            period=result_a.period,
            expected_evaluations=1,  # όχι 2 -> δεν διπλασιάστηκε
            expected_scores=2,  # όχι 4 -> replace, όχι append
        )
        _assert_chroma_state(
            chroma_dir,
            doc_id=result_a.doc_id,
            expected_count=2,  # όχι 4 -> delete-then-add, όχι accumulate
            expect_fallback=False,
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
    period: str,
    expected_evaluations: int,
    expected_scores: int,
) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        eval_rows = conn.execute(
            "SELECT id FROM evaluations WHERE person_id = ? AND period = ?",
            (person_id, period),
        ).fetchall()
        assert len(eval_rows) == expected_evaluations, (
            f"αναμένονταν {expected_evaluations} evaluation rows, βρέθηκαν {len(eval_rows)}"
        )
        if eval_rows:
            eval_id = eval_rows[0]["id"]
            scores_count = conn.execute(
                "SELECT COUNT(*) AS n FROM scores WHERE eval_id = ?", (eval_id,)
            ).fetchone()["n"]
            assert scores_count == expected_scores, (
                f"αναμένονταν {expected_scores} scores, βρέθηκαν {scores_count}"
            )
    finally:
        conn.close()


def _assert_chroma_state(
    chroma_dir: Path,
    doc_id: str,
    expected_count: int,
    expect_fallback: bool,
) -> None:
    from app.ingestion.vectorstore import get_collection

    collection = get_collection(chroma_dir)
    result = collection.get(where={"doc_id": doc_id})
    ids = result["ids"]
    assert len(ids) == expected_count, (
        f"doc_id={doc_id}: αναμένονταν {expected_count} chunks στο Chroma, βρέθηκαν {len(ids)}"
    )
    for metadata in result["metadatas"]:
        assert metadata["fallback"] is expect_fallback
        assert metadata["doc_id"] == doc_id
        assert "person_id" in metadata and "period" in metadata  # Φάση 3 isolation filter


if __name__ == "__main__":
    run_all()
