"""Tests for run.py with a fake requests module. Synthetic data only, no Ollama.

Run: PYTHONPATH=. python evals/spikes/extractive/test_run.py
"""

import ast
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import traceback
from pathlib import Path

from evals.spikes.extractive import run as R

PERIOD = "2001-01-01..2001-12-31"


def raises(fn, exc=R.RunError) -> str:
    try:
        fn()
    except exc as e:
        return str(e)
    raise AssertionError(f"{exc.__name__} not raised")


class FakeResponse:
    def __init__(self, data):
        self._data = data
        self.text = json.dumps(data)

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeHTTP:
    """Records every call; chat answers come from a queue (or a callable)."""

    def __init__(self, chat_contents=None, ps_models=None, version="0.0.0-test"):
        self.calls = []
        self.chat_contents = list(chat_contents or [])
        self.ps_models = list(ps_models or [])
        self.version = version

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, None))
        if url.endswith("/api/version"):
            return FakeResponse({"version": self.version})
        if url.endswith("/api/ps"):
            models = self.ps_models.pop(0) if self.ps_models else []
            return FakeResponse({"models": [{"name": m} for m in models]})
        raise AssertionError(url)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/api/generate"):
            return FakeResponse({"done": True})
        if url.endswith("/api/chat"):
            content = self.chat_contents.pop(0) if self.chat_contents else "OK"
            if callable(content):
                content = content(json)
            return FakeResponse({"message": {"content": content}, "prompt_eval_count": 100,
                                 "eval_count": 10, "done_reason": "stop"})
        raise AssertionError(url)

    def chats(self):
        return [p for m, u, p in self.calls if m == "POST" and u.endswith("/api/chat")]


def client(http) -> R.Ollama:
    return R.Ollama("http://x", "krikri:8b", 10, http=http)


def frozen_entry(qid: str, body: str = "ΧΑΡΑΚΤΗΡΙΣΜΟΣ: ΕΞΑΙΡΕΤΟΣ (100)", n: int = 2) -> dict:
    excerpts = [
        {"n": i, "doc_id": "D", "page": i, "section": "S", "period": PERIOD,
         "score": 1.0 / i, "body": body, "raw_document": body}
        for i in range(1, n + 1)
    ]
    return {"qid": qid, "question": f"Q {qid}", "period": PERIOD, "excerpts": excerpts,
            "user_prompt_extractive": f"EXTRACTIVE {qid}", "user_prompt_v4": f"V4 {qid}"}


def all_frozen(**kw) -> dict:
    return {qid: frozen_entry(qid, **kw) for qid in {q for _, q in R.RUN_ORDER}}


# --- payload shape ---------------------------------------------------------


def test_extractive_payload_shape():
    http = FakeHTTP(chat_contents=['{"quotes": []}'])
    R.run_question(client(http), "E1", "SYS", "C4", frozen_entry("C4", n=3))
    [p] = http.chats()
    assert p["format"] == R.quotes_schema(3)
    assert p["format"]["properties"]["quotes"]["items"]["properties"]["excerpt"]["maximum"] == 3
    assert p["keep_alive"] == R.KEEP_ALIVE
    assert p["options"] == {"temperature": 0.0, "seed": 42, "num_ctx": 8192}
    assert "format" not in p["options"] and "keep_alive" not in p["options"]
    assert "num_ctx" not in p and "temperature" not in p and "seed" not in p
    assert p["stream"] is False
    assert p["messages"] == [{"role": "system", "content": "SYS"},
                             {"role": "user", "content": "EXTRACTIVE C4"}]


def test_v4_payload_has_no_format():
    http = FakeHTTP(chat_contents=["ελεύθερο κείμενο"])
    rec = R.run_question(client(http), "V4", "SYS", "C4", frozen_entry("C4"))
    [p] = http.chats()
    assert "format" not in p
    assert p["messages"][1]["content"] == "V4 C4"
    assert p["options"]["num_ctx"] == 8192 and p["keep_alive"] == R.KEEP_ALIVE
    assert rec["parse_status"] == "free_text" and rec["raw_content"] == "ελεύθερο κείμενο"


def test_unload_payload_top_level_keep_alive_zero():
    http = FakeHTTP(ps_models=[[]])
    client(http).unload(sleep=lambda s: None)
    [(m, url, p)] = [c for c in http.calls if c[0] == "POST"]
    assert url.endswith("/api/generate") and p == {"model": "krikri:8b", "keep_alive": 0}


