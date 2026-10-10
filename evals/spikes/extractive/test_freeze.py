"""Tests for the pure parts of freeze.py. Synthetic data only, no models, no Chroma.

Run: PYTHONPATH=. python evals/spikes/extractive/test_freeze.py
"""

import contextlib
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

from evals.spikes.extractive.freeze import (
    COPY_DIRNAME,
    EXIT_COPY_LEFT,
    EXIT_ERROR,
    EXIT_MUTATION,
    REPO_ROOT,
    SECTION_PREFIX,
    SUBSECTION_PREFIX,
    FreezeError,
    build_extractive_user_prompt,
    build_hash_lines,
    check_equivalence,
    check_out_dir,
    check_periods,
    freeze,
    hash_tree,
    line_stats,
    load_questions,
    preflight,
    resolve_person_id,
    run,
    strip_headers,
)

# isort: split
# app is importable only after freeze has put backend/ on sys.path.
import app.core.config as app_config  # noqa: E402
from app.ingestion.context_header import add_section_context_header  # noqa: E402
from app.ingestion.subsection_marker import annotate_subsection_continuation  # noqa: E402


def cps(s: str) -> list[str]:
    return [f"U+{ord(c):04X}" for c in s]


def raises(fn, exc=FreezeError) -> str:
    try:
        fn()
    except exc as e:
        return str(e)
    raise AssertionError(f"{exc.__name__} not raised")


def production_document(body: str, section: str | None, subsection: str | None) -> str:
    # Same order as pipeline.py:161-162.
    return add_section_context_header(annotate_subsection_continuation(body, subsection), section)


# --- prefixes --------------------------------------------------------------


def test_prefix_codepoints():
    assert cps(SECTION_PREFIX) == [
        "U+005B", "U+0395", "U+039D", "U+039F", "U+03A4", "U+0397", "U+03A4", "U+0391", "U+003A",
    ]
    assert SECTION_PREFIX == "[\u0395\u039d\u039f\u03a4\u0397\u03a4\u0391:"
    assert SUBSECTION_PREFIX == (
        "[\u03a3\u03a5\u039d\u0395\u03a7\u0395\u0399\u0391 "
        "\u03a5\u03a0\u039f\u0395\u039d\u039f\u03a4\u0397\u03a4\u0391\u03a3:"
    )


def test_section_header_format_matches_production():
    assert add_section_context_header("X", "S") == f"{SECTION_PREFIX} S]\n\nX"
    assert annotate_subsection_continuation("X", "α. Τ") == f"{SUBSECTION_PREFIX} α. Τ]\n\nX"


# --- strip_headers ---------------------------------------------------------


def test_strip_both_headers():
    body = "ΓΡΑΜΜΗ 1\nΓΡΑΜΜΗ 2"
    doc = production_document(body, "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ", "γ.  Ανά Κατηγορία")
    assert doc.startswith(SECTION_PREFIX)
    assert strip_headers(doc, "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ") == (body, "γ.  Ανά Κατηγορία")


def test_strip_section_only():
    doc = production_document("ΣΩΜΑ", "ΤΟΠΟΘΕΤΗΣΕΙΣ", None)
    assert strip_headers(doc, "ΤΟΠΟΘΕΤΗΣΕΙΣ") == ("ΣΩΜΑ", None)


def test_strip_unknown_section_has_no_header():
    # section=None at ingestion: no header in the text, metadata says "Άγνωστη Ενότητα".
    doc = production_document("ΣΩΜΑ", None, None)
    assert doc == "ΣΩΜΑ"
    assert strip_headers(doc, "Άγνωστη Ενότητα") == ("ΣΩΜΑ", None)


def test_strip_subsection_only():
    doc = production_document("ΣΩΜΑ", None, "δ. Υγεία")
    assert strip_headers(doc, "Άγνωστη Ενότητα") == ("ΣΩΜΑ", "δ. Υγεία")


