"""RAG pipeline quality evaluation harness (Phase 5, round 2).

Seeds a temp SQLite database and a temp ChromaDB collection with synthetic
Greek evaluation data, then runs every case in golden_set.json through the
real `SemanticRetriever` (real ChromaDB collection, real IsolationScope where
filter) using deterministic fakes for the embedder/reranker/LLM. The goal is
measuring the retrieval PIPELINE end to end, not the quality of BAAI/bge-m3
or the local Ollama model.

Metrics per case and in aggregate:
  - citation_recall: |retrieved doc_ids intersect expected| / |expected|
  - citation_precision: |retrieved doc_ids intersect expected| / |retrieved|
  - isolation_leaks: retrieved doc_ids that truly belong to a different
    person_id/period than the one that was scoped. Safety-critical, must be 0.
  - empty_scope_correct: every empty-scope case returns citations == [].

Exit code is nonzero if isolation_leaks > 0 or empty_scope_correct fails,
regardless of recall/precision (those are reported only; thresholds come
later once real ingested data exists).

Standalone script, no pytest: `python evals/run_evals.py`
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

# Must be set before chromadb is imported: avoids a slow/blocked outbound
# telemetry call on PersistentClient construction in sandboxed CI runners.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db import repository  # noqa: E402
from app.db.database import get_connection, init_db  # noqa: E402
from app.ingestion.vectorstore import add_chunks, get_collection  # noqa: E402
from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.semantic import SemanticRetriever  # noqa: E402

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.json"

EMBED_DIM = 256
STEM_LEN = 6

# Synthetic corpus: one entry per document, each with its own chunks
# (page, section, text). Covers every golden_set.json case, including
# isolation-bait pairs (near-identical text across people/periods) and one
# person (P005) with no documents at all for the empty-scope case.
CORPUS_DOCS = [
    {
        "doc_id": "P001-2025-MAIN",
        "person_id": "P001",
        "person_name": "Μαρία Παπαδοπούλου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Στοχοθεσία",
                "text": (
                    "Η Μαρία πέτυχε όλους τους ετήσιους στόχους της για το 2025, "
                    "με έμφαση στη βελτίωση της παραγωγικότητας της ομάδας."
                ),
            },
            {
                "page": 2,
                "section": "Ηγετική Ικανότητα",
                "text": (
                    "Επέδειξε εξαιρετική ηγετική ικανότητα καθοδηγώντας την ομάδα "
                    "σε δύσκολες συνθήκες κατά το 2025."
                ),
            },
        ],
    },
    {
        "doc_id": "P001-2025-PEER",
        "person_id": "P001",
        "person_name": "Μαρία Παπαδοπούλου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Συνεργασία",
                "text": (
                    "Οι συνάδελφοι αξιολόγησαν θετικά τη συνεργασία της Μαρίας "
                    "σε ομαδικά έργα κατά το 2025."
                ),
            },
        ],
    },
    {
        "doc_id": "P002-2025-MAIN",
        "person_id": "P002",
        "person_name": "Γιώργος Νικολάου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Στοχοθεσία",
                "text": (
                    "Ο Γιώργος πέτυχε όλους τους ετήσιους στόχους του για το 2025, "
                    "με έμφαση στη βελτίωση της παραγωγικότητας της ομάδας."
                ),
            },
            {
                "page": 2,
                "section": "Συνεργασία",
                "text": "Συνεργάστηκε αποτελεσματικά με άλλα τμήματα κατά τη διάρκεια του 2025.",
            },
        ],
    },
    {
        "doc_id": "P001-2024-MAIN",
        "person_id": "P001",
        "person_name": "Μαρία Παπαδοπούλου",
        "period": "2024",
        "chunks": [
            {
                "page": 1,
                "section": "Στοχοθεσία",
                "text": "Το 2024 η Μαρία πέτυχε μερικώς τους στόχους της λόγω αλλαγής ρόλου στην ομάδα.",
            },
        ],
    },
    {
        "doc_id": "P003-2024-MAIN",
        "person_id": "P003",
        "person_name": "Ελένη Κωνσταντίνου",
        "period": "2024",
        "chunks": [
            {
                "page": 1,
                "section": "Συνεργασία",
                "text": "Η Ελένη συνεργάστηκε άψογα με τους συναδέλφους της καθ' όλη τη διάρκεια του 2024.",
            },
            {
                "page": 2,
                "section": "Σχέδιο Ανάπτυξης",
                "text": (
                    "Προτείνεται συμμετοχή σε πρόγραμμα mentoring για ανάπτυξη "
                    "διοικητικών δεξιοτήτων το 2024."
                ),
            },
        ],
    },
    {
        "doc_id": "P004-2025-MAIN",
        "person_id": "P004",
        "person_name": "Κώστας Δημητρίου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Δυνατά Σημεία",
                "text": (
                    "Ο Κώστας διακρίνεται για την αναλυτική σκέψη και την προσοχή στη "
                    "λεπτομέρεια κατά την εκτέλεση των καθηκόντων."
                ),
            },
            {
                "page": 2,
                "section": "Σημεία Βελτίωσης",
                "text": "Χρειάζεται βελτίωση στη διαχείριση χρόνου κατά τις περιόδους υψηλού φόρτου εργασίας.",
            },
            {
                "page": 3,
                "section": "Στοχοθεσία",
                "text": "Ο Κώστας πέτυχε τους περισσότερους στόχους του για το 2025 με μικρές καθυστερήσεις.",
            },
        ],
    },
    {
        "doc_id": "P004-2025-PEER",
        "person_id": "P004",
        "person_name": "Κώστας Δημητρίου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Συνεργασία",
                "text": "Συνεργάζεται αποτελεσματικά με τους συναδέλφους στα κοινά έργα της ομάδας.",
            },
        ],
    },
    {
        "doc_id": "P004-2025-SELF",
        "person_id": "P004",
        "person_name": "Κώστας Δημητρίου",
        "period": "2025",
        "chunks": [
            {
                "page": 1,
                "section": "Αυτοαξιολόγηση",
                "text": "Ο ίδιος θεωρεί ότι βελτιώθηκε σημαντικά στη διαχείριση χρόνου κατά το τελευταίο τρίμηνο.",
            },
            {
                "page": 2,
                "section": "Στόχοι Επόμενης Περιόδου",
                "text": "Θέτει ως στόχο την περαιτέρω ανάπτυξη δεξιοτήτων διαχείρισης έργων.",
            },
        ],
    },
    {
        "doc_id": "P002-2024-MAIN",
        "person_id": "P002",
        "person_name": "Γιώργος Νικολάου",
        "period": "2024",
        "chunks": [
            {
                "page": 1,
                "section": "Στοχοθεσία",
                "text": "Ο Γιώργος το 2024 υπερκάλυψε τους στόχους του σε πωλήσεις με σημαντική αύξηση εσόδων.",
            },
        ],
    },
    # P005 has no documents at all -> backs the empty_scope_p005_2025 case.
]


def _normalize_token(token: str) -> str:
    """Lowercase, strip Greek diacritics, truncate to a crude stem.

    Truncating absorbs simple suffix inflection (e.g. genitive "Κώστα" vs
    nominative "Κώστας") without pulling in a real stemmer/tokenizer.
    """
    decomposed = unicodedata.normalize("NFD", token.lower())
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_accents[:STEM_LEN]


def _tokenize(text: str) -> list[str]:
    words = "".join(ch if ch.isalnum() else " " for ch in text).split()
    return [_normalize_token(w) for w in words if w]


class BagOfWordsEmbedder:
    """Deterministic, dependency-free stand-in for BAAI/bge-m3.

    Hashes normalized word stems into a fixed-size bucket vector so chunks
    sharing vocabulary end up with cosine-similar embeddings. Enough to
    exercise the retrieval pipeline without a real embedding model.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * EMBED_DIM
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBED_DIM
            vector[bucket] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class LexicalOverlapReranker:
    """Deterministic stand-in for the bge-reranker cross-encoder: ranks by
    shared word-stem count with the query."""

    def rerank(self, query: str, docs: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        if not docs:
            return []
        query_tokens = set(_tokenize(query))
        scored = [(i, float(len(query_tokens & set(_tokenize(doc))))) for i, doc in enumerate(docs)]
        ranked = sorted(scored, key=lambda pair: (-pair[1], pair[0]))
        return ranked[:top_k]


class EchoLLM:
    """Echoes the grounded prompt back verbatim instead of calling a real
    model, so the generated answer is fully deterministic."""

    model_name = "echo-fake-llm"

    def generate(self, system: str, user: str) -> str:
        return user


def _seed(db_path: Path, chroma_dir: Path):
    init_db(db_path)
    conn = get_connection(db_path)
    collection = get_collection(chroma_dir)
    embedder = BagOfWordsEmbedder()

    seen_persons: set[str] = set()
    seen_evals: set[tuple[str, str]] = set()
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for doc in CORPUS_DOCS:
        if doc["person_id"] not in seen_persons:
            repository.upsert_person(conn, doc["person_id"], doc["person_name"])
            seen_persons.add(doc["person_id"])
        eval_key = (doc["person_id"], doc["period"])
        if eval_key not in seen_evals:
            repository.upsert_evaluation(conn, doc["person_id"], doc["period"], "A", None)
            seen_evals.add(eval_key)
        repository.upsert_document(
            conn, doc["doc_id"], doc["person_id"], doc["period"], "synthetic", len(doc["chunks"])
        )
        for chunk in doc["chunks"]:
            ids.append(f"{doc['doc_id']}:{chunk['page']}")
            documents.append(chunk["text"])
            metadatas.append(
                {
                    "person_id": doc["person_id"],
                    "period": doc["period"],
                    "doc_id": doc["doc_id"],
                    "page": chunk["page"],
                    "section": chunk["section"],
                }
            )
    conn.commit()

    embeddings = embedder.embed(documents)
    add_chunks(collection, ids, documents, embeddings, metadatas)
    return conn, collection


def _doc_truth_map(conn) -> dict[str, tuple[str, str]]:
    rows = conn.execute("SELECT doc_id, person_id, period FROM documents").fetchall()
    return {row["doc_id"]: (row["person_id"], row["period"]) for row in rows}


def _run_case(retriever: SemanticRetriever, case: dict, doc_truth: dict) -> dict:
    scope = IsolationScope(person_id=case["person_id"], period=case["period"])
    result = retriever.query(case["question"], scope)

    retrieved = set(result.retrieved_doc_ids)
    expected = set(case["expected_doc_ids"])

    leaks = sum(
        1 for doc_id in retrieved if doc_truth.get(doc_id) != (case["person_id"], case["period"])
    )

    recall: float | None
    precision: float | None
    empty_ok: bool | None
    if expected:
        recall = len(retrieved & expected) / len(expected)
        precision = (len(retrieved & expected) / len(retrieved)) if retrieved else 0.0
        empty_ok = None
    else:
        recall = None
        precision = None
        empty_ok = retrieved == set() and result.citations == []

    return {
        "id": case["id"],
        "recall": recall,
        "precision": precision,
        "leaks": leaks,
        "empty_ok": empty_ok,
        "retrieved_doc_ids": sorted(retrieved),
        "expected_doc_ids": sorted(expected),
    }


def _format_metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def run_evals() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="evalassist_evals_"))
    try:
        db_path = tmp_dir / "eval.db"
        chroma_dir = tmp_dir / "chroma"
        conn, collection = _seed(db_path, chroma_dir)
        doc_truth = _doc_truth_map(conn)

        retriever = SemanticRetriever(
            embedder=BagOfWordsEmbedder(),
            vectorstore=collection,
            reranker=LexicalOverlapReranker(),
            llm=EchoLLM(),
        )

        cases = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
        rows = [_run_case(retriever, case, doc_truth) for case in cases]
        conn.close()

        print(f"{'CASE':<26}{'RECALL':<9}{'PRECISION':<11}{'LEAKS':<7}{'EMPTY_OK':<10}")
        for row in rows:
            empty_col = "-" if row["empty_ok"] is None else ("OK" if row["empty_ok"] else "FAIL")
            print(
                f"{row['id']:<26}{_format_metric(row['recall']):<9}"
                f"{_format_metric(row['precision']):<11}{row['leaks']:<7}{empty_col:<10}"
            )
            if row["retrieved_doc_ids"] != row["expected_doc_ids"]:
                print(f"    expected doc_ids: {row['expected_doc_ids']}")
                print(f"    retrieved doc_ids: {row['retrieved_doc_ids']}")

        scored_recalls = [row["recall"] for row in rows if row["recall"] is not None]
        scored_precisions = [row["precision"] for row in rows if row["precision"] is not None]
        total_leaks = sum(row["leaks"] for row in rows)
        empty_checks = [row["empty_ok"] for row in rows if row["empty_ok"] is not None]
        empty_scope_correct = bool(empty_checks) and all(empty_checks)

        mean_recall = sum(scored_recalls) / len(scored_recalls) if scored_recalls else float("nan")
        mean_precision = (
            sum(scored_precisions) / len(scored_precisions) if scored_precisions else float("nan")
        )

        print("\n--- Aggregate ---")
        print(f"cases:                {len(rows)}")
        print(f"mean citation_recall: {mean_recall:.2f}")
        print(f"mean citation_precision: {mean_precision:.2f}")
        print(f"total isolation_leaks: {total_leaks}")
        print(f"empty_scope_correct:  {empty_scope_correct}")

        passed = total_leaks == 0 and empty_scope_correct
        print(f"\n{'PASS' if passed else 'FAIL'}: isolation_leaks == 0 and empty_scope_correct")
        return 0 if passed else 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_evals())
