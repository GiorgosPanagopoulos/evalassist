"""Freeze the semantic retrieval for the extractive spike (EXTRACTIVE_DESIGN.md 8.2).

Copies the Chroma folder to <out>/_chroma_copy, opens ONLY the copy, runs production
embed -> Chroma (IsolationScope where) -> rerank once per question, and writes
frozen_<qid>.json plus HASHES.txt. Then re-runs SemanticRetriever.query() with
a capturing fake LLM and raises if it disagrees with the frozen excerpts.

No API call, no Ollama, no writes to the database or the original Chroma.
The copy is deleted at the end; if that fails the exit code is 3.

Run from the repo root:
  python evals/spikes/extractive/freeze.py --person-id auto \
      --questions private/scratch/extractive_spike/questions.jsonl \
      --out private/scratch/extractive_spike/frozen
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Must be set before chromadb is imported (see evals/run_evals.py).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ingestion.context_header import _MARKER_PREFIX as SECTION_PREFIX  # noqa: E402
from app.ingestion.subsection_marker import _MARKER_PREFIX as SUBSECTION_PREFIX  # noqa: E402
from app.models.evaluation import CAREER_PERIOD  # noqa: E402

COPY_DIRNAME = "_chroma_copy"
EXIT_ERROR = 1
EXIT_MUTATION = 2
EXIT_COPY_LEFT = 3

SUBSECTION_END = "]\n\n"
FINAL_PUNCTUATION = frozenset(".!?;\u037e\u2026")  # incl. Greek question mark U+037E
QID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}$")


class FreezeError(RuntimeError):
    pass


# --- pure helpers ----------------------------------------------------------


def strip_headers(document: str, section: str) -> tuple[str, str | None]:
    """(body, subsection_title). Section header: exact match built from the
    metadata. Subsection marker: from its prefix to the first "]\\n\\n"."""
    text = document
    section_header = f"{SECTION_PREFIX} {section}]\n\n"
    if text.startswith(section_header):
        text = text[len(section_header) :]

    subsection_title = None
    if text.startswith(SUBSECTION_PREFIX):
        end = text.find(SUBSECTION_END)
        if end == -1:
            raise FreezeError(f"unterminated subsection marker: {document[:80]!r}")
        subsection_title = text[len(SUBSECTION_PREFIX) : end].strip()
        text = text[end + len(SUBSECTION_END) :]

    if text.startswith(SECTION_PREFIX) or text.startswith(SUBSECTION_PREFIX):
        raise FreezeError(f"header left after stripping (section={section!r}): {text[:80]!r}")
    return text, subsection_title


def line_stats(body: str) -> dict:
    lines = body.split("\n")
    nonempty = [ln.rstrip() for ln in lines if ln.strip()]
    no_final = [ln for ln in nonempty if ln[-1] not in FINAL_PUNCTUATION]
    return {
        "n_chars": len(body),
        "n_lines": len(lines),
        "n_nonempty_lines": len(nonempty),
        "n_lines_without_final_punctuation": len(no_final),
    }


def build_extractive_user_prompt(question: str, excerpts: list[dict]) -> str:
    """User prompt of section 4.1: numbered excerpts, period in the label,
    bodies without headers."""
    blocks = []
    for ex in excerpts:
        label = f"[{ex['n']}] [{ex['doc_id']} σελ.{ex['page']} - {ex['section']}"
        label += f" - περίοδος: {ex['period']}"
        if ex["subsection"]:
            label += f" - υποενότητα: {ex['subsection']}"
        if ex["person_name"]:
            label += f" - person_name: {ex['person_name']}"
        label += "]"
        blocks.append(f"{label}\n{ex['body']}")
    return f"Ερώτημα: {question}\n\nΑποσπάσματα:\n\n" + "\n\n---\n\n".join(blocks)


def load_questions(path: Path) -> list[dict]:
    questions = []
    seen = set()
    try:
        # utf-8-sig: PowerShell 5.1 "Set-Content -Encoding utf8" writes a BOM.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FreezeError(f"{path}: not UTF-8 ({exc}); save it as UTF-8") from exc
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FreezeError(f"{path}:{lineno}: invalid JSON ({exc})") from exc
        if not isinstance(q, dict):
            raise FreezeError(f"{path}:{lineno}: not a JSON object")
        missing = {"id", "question", "period"} - q.keys()
        if missing:
            raise FreezeError(f"{path}:{lineno}: missing {sorted(missing)}")
        if not QID_RE.match(q["id"]) or q["id"] in seen:
            raise FreezeError(f"{path}:{lineno}: bad or duplicate id {q['id']!r}")
        if not (PERIOD_RE.match(q["period"]) or q["period"] == CAREER_PERIOD):
            raise FreezeError(f"{path}:{lineno}: bad period {q['period']!r}")
        seen.add(q["id"])
        questions.append(q)
    if not questions:
        raise FreezeError(f"{path}: no questions")
    return questions


def codepoints(s: str) -> str:
    return " ".join(f"U+{ord(c):04X}" for c in s)


def resolve_person_id(con: sqlite3.Connection, person_arg: str) -> str:
    """Exact match in persons, or 'auto' when the database holds exactly one person."""
    if person_arg == "auto":
        ids = [r[0] for r in con.execute("SELECT person_id FROM persons")]
        if len(ids) != 1:
            raise FreezeError(
                f"--person-id auto needs exactly one person in persons, found {len(ids)}"
            )
        return ids[0]
    row = con.execute("SELECT 1 FROM persons WHERE person_id = ?", (person_arg,)).fetchone()
    if row is None:
        raise FreezeError(
            f"--person-id not found in persons (exact match). "
            f"Argument {person_arg!r}, length {len(person_arg)}, codepoints: {codepoints(person_arg)}"
        )
    return person_arg


def check_periods(con: sqlite3.Connection, person_id: str, questions: list[dict]) -> None:
    known = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT period FROM evaluations WHERE person_id = ?", (person_id,)
        )
    }
    missing = [
        (q["id"], q["period"])
        for q in questions
        if q["period"] != CAREER_PERIOD and q["period"] not in known
    ]
    if missing:
        raise FreezeError(
            "question period not in this person's evaluations: "
            + ", ".join(f"{qid}={period!r}" for qid, period in missing)
            + f". Known periods: {sorted(known)}"
        )


def preflight(db_path: Path, person_arg: str, questions_path: Path, out: Path):
    """All input checks, before chromadb is imported and before any model loads."""
    questions = load_questions(questions_path)
    check_out_dir(out)
    con = _ro_connect(db_path)
    try:
        person_id = resolve_person_id(con, person_arg)
        check_periods(con, person_id, questions)
    finally:
        con.close()
    return person_id, questions


def check_out_dir(out: Path, repo_root: Path = REPO_ROOT) -> None:
    """Frozen files contain real text: never inside a tracked part of the repo."""
    out = out.resolve()
    if out.is_relative_to(repo_root) and not out.is_relative_to(repo_root / "private"):
        raise FreezeError(f"--out must be under private/ or outside the repo: {out}")
    if out.exists() and any(p.name != COPY_DIRNAME for p in out.iterdir()):
        raise FreezeError(f"--out is not empty: {out}")


def remove_copy(copy_dir: Path) -> bool:
    """Delete the Chroma copy. On failure say loudly that real data was left."""
    if not copy_dir.exists():
        return True
    try:
        shutil.rmtree(copy_dir)
    except OSError as exc:
        print(
            f"\nCHROMA COPY NOT DELETED: {copy_dir}\n"
            f"  It contains REAL DATA (a full copy of the Chroma store).\n"
            f"  Delete it by hand. Reason: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def check_equivalence(frozen_excerpts: list[dict], citations: list, user_prompt: str | None):
    """Raise unless SemanticRetriever.query() saw exactly the frozen excerpts."""
    got = [(c.doc_id, c.page, c.section, c.score) for c in citations]
    want = [(e["doc_id"], e["page"], e["section"], e["score"]) for e in frozen_excerpts]
    if got != want:
        raise FreezeError(f"citations differ from frozen excerpts:\n got={got}\nwant={want}")
    if not frozen_excerpts:
        return
    if user_prompt is None:
        raise FreezeError("retriever did not call the LLM although excerpts exist")
    pos = 0
    for e in frozen_excerpts:
        found = user_prompt.find(e["raw_document"], pos)
        if found == -1:
            raise FreezeError(f"raw document of excerpt {e['n']} not in user_prompt (in order)")
        pos = found + len(e["raw_document"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_hash_lines(
    written: list[Path], copy_dir: Path, questions_path: Path, chroma_hashes: dict[str, str]
) -> list[str]:
    """HASHES.txt lines. Nothing from the Chroma copy is ever listed."""
    copy_dir = copy_dir.resolve()
    lines = []
    for p in written:
        if p.resolve().is_relative_to(copy_dir):
            raise FreezeError(f"refusing to hash a file of the Chroma copy: {p}")
        lines.append(f"{sha256_file(p)}  {p.name}")
    lines.append(f"{sha256_file(questions_path)}  questions:{questions_path.name}")
    lines += [f"{h}  chroma_original/{name}" for name, h in chroma_hashes.items()]
    return lines


def hash_tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- state snapshots (read-only) -------------------------------------------


def _ro_connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FreezeError(f"sqlite file not found: {path}")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)


def chroma_count_readonly(chroma_dir: Path, collection_name: str) -> int:
    # chromadb 1.5.x internal schema, read without opening a client.
    con = _ro_connect(chroma_dir / "chroma.sqlite3")
    try:
        (n,) = con.execute(
            "SELECT COUNT(*) FROM embeddings e JOIN segments s ON e.segment_id = s.id "
            "JOIN collections c ON s.collection = c.id "
            "WHERE c.name = ? AND s.scope = 'METADATA'",
            (collection_name,),
        ).fetchone()
    finally:
        con.close()
    return n


def snapshot(db_path: Path, chroma_dir: Path, collection_name: str) -> dict:
    con = _ro_connect(db_path)
    try:
        evaluations = con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        field_scores = con.execute("SELECT COUNT(*) FROM field_scores").fetchone()[0]
        audit_max = con.execute("SELECT MAX(id) FROM audit_log").fetchone()[0]
    finally:
        con.close()
    git = subprocess.run(
        ["git", "status", "--short"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return {
        "evaluations": evaluations,
        "field_scores": field_scores,
        "audit_log_max_id": audit_max,
        "chroma_count": chroma_count_readonly(chroma_dir, collection_name),
        "chroma_hashes": hash_tree(chroma_dir),
        "git_status_short": git,
    }


# --- main ------------------------------------------------------------------


class CapturingLLM:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.user_prompt: str | None = None

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.user_prompt = user_prompt
        return ""


def freeze(person_arg: str, questions_path: Path, out: Path, copy_dir: Path) -> int:
    from app.core.config import get_settings

    settings = get_settings()
    person_id, questions = preflight(Path(settings.DB_PATH), person_arg, questions_path, out)
    print(f"[preflight] person_id OK ({'auto' if person_arg == 'auto' else 'exact match'}), "
          f"{len(questions)} questions, all periods present")

    import chromadb

    from app.ingestion.embedder import Embedder
    from app.retrieval import semantic
    from app.retrieval.isolation import IsolationScope
    from app.retrieval.reranker import Reranker

    original = Path(settings.CHROMA_PATH).resolve()
    collection_name = settings.CHROMA_COLLECTION
    before = snapshot(Path(settings.DB_PATH), original, collection_name)
    print(f"[before] evaluations={before['evaluations']} field_scores={before['field_scores']} "
          f"audit_log_max_id={before['audit_log_max_id']} chroma_count={before['chroma_count']}")
    print(f"[before] git status --short:\n{before['git_status_short']}", end="")
    if before["chroma_count"] <= 0:
        raise FreezeError(f"original collection {collection_name!r} is empty or missing")

    if copy_dir.exists():
        print(f"[copy] removing stale copy from a previous run: {copy_dir}")
        shutil.rmtree(copy_dir)
    out.mkdir(parents=True, exist_ok=True)
    client = None
    try:
        shutil.copytree(original, copy_dir)
        if hash_tree(copy_dir) != before["chroma_hashes"]:
            raise FreezeError("Chroma copy differs from the original (was the backend running?)")

        client = chromadb.PersistentClient(path=str(copy_dir))
        collection = client.get_collection(collection_name)
        copy_count = collection.count()
        if not (copy_count > 0 and copy_count == before["chroma_count"]):
            raise FreezeError(f"copy count {copy_count} != original {before['chroma_count']}")
        print(f"[copy] {copy_dir} count={copy_count}")

        embedder = Embedder()
        reranker = Reranker()
        written: list[Path] = []
        frozen_by_qid: dict[str, dict] = {}

        for q in questions:
            scope = IsolationScope(person_id=person_id, period=q["period"])
            # Same steps and constants as SemanticRetriever.query (semantic.py:52-72).
            where = scope.build_chroma_where()
            [query_embedding] = embedder.embed([q["question"]])
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=semantic.TOP_K_RETRIEVE,
                where=where,
            )
            documents = results["documents"][0] if results["documents"] else []
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            reranked = (
                reranker.rerank(q["question"], documents, top_k=semantic.TOP_K_RERANK)
                if documents
                else []
            )

            excerpts = []
            for n, (idx, score) in enumerate(reranked, start=1):
                meta = metadatas[idx]
                raw = documents[idx]
                body, subsection = strip_headers(raw, meta["section"])
                excerpts.append(
                    {
                        "n": n,
                        "doc_id": meta["doc_id"],
                        "page": meta["page"],
                        "section": meta["section"],
                        "period": meta["period"],
                        "score": score,
                        "person_name": meta.get("person_name"),
                        "subsection": subsection,
                        "raw_document": raw,
                        "body": body,
                        **line_stats(body),
                    }
                )

            # Equivalence check against the unmodified production retriever.
            llm = CapturingLLM(settings.resolved_gen_model)
            retriever = semantic.SemanticRetriever(
                embedder=embedder, vectorstore=collection, reranker=reranker, llm=llm
            )
            result = retriever.query(q["question"], scope)
            check_equivalence(excerpts, result.citations, llm.user_prompt)

            frozen = {
                "qid": q["id"],
                "question": q["question"],
                "period": q["period"],
                "n_candidates": len(documents),
                "excerpts": excerpts,
                "user_prompt_extractive": build_extractive_user_prompt(q["question"], excerpts),
                # Exact production user prompt (captured), for the V4 baseline.
                "user_prompt_v4": llm.user_prompt,
                "v4_prompt_version": result.prompt_version,
            }
            frozen_by_qid[q["id"]] = frozen
            path = out / f"frozen_{q['id']}.json"
            path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(path)
            print(f"[frozen] {q['id']}: candidates={len(documents)} excerpts={len(excerpts)} "
                  f"equivalence=OK")
            for e in excerpts:
                print(f"    n={e['n']} p.{e['page']} {e['section']} | {e['period']} | "
                      f"score={e['score']:.4f} chars={e['n_chars']} lines={e['n_lines']} "
                      f"no_final_punct={e['n_lines_without_final_punctuation']}")
    finally:
        # Stops chromadb's cached System so the copy's files are released.
        if client is not None:
            client.close()

    after = snapshot(Path(settings.DB_PATH), original, collection_name)
    mutated = {k: (before[k], after[k]) for k in before if before[k] != after[k]}

    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "chromadb_version": chromadb.__version__,
        "embedding_model": settings.EMBEDDING_MODEL,
        "reranker_model": settings.RERANKER_MODEL,
        "top_k_retrieve": semantic.TOP_K_RETRIEVE,
        "top_k_rerank": semantic.TOP_K_RERANK,
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
        "questions_sha256": sha256_file(questions_path),
        "mutation_check": {
            "before": {k: v for k, v in before.items() if k != "chroma_hashes"},
            "after": {k: v for k, v in after.items() if k != "chroma_hashes"},
            "changed": sorted(mutated),
        },
    }
    meta_path = out / "freeze_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(meta_path)

    lines = build_hash_lines(written, copy_dir, questions_path, before["chroma_hashes"])
    (out / "HASHES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[after] evaluations={after['evaluations']} field_scores={after['field_scores']} "
          f"audit_log_max_id={after['audit_log_max_id']} chroma_count={after['chroma_count']}")
    print(f"[after] git status --short:\n{after['git_status_short']}", end="")
    if mutated:
        print(f"MUTATION DETECTED: {sorted(mutated)}", file=sys.stderr)
        return EXIT_MUTATION
    print(f"OK: no mutation. Wrote {len(written)} files + HASHES.txt to {out}")
    return 0


def run(person_id: str, questions_path: Path, out: Path, freeze_fn=freeze) -> int:
    """freeze() plus mandatory deletion of the Chroma copy, whatever happened."""
    copy_dir = out / COPY_DIRNAME
    try:
        rc = freeze_fn(person_id, questions_path, out, copy_dir)
    except FreezeError as exc:
        print(f"FREEZE ERROR: {exc}", file=sys.stderr)
        rc = EXIT_ERROR
    except Exception:
        traceback.print_exc()
        rc = EXIT_ERROR
    if not remove_copy(copy_dir):
        return EXIT_COPY_LEFT
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--person-id", required=True, help='exact person_id, or "auto"')
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    return run(args.person_id, args.questions, args.out)


if __name__ == "__main__":
    sys.exit(main())
