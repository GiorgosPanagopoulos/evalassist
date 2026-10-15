"""Meta endpoints: person/period lookups (χωρίς isolation scope — μη
person-scoped listings). Απαιτούν session (require_user στο include_router):
δίνουν ονόματα αξιολογουμένων. Το health check είναι στο routes_health."""

import sqlite3

from fastapi import APIRouter, Depends

from app.api.deps import get_db

router = APIRouter()


@router.get("/persons")
def list_persons(conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    rows = conn.execute("SELECT person_id, name FROM persons ORDER BY person_id").fetchall()
    return [{"person_id": row["person_id"], "name": row["name"]} for row in rows]


@router.get("/persons/{person_id}/periods")
def list_periods(person_id: str, conn: sqlite3.Connection = Depends(get_db)) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT period FROM evaluations WHERE person_id = ? ORDER BY period",
        (person_id,),
    ).fetchall()
    return [row["period"] for row in rows]