def test_strip_keeps_later_brackets_in_body():
    body = "Α ]\n\nΒ [ΕΝΟΤΗΤΑ: Χ]\n\nΓ"
    doc = production_document(body, "S", "α. T")
    assert strip_headers(doc, "S") == (body, "α. T")


def test_strip_section_mismatch_raises():
    doc = production_document("ΣΩΜΑ", "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ", None)
    raises(lambda: strip_headers(doc, "ΤΟΠΟΘΕΤΗΣΕΙΣ"))


def test_strip_unterminated_subsection_raises():
    raises(lambda: strip_headers(f"{SUBSECTION_PREFIX} α. T] ΣΩΜΑ", "S"))


def test_strip_double_header_raises():
    doc = f"{SECTION_PREFIX} S]\n\n{SECTION_PREFIX} S]\n\nΣΩΜΑ"
    raises(lambda: strip_headers(doc, "S"))
    doc = f"{SUBSECTION_PREFIX} a]\n\n{SUBSECTION_PREFIX} b]\n\nΣΩΜΑ"
    raises(lambda: strip_headers(doc, "S"))


# --- dump stats and prompt -------------------------------------------------


def test_line_stats():
    body = "ΠΡΩΤΗ ΓΡΑΜΜΗ.\nΔΕΝ\n\nΣΥΝΙΣΤΑΤΑΙ;\nΕΞΑΙΡΕΤΟΣ (100)  "
    assert line_stats(body) == {
        "n_chars": len(body),
        "n_lines": 5,
        "n_nonempty_lines": 4,
        "n_lines_without_final_punctuation": 2,
    }
    assert line_stats("") == {
        "n_chars": 0, "n_lines": 1, "n_nonempty_lines": 0, "n_lines_without_final_punctuation": 0,
    }


def test_extractive_user_prompt_format():
    excerpts = [
        {"n": 1, "doc_id": "D", "page": 2, "section": "S1", "period": "career",
         "subsection": "α. T", "person_name": "N", "body": "B1"},
        {"n": 2, "doc_id": "D", "page": 3, "section": "S2", "period": "2001-01-01..2001-12-31",
         "subsection": None, "person_name": None, "body": "B2"},
    ]
    assert build_extractive_user_prompt("Q;", excerpts) == (
        "Ερώτημα: Q;\n\nΑποσπάσματα:\n\n"
        "[1] [D σελ.2 - S1 - περίοδος: career - υποενότητα: α. T - person_name: N]\nB1"
        "\n\n---\n\n"
        "[2] [D σελ.3 - S2 - περίοδος: 2001-01-01..2001-12-31]\nB2"
    )


# --- inputs and output guard -----------------------------------------------


def _questions_file(lines: list[str]) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "q.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_load_questions_valid():
    p = _questions_file([
        json.dumps({"id": "C1", "question": "Q1", "period": "2001-01-01..2001-12-31"}),
        "",
        json.dumps({"id": "B09", "question": "Q2", "period": "career"}),
    ])
    assert [q["id"] for q in load_questions(p)] == ["C1", "B09"]


def test_load_questions_invalid():
    ok = {"id": "C1", "question": "Q", "period": "2001-01-01..2001-12-31"}
    bad_sets = [
        [json.dumps({"id": "C1", "question": "Q"})],
        [json.dumps({**ok, "id": "../x"})],
        [json.dumps(ok), json.dumps(ok)],
        [json.dumps({**ok, "period": "2001"})],
        [""],
    ]
    for lines in bad_sets:
        raises(lambda lines=lines: load_questions(_questions_file(lines)))


def test_out_dir_guard():
    raises(lambda: check_out_dir(REPO_ROOT / "evals" / "spikes" / "extractive" / "out"))
    raises(lambda: check_out_dir(REPO_ROOT / "frozen"))
    check_out_dir(REPO_ROOT / "private" / "scratch" / "does_not_exist_xyz")
    outside = Path(tempfile.mkdtemp())
    check_out_dir(outside)
    (outside / "f").write_text("x")
    raises(lambda: check_out_dir(outside))


