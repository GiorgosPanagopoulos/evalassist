"""End-to-end validation με ΠΡΑΓΜΑΤΙΚΑ μοντέλα (bge-m3, bge-reranker-v2-m3,
Ollama qwen2.5:14b) πάνω στα synthetic PDFs (fixtures/synthetic_pdfs/,
βλ. scripts/generate_synthetic_pdfs.py + fixtures/synthetic_ground_truth.json).

Plain assert, ΟΧΙ pytest. Standalone: `python scripts/e2e_synthetic_test.py`.
ΔΕΝ μπαίνει στο pytest/CI suite — χρειάζεται πραγματικό Ollama + torch/
sentence-transformers (bge-m3/bge-reranker-v2-m3 κατεβαίνουν αυτόματα στο
πρώτο τρέξιμο αν δεν υπάρχουν ήδη τοπικά, ~2GB).

Isolation από production: ίδιο pattern με evals/run_evals.py — προσωρινό
SQLite + προσωρινό ChromaDB σε tempdir, direct param injection στο
ingestion/retrieval pipeline (ΟΧΙ config/env override). ΚΑΝΕΝΑ import/χρήση
των production defaults (backend/data/evalassist.db, backend/chroma_db).

Στο ground truth, "" σε postings date_to/days δηλώνει ανοιχτή τοποθέτηση· ο
parser το επιστρέφει ως None (extractor.py:_parse_date/_parse_int) — ένα
μελλοντικό check_postings πρέπει να συγκρίνει με None, όχι με "".
"""

import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# E2E_DEVICE: device param για Embedder/Reranker (π.χ. "cuda" σε GPU μηχανή, μηδέν edit).
# E2E_LLM: το Ollama μοντέλο — περνιέται στο OllamaClient ΚΑΙ ελέγχεται από check_ollama().
# Το OLLAMA_MODEL env var εδώ αξιοποιεί το ήδη υπάρχον pydantic-settings override
# (backend/app/core/config.py) — καμία αλλαγή σε production κώδικα.
E2E_DEVICE = os.environ.get("EVALASSIST_E2E_DEVICE", "cpu")
E2E_LLM = os.environ.get("EVALASSIST_E2E_LLM", "qwen2.5:14b")
os.environ["OLLAMA_MODEL"] = E2E_LLM

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from app.core.audit import AuditEntry, write_audit  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.database import get_connection, init_db  # noqa: E402
from app.ingestion.embedder import Embedder  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402
from app.ingestion.vectorstore import get_collection  # noqa: E402
from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.llm import OllamaClient  # noqa: E402
from app.retrieval.models import Citation  # noqa: E402
from app.retrieval.reranker import Reranker  # noqa: E402
from app.retrieval.semantic import NO_DATA_ANSWER, SemanticRetriever  # noqa: E402
from app.retrieval.structured import get_scores  # noqa: E402

import json  # noqa: E402

# GROUND_TRUTH_PATH/OUTPUT_DIR υπολογίζονται ανεξάρτητα (όχι import από
# scripts.generate_synthetic_pdfs στο module level) ώστε το βαρύ WeasyPrint
# import να μη χρειάζεται καθόλου στην κοινή περίπτωση όπου τα synthetic
# PDFs ήδη υπάρχουν — βλ. ensure_pdfs() παρακάτω για το lazy import.
GROUND_TRUTH_PATH = REPO_ROOT / "fixtures" / "synthetic_ground_truth.json"
OUTPUT_DIR = REPO_ROOT / "fixtures" / "synthetic_pdfs"

KEYWORDS = {
    "Μ-99001": "σόναρ",
    "Μ-99002": "πυραυλικά",
    "Μ-99003": "αφαλάτωση",
}


