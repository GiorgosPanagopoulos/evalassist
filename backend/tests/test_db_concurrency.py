"""Παράλληλα requests πάνω στην ίδια SQLite ΒΔ.

Το UI στέλνει ταυτόχρονα GET /persons/{id}/periods και GET /person/{id}/timeline.
Το FastAPI τρέχει το get_db (sync generator), το get_current_session και το
endpoint σε threads του threadpool που μπορεί να διαφέρουν μεταξύ τους, οπότε
η σύνδεση ανά request πρέπει να χρησιμοποιείται από όποιο thread την πάρει.

  - positive: N παράλληλα timeline + N παράλληλα periods, όλα 200.
  - positive: ακριβώς μία γραμμή audit ανά timeline request (το periods δεν
    κάνει audit), καμία χαμένη και καμία διπλή.
  - η βάση μπαίνει σε WAL· αν δεν μπει (π.χ. network filesystem), μία
    προειδοποίηση στο log ανά βάση, όχι σε κάθε σύνδεση.

Πραγματική ταυτοχρονία: httpx.AsyncClient πάνω στο ASGITransport και
asyncio.gather, όχι σειριακές κλήσεις του TestClient.

Εκτελείται standalone: `PYTHONPATH=. python tests/test_db_concurrency.py`
"""

import asyncio
import logging
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from auth_helpers import BASE_URL, TEST_PASSWORD, TEST_USERNAME, make_user  # noqa: E402
from db_helpers import remove_db  # noqa: E402

from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db import (
    database,  # noqa: E402
    repository,  # noqa: E402
)
from app.db.database import get_connection, init_db  # noqa: E402
from app.models.evaluation import EvaluationEntry, EvaluatorInfo  # noqa: E402

PERSON = "Μ-01253"
DOC_ID = "29b215931c674b6e"
N = 8

_PERIODS = [
    ("2022-01-01", "2022-06-30", 100),
    ("2022-07-01", "2022-12-31", 99),
    ("2023-01-01", "2023-06-30", 96),
    ("2023-07-01", "2023-12-31", 100),
]


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repository.upsert_person(conn, PERSON, "Παπαδόπουλος Γιώργος")
    for start, end, score in _PERIODS:
        entry = EvaluationEntry(
            period_start=date.fromisoformat(start),
            period_end=date.fromisoformat(end),
            characterization="ΕΞΑΙΡΕΤΟΣ",
            score=score,
            ea_type="Ε.Α.",
            unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
            evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Ιωάννης Καραγιάννης", role="Διοικητής"),
            source_page=4,
        )
        repository.upsert_evaluation(conn, PERSON, entry)
        repository.upsert_document(conn, DOC_ID, PERSON, entry.period, "/docs/m-01253.pdf", 12)
    conn.commit()
    conn.close()
    return db_path


async def _parallel_requests() -> tuple[list[httpx.Response], list[httpx.Response]]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        login = await client.post(
            "/api/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert login.status_code == 200, login.text

        timeline = [client.get(f"/api/person/{PERSON}/timeline") for _ in range(N)]
        periods = [client.get(f"/api/persons/{PERSON}/periods") for _ in range(N)]
        responses = await asyncio.gather(*timeline, *periods)
    return list(responses[:N]), list(responses[N:])


def _audit_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    conn.close()
    return rows


def test_parallel_timeline_and_periods_all_200_one_audit_row_each():
    db_path = _make_temp_db()
    try:
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, DB_PATH=db_path)
        make_user(db_path)

        timeline, periods = asyncio.run(_parallel_requests())

        statuses = Counter(
            [f"timeline {r.status_code}" for r in timeline]
            + [f"periods {r.status_code}" for r in periods]
        )
        assert statuses == Counter({"timeline 200": N, "periods 200": N}), dict(statuses)
        for r in timeline:
            assert len(r.json()["result"]["points"]) == len(_PERIODS)
        for r in periods:
            assert len(r.json()) == len(_PERIODS)

        rows = _audit_rows(db_path)
        audit_ids = [r.json()["audit_id"] for r in timeline]
        assert len(set(audit_ids)) == N, audit_ids
        assert sorted(audit_ids) == [row["id"] for row in rows], (audit_ids, len(rows))
        for row in rows:
            assert row["mode"] == "structured"
            assert row["user"] == TEST_USERNAME
            assert row["person_id"] == PERSON
            assert row["period"] == "all"
    finally:
        app.dependency_overrides.clear()
        remove_db(db_path)


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_wal_mode_and_single_warning_when_unavailable():
    db_path = _make_temp_db()
    records = _Records()
    logger = logging.getLogger(database.__name__)
    logger.addHandler(records)
    try:
        conn = get_connection(db_path)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.close()
        assert records.records == []

        # In-memory βάση: το SQLite αρνείται το WAL και κρατά "memory", όπως
        # θα κρατούσε το "delete" σε filesystem που δεν το υποστηρίζει.
        memory = Path(":memory:")
        for _ in range(2):
            get_connection(memory).close()
        warnings = [r for r in records.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, [r.getMessage() for r in records.records]
        assert "journal_mode=memory" in warnings[0].getMessage()
        assert "τοπικό δίσκο" in warnings[0].getMessage()
    finally:
        logger.removeHandler(records)
        database._non_wal_warned.discard(Path(":memory:"))
        remove_db(db_path)


def run_all():
    tests = [
        test_parallel_timeline_and_periods_all_200_one_audit_row_each,
        test_wal_mode_and_single_warning_when_unavailable,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
