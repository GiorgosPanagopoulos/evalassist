"""Mini test/sample flow για το backend/app/core/prompt_loader.py (refactor step).

Καλύπτει:
  - load v1 ρητά.
  - "latest" resolution: ντετερμινιστικό μέγιστο vN ανάμεσα σε πολλαπλά
    διαθέσιμα αρχεία (fake prompt directory, χωρίς εξάρτηση από τα
    πραγματικά prompts/ του project).
  - missing name / missing version -> PromptNotFoundError.

Εκτελείται standalone: `python tests/test_prompt_loader.py`
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.core.prompt_loader as prompt_loader  # noqa: E402
from app.core.prompt_loader import PromptNotFoundError, load_prompt  # noqa: E402


def test_real_semantic_rag_v1_loads():
    text, version = load_prompt("semantic_rag", version="v1")
    assert version == "v1"
    assert "Ελληνικά" in text


def test_missing_prompt_name_raises():
    try:
        load_prompt("does_not_exist")
    except PromptNotFoundError:
        pass
    else:
        raise AssertionError("αναμένονταν PromptNotFoundError για άγνωστο prompt name")


def test_latest_resolution_and_missing_version_with_fake_prompts_dir():
    tmp_dir = Path(tempfile.mkdtemp(prefix="evalassist_prompts_test_"))
    original_prompts_dir = prompt_loader.PROMPTS_DIR
    try:
        prompt_dir = tmp_dir / "fake_prompt"
        prompt_dir.mkdir()
        (prompt_dir / "v1.txt").write_text("πρώτη έκδοση", encoding="utf-8")
        (prompt_dir / "v2.txt").write_text("δεύτερη έκδοση", encoding="utf-8")
        (prompt_dir / "v10.txt").write_text("δέκατη έκδοση", encoding="utf-8")
        prompt_loader.PROMPTS_DIR = tmp_dir

        text, version = load_prompt("fake_prompt")  # default: latest
        assert version == "v10", f"αναμένονταν v10 ως latest (max), βρέθηκε {version}"
        assert text == "δέκατη έκδοση"

        text_v1, version_v1 = load_prompt("fake_prompt", version="v1")
        assert version_v1 == "v1"
        assert text_v1 == "πρώτη έκδοση"

        try:
            load_prompt("fake_prompt", version="v99")
        except PromptNotFoundError:
            pass
        else:
            raise AssertionError("αναμένονταν PromptNotFoundError για ανύπαρκτη version")
    finally:
        prompt_loader.PROMPTS_DIR = original_prompts_dir
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_all():
    tests = [
        test_real_semantic_rag_v1_loads,
        test_missing_prompt_name_raises,
        test_latest_resolution_and_missing_version_with_fake_prompts_dir,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
