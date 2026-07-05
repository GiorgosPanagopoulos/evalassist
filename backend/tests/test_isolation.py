"""Mini test/sample flow για το IsolationScope (Φάση 3).

Καλύπτει:
  - build_chroma_where(): $and dict με 2 πεδία (person_id, period) και 3
    πεδία (+ doc_id).
  - build_sql_where(): parameterized WHERE fragment + params, με και χωρίς
    doc_id narrowing.

Εκτελείται standalone: `python tests/test_isolation.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.isolation import IsolationScope  # noqa: E402


def test_chroma_where_two_fields():
    scope = IsolationScope(person_id="p1", period="2025")
    where = scope.build_chroma_where()
    assert where == {"$and": [{"person_id": "p1"}, {"period": "2025"}]}


def test_chroma_where_three_fields_with_doc_id():
    scope = IsolationScope(person_id="p1", period="2025", doc_id="doc-abc")
    where = scope.build_chroma_where()
    assert where == {"$and": [{"person_id": "p1"}, {"period": "2025"}, {"doc_id": "doc-abc"}]}


def test_sql_where_two_fields():
    scope = IsolationScope(person_id="p1", period="2025")
    where, params = scope.build_sql_where()
    assert where == "person_id = ? AND period = ?"
    assert params == ["p1", "2025"]


def test_sql_where_doc_id_narrowed():
    scope = IsolationScope(person_id="p1", period="2025", doc_id="doc-abc")
    where, params = scope.build_sql_where()
    assert where == "person_id = ? AND period = ? AND doc_id = ?"
    assert params == ["p1", "2025", "doc-abc"]


def run_all():
    tests = [
        test_chroma_where_two_fields,
        test_chroma_where_three_fields_with_doc_id,
        test_sql_where_two_fields,
        test_sql_where_doc_id_narrowed,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
