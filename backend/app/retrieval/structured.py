"""Ντετερμινιστικά SQL lookups πάνω σε evaluations/field_scores/documents —
καμία κλήση σε LLM εδώ.

Κάθε query περνάει από `IsolationScope.build_sql_where()` (parameterized,
ποτέ string interpolation user input). Άδειο αποτέλεσμα -> valid
StructuredResult με άδειο `data`, όχι exception.
"""

import json
import sqlite3

from app.retrieval.isolation import IsolationScope
from app.retrieval.models import StructuredResult


def _doc_ids_in_scope(conn: sqlite3.Connection, scope: IsolationScope) -> list[str]:
    where, params = scope.build_sql_where()
    rows = conn.execute(f"SELECT doc_id FROM documents WHERE {where}", params).fetchall()
    return [r["doc_id"] for r in rows]


def _coerce_value(raw: str) -> int | str:
    return int(raw) if raw.isdigit() else raw


def _field_scores(conn: sqlite3.Connection, eval_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT field_code, description, value FROM field_scores WHERE eval_id = ? "
        "ORDER BY field_code",
        (eval_id,),
    ).fetchall()
    return [
        {
            "field_code": r["field_code"],
            "description": r["description"],
            "value": _coerce_value(r["value"]),
        }
        for r in rows
    ]


def get_scores(conn: sqlite3.Connection, scope: IsolationScope) -> StructuredResult:
    where, params = scope.build_sql_where()
    row = conn.execute(f"SELECT * FROM evaluations WHERE {where}", params).fetchone()
    doc_ids = _doc_ids_in_scope(conn, scope)

    if row is None:
        return StructuredResult(data={}, sources=[], retrieved_doc_ids=doc_ids)

    data = {
        "person_id": scope.person_id,
        "period": scope.period,
        "ea_type": row["ea_type"],
        "characterization": row["characterization"],
        "score": row["score"],
        "unit": row["unit"],
        "duties": json.loads(row["duties"]) if row["duties"] else [],
        "rank_at_time": row["rank_at_time"],
        "evaluator": {
            "rank": row["evaluator_rank"],
            "name": row["evaluator_name"],
            "role": row["evaluator_role"],
        },
        "gnomatevon": (
            {"rank": row["gnomatevon_rank"], "name": row["gnomatevon_name"], "role": row["gnomatevon_role"]}
            if row["gnomatevon_name"]
            else None
        ),
        "defects": row["defects"],
        "evaluator_notes": row["evaluator_notes"],
        "gnomatevon_notes": row["gnomatevon_notes"],
        "field_scores": _field_scores(conn, row["id"]),
    }
    sources = [{"doc_id": doc_id, "section": "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ"} for doc_id in doc_ids]
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
        "entry_a": result_a.data,
        "entry_b": result_b.data,
    }
    sources = result_a.sources + result_b.sources
    retrieved_doc_ids = sorted(set(result_a.retrieved_doc_ids) | set(result_b.retrieved_doc_ids))
    return StructuredResult(data=data, sources=sources, retrieved_doc_ids=retrieved_doc_ids)


def top_bottom_sections(
    conn: sqlite3.Connection, scope: IsolationScope, n: int = 3
) -> StructuredResult:
    """Top/bottom N αναλυτικά πεδία (field_scores) βάσει αριθμητικής τιμής —
    τα ΝΑΙ/ΟΧΙ πεδία δεν κατατάσσονται (δεν είναι αριθμητικά)."""
    result = get_scores(conn, scope)
    field_scores = result.data.get("field_scores", [])
    numeric = [fs for fs in field_scores if isinstance(fs["value"], int)]
    ranked = sorted(numeric, key=lambda fs: fs["value"], reverse=True)

    data = {
        "person_id": scope.person_id,
        "period": scope.period,
        "top": ranked[:n],
        "bottom": list(reversed(ranked[-n:])) if ranked else [],
    }
    return StructuredResult(
        data=data, sources=result.sources, retrieved_doc_ids=result.retrieved_doc_ids
    )
