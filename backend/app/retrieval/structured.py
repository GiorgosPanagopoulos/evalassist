"""Ντετερμινιστικά SQL lookups πάνω σε evaluations/scores/documents — καμία
κλήση σε LLM εδώ.

Κάθε query περνάει από `IsolationScope.build_sql_where()` (parameterized,
ποτέ string interpolation user input). Άδειο αποτέλεσμα -> valid
StructuredResult με άδειο `data`, όχι exception.
"""

import sqlite3

from app.retrieval.isolation import IsolationScope
from app.retrieval.models import StructuredResult


def _doc_ids_in_scope(conn: sqlite3.Connection, scope: IsolationScope) -> list[str]:
    where, params = scope.build_sql_where()
    rows = conn.execute(f"SELECT doc_id FROM documents WHERE {where}", params).fetchall()
    return [r["doc_id"] for r in rows]


def get_scores(conn: sqlite3.Connection, scope: IsolationScope) -> StructuredResult:
    where, params = scope.build_sql_where()
    rows = conn.execute(
        f"""
        SELECT e.gnmatefsi, e.overall_comment, s.section, s.score, s.comment
        FROM evaluations e
        JOIN scores s ON s.eval_id = e.id
        WHERE {where}
        """,
        params,
    ).fetchall()
    doc_ids = _doc_ids_in_scope(conn, scope)

    if not rows:
        return StructuredResult(data={}, sources=[], retrieved_doc_ids=doc_ids)

    sections = [
        {"section": r["section"], "score": r["score"], "comment": r["comment"]} for r in rows
    ]
    data = {
        "person_id": scope.person_id,
        "period": scope.period,
        "gnmatefsi": rows[0]["gnmatefsi"],
        "overall_comment": rows[0]["overall_comment"],
        "sections": sections,
    }
    sources = [
        {"doc_id": doc_id, "section": s["section"]} for s in sections for doc_id in doc_ids
    ]
    return StructuredResult(data=data, sources=sources, retrieved_doc_ids=doc_ids)


def compare_periods(
    conn: sqlite3.Connection, person_id: str, period_a: str, period_b: str
) -> StructuredResult:
    result_a = get_scores(conn, IsolationScope(person_id=person_id, period=period_a))
    result_b = get_scores(conn, IsolationScope(person_id=person_id, period=period_b))

    data = {
        "person_id": person_id,
        "period_a": period_a,
        "period_b": period_b,
        "sections_a": result_a.data.get("sections", []),
        "sections_b": result_b.data.get("sections", []),
    }
    sources = result_a.sources + result_b.sources
    retrieved_doc_ids = sorted(set(result_a.retrieved_doc_ids) | set(result_b.retrieved_doc_ids))
    return StructuredResult(data=data, sources=sources, retrieved_doc_ids=retrieved_doc_ids)


def top_bottom_sections(conn: sqlite3.Connection, scope: IsolationScope, n: int = 3) -> StructuredResult:
    result = get_scores(conn, scope)
    sections = result.data.get("sections", [])
    ranked = sorted(sections, key=lambda s: s["score"], reverse=True)

    data = {
        "person_id": scope.person_id,
        "period": scope.period,
        "top": ranked[:n],
        "bottom": list(reversed(ranked[-n:])) if ranked else [],
    }
    return StructuredResult(data=data, sources=result.sources, retrieved_doc_ids=result.retrieved_doc_ids)
