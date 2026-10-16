"""Tests για τα scripts του deploy/ (structured-only deploy).

build_deploy_db.py, πάνω σε συνθετική πηγή (ποτέ την πραγματική ΒΔ):
  - η νέα βάση έχει ακριβώς τις γραμμές των πινάκων δεδομένων και άδειους
    users/sessions/auth_log/audit_log, με τα triggers του τρέχοντος schema.
  - η πηγή μένει byte προς byte ίδια.
  - αρνείται target που υπάρχει (και δεν το αγγίζει) και πηγή που λείπει.
  - το CLI δεν τυπώνει περιεχόμενο.

smoke_test.py, απέναντι σε πραγματικό uvicorn με COOKIE_SECURE=true σε http:
  - περνά όλους τους ελέγχους χωρίς να τυπώσει κωδικό ή τιμή cookie.
  - αποτυγχάνει σε λάθος κωδικό, χωρίς να τον τυπώσει.
  - αποτυγχάνει αν το semantic είναι ανοιχτό.

deploy/: το repo είναι δημόσιο, άρα κανένα hostname, εσωτερικό path, όνομα ή
στοιχείο φακέλου.

Εκτελείται standalone: `python tests/test_deploy_package.py`
"""

import hashlib
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEPLOY_DIR = BACKEND_DIR.parent / "deploy"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(DEPLOY_DIR))

import build_deploy_db  # noqa: E402
import smoke_test  # noqa: E402
from auth_helpers import TEST_PASSWORD, TEST_USERNAME, make_user  # noqa: E402

from app.api.deps import get_semantic_retriever_factory  # noqa: E402
from app.api.main import create_app  # noqa: E402
from app.auth import service  # noqa: E402
from app.core.audit import AuditEntry, write_audit  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.models.evaluation import CAREER_PERIOD, EvaluationEntry, EvaluatorInfo, FieldScore  # noqa: E402
from app.retrieval.models import SemanticResult  # noqa: E402

PERSON_ID = "P-DEPLOY-7731"
PERSON_NAME = "Δεπλοΐδης Συνθετικός"
PERIOD = "2025-01-01..2025-12-31"
QUESTION = "Πώς ήταν η στοχοθεσία ΚΑΡΑΜΠΟΛΙΚΟΣ;"

DATA_TABLES = build_deploy_db.DATA_TABLES
EMPTY_TABLES = build_deploy_db.EMPTY_TABLES


def _temp_path(suffix: str = ".db") -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(path)


def _make_source_db() -> Path:
    """Συνθετική βάση ανάπτυξης: δεδομένα σε όλους τους πίνακες δεδομένων,
    και χρήστης, session, auth_log, audit_log που ΔΕΝ πρέπει να περάσουν."""
    db_path = _temp_path()
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repository.upsert_person(conn, PERSON_ID, PERSON_NAME)
    entry = EvaluationEntry(
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        characterization="ΕΞΑΙΡΕΤΟΣ",
        score=97,
        ea_type="Ε.Α.",
        unit="Φ/Γ ΣΥΝΘΕΤΙΚΟ",
        evaluator=EvaluatorInfo(rank="Πλοίαρχος", name="Αξιολογητής Συνθετικός", role="Διοικητής"),
        field_scores=[FieldScore(field_code="141", value=97), FieldScore(field_code="51", value=95)],
        source_page=4,
    )
    assert entry.period == PERIOD
    eval_id = repository.upsert_evaluation(conn, PERSON_ID, entry)
    repository.replace_field_scores(conn, eval_id, entry.field_scores)
    repository.upsert_document(conn, "doc-deploy", PERSON_ID, PERIOD, "synthetic.pdf", 8)
    repository.upsert_document(conn, "doc-deploy", PERSON_ID, CAREER_PERIOD, "synthetic.pdf", 8)
    conn.execute(
        "INSERT INTO promotions (person_id, row_index, rank, decision_date, decision, promotion_date) "
        "VALUES (?, 0, 'ΥΠΟΠΛΟΙΑΡΧΟΣ', '01/01/2020', 'ΠΑΜΨΗΦΕΙ', '01/07/2020')",
        (PERSON_ID,),
    )
    conn.execute(
        "INSERT INTO service_time (person_id, row_index, subsection, label, years, months, days) "
        "VALUES (?, 0, 'α', 'ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ', 10, 2, 3)",
        (PERSON_ID,),
    )
    write_audit(
        conn,
        AuditEntry(
            user="dev-user",
            query=QUESTION,
            retrieved_doc_ids=["doc-deploy"],
            mode="semantic",
            answer_text=f"Απάντηση για {PERSON_NAME}",
            person_id=PERSON_ID,
            period=PERIOD,
        ),
    )
    conn.commit()
    conn.close()

    user_id = make_user(db_path, "dev-admin", "admin")
    conn = sqlite3.connect(db_path)
    service.create_session(conn, user_id, "dev-admin", datetime.now(timezone.utc), 8)
    conn.close()
    return db_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


