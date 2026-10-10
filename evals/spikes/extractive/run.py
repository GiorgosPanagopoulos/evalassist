"""Run one prompt variant of the extractive spike against Ollama (EXTRACTIVE_DESIGN.md 8.3).

Reads the frozen retrieval written by freeze.py, calls /api/chat directly and
verifies quotes with verify.py. Imports only the stdlib, requests and verify:
no embedder, no reranker, no chromadb, no backend.

Run from the repo root, one variant per process:
  python evals/spikes/extractive/run.py --variant E1 --mode isolated --model <model> \
      --frozen-dir private/scratch/extractive_spike/frozen \
      --out private/scratch/extractive_spike/out
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import Excerpt, unique_displays, verify_quote  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
V4_PROMPT_PATH = REPO_ROOT / "backend" / "app" / "prompts" / "semantic_rag" / "v4.txt"
VARIANT_PROMPTS = {"E1": HERE / "variants" / "E1.txt", "E2": HERE / "variants" / "E2.txt"}

# Production parameters (backend/app/core/config.py defaults).
TEMPERATURE = 0.0
SEED = 42
NUM_CTX = 8192
KEEP_ALIVE = "30m"  # OLLAMA_KEEP_ALIVE default
CTX_NEAR_LIMIT_RATIO = 0.9
MAX_QUOTES = 8

# Fixed order (8.3.1); C1 runs twice for the determinism check.
RUN_ORDER = [("C4", "C4"), ("T15", "T15"), ("C1a", "C1"), ("T17", "T17"),
             ("B09", "B09"), ("T18", "T18"), ("C1b", "C1")]

WARMUP_SYSTEM = "Απάντησε OK."
WARMUP_USER = "OK"
SELFTEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}
PS_RETRIES = 3
PS_WAIT_S = 2.0

EXIT_ERROR = 1
EXIT_SELFTEST = 4


class RunError(RuntimeError):
    pass


# --- payloads --------------------------------------------------------------


def quotes_schema(k: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "quotes": {
                "type": "array",
                "maxItems": MAX_QUOTES,
                "items": {
                    "type": "object",
                    "properties": {
                        "excerpt": {"type": "integer", "minimum": 1, "maximum": k},
                        "text": {"type": "string", "minLength": 1},
                    },
                    "required": ["excerpt", "text"],
                },
            }
        },
        "required": ["quotes"],
    }


def chat_payload(model: str, system: str, user: str, keep_alive, fmt: dict | None) -> dict:
    """Same keys and values as backend/app/retrieval/llm.py, plus top-level format."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": TEMPERATURE, "seed": SEED, "num_ctx": NUM_CTX},
    }
    if fmt is not None:
        payload["format"] = fmt
    return payload


def check_payload(payload: dict, expect_format: bool) -> None:
    """Guard against the silent Ollama failure modes: options-only fields at
    top level and top-level fields inside options are ignored without error."""
    options = payload.get("options")
    if not isinstance(options, dict):
        raise RunError("payload has no options dict")
    for key in ("format", "keep_alive"):
        if key in options:
            raise RunError(f"{key} must be top-level, found inside options")
    for key in ("temperature", "seed", "num_ctx"):
        if key in payload:
            raise RunError(f"{key} must be inside options, found at top level")
    if options != {"temperature": TEMPERATURE, "seed": SEED, "num_ctx": NUM_CTX}:
        raise RunError(f"unexpected options: {options}")
    if "keep_alive" not in payload:
        raise RunError("keep_alive missing at top level")
    if payload.get("stream") is not False:
        raise RunError("stream must be False")
    if expect_format and not isinstance(payload.get("format"), dict):
        raise RunError("format (JSON schema dict) missing at top level")
    if not expect_format and "format" in payload:
        raise RunError("format must not be sent for this call")


def unload_payload(model: str) -> dict:
    return {"model": model, "keep_alive": 0}


# --- parsing and decision --------------------------------------------------