def test_out_dir_guard_ignores_chroma_copy():
    out = Path(tempfile.mkdtemp())
    (out / COPY_DIRNAME).mkdir()
    (out / COPY_DIRNAME / "chroma.sqlite3").write_bytes(b"x")
    check_out_dir(out)
    (out / "frozen_C1.json").write_text("{}")
    raises(lambda: check_out_dir(out))


def test_hash_lines_exclude_chroma_copy():
    out = Path(tempfile.mkdtemp())
    copy_dir = out / COPY_DIRNAME
    copy_dir.mkdir()
    (copy_dir / "chroma.sqlite3").write_bytes(b"x")
    frozen = out / "frozen_C1.json"
    frozen.write_text("{}")
    q = out / "q.jsonl"
    q.write_text("{}")
    lines = build_hash_lines([frozen], copy_dir, q, {"chroma.sqlite3": "h"})
    assert [ln.split("  ", 1)[1] for ln in lines] == [
        "frozen_C1.json", "questions:q.jsonl", "chroma_original/chroma.sqlite3",
    ]
    assert not any(COPY_DIRNAME in ln for ln in lines)
    raises(lambda: build_hash_lines([copy_dir / "chroma.sqlite3"], copy_dir, q, {}))


# --- run(): mandatory deletion of the Chroma copy ---------------------------


def _fake_freeze(rc=0, exc=None):
    def fake(person_id, questions_path, out, copy_dir):
        copy_dir.mkdir(parents=True)
        (copy_dir / "chroma.sqlite3").write_bytes(b"real data")
        if exc is not None:
            raise exc
        return rc

    return fake


def _run_capturing(out: Path, fake) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = run("P", Path("q.jsonl"), out, freeze_fn=fake)
    return rc, err.getvalue()


def test_run_deletes_copy_exit_0():
    out = Path(tempfile.mkdtemp())
    rc, err = _run_capturing(out, _fake_freeze(0))
    assert rc == 0, err
    assert not (out / COPY_DIRNAME).exists()


def test_run_deletes_copy_and_keeps_exit_code():
    out = Path(tempfile.mkdtemp())
    assert _run_capturing(out, _fake_freeze(EXIT_MUTATION))[0] == EXIT_MUTATION
    assert not (out / COPY_DIRNAME).exists()
    out = Path(tempfile.mkdtemp())
    rc, err = _run_capturing(out, _fake_freeze(exc=FreezeError("boom")))
    assert rc == EXIT_ERROR and "FREEZE ERROR: boom" in err
    assert not (out / COPY_DIRNAME).exists()
    out = Path(tempfile.mkdtemp())
    rc, err = _run_capturing(out, _fake_freeze(exc=ValueError("crash")))
    assert rc == EXIT_ERROR and "ValueError: crash" in err
    assert not (out / COPY_DIRNAME).exists()


def _make_undeletable(copy_dir: Path) -> None:
    # A directory without write permission cannot have its entries removed.
    os.chmod(copy_dir, stat.S_IRUSR | stat.S_IXUSR)


def test_run_copy_deletion_fails():
    assert EXIT_COPY_LEFT not in (0, EXIT_ERROR, EXIT_MUTATION)
    if os.name == "nt":
        # POSIX directory permissions are needed to make rmtree fail for real.
        print("    (SKIPPED on Windows: needs POSIX directory permissions)")
        return
    for inner in (_fake_freeze(0), _fake_freeze(EXIT_MUTATION), _fake_freeze(exc=FreezeError("x"))):
        out = Path(tempfile.mkdtemp())
        copy_dir = out / COPY_DIRNAME

        def fake(person_id, questions_path, out_, copy_dir_, inner=inner):
            try:
                return inner(person_id, questions_path, out_, copy_dir_)
            finally:
                _make_undeletable(copy_dir_)

        try:
            rc, err = _run_capturing(out, fake)
            assert rc == EXIT_COPY_LEFT, (rc, err)
            assert str(copy_dir) in err and "REAL DATA" in err and "by hand" in err, err
            assert copy_dir.exists()
        finally:
            os.chmod(copy_dir, stat.S_IRWXU)


