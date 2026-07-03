"""Meta endpoints: person/period lookups (χωρίς isolation scope — μη
person-scoped listings) και health check."""

import sqlite3

import httpx
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.core.config import Settings, get_settings

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


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    ollama_reachable = False
    try:
        response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=1.0)
        ollama_reachable = response.status_code == 200
    except Exception:
        ollama_reachable = False
    return {"status": "ok", "ollama_reachable": ollama_reachable}