# --- build_deploy_db ----------------------------------------------------------


def test_build_copies_only_data_tables_and_leaves_source_unchanged():
    source = _make_source_db()
    target = _temp_path()
    target.unlink()
    try:
        source_hash = _sha256(source)
        src = sqlite3.connect(source)
        for table in EMPTY_TABLES:
            assert _count(src, table) >= 1, table  # η πηγή έχει όντως τέτοιες γραμμές
        expected = {table: _rows(src, table) for table in DATA_TABLES}
        src.close()

        counts = build_deploy_db.build(source, target)

        assert _sha256(source) == source_hash
        dst = sqlite3.connect(target)
        for table in DATA_TABLES:
            assert _rows(dst, table) == expected[table], table
            assert counts[table] == len(expected[table]) >= 1, table
        for table in EMPTY_TABLES:
            assert _count(dst, table) == 0, table
            assert counts[table] == 0, table
        triggers = {
            r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        }
        assert {"audit_log_no_update", "audit_log_no_delete"} <= triggers
        audit_columns = [r[1] for r in dst.execute("PRAGMA table_info(audit_log)")]
        assert audit_columns[-3:] == ["person_id", "period", "other_period"]
        assert dst.execute("PRAGMA foreign_key_check").fetchall() == []
        dst.close()
    finally:
        os.remove(source)
        target.unlink(missing_ok=True)


def test_build_refuses_existing_target_and_leaves_it_untouched():
    source = _make_source_db()
    target = _temp_path()
    target.write_bytes(b"not a database, must survive")
    try:
        try:
            build_deploy_db.build(source, target)
            assert False, "expected FileExistsError"
        except FileExistsError:
            pass
        assert target.read_bytes() == b"not a database, must survive"
    finally:
        os.remove(source)
        os.remove(target)


def test_build_refuses_missing_source_without_creating_target():
    source = _temp_path()
    source.unlink()
    target = _temp_path()
    target.unlink()
    try:
        build_deploy_db.build(source, target)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
    assert not target.exists()


def test_build_cli_prints_no_content():
    source = _make_source_db()
    target = _temp_path()
    target.unlink()
    try:
        result = subprocess.run(
            [sys.executable, str(DEPLOY_DIR / "build_deploy_db.py"),
             "--source", str(source), "--target", str(target)],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, result.stderr[-2000:]
        output = result.stdout + result.stderr
        for forbidden in (PERSON_ID, PERSON_NAME, "ΚΑΡΑΜΠΟΛΙΚΟΣ", "dev-admin", "doc-deploy", PERIOD):
            assert forbidden not in output, forbidden
        assert "persons: 1" in output and "audit_log: 0" in output
    finally:
        os.remove(source)
        target.unlink(missing_ok=True)


# --- smoke_test ---------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeSemanticRetriever:
    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer="FAKE", citations=[], retrieved_doc_ids=[], model="fake", prompt_version="v2"
        )


@contextmanager
def _server(db_path: Path, semantic_enabled: bool = False):
    """Πραγματικός uvicorn σε http, με COOKIE_SECURE=true όπως στην παραγωγή."""
    app = create_app()
    settings = Settings(
        _env_file=None,
        DB_PATH=db_path,
        SEMANTIC_ENABLED=semantic_enabled,
        COOKIE_SECURE=True,
        OLLAMA_URL="http://127.0.0.1:9",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_semantic_retriever_factory] = lambda: FakeSemanticRetriever
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="on", log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "ο uvicorn δεν ξεκίνησε"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(30)


def _make_server_db() -> Path:
    db_path = _make_source_db()
    make_user(db_path)  # TEST_USERNAME / TEST_PASSWORD, must_change_pw=False
    return db_path