def test_check_payload_accepts_valid():
    R.check_payload(R.chat_payload("m", "s", "u", "30m", {"type": "object"}), expect_format=True)
    R.check_payload(R.chat_payload("m", "s", "u", "30m", None), expect_format=False)


def test_check_payload_rejects_invalid():
    good = R.chat_payload("m", "s", "u", "30m", {"type": "object"})
    bad = []
    p = json.loads(json.dumps(good))
    p["options"]["format"] = p.pop("format")
    bad.append((p, True))
    p = json.loads(json.dumps(good))
    p["options"]["keep_alive"] = p.pop("keep_alive")
    bad.append((p, True))
    p = json.loads(json.dumps(good))
    p["num_ctx"] = p["options"].pop("num_ctx")
    bad.append((p, True))
    p = json.loads(json.dumps(good))
    p["options"]["num_ctx"] = 2048
    bad.append((p, True))
    p = json.loads(json.dumps(good))
    p["format"] = "json"
    bad.append((p, True))
    bad.append((R.chat_payload("m", "s", "u", "30m", None), True))
    bad.append((good, False))
    p = json.loads(json.dumps(good))
    p["stream"] = True
    bad.append((p, True))
    for payload, expect in bad:
        raises(lambda payload=payload, expect=expect: R.check_payload(payload, expect))


def test_chat_refuses_bad_payload_before_sending():
    http = FakeHTTP()
    bad = R.chat_payload("m", "s", "u", "30m", None)
    bad["options"]["keep_alive"] = "30m"
    raises(lambda: client(http).chat(bad, expect_format=False))
    assert http.calls == []


# --- prompts ---------------------------------------------------------------


def test_v4_system_prompt_read_from_backend_file():
    path = R.REPO_ROOT / "backend" / "app" / "prompts" / "semantic_rag" / "v4.txt"
    assert R.V4_PROMPT_PATH == path
    assert R.system_prompt_for("V4") == path.read_text(encoding="utf-8")


def test_e1_e2_differ_only_in_last_sentence():
    e1 = R.system_prompt_for("E1")
    e2 = R.system_prompt_for("E2")
    last = 'Αν κανένα απόσπασμα δεν απαντά στο ερώτημα, επίστρεψε {"quotes": []}.\n'
    assert e1 == e2 + "\n" + last
    for word in ("Αν ", "μόνο", "δεν βρέθηκε", "καμία", "κενή", "άρνηση"):
        assert word not in e2, word
    assert "παράδειγμα" not in e1.lower() and "ΓΙΑ ΤΟ ΕΤΟΣ" not in e1


def test_e_prompts_match_design_if_available():
    design = R.REPO_ROOT / "private" / "prompts" / "EXTRACTIVE_DESIGN.md"
    if not design.is_file():
        print("    (design not present, skipped)")
        return
    text = design.read_text(encoding="utf-8")
    for v in ("E1", "E2"):
        block = text.split(f"### Παραλλαγή {v}:", 1)[1].split("```\n", 2)[1]
        assert R.system_prompt_for(v) == block, v


# --- parsing and decisions -------------------------------------------------


def test_parse_valid():
    assert R.parse_quotes('{"quotes": [{"excerpt": 1, "text": "Α"}]}') == ("ok", [(1, "Α")])
    assert R.parse_quotes('{"quotes": [], "extra": 1}') == ("ok", [])


def test_parse_wrong_types_are_invalid_not_crash():
    cases = [
        "not json", "", "[]", '{"quotes": {}}', '{"other": []}',
        '{"quotes": ["x"]}',
        '{"quotes": [{"excerpt": "1", "text": "Α"}]}',
        '{"quotes": [{"excerpt": 1.0, "text": "Α"}]}',
        '{"quotes": [{"excerpt": true, "text": "Α"}]}',
        '{"quotes": [{"excerpt": null, "text": "Α"}]}',
        '{"quotes": [{"excerpt": 1, "text": 5}]}',
        '{"quotes": [{"excerpt": 1}]}',
    ]
    for c in cases:
        status, quotes = R.parse_quotes(c)
        assert status in ("invalid_json", "invalid_schema") and quotes is None, c


def test_wrong_type_in_run_becomes_llm_output_invalid():
    http = FakeHTTP(chat_contents=['{"quotes": [{"excerpt": "1", "text": "ΕΞΑΙΡΕΤΟΣ"}]}'])
    rec = R.run_question(client(http), "E2", "SYS", "C1a", frozen_entry("C1"))
    assert rec["parse_status"] == "invalid_schema"
    assert rec["decision"] == {"kind": "refusal", "refusal_reason": "llm_output_invalid"}