def parse_quotes(content: str) -> tuple[str, list[tuple[int, str]] | None]:
    """Section 1: json.loads, then schema check. Any wrong type is
    llm_output_invalid here, so verify_quote never sees it."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return "invalid_json", None
    if not isinstance(data, dict) or not isinstance(data.get("quotes"), list):
        return "invalid_schema", None
    quotes = []
    for item in data["quotes"]:
        if not isinstance(item, dict):
            return "invalid_schema", None
        n, text = item.get("excerpt"), item.get("text")
        if isinstance(n, bool) or not isinstance(n, int) or not isinstance(text, str):
            return "invalid_schema", None
        quotes.append((n, text))
    return "ok", quotes


def decide(parse_status: str, results: list) -> dict:
    if parse_status != "ok":
        return {"kind": "refusal", "refusal_reason": "llm_output_invalid"}
    if not results:
        return {"kind": "refusal", "refusal_reason": "no_quote_returned"}
    n_ok = sum(r.verified for r in results)
    if n_ok == 0:
        return {"kind": "refusal", "refusal_reason": "no_verified_quote",
                "n_rejected": len(results)}
    return {"kind": "quotes", "refusal_reason": None, "n_verified": n_ok,
            "n_rejected": len(results) - n_ok}


def flags_for(resp: dict) -> list[str]:
    flags = []
    pec = resp.get("prompt_eval_count")
    if isinstance(pec, int) and pec >= CTX_NEAR_LIMIT_RATIO * NUM_CTX:
        flags.append("CTX_NEAR_LIMIT")
    if resp.get("done_reason") == "length":
        flags.append("OUTPUT_TRUNCATED")
    return flags


def ollama_counts(resp: dict) -> dict:
    keys = ("prompt_eval_count", "eval_count", "total_duration", "load_duration",
            "prompt_eval_duration", "eval_duration", "done_reason")
    return {k: resp.get(k) for k in keys}


def result_to_dict(r) -> dict:
    return {
        "excerpt": r.excerpt,
        "text": r.text,
        "verified": r.verified,
        "reason": r.reason,
        "found_in": r.found_in,
        "quote_text": r.quote_text,
        "positions": r.positions,
        "displays": [d.__dict__ for d in r.displays],
    }


# --- Ollama client ---------------------------------------------------------


def _model_key(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


class Ollama:
    def __init__(self, base_url: str, model: str, timeout: float, http=requests):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.http = http

    def version(self) -> str:
        r = self.http.get(f"{self.base_url}/api/version", timeout=30)
        r.raise_for_status()
        return r.json().get("version", "")

    def loaded_models(self) -> list[str]:
        r = self.http.get(f"{self.base_url}/api/ps", timeout=30)
        r.raise_for_status()
        return [m.get("name") or m.get("model") for m in r.json().get("models", [])]

    def unload(self, sleep=time.sleep) -> list[str]:
        r = self.http.post(f"{self.base_url}/api/generate", json=unload_payload(self.model),
                           timeout=self.timeout)
        r.raise_for_status()
        want = _model_key(self.model)
        for attempt in range(PS_RETRIES + 1):
            loaded = self.loaded_models()
            if want not in {_model_key(m) for m in loaded if m}:
                return loaded
            if attempt < PS_RETRIES:
                sleep(PS_WAIT_S)
        raise RunError(f"model {self.model} still loaded after unload: {loaded}")

    def chat(self, payload: dict, expect_format: bool) -> tuple[dict, float]:
        check_payload(payload, expect_format)
        t0 = time.perf_counter()
        r = self.http.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        elapsed = time.perf_counter() - t0
        r.raise_for_status()
        return r.json(), elapsed


def self_test(client: Ollama) -> dict:
    """One trivial structured call. Aborts before any real question if the
    server does not honour a JSON schema in format."""
    payload = chat_payload(client.model, "Απάντησε σε JSON.", "Είναι το 2 ζυγός αριθμός;",
                           KEEP_ALIVE, SELFTEST_SCHEMA)
    resp, elapsed = client.chat(payload, expect_format=True)
    content = resp.get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        data = None
    ok = isinstance(data, dict) and isinstance(data.get("ok"), bool)
    record = {"content": content, "ok": ok, "seconds": elapsed, **ollama_counts(resp)}
    if not ok:
        raise RunError(
            "FORMAT SELF-TEST FAILED: the response is not valid JSON of the trivial schema. "
            f"This Ollama does not seem to honour a JSON schema in 'format'. content={content!r}"
        )
    return record


# --- frozen input ----------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_hashes(frozen_dir: Path) -> dict[str, str]:
    hashes_path = frozen_dir / "HASHES.txt"
    if not hashes_path.is_file():
        raise RunError(f"HASHES.txt not found in {frozen_dir}")
    expected = {}
    for line in hashes_path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if name.startswith("frozen_") and name.endswith(".json"):
            expected[name] = digest
    for name, digest in expected.items():
        actual = sha256_file(frozen_dir / name)
        if actual != digest:
            raise RunError(f"{name}: sha256 {actual} != HASHES.txt {digest}")
    return expected


def load_frozen(frozen_dir: Path) -> dict[str, dict]:
    hashed = verify_frozen_hashes(frozen_dir)
    frozen = {}
    for _, qid in RUN_ORDER:
        name = f"frozen_{qid}.json"
        if name not in hashed:
            raise RunError(f"{name} missing or not listed in HASHES.txt")
        frozen[qid] = json.loads((frozen_dir / name).read_text(encoding="utf-8"))
    return frozen


def system_prompt_for(variant: str) -> str:
    path = V4_PROMPT_PATH if variant == "V4" else VARIANT_PROMPTS[variant]
    return path.read_text(encoding="utf-8")


def check_out_dir(out_dir: Path, repo_root: Path = REPO_ROOT) -> None:
    out_dir = out_dir.resolve()
    if out_dir.is_relative_to(repo_root) and not out_dir.is_relative_to(repo_root / "private"):
        raise RunError(f"--out must be under private/ or outside the repo: {out_dir}")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RunError(f"output dir is not empty: {out_dir}")


# --- one question ----------------------------------------------------------


def run_question(client: Ollama, variant: str, system: str, label: str, frozen: dict) -> dict:
    excerpts = frozen["excerpts"]
    record = {
        "label": label,
        "qid": frozen["qid"],
        "question": frozen["question"],
        "period": frozen["period"],
        "variant": variant,
        "top_rerank_score": excerpts[0]["score"] if excerpts else None,
        "n_excerpts": len(excerpts),
    }
    if not excerpts:
        record.update(parse_status="not_called", raw_content=None, quotes=[], displays=[],
                      decision={"kind": "refusal", "refusal_reason": "no_data_in_scope"},
                      flags=[], valid=True)
        return record

    extractive = variant != "V4"
    user = frozen["user_prompt_extractive"] if extractive else frozen["user_prompt_v4"]
    fmt = quotes_schema(len(excerpts)) if extractive else None
    payload = chat_payload(client.model, system, user, KEEP_ALIVE, fmt)
    resp, elapsed = client.chat(payload, expect_format=extractive)
    content = resp.get("message", {}).get("content", "")
    flags = flags_for(resp)
    record.update(
        raw_content=content,
        seconds=elapsed,
        user_prompt_sha256=hashlib.sha256(user.encode("utf-8")).hexdigest(),
        format=fmt,
        flags=flags,
        valid=not flags,
        **ollama_counts(resp),
    )
    if not extractive:
        record.update(parse_status="free_text", quotes=[], displays=[],
                      decision={"kind": "free_text", "refusal_reason": None})
        return record

    parse_status, quotes = parse_quotes(content)
    bodies = [Excerpt(e["body"], e["period"], e["doc_id"], e["page"], e["section"])
              for e in excerpts]
    results = [verify_quote(n, text, bodies) for n, text in quotes or []]
    record.update(
        parse_status=parse_status,
        quotes=[result_to_dict(r) for r in results],
        displays=[d.__dict__ for d in unique_displays(results)],
        decision=decide(parse_status, results),
    )
    return record


def warm_up(client: Ollama) -> dict:
    payload = chat_payload(client.model, WARMUP_SYSTEM, WARMUP_USER, KEEP_ALIVE, None)
    resp, elapsed = client.chat(payload, expect_format=False)
    return {"seconds": elapsed, "content": resp.get("message", {}).get("content"),
            **ollama_counts(resp)}


def run_all(client: Ollama, variant: str, mode: str, frozen: dict[str, dict],
            sink, sleep=time.sleep) -> dict:
    """sink(label, record) persists each record as soon as it exists."""
    system = system_prompt_for(variant)
    records = {}
    if mode == "sequential":
        ps_before = client.unload(sleep=sleep)
        sink("_warmup", {"ps_before": ps_before, **warm_up(client)})
    for label, qid in RUN_ORDER:
        extra = {}
        if mode == "isolated":
            extra["ps_before"] = client.unload(sleep=sleep)
            extra["warmup"] = warm_up(client)
        rec = run_question(client, variant, system, label, frozen[qid])
        rec.update(extra)
        records[label] = rec
        sink(label, rec)
        print(f"[{variant}/{mode}] {label}: parse={rec['parse_status']} "
              f"decision={rec['decision']} flags={rec['flags']} "
              f"prompt_eval_count={rec.get('prompt_eval_count')}")
    a, b = records["C1a"].get("raw_content"), records["C1b"].get("raw_content")
    return {
        "c1_identical": a is not None and a == b,
        "c1a_sha256": hashlib.sha256((a or "").encode("utf-8")).hexdigest(),
        "c1b_sha256": hashlib.sha256((b or "").encode("utf-8")).hexdigest(),
        "system_prompt_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
    }


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None, http=requests) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", required=True, choices=["E1", "E2", "V4"])
    parser.add_argument("--frozen-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", required=True, choices=["isolated", "sequential"])
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    out_dir = args.out / args.mode / args.variant
    try:
        check_out_dir(out_dir)
        frozen = load_frozen(args.frozen_dir)
        client = Ollama(args.base_url, args.model, args.timeout, http=http)
        meta = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "variant": args.variant,
            "mode": args.mode,
            "model": args.model,
            "ollama_version": client.version(),
            "params": {"temperature": TEMPERATURE, "seed": SEED, "num_ctx": NUM_CTX,
                       "keep_alive": KEEP_ALIVE, "timeout_s": args.timeout},
            "frozen_hashes": verify_frozen_hashes(args.frozen_dir),
        }
        print(f"Ollama version: {meta['ollama_version']}")
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.variant != "V4":
            try:
                meta["format_self_test"] = self_test(client)
            except RunError as exc:
                meta["format_self_test"] = {"ok": False, "error": str(exc)}
                write_json(out_dir / "run_meta.json", meta)
                print(str(exc), file=sys.stderr)
                return EXIT_SELFTEST
            print("Format self-test: OK")
        else:
            meta["format_self_test"] = "skipped: V4 sends no format"

        meta.update(run_all(client, args.variant, args.mode, frozen,
                            sink=lambda label, rec: write_json(out_dir / f"{label}.json", rec)))
        meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(out_dir / "run_meta.json", meta)
        print(f"C1a == C1b byte for byte: {meta['c1_identical']}")
        print(f"Wrote {out_dir}")
        return 0
    except (RunError, requests.RequestException) as exc:
        print(f"RUN ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