# --- preflight: person_id, periods, encoding ---------------------------------

P1 = "1234567"
P2 = "7654321"
PER_A = "2001-01-01..2001-12-31"
PER_B = "2002-01-01..2002-06-30"


def _db(persons: list[str], evaluations: list[tuple[str, str]]) -> Path:
    path = Path(tempfile.mkdtemp()) / "db.sqlite3"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE persons (person_id TEXT PRIMARY KEY, name TEXT NOT NULL)")
    con.execute("CREATE TABLE evaluations (person_id TEXT NOT NULL, period TEXT NOT NULL)")
    con.executemany("INSERT INTO persons VALUES (?, 'N')", [(p,) for p in persons])
    con.executemany("INSERT INTO evaluations VALUES (?, ?)", evaluations)
    con.commit()
    con.close()
    return path


def _con(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def test_person_id_exact_match():
    con = _con(_db([P1, P2], []))
    assert resolve_person_id(con, P1) == P1
    assert resolve_person_id(con, P2) == P2


def test_person_id_not_found_shows_codepoints():
    con = _con(_db([P1], []))
    fullwidth = "".join(chr(0xFF10 + int(d)) for d in P1)
    for bad in (P1 + " ", " " + P1, P1[:-1], fullwidth, P1 + "\ufeff", ""):
        msg = raises(lambda bad=bad: resolve_person_id(con, bad))
        assert "codepoints:" in msg, msg
        for c in bad:
            assert f"U+{ord(c):04X}" in msg, (bad, msg)
    msg = raises(lambda: resolve_person_id(con, fullwidth))
    assert "U+FF11" in msg


def test_person_id_auto():
    assert resolve_person_id(_con(_db([P1], [])), "auto") == P1
    raises(lambda: resolve_person_id(_con(_db([], [])), "auto"))
    msg = raises(lambda: resolve_person_id(_con(_db([P1, P2], [])), "auto"))
    assert "found 2" in msg and P1 not in msg and P2 not in msg


def test_periods_present():
    con = _con(_db([P1, P2], [(P1, PER_A), (P1, PER_B), (P2, "2003-01-01..2003-12-31")]))
    qs = [{"id": "A", "period": PER_A}, {"id": "B", "period": PER_B},
          {"id": "C", "period": "career"}]
    check_periods(con, P1, qs)


def test_periods_missing():
    con = _con(_db([P1, P2], [(P1, PER_A), (P2, PER_B)]))
    msg = raises(lambda: check_periods(con, P1, [{"id": "B09", "period": PER_B}]))
    assert "B09" in msg and PER_B in msg
    raises(lambda: check_periods(con, P1, [{"id": "X", "period": "2001-01-01..2001-12-30"}]))
    raises(lambda: check_periods(con, P2, [{"id": "X", "period": PER_A}]))


def _qfile(content: bytes) -> Path:
    p = Path(tempfile.mkdtemp()) / "questions.jsonl"
    p.write_bytes(content)
    return p


def test_questions_utf8_with_and_without_bom():
    line = json.dumps({"id": "C1", "question": "Ποιος ήταν ο χαρακτηρισμός;", "period": PER_A},
                      ensure_ascii=False)
    for raw in (line.encode("utf-8"), b"\xef\xbb\xbf" + line.encode("utf-8")):
        [q] = load_questions(_qfile(raw))
        assert q["id"] == "C1" and q["question"].startswith("Ποιος")


def test_questions_wrong_encoding_rejected():
    line = json.dumps({"id": "C1", "question": "Ποιος;", "period": PER_A}, ensure_ascii=False)
    for raw in (line.encode("cp1253"), line.encode("utf-16")):
        msg = raises(lambda raw=raw: load_questions(_qfile(raw)))
        assert "UTF-8" in msg, msg
    raises(lambda: load_questions(_qfile(b"\xef\xbb\xbf" + b"not json")))


def test_preflight_ok():
    db = _db([P1], [(P1, PER_A)])
    q = _qfile(json.dumps({"id": "C1", "question": "Q", "period": PER_A}).encode())
    person, qs = preflight(db, "auto", q, Path(tempfile.mkdtemp()))
    assert person == P1 and [x["id"] for x in qs] == ["C1"]


class _ChromadbBlocked:
    """sys.modules['chromadb'] = None makes 'import chromadb' raise ImportError."""

    def __enter__(self):
        self.saved = sys.modules.get("chromadb", "absent")
        sys.modules["chromadb"] = None

    def __exit__(self, *exc):
        if self.saved == "absent":
            del sys.modules["chromadb"]
        else:
            sys.modules["chromadb"] = self.saved


def _freeze_with_db(db: Path, person_arg: str, period: str):
    q = _qfile(json.dumps({"id": "C1", "question": "Q", "period": period}).encode())
    out = Path(tempfile.mkdtemp())
    saved = app_config.get_settings
    app_config.get_settings = lambda: SimpleNamespace(DB_PATH=db)
    try:
        with _ChromadbBlocked():
            return freeze(person_arg, q, out, out / COPY_DIRNAME)
    finally:
        app_config.get_settings = saved


def test_freeze_fails_before_chromadb_and_models():
    db = _db([P1], [(P1, PER_A)])
    # Bad person / bad period: FreezeError before 'import chromadb' is reached.
    raises(lambda: _freeze_with_db(db, P2, PER_A))
    raises(lambda: _freeze_with_db(db, P1, PER_B))
    raises(lambda: _freeze_with_db(_db([P1, P2], [(P1, PER_A)]), "auto", PER_A))
    # Control: valid inputs pass preflight and stop at the blocked import.
    raises(lambda: _freeze_with_db(db, P1, PER_A), exc=ImportError)
    raises(lambda: _freeze_with_db(db, "auto", "career"), exc=ImportError)


def test_hash_tree():
    d = Path(tempfile.mkdtemp())
    (d / "sub").mkdir()
    (d / "a").write_bytes(b"a")
    (d / "sub" / "b").write_bytes(b"b")
    h = hash_tree(d)
    assert sorted(h) == ["a", "sub/b"]
    assert h["a"] == "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"


# --- equivalence check -----------------------------------------------------


def _frozen():
    return [
        {"n": 1, "doc_id": "D", "page": 1, "section": "S1", "score": 0.9, "raw_document": "RAW1"},
        {"n": 2, "doc_id": "D", "page": 2, "section": "S2", "score": 0.5, "raw_document": "RAW2"},
    ]


def _cit(e):
    return SimpleNamespace(doc_id=e["doc_id"], page=e["page"], section=e["section"], score=e["score"])


def test_equivalence_ok():
    fr = _frozen()
    check_equivalence(fr, [_cit(e) for e in fr], "[l]\nRAW1\n\n---\n\n[l]\nRAW2")
    check_equivalence([], [], None)


def test_equivalence_failures():
    fr = _frozen()
    cits = [_cit(e) for e in fr]
    prompt = "[l]\nRAW1\n\n---\n\n[l]\nRAW2"
    raises(lambda: check_equivalence(fr, cits[::-1], prompt))
    changed = [_cit({**fr[0], "score": 0.91}), cits[1]]
    raises(lambda: check_equivalence(fr, changed, prompt))
    raises(lambda: check_equivalence(fr, cits[:1], prompt))
    raises(lambda: check_equivalence(fr, cits, "[l]\nRAW1"))
    raises(lambda: check_equivalence(fr, cits, "[l]\nRAW2\n\n---\n\n[l]\nRAW1"))
    raises(lambda: check_equivalence(fr, cits, None))


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