def test_decisions():
    def rec_for(content):
        http = FakeHTTP(chat_contents=[content])
        return R.run_question(client(http), "E1", "SYS", "C1a", frozen_entry("C1"))

    r = rec_for('{"quotes": []}')
    assert r["decision"]["refusal_reason"] == "no_quote_returned"
    r = rec_for('{"quotes": [{"excerpt": 1, "text": "ΜΕΤΡΙΟΣ"}, {"excerpt": 9, "text": "Χ"}]}')
    assert r["decision"]["refusal_reason"] == "no_verified_quote"
    assert [q["reason"] for q in r["quotes"]] == ["not_found", "bad_excerpt_index"]
    r = rec_for('{"quotes": [{"excerpt": 2, "text": "εξαίρετος (100)"}, {"excerpt": 1, "text": "Χ"}]}')
    assert r["decision"] == {"kind": "quotes", "refusal_reason": None,
                             "n_verified": 1, "n_rejected": 1}
    q = r["quotes"][0]
    assert q["quote_text"] == "ΕΞΑΙΡΕΤΟΣ (100)"
    assert q["displays"][0]["display_text"] == "ΧΑΡΑΚΤΗΡΙΣΜΟΣ: ΕΞΑΙΡΕΤΟΣ (100)"
    assert q["displays"][0]["period"] == PERIOD and q["displays"][0]["page"] == 2
    assert r["top_rerank_score"] == 1.0 and r["valid"] is True


def test_no_excerpts_means_no_call():
    http = FakeHTTP()
    rec = R.run_question(client(http), "E1", "SYS", "T17", frozen_entry("T17", n=0))
    assert http.calls == [] and rec["decision"]["refusal_reason"] == "no_data_in_scope"
    assert rec["top_rerank_score"] is None


def test_flags():
    assert R.flags_for({"prompt_eval_count": 7372}) == []
    assert R.flags_for({"prompt_eval_count": 7373}) == ["CTX_NEAR_LIMIT"]
    assert R.flags_for({"prompt_eval_count": 8192, "done_reason": "length"}) == [
        "CTX_NEAR_LIMIT", "OUTPUT_TRUNCATED"]
    assert R.flags_for({}) == []


# --- unload, ps, self-test -------------------------------------------------


def test_unload_retries_then_aborts():
    http = FakeHTTP(ps_models=[["krikri:8b"], ["krikri:8b"], []])
    assert client(http).unload(sleep=lambda s: None) == []
    http = FakeHTTP(ps_models=[["krikri:8b"]] * (R.PS_RETRIES + 1))
    raises(lambda: client(http).unload(sleep=lambda s: None))
    http = FakeHTTP(ps_models=[["other:latest"]])
    assert client(http).unload(sleep=lambda s: None) == ["other:latest"]
    bare = R.Ollama("http://x", "krikri", 10, http=FakeHTTP(ps_models=[["krikri:latest"]] * 4))
    raises(lambda: bare.unload(sleep=lambda s: None))


def test_self_test_ok_and_fail():
    rec = R.self_test(client(FakeHTTP(chat_contents=['{"ok": true}'])))
    assert rec["ok"] is True
    for bad in ("OK", '{"ok": "yes"}', "{}", '{"ok": true'):
        raises(lambda bad=bad: R.self_test(client(FakeHTTP(chat_contents=[bad]))))
    http = FakeHTTP(chat_contents=['{"ok": true}'])
    R.self_test(client(http))
    [p] = http.chats()
    assert p["format"] == R.SELFTEST_SCHEMA and "format" not in p["options"]


# --- whole run -------------------------------------------------------------


def _sequence(http):
    out = []
    for m, url, p in http.calls:
        if url.endswith("/api/generate"):
            out.append("unload")
        elif url.endswith("/api/ps"):
            out.append("ps")
        elif url.endswith("/api/chat"):
            out.append("warmup" if p["messages"][0]["content"] == R.WARMUP_SYSTEM else "q")
    return out


