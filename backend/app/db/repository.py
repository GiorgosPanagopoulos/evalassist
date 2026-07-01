"""Idempotent persistence βοηθητικά για persons/evaluations/scores/documents.
Re-run ingestion του ίδιου doc_id/person/period ενημερώνει, δεν διπλασιάζει."""

import sqlite3

from app.models.evaluation import SectionScore


def upsert_person(conn: sqlite3.Connection, person_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO persons (person_id, name) VALUES (?, ?)
        ON CONFLICT(person_id) DO UPDATE SET name = excluded.name
        """,
        (person_id, name),
    )


def upsert_evaluation(
    conn: sqlite3.Connection,
    person_id: str,
    period: str,
    gnmatefsi: str,
    overall_comment: str | None,
) -> int:
    conn.execute(
        """
        INSERT INTO evaluations (person_id, period, gnmatefsi, overall_comment)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(person_id, period) DO UPDATE SET
            gnmatefsi = excluded.gnmatefsi,
            overall_comment = excluded.overall_comment
        """,
        (person_id, period, gnmatefsi, overall_comment),
    )
    row = conn.execute(
        "SELECT id FROM evaluations WHERE person_id = ? AND period = ?",
        (person_id, period),
    ).fetchone()
    return row["id"]


def replace_scores(conn: sqlite3.Connection, eval_id: int, sections: list[SectionScore]) -> None:
    conn.execute("DELETE FROM scores WHERE eval_id = ?", (eval_id,))
    conn.executemany(
        "INSERT INTO scores (eval_id, section, score, comment) VALUES (?, ?, ?, ?)",
        [(eval_id, s.section, s.score, s.comment) for s in sections],
    )


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
        ON CONFLICT(doc_id) DO UPDATE SET
            person_id = excluded.person_id,
            period = excluded.period,
            path = excluded.path,
            page_count = excluded.page_count
        """,
        (doc_id, person_id, period, path, page_count),
    )
