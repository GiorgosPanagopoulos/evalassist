"""Mini test/sample flow για το backend/app/ingestion/context_header.py
(προσθήκη section context marker στο τοπικό indexed text πριν το add_chunk).

Εκτελείται standalone: `python tests/test_context_header.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ingestion.context_header as context_header  # noqa: E402
from app.ingestion.context_header import add_section_context_header  # noqa: E402

_SECTION = "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ"
_TEXT = "1. - ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ (Ημερομηνία Τελευταίας Προαγωγής: 05/07/2019)\n\nΒΑΘΜΟΣ"


def test_normal_case_prepends_marker():
    result = add_section_context_header(_TEXT, _SECTION)
    assert result == f"[ΕΝΟΤΗΤΑ: {_SECTION}]\n\n{_TEXT}"


def test_section_none_returns_text_unchanged():
    assert add_section_context_header(_TEXT, None) == _TEXT


def test_idempotency_second_call_does_not_double_marker():
    once = add_section_context_header(_TEXT, _SECTION)
    twice = add_section_context_header(once, _SECTION)
    assert once == twice


def test_exception_path_returns_input_unchanged():
    original = context_header._annotate

    def _boom(_text, _section):
        raise RuntimeError("forced failure for test")

    context_header._annotate = _boom
    try:
        result = add_section_context_header(_TEXT, _SECTION)
    finally:
        context_header._annotate = original
    assert result == _TEXT


def run_all():
    tests = [
        test_normal_case_prepends_marker,
        test_section_none_returns_text_unchanged,
        test_idempotency_second_call_does_not_double_marker,
        test_exception_path_returns_input_unchanged,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
