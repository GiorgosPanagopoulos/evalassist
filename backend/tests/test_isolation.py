"""Mini test/sample flow για το IsolationScope (Φάση 3).

Καλύπτει:
  - build_chroma_where(): $and dict με person_id (hard AND, ποτέ μέσα σε
    $or) + $or(period, career) για τη διεύρυνση career-wide chunks, με και
    χωρίς doc_id narrowing.
  - build_sql_where(): parameterized WHERE fragment + params, με και χωρίς
    doc_id narrowing.

Εκτελείται standalone: `python tests/test_isolation.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.isolation import IsolationScope  # noqa: E402


def test_chroma_where_widens_period_to_include_career():
    scope = IsolationScope(person_id="p1", period="2025")
    where = scope.build_chroma_where()
    assert where == {
        "$and": [
            {"person_id": "p1"},
            {"$or": [{"period": "2025"}, {"period": "career"}]},
        ]
    }


def test_chroma_where_three_fields_with_doc_id():
    scope = IsolationScope(person_id="p1", period="2025", doc_id="doc-abc")
    where = scope.build_chroma_where()
    assert where == {
        "$and": [
            {"person_id": "p1"},
            {"$or": [{"period": "2025"}, {"period": "career"}]},
            {"doc_id": "doc-abc"},
        ]
    }


def test_chroma_where_no_duplicate_or_when_period_is_career():
    """Όταν το ζητούμενο period ΕΙΝΑΙ ήδη 'career', δεν χρειάζεται $or
    διπλότυπο (θα ήταν {period: career} OR {period: career})."""
    scope = IsolationScope(person_id="p1", period="career")
    where = scope.build_chroma_where()
    assert where == {"$and": [{"person_id": "p1"}, {"period": "career"}]}


def test_chroma_where_person_id_never_inside_or():
    """Regression: person_id πρέπει να μένει πάντα hard top-level AND
    clause, ΠΟΤΕ μέσα στο $or του period. Αυτό είναι το πραγματικό isolation."""
    scope = IsolationScope(person_id="p1", period="2025")
    where = scope.build_chroma_where()
    top_level_fields = {tuple(clause.keys())[0] for clause in where["$and"]}
    assert "person_id" in top_level_fields
    or_clause = next(clause["$or"] for clause in where["$and"] if "$or" in clause)
    assert all("person_id" not in leaf for leaf in or_clause)


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
        test_chroma_where_widens_period_to_include_career,
        test_chroma_where_three_fields_with_doc_id,
        test_chroma_where_no_duplicate_or_when_period_is_career,
        test_chroma_where_person_id_never_inside_or,
        test_sql_where_two_fields,
        test_sql_where_doc_id_narrowed,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