def test_isolated_order_and_c1_comparison():
    http = FakeHTTP()
    records = {}
    meta = R.run_all(client(http), "E1", "isolated", all_frozen(),
                     sink=lambda label, rec: records.__setitem__(label, rec), sleep=lambda s: None)
    assert _sequence(http) == ["unload", "ps", "warmup", "q"] * 7
    assert [k for k in records] == [label for label, _ in R.RUN_ORDER]
    assert all("ps_before" in r and "warmup" in r for r in records.values())
    assert meta["c1_identical"] is True
    warm = [p for p in http.chats() if p["messages"][0]["content"] == R.WARMUP_SYSTEM]
    assert all("format" not in p and p["options"]["num_ctx"] == 8192 for p in warm)


def test_sequential_unloads_once():
    http = FakeHTTP()
    records = {}
    R.run_all(client(http), "E2", "sequential", all_frozen(),
              sink=lambda label, rec: records.__setitem__(label, rec), sleep=lambda s: None)
    assert _sequence(http) == ["unload", "ps", "warmup"] + ["q"] * 7
    assert "_warmup" in records and "ps_before" not in records["C4"]


def test_c1_difference_detected():
    answers = iter(['{"quotes": []}'] * 20)
    contents = []
    for label, _ in R.RUN_ORDER:
        contents += ["OK", '{"quotes": [{"excerpt": 1, "text": "Χ"}]}' if label == "C1b"
                     else next(answers)]
    http = FakeHTTP(chat_contents=contents)
    meta = R.run_all(client(http), "E1", "isolated", all_frozen(), sink=lambda *a: None,
                     sleep=lambda s: None)
    assert meta["c1_identical"] is False and meta["c1a_sha256"] != meta["c1b_sha256"]


def _frozen_dir(entries: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    lines = []
    for qid, entry in entries.items():
        p = d / f"frozen_{qid}.json"
        p.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (d / "HASHES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def test_frozen_hash_check():
    d = _frozen_dir(all_frozen())
    assert set(R.load_frozen(d)) == {"C4", "T15", "C1", "T17", "B09", "T18"}
    (d / "frozen_C4.json").write_text("{}", encoding="utf-8")
    raises(lambda: R.load_frozen(d))
    entries = all_frozen()
    del entries["B09"]
    raises(lambda: R.load_frozen(_frozen_dir(entries)))


def test_main_end_to_end_and_self_test_abort():
    frozen_dir = _frozen_dir(all_frozen())
    out = Path(tempfile.mkdtemp())
    http = FakeHTTP(chat_contents=['{"ok": true}'])
    with contextlib.redirect_stdout(io.StringIO()):
        rc = R.main(["--variant", "E1", "--frozen-dir", str(frozen_dir), "--out", str(out),
                     "--model", "krikri:8b", "--mode", "isolated"], http=http)
    assert rc == 0
    run_dir = out / "isolated" / "E1"
    names = sorted(p.name for p in run_dir.iterdir())
    assert names == sorted([f"{label}.json" for label, _ in R.RUN_ORDER] + ["run_meta.json"])
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["ollama_version"] == "0.0.0-test" and meta["format_self_test"]["ok"] is True
    # Second run into the same dir is refused.
    with contextlib.redirect_stderr(io.StringIO()):
        rc = R.main(["--variant", "E1", "--frozen-dir", str(frozen_dir), "--out", str(out),
                     "--model", "krikri:8b", "--mode", "isolated"], http=FakeHTTP())
    assert rc == R.EXIT_ERROR

    out = Path(tempfile.mkdtemp())
    http = FakeHTTP(chat_contents=["not json"])
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        rc = R.main(["--variant", "E2", "--frozen-dir", str(frozen_dir), "--out", str(out),
                     "--model", "krikri:8b", "--mode", "isolated"], http=http)
    assert rc == R.EXIT_SELFTEST and "FORMAT SELF-TEST FAILED" in err.getvalue()
    assert len(http.chats()) == 1  # nothing ran after the failed self-test


def test_out_dir_guard():
    raises(lambda: R.check_out_dir(R.REPO_ROOT / "evals" / "out"))
    R.check_out_dir(R.REPO_ROOT / "private" / "scratch" / "does_not_exist_xyz")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module.split(".")[0])
    return mods


def test_only_stdlib_requests_and_verify_imported():
    allowed_stdlib = {"argparse", "hashlib", "json", "sys", "time", "datetime", "pathlib",
                      "unicodedata", "dataclasses"}
    run_mods = _imported_modules(Path(R.__file__))
    assert run_mods <= allowed_stdlib | {"requests", "verify"}, run_mods
    verify_mods = _imported_modules(Path(R.__file__).with_name("verify.py"))
    assert verify_mods <= allowed_stdlib, verify_mods


def main() -> int:
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