class Report:
    def __init__(self) -> None:
        self.categories: dict[str, list[str]] = {}

    def run(self, category: str, fn) -> None:
        failures = self.categories.setdefault(category, [])
        try:
            fn(failures)
        except AssertionError as exc:
            failures.append(str(exc))
        except Exception as exc:  # noqa: BLE001 — καταγράφουμε κάθε unexpected error ως failure
            failures.append(f"UNEXPECTED {type(exc).__name__}: {exc}")

    def check(self, category: str, condition: bool, message: str) -> None:
        if not condition:
            self.categories.setdefault(category, []).append(message)

    def print_summary(self) -> bool:
        print("\n=== SUMMARY ===")
        all_ok = True
        for category, failures in self.categories.items():
            status = "PASS" if not failures else "FAIL"
            if failures:
                all_ok = False
            print(f"{status:5s} {category}")
            for f in failures:
                print(f"        - {f}")
        print(f"\n{'PASS' if all_ok else 'FAIL'}: e2e synthetic test")
        return all_ok


def check_ollama() -> None:
    settings = get_settings()
    try:
        resp = requests.get(f"{settings.OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"FAIL  Ollama δεν είναι διαθέσιμο στο {settings.OLLAMA_URL}: {exc}", file=sys.stderr)
        print("      Ξεκινήστε το Ollama (`ollama serve`) και βεβαιωθείτε ότι το μοντέλο", file=sys.stderr)
        print(f"      {settings.OLLAMA_MODEL} είναι κατεβασμένο (`ollama pull {settings.OLLAMA_MODEL}`).", file=sys.stderr)
        sys.exit(1)

    models = [m.get("name", "") for m in resp.json().get("models", [])]
    target = settings.OLLAMA_MODEL
    target_stem = target.split(":")[0]
    if not any(m == target or m.startswith(target_stem) for m in models):
        print(f"FAIL  Το μοντέλο {target} δεν βρέθηκε στο Ollama. Διαθέσιμα: {models}", file=sys.stderr)
        print(f"      Τρέξτε: ollama pull {target}", file=sys.stderr)
        sys.exit(1)

    print(f"OK    Ollama διαθέσιμο στο {settings.OLLAMA_URL}, μοντέλο {target} βρέθηκε.")


def ensure_pdfs() -> list[Path]:
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    expected = {p["agm"] for p in ground_truth["persons"]}
    existing = {p.stem for p in OUTPUT_DIR.glob("*.pdf")} if OUTPUT_DIR.exists() else set()
    if expected <= existing:
        print(f"OK    Synthetic PDFs ήδη υπάρχουν στο {OUTPUT_DIR.relative_to(REPO_ROOT)}, παραλείπεται generation.")
        return [OUTPUT_DIR / f"{agm}.pdf" for agm in expected]
    print("...   Generation synthetic PDFs (WeasyPrint)...")
    from scripts.generate_synthetic_pdfs import generate_all  # lazy: αποφεύγει το βαρύ

    paths = generate_all()
    print(f"OK    {len(paths)} synthetic PDFs δημιουργήθηκαν.")
    return paths


def _doc_ids_for_person(conn: sqlite3.Connection, person_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT doc_id FROM documents WHERE person_id = ?", (person_id,)
    ).fetchall()
    return {r["doc_id"] for r in rows}


def _chunk_metadatas_for(collection, doc_id: str, page: int) -> list[dict]:
    result = collection.get(where={"$and": [{"doc_id": doc_id}, {"page": page}]})
    return result["metadatas"]


def assert_citation_grounded(
    failures: list[str],
    collection,
    conn: sqlite3.Connection,
    citation: Citation,
    expected_person_id: str,
    expected_period: str | None = None,
) -> None:
    metadatas = _chunk_metadatas_for(collection, citation.doc_id, citation.page)
    if not metadatas:
        failures.append(
            f"citation {citation.doc_id}:{citation.page} δεν αντιστοιχεί σε κανένα ingested chunk"
        )
        return
    matching = [m for m in metadatas if m.get("section") == citation.section]
    if not matching:
        failures.append(
            f"citation section={citation.section!r} δεν βρέθηκε στα ingested chunks "
            f"του {citation.doc_id}:{citation.page} (sections={[m.get('section') for m in metadatas]})"
        )
        return
    for meta in matching:
        if meta.get("person_id") != expected_person_id:
            failures.append(
                f"ISOLATION LEAK: citation {citation.doc_id}:{citation.page} ({citation.section}) "
                f"ανήκει σε person_id={meta.get('person_id')}, αναμενόταν {expected_person_id}"
            )
        if expected_period is not None and meta.get("period") != expected_period:
            failures.append(
                f"CROSS-PERIOD LEAK: citation {citation.doc_id}:{citation.page} ({citation.section}) "
                f"ανήκει σε period={meta.get('period')}, αναμενόταν {expected_period}"
            )
    doc_ids_of_person = _doc_ids_for_person(conn, expected_person_id)
    if citation.doc_id not in doc_ids_of_person:
        failures.append(
            f"citation doc_id={citation.doc_id} δεν βρίσκεται στο documents table για "
            f"person_id={expected_person_id}"
        )


def main() -> int:
    print(f"...   EVALASSIST_E2E_DEVICE={E2E_DEVICE!r}  EVALASSIST_E2E_LLM={E2E_LLM!r}")
    check_ollama()
    ensure_pdfs()

    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    persons_gt = {p["agm"]: p for p in ground_truth["persons"]}

    tmp_dir = Path(tempfile.mkdtemp(prefix="evalassist_e2e_"))
    report = Report()
    try:
        db_path = tmp_dir / "eval.db"
        chroma_dir = tmp_dir / "chroma"
        init_db(db_path)
        conn = get_connection(db_path)
        collection = get_collection(chroma_dir)

        print("...   Φόρτωση bge-m3 embedder (πρώτη φορά: download ~2GB, μπορεί να αργήσει)...")
        # EVALASSIST_E2E_DEVICE (default "cpu"): στο ίδιο μηχάνημα τρέχει και το Ollama στο
        # GPU· η ταυτόχρονη χρήση του Metal/MPS GPU από τα sentence-transformers μοντέλα
        # οδήγησε σε kIOGPUCommandBufferCallbackErrorOutOfMemory. Σε GPU μηχανή θέστε
        # EVALASSIST_E2E_DEVICE=cuda.
        embedder = Embedder(device=E2E_DEVICE)

        # --- Ingestion (πραγματικό pipeline, Task 2 code paths) ---
        results = {}
        for agm in persons_gt:
            pdf_path = OUTPUT_DIR / f"{agm}.pdf"
            print(f"...   Ingesting {pdf_path.name}...")
            result = run_ingestion(pdf_path, embedder=embedder, db_path=db_path, chroma_dir=chroma_dir)
            results[agm] = result
            print(f"OK    {agm}: person_id={result.person_id}, periods={result.periods}, chunks={result.chunk_count}")

        def check_ingestion(failures: list[str]) -> None:
            person_count = conn.execute("SELECT COUNT(*) AS n FROM persons").fetchone()["n"]
            if person_count != 3:
                failures.append(f"αναμένονταν 3 persons, βρέθηκαν {person_count}")

            eval_count = conn.execute("SELECT COUNT(*) AS n FROM evaluations").fetchone()["n"]
            if eval_count != 6:
                failures.append(f"αναμένονταν 6 evaluations, βρέθηκαν {eval_count}")

            doc_count = conn.execute("SELECT COUNT(DISTINCT doc_id) AS n FROM documents").fetchone()["n"]
            if doc_count != 3:
                failures.append(f"αναμένονταν 3 distinct doc_id στο documents table, βρέθηκαν {doc_count}")

            for agm, result in results.items():
                if result.person_id != agm:
                    failures.append(f"person_id mismatch: {result.person_id} != {agm}")
                if result.chunk_count == 0:
                    failures.append(f"{agm}: 0 chunks στο Chroma")
                chroma_rows = collection.get(where={"doc_id": result.doc_id})
                if len(chroma_rows["ids"]) != result.chunk_count:
                    failures.append(
                        f"{agm}: Chroma έχει {len(chroma_rows['ids'])} chunks, "
                        f"IngestionResult ανέφερε {result.chunk_count}"
                    )
                for meta in chroma_rows["metadatas"]:
                    for key in ("person_id", "person_name", "period", "section", "score", "doc_id", "page"):
                        if key not in meta:
                            failures.append(f"{agm}: chunk metadata λείπει το κλειδί {key!r}")

        report.run("Ingestion", check_ingestion)

        # --- Health entries: ΜΟΝΟ in-memory έλεγχος πάνω στο IngestionResult
        # (summary_note.health_entries) — τα health entries ΔΕΝ γράφονται σε
        # SQLite ούτε ξεχωριστά δομημένα στο ChromaDB (βλ. app/ingestion/
        # pipeline.py: κανένα repository.upsert/replace_* για health), άρα
        # δεν υπάρχει άλλο σημείο παρατήρησης χωρίς νέο SQLite wiring.
        def check_health(failures: list[str]) -> None:
            for agm, person_gt in persons_gt.items():
                entries_gt = person_gt["health_entries"]
                entries = results[agm].summary_note.health_entries
                if len(entries) != len(entries_gt):
                    failures.append(
                        f"{agm}: {len(entries)} health entries, αναμένονταν {len(entries_gt)}"
                    )
                    continue
                for got, expected in zip(entries, entries_gt):
                    expected_date = (
                        datetime.date.fromisoformat(expected["date"]) if expected["date"] else None
                    )
                    if got.date != expected_date:
                        failures.append(f"{agm}: health.date={got.date} != {expected_date}")
                    if got.opinion_ref != expected["opinion_ref"]:
                        failures.append(
                            f"{agm}: health.opinion_ref={got.opinion_ref!r} != {expected['opinion_ref']!r}"
                        )
                    if got.leave_days != expected["leave_days"]:
                        failures.append(
                            f"{agm}: health.leave_days={got.leave_days!r} != {expected['leave_days']!r}"
                        )
                    if got.leave_days_raw != expected["leave_days_raw"]:
                        failures.append(
                            f"{agm}: health.leave_days_raw={got.leave_days_raw!r} != "
                            f"{expected['leave_days_raw']!r}"
                        )
                    if got.description != expected["description"]:
                        failures.append(
                            f"{agm}: health.description={got.description!r} != {expected['description']!r}"
                        )

        report.run("Health entries", check_health)

        # --- Structured mode: exact match έναντι ground truth, καμία κλήση LLM ---
        def check_structured(failures: list[str]) -> None:
            for agm, person_gt in persons_gt.items():
                for entry_gt in person_gt["evaluations"]:
                    period = f"{entry_gt['period_start']}..{entry_gt['period_end']}"
                    scope = IsolationScope(person_id=agm, period=period)
                    result = get_scores(conn, scope)
                    write_audit(
                        conn,
                        AuditEntry(
                            user="e2e_test", query=f"get_scores {agm} {period}",
                            retrieved_doc_ids=result.retrieved_doc_ids, mode="structured",
                        ),
                    )
                    conn.commit()

                    data = result.data
                    if not data:
                        failures.append(f"{agm}/{period}: structured get_scores επέστρεψε άδειο data")
                        continue
                    if data.get("score") != entry_gt["score"]:
                        failures.append(
                            f"{agm}/{period}: score={data.get('score')} != ground truth {entry_gt['score']}"
                        )
                    if data.get("characterization") != entry_gt["characterization"]:
                        failures.append(
                            f"{agm}/{period}: characterization={data.get('characterization')!r} != "
                            f"ground truth {entry_gt['characterization']!r}"
                        )
                    got_fs = {(fs["field_code"], fs["value"]) for fs in data.get("field_scores", [])}
                    expected_fs = {(fs["field_code"], fs["value"]) for fs in entry_gt["field_scores"]}
                    if got_fs != expected_fs:
                        failures.append(
                            f"{agm}/{period}: field_scores {got_fs} != ground truth {expected_fs}"
                        )

        report.run("Structured mode (exact match)", check_structured)

        # --- Semantic mode: real bge-m3 + bge-reranker-v2-m3 + Ollama ---
        print("...   Φόρτωση bge-reranker-v2-m3 (πρώτη φορά: download)...")
        reranker = Reranker(device=E2E_DEVICE)
        # timeout=600: qwen2.5:14b σε αυτό το μηχάνημα (υπό φόρτο, CPU-only embedding/
        # reranking παράλληλα) ξεπερνούσε το default timeout=120s.
        llm = OllamaClient(timeout=600)
        retriever = SemanticRetriever(
            embedder=embedder, vectorstore=collection, reranker=reranker, llm=llm
        )

        def check_semantic(failures: list[str]) -> None:
            for agm, person_gt in persons_gt.items():
                entry_gt = person_gt["evaluations"][0]
                period = f"{entry_gt['period_start']}..{entry_gt['period_end']}"
                scope = IsolationScope(person_id=agm, period=period)
                question = f"Πώς αξιολογήθηκε ο/η {person_gt['name']} κατά την περίοδο {period};"
                print(f"...   Semantic query για {agm} ({period})...")
                result = retriever.query(question, scope)
                write_audit(
                    conn,
                    AuditEntry(
                        user="e2e_test", query=question,
                        retrieved_doc_ids=result.retrieved_doc_ids, mode="semantic",
                    ),
                )
                conn.commit()

                if not result.citations:
                    failures.append(f"{agm}/{period}: semantic query δεν επέστρεψε citations")
                    continue
                for citation in result.citations:
                    assert_citation_grounded(
                        failures, collection, conn, citation, expected_person_id=agm, expected_period=period
                    )

        report.run("Semantic mode (grounded citations)", check_semantic)

        # --- Isolation (hard gate): scope σε A + λέξη-κλειδί του B -> ποτέ leak ---
        def check_isolation(failures: list[str]) -> None:
            agms = list(persons_gt.keys())
            for a in agms:
                period_a = f"{persons_gt[a]['evaluations'][0]['period_start']}..{persons_gt[a]['evaluations'][0]['period_end']}"
                scope = IsolationScope(person_id=a, period=period_a)
                for b in agms:
                    if a == b:
                        continue
                    keyword_b = KEYWORDS[b]
                    question = f"Τι αναφέρεται σχετικά με {keyword_b};"
                    result = retriever.query(question, scope)
                    write_audit(
                        conn,
                        AuditEntry(
                            user="e2e_test", query=question,
                            retrieved_doc_ids=result.retrieved_doc_ids, mode="semantic",
                        ),
                    )
                    conn.commit()

                    if not result.citations:
                        if result.answer != NO_DATA_ANSWER:
                            failures.append(
                                f"{a} scoped, keyword of {b} ({keyword_b}): 0 citations αλλά η "
                                f"απάντηση δεν είναι το NO_DATA_ANSWER"
                            )
                        continue
                    for citation in result.citations:
                        assert_citation_grounded(
                            failures, collection, conn, citation, expected_person_id=a, expected_period=period_a
                        )

        report.run("Isolation (hard gate, 0 leaks)", check_isolation)

        # --- Cross-period isolation: scope σε (A, period_1) δεν φέρνει period_2 ---
        def check_cross_period_isolation(failures: list[str]) -> None:
            for agm, person_gt in persons_gt.items():
                if len(person_gt["evaluations"]) < 2:
                    continue
                entry_1 = person_gt["evaluations"][0]
                period_1 = f"{entry_1['period_start']}..{entry_1['period_end']}"
                scope = IsolationScope(person_id=agm, period=period_1)
                question = f"Ποια ήταν η συνολική εικόνα του/της {person_gt['name']};"
                result = retriever.query(question, scope)
                write_audit(
                    conn,
                    AuditEntry(
                        user="e2e_test", query=question,
                        retrieved_doc_ids=result.retrieved_doc_ids, mode="semantic",
                    ),
                )
                conn.commit()
                for citation in result.citations:
                    assert_citation_grounded(
                        failures, collection, conn, citation, expected_person_id=agm, expected_period=period_1
                    )

        report.run("Cross-period isolation", check_cross_period_isolation)

        # --- Audit: κάθε κλήση παραπάνω έγραψε γραμμή στο audit_log ---
        def check_audit(failures: list[str]) -> None:
            rows = conn.execute("SELECT mode, retrieved_doc_ids FROM audit_log").fetchall()
            if not rows:
                failures.append("audit_log είναι άδειο")
                return
            modes = {r["mode"] for r in rows}
            if "structured" not in modes:
                failures.append("καμία audit_log εγγραφή με mode='structured'")
            if "semantic" not in modes:
                failures.append("καμία audit_log εγγραφή με mode='semantic'")
            for r in rows:
                json.loads(r["retrieved_doc_ids"])  # πρέπει να είναι valid JSON

        report.run("Audit log", check_audit)

        conn.close()
        return 0 if report.print_summary() else 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