def _run_smoke(base_url: str, password: str) -> tuple[int, list[str], list[str]]:
    answers = iter([TEST_USERNAME, PERSON_ID, PERIOD])
    lines: list[str] = []
    cookies: list[str] = []
    original = smoke_test.cookie_header

    def recording_cookie_header(headers):
        value = original(headers)
        cookies.append(value)
        return value

    smoke_test.cookie_header = recording_cookie_header
    try:
        code = smoke_test.main(
            base_url,
            input_fn=lambda prompt: next(answers),
            getpass_fn=lambda prompt: password,
            out=lines.append,
        )
    finally:
        smoke_test.cookie_header = original
    return code, lines, cookies


def test_smoke_passes_on_structured_only_server_without_printing_secrets():
    db_path = _make_server_db()
    try:
        with _server(db_path) as base_url:
            code, lines, cookies = _run_smoke(base_url, TEST_PASSWORD)
        output = "\n".join(lines)
        assert code == 0, output
        assert sum(line.startswith("OK  ") for line in lines) == 7, output
        assert "FAIL" not in output
        assert "Secure" in output and "HttpOnly" in output
        # Το cookie βρέθηκε και στάλθηκε ρητά (αλλιώς το me θα ήταν 401)...
        assert cookies and "=" in cookies[0]
        token = cookies[0].split("=", 1)[1]
        # ...αλλά ούτε αυτό ούτε ο κωδικός ούτε δεδομένα τυπώθηκαν.
        for forbidden in (token, TEST_PASSWORD, PERSON_ID, PERSON_NAME, "doc-deploy"):
            assert forbidden not in output, forbidden
        conn = sqlite3.connect(db_path)
        # Το logout του smoke έκλεισε το session του (μένει μόνο του _make_source_db).
        assert _count(conn, "sessions") == 1
        conn.close()
    finally:
        os.remove(db_path)


def test_smoke_fails_on_wrong_password_without_printing_it():
    db_path = _make_server_db()
    wrong = "wrong-synthetic-pass-42"
    try:
        with _server(db_path) as base_url:
            code, lines, _ = _run_smoke(base_url, wrong)
        output = "\n".join(lines)
        assert code == 1, output
        assert any(line.startswith("FAIL login") for line in lines), output
        assert wrong not in output
    finally:
        os.remove(db_path)


def test_smoke_fails_when_semantic_is_enabled():
    db_path = _make_server_db()
    try:
        with _server(db_path, semantic_enabled=True) as base_url:
            code, lines, _ = _run_smoke(base_url, TEST_PASSWORD)
        output = "\n".join(lines)
        assert code == 1, output
        assert any(line.startswith("FAIL me, semantic_enabled=false") for line in lines), output
        assert any(line.startswith("FAIL semantic κλειστό") for line in lines), output
    finally:
        os.remove(db_path)


# --- deploy/ χωρίς αναγνωριστικά ----------------------------------------------

_FORBIDDEN_PATTERNS = [
    r"/home/",
    r"[A-Za-z]:[\\/]Users",
    r"[ΜM]-\d{3,}",
    r"ailab",
    r"\bportal\.[a-z]",
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    r"\b[a-z0-9-]+\.(?:gr|com|net|org|mil|local|lan|intra)\b",
    r"[Pp]anagopoul|Παναγόπουλ|gpana",
    r"29b215931c674b6e",
]
# Η μόνη διεύθυνση που επιτρέπεται: το loopback όπου ακούει το uvicorn.
_ALLOWED_MATCHES = {"127.0.0.1"}


def test_deploy_dir_has_no_identifying_strings():
    files = [p for p in DEPLOY_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert files, "ο φάκελος deploy/ είναι άδειος"
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, text):
                if match.group(0) in _ALLOWED_MATCHES:
                    continue
                hits.append(f"{path.name}: {pattern!r} -> {match.group(0)!r}")
    assert hits == [], "\n".join(hits)


def run_all():
    tests = [
        test_build_copies_only_data_tables_and_leaves_source_unchanged,
        test_build_refuses_existing_target_and_leaves_it_untouched,
        test_build_refuses_missing_source_without_creating_target,
        test_build_cli_prints_no_content,
        test_smoke_passes_on_structured_only_server_without_printing_secrets,
        test_smoke_fails_on_wrong_password_without_printing_it,
        test_smoke_fails_when_semantic_is_enabled,
        test_deploy_dir_has_no_identifying_strings,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
