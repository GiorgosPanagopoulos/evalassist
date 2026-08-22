"""Idempotent persistence βοηθητικά για persons/evaluations/field_scores/documents/promotions.
Re-run ingestion του ίδιου doc_id/person/period ενημερώνει, δεν διπλασιάζει."""

import json
import sqlite3

from app.models.evaluation import EvaluationEntry, FieldScore


def upsert_person(conn: sqlite3.Connection, person_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO persons (person_id, name) VALUES (?, ?)
        ON CONFLICT(person_id) DO UPDATE SET name = excluded.name
        """,
        (person_id, name),
    )


def upsert_evaluation(conn: sqlite3.Connection, person_id: str, entry: EvaluationEntry) -> int:
    period = entry.period
    gnomatevon = entry.gnomatevon
    conn.execute(
        """
        INSERT INTO evaluations (
            person_id, period, period_start, period_end, ea_type, characterization,
            score, unit, duties, rank_at_time,
            evaluator_rank, evaluator_name, evaluator_role,
            gnomatevon_rank, gnomatevon_name, gnomatevon_role,
            defects, evaluator_notes, gnomatevon_notes, source_page
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(person_id, period) DO UPDATE SET
            period_start = excluded.period_start,
            period_end = excluded.period_end,
            ea_type = excluded.ea_type,
            characterization = excluded.characterization,
            score = excluded.score,
            unit = excluded.unit,
            duties = excluded.duties,
            rank_at_time = excluded.rank_at_time,
            evaluator_rank = excluded.evaluator_rank,
            evaluator_name = excluded.evaluator_name,
            evaluator_role = excluded.evaluator_role,
            gnomatevon_rank = excluded.gnomatevon_rank,
            gnomatevon_name = excluded.gnomatevon_name,
            gnomatevon_role = excluded.gnomatevon_role,
            defects = excluded.defects,
            evaluator_notes = excluded.evaluator_notes,
            gnomatevon_notes = excluded.gnomatevon_notes,
            source_page = excluded.source_page
        """,
        (
            person_id,
            period,
            entry.period_start.isoformat(),
            entry.period_end.isoformat(),
            entry.ea_type,
            entry.characterization,
            entry.score,
            entry.unit,
            json.dumps([d.model_dump() for d in entry.duties], ensure_ascii=False),
            entry.rank_at_time,
            entry.evaluator.rank,
            entry.evaluator.name,
            entry.evaluator.role,
            gnomatevon.rank if gnomatevon else None,
            gnomatevon.name if gnomatevon else None,
            gnomatevon.role if gnomatevon else None,
            entry.defects,
            entry.evaluator_notes,
            entry.gnomatevon_notes,
            entry.source_page,
        ),
    )
    row = conn.execute(
        "SELECT id FROM evaluations WHERE person_id = ? AND period = ?",
        (person_id, period),
    ).fetchone()
    return row["id"]


def replace_field_scores(
    conn: sqlite3.Connection, eval_id: int, field_scores: list[FieldScore]
) -> None:
    conn.execute("DELETE FROM field_scores WHERE eval_id = ?", (eval_id,))
    conn.executemany(
        "INSERT INTO field_scores (eval_id, field_code, description, value) VALUES (?, ?, ?, ?)",
        [(eval_id, fs.field_code, fs.description, str(fs.value)) for fs in field_scores],
    )


def replace_promotions(conn: sqlite3.Connection, person_id: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM promotions WHERE person_id = ?", (person_id,))
    conn.executemany(
        """
        INSERT INTO promotions (person_id, row_index, rank, decision_date, decision, promotion_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                person_id,
                i,
                row["rank"],
                row["decision_date"],
                row["decision"],
                row["promotion_date"],
            )
            for i, row in enumerate(rows)
        ],
    )


def replace_service_time(conn: sqlite3.Connection, person_id: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM service_time WHERE person_id = ?", (person_id,))
    conn.executemany(
        """
        INSERT INTO service_time
            (person_id, row_index, subsection, label, rank, unit, years, months, days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                person_id,
                i,
                row["subsection"],
                row["label"],
                row.get("rank"),
                row.get("unit"),
                row["years"],
                row["months"],
                row["days"],
            )
            for i, row in enumerate(rows)
        ],
    )


def get_promotions(conn: sqlite3.Connection, person_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT row_index, rank, decision_date, decision, promotion_date
        FROM promotions WHERE person_id = ? ORDER BY row_index
        """,
        (person_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_service_time(conn: sqlite3.Connection, person_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT row_index, subsection, label, years, months, days
        FROM service_time WHERE person_id = ? ORDER BY row_index
        """,
        (person_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_document(
    conn: sqlite3.Connection,
    doc_id: str,
    person_id: str,
    period: str,
    path: str,
    page_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO documents (doc_id, person_id, period, path, page_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(doc_id, period) DO UPDATE SET
            person_id = excluded.person_id,
            path = excluded.path,
            page_count = excluded.page_count
        """,
        (doc_id, person_id, period, path, page_count),
    )
