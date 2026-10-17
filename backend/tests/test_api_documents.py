"""Tests για το GET /person/{person_id}/documents/{doc_id}/file?period=...

Πάνω σε temp SQLite και temp DOCS_ROOT με συνθετικά PDF bytes (το doc_id
είναι το sha256[:16] τους, όπως στο ingestion):
  - positive: 200, bytes ίδια με το αρχείο, inline + no-store + nosniff,
    μία γραμμή audit με το doc_id.
  - negative: cross-person, λάθος period, path traversal στο path της ΒΔ
    (σχετικό, απόλυτο, symlink), "../" στο URL, αρχείο που λείπει, όχι PDF,
    hash mismatch, πολύ μεγάλο (stat πριν το read), DOCS_ROOT κενό: όλα το
    ίδιο 404 με το ίδιο body, ακριβώς μία γραμμή audit με τον λόγο, κανένα byte.
  - negative: χωρίς period 422 και χωρίς session 401, χωρίς audit.
  - αποτυχία του audit: 500 χωρίς bytes στην επιτυχία· στο error path 404 και
    ERROR στο log.
  - logs: WARNING μόνο για outside_root / hash_mismatch / file_missing /
    unreadable, με τον κωδικό μόνο· κανένα log για not_found·
    κανένα path, person_id, doc_id ή period σε κανένα record.

Εκτελείται standalone: `PYTHONPATH=. python tests/test_api_documents.py`
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_helpers import BASE_URL, TEST_USERNAME, login, make_user  # noqa: E402
from db_helpers import remove_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes_documents  # noqa: E402
from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.models.evaluation import CAREER_PERIOD  # noqa: E402

P1 = "P-DOC-0001"
P2 = "P-DOC-0002"
PERIOD_2023 = "2023-01-01..2023-12-31"
PERIOD_2024 = "2024-01-01..2024-12-31"
NOT_FOUND = {"detail": routes_documents.NOT_FOUND_DETAIL}


def _pdf(label: str, size: int = 0) -> bytes:
    body = f"%PDF-1.4\n% synthetic {label}\n".encode()
    return body + b"0" * max(0, size - len(body) - 6) + b"%%EOF\n"


def _doc_id(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


@dataclass
class Env:
    base: Path
    root: Path
    db_path: Path
    d1: str
    d2: str
    d3: str
    d1_bytes: bytes
    secret_id: str

    def write(self, relative: str, content: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def insert(self, doc_id: str, person_id: str, period: str, path: str) -> None:
        conn = sqlite3.connect(self.db_path)
        repository.upsert_document(conn, doc_id, person_id, period, path, 1)
        conn.commit()
        conn.close()

    def settings(self, **overrides) -> Settings:
        values = {"DB_PATH": self.db_path, "DOCS_ROOT": self.root} | overrides
        return Settings(_env_file=None, **values)


def _make_env() -> Env:
    base = Path(tempfile.mkdtemp())
    root = base / "docs"
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)

    d1_bytes, d2_bytes, d3_bytes = _pdf("d1"), _pdf("d2"), _pdf("d3")
    # Έξω από το DOCS_ROOT, με έγκυρο PDF και σωστό hash: μόνο ο έλεγχος του
    # path πρέπει να το σταματήσει.
    secret = _pdf("secret outside root")
    (base / "outside").mkdir()
    (base / "outside" / "secret.pdf").write_bytes(secret)

    env = Env(base, root, db_path, _doc_id(d1_bytes), _doc_id(d2_bytes), _doc_id(d3_bytes),
              d1_bytes, _doc_id(secret))
    env.write("p1/d1.pdf", d1_bytes)
    env.write("p1/d2.pdf", d2_bytes)
    env.write("p2/d3.pdf", d3_bytes)

    conn = sqlite3.connect(db_path)
    repository.upsert_person(conn, P1, "Συνθετικός Πρώτος")
    repository.upsert_person(conn, P2, "Συνθετική Δεύτερη")
    conn.commit()
    conn.close()
    env.insert(env.d1, P1, PERIOD_2023, "p1/d1.pdf")
    env.insert(env.d1, P1, CAREER_PERIOD, "p1/d1.pdf")
    env.insert(env.d2, P1, PERIOD_2024, "p1/d2.pdf")
    env.insert(env.d3, P2, PERIOD_2023, "p2/d3.pdf")
    return env


def _cleanup(env: Env) -> None:
    app.dependency_overrides.clear()
    remove_db(env.db_path)
    shutil.rmtree(env.base, ignore_errors=True)


def _client(env: Env, **overrides) -> TestClient:
    settings = env.settings(**overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    make_user(env.db_path)
    # 500 ως response (όπως στον server), όχι exception στο test.
    client = TestClient(app, base_url=BASE_URL, raise_server_exceptions=False)
    login(client)
    return client


def _url(person_id: str, doc_id: str) -> str:
    return f"/api/person/{person_id}/documents/{doc_id}/file"


def _audit_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    conn.close()
    return rows


def _get_refused(client, env, person_id, doc_id, period, reason):
    """Μία κλήση που πρέπει να απορριφθεί: ίδιο 404, κανένα byte, ακριβώς μία
    νέα γραμμή audit με τον λόγο."""
    before = len(_audit_rows(env.db_path))
    response = client.get(_url(person_id, doc_id), params={"period": period})
    assert response.status_code == 404, response.text
    assert response.json() == NOT_FOUND, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert b"%PDF" not in response.content
    rows = _audit_rows(env.db_path)
    assert len(rows) == before + 1, (before, len(rows))
    row = rows[-1]
    assert row["mode"] == "structured"
    assert row["user"] == TEST_USERNAME
    assert row["refusal_reason"] == reason, row["refusal_reason"]
    assert json.loads(row["retrieved_doc_ids"]) == []
    assert (row["person_id"], row["period"]) == (person_id, period)
    assert json.loads(row["query"]) == {
        "endpoint": "document_file", "person_id": person_id, "doc_id": doc_id, "period": period
    }
    return response


# --- positive -----------------------------------------------------------------


def test_serves_pdf_inline_no_store_with_one_audit_row():
    env = _make_env()
    try:
        client = _client(env)

        response = client.get(_url(P1, env.d1), params={"period": PERIOD_2023})

        assert response.status_code == 200, response.text
        assert response.content == env.d1_bytes
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == f'inline; filename="{env.d1}.pdf"'
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"

        rows = _audit_rows(env.db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["mode"] == "structured"
        assert row["user"] == TEST_USERNAME
        assert json.loads(row["retrieved_doc_ids"]) == [env.d1]
        assert row["refusal_reason"] is None
        assert (row["person_id"], row["period"]) == (P1, PERIOD_2023)

        # Το ίδιο PDF και για την career-wide γραμμή του.
        response = client.get(_url(P1, env.d1), params={"period": CAREER_PERIOD})
        assert response.status_code == 200
        assert response.content == env.d1_bytes
        assert len(_audit_rows(env.db_path)) == 2
    finally:
        _cleanup(env)


# --- isolation ----------------------------------------------------------------


def test_cross_person_is_404_with_audit_and_no_bytes():
    env = _make_env()
    try:
        client = _client(env)
        # Ο P1 ζητά το έγγραφο του P2, με την περίοδο του P2.
        _get_refused(client, env, P1, env.d3, PERIOD_2023, "not_found")
        # Και αντίστροφα.
        _get_refused(client, env, P2, env.d1, PERIOD_2023, "not_found")
    finally:
        _cleanup(env)


def test_right_doc_id_wrong_period_is_404():
    env = _make_env()
    try:
        client = _client(env)
        # Ο P1 έχει την περίοδο 2024, αλλά με το D2, όχι με το D1.
        _get_refused(client, env, P1, env.d1, PERIOD_2024, "not_found")
        _get_refused(client, env, P1, env.d1, "2099-01-01..2099-12-31", "not_found")
    finally:
        _cleanup(env)


# --- path από τη ΒΔ -----------------------------------------------------------


def test_traversal_in_db_path_is_refused():
    env = _make_env()
    try:
        client = _client(env)
        secret = env.base / "outside" / "secret.pdf"

        env.insert(env.secret_id, P1, "rel", "../outside/secret.pdf")
        _get_refused(client, env, P1, env.secret_id, "rel", "outside_root")

        env.insert(env.secret_id, P1, "abs", str(secret))
        _get_refused(client, env, P1, env.secret_id, "abs", "outside_root")

        # Symlink μέσα στο root που δείχνει έξω.
        (env.root / "p1" / "link.pdf").symlink_to(secret)
        env.insert(env.secret_id, P1, "link", "p1/link.pdf")
        _get_refused(client, env, P1, env.secret_id, "link", "outside_root")

        # Ούτε ένα "../" που καταλήγει πάλι μέσα στο root δεν χρειάζεται να
        # απορριφθεί: μετρά το τελικό path, όχι η μορφή του.
        env.insert(env.d1, P1, "back-in", "p2/../p1/d1.pdf")
        response = client.get(_url(P1, env.d1), params={"period": "back-in"})
        assert response.status_code == 200
        assert response.content == env.d1_bytes
    finally:
        _cleanup(env)


def test_traversal_in_url_params_never_reaches_filesystem():
    env = _make_env()
    try:
        client = _client(env)
        # Τα %2E%2E γίνονται ".." μετά το decoding: ταιριάζουν στο route ως
        # person_id/doc_id, αλλά πάνε μόνο σε SQL parameters.
        before = len(_audit_rows(env.db_path))
        response = client.get(
            "/api/person/%2E%2E/documents/%2E%2E/file", params={"period": PERIOD_2023}
        )
        assert response.status_code == 404
        assert b"%PDF" not in response.content
        rows = _audit_rows(env.db_path)
        assert len(rows) == before + 1
        assert rows[-1]["refusal_reason"] == "not_found"
        assert (rows[-1]["person_id"], json.loads(rows[-1]["query"])["doc_id"]) == ("..", "..")

        # Με κωδικοποιημένο "/" δεν ταιριάζει καν στο route.
        response = client.get(
            "/api/person/P/documents/..%2F..%2Foutside%2Fsecret/file", params={"period": "x"}
        )
        assert response.status_code == 404
        assert b"%PDF" not in response.content
    finally:
        _cleanup(env)


def test_missing_file_not_pdf_and_hash_mismatch_are_refused():
    env = _make_env()
    try:
        client = _client(env)

        env.insert(env.d1, P1, "gone", "p1/gone.pdf")
        _get_refused(client, env, P1, env.d1, "gone", "file_missing")

        text = b"%PDF-1.4 not really a pdf file name\n"
        env.write("p1/note.txt", text)
        env.insert(_doc_id(text), P1, "txt", "p1/note.txt")
        _get_refused(client, env, P1, _doc_id(text), "txt", "not_pdf")

        # Το αρχείο άλλαξε μετά το ingestion: ίδιο path, άλλο περιεχόμενο.
        env.write("p1/tampered.pdf", env.d1_bytes + b"% appended\n")
        env.insert(env.d1, P1, "tampered", "p1/tampered.pdf")
        _get_refused(client, env, P1, env.d1, "tampered", "hash_mismatch")
    finally:
        _cleanup(env)


def test_too_large_is_refused_by_stat_before_read():
    env = _make_env()
    original_open = Path.open
    opened: list[Path] = []

    def tracking_open(self, *args, **kwargs):
        opened.append(Path(self).resolve())
        return original_open(self, *args, **kwargs)

    try:
        client = _client(env, MAX_DOC_BYTES=1024)
        big = _pdf("big", size=2048)
        big_path = env.write("p1/big.pdf", big).resolve()
        env.insert(_doc_id(big), P1, "big", "p1/big.pdf")

        Path.open = tracking_open
        _get_refused(client, env, P1, _doc_id(big), "big", "too_large")
        assert big_path not in opened, "το αρχείο διαβάστηκε πριν τον έλεγχο μεγέθους"

        # Ακριβώς στο όριο: σερβίρεται.
        exact = _pdf("exact", size=1024)
        assert len(exact) == 1024
        env.write("p1/exact.pdf", exact)
        env.insert(_doc_id(exact), P1, "exact", "p1/exact.pdf")
        response = client.get(_url(P1, _doc_id(exact)), params={"period": "exact"})
        assert response.status_code == 200
        assert response.content == exact
    finally:
        Path.open = original_open
        _cleanup(env)


def test_docs_root_unset_is_404():
    env = _make_env()
    try:
        client = _client(env, DOCS_ROOT=None)
        _get_refused(client, env, P1, env.d1, PERIOD_2023, "docs_disabled")
    finally:
        _cleanup(env)


# --- request χωρίς period / χωρίς session ---------------------------------------


def test_missing_period_is_422_and_no_session_is_401_without_audit():
    env = _make_env()
    try:
        client = _client(env)
        response = client.get(_url(P1, env.d1))
        assert response.status_code == 422
        assert b"%PDF" not in response.content

        anonymous = TestClient(app, base_url=BASE_URL, raise_server_exceptions=False)
        response = anonymous.get(_url(P1, env.d1), params={"period": PERIOD_2023})
        assert response.status_code == 401
        assert b"%PDF" not in response.content

        assert _audit_rows(env.db_path) == []
    finally:
        _cleanup(env)


# --- αποτυχία του audit -------------------------------------------------------


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _failing_audit(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


def test_failed_audit_on_success_path_returns_no_bytes():
    env = _make_env()
    original = routes_documents.write_audit
    try:
        client = _client(env)
        routes_documents.write_audit = _failing_audit

        response = client.get(_url(P1, env.d1), params={"period": PERIOD_2023})

        assert response.status_code == 500, response.text
        assert response.json() == {"detail": "Internal server error"}
        assert b"%PDF" not in response.content
        assert _audit_rows(env.db_path) == []
    finally:
        routes_documents.write_audit = original
        _cleanup(env)


def test_failed_audit_on_error_path_is_logged_and_still_404():
    env = _make_env()
    original = routes_documents.write_audit
    records = _Records()
    logger = logging.getLogger(routes_documents.__name__)
    try:
        client = _client(env)
        routes_documents.write_audit = _failing_audit
        logger.addHandler(records)

        response = client.get(_url(P1, env.d3), params={"period": PERIOD_2023})

        assert response.status_code == 404
        assert response.json() == NOT_FOUND
        assert b"%PDF" not in response.content
        assert _audit_rows(env.db_path) == []
        errors = [r for r in records.records if r.levelno >= logging.ERROR]
        assert len(errors) == 1, [r.getMessage() for r in records.records]
        assert "OperationalError" in errors[0].getMessage()
        assert "database is locked" not in errors[0].getMessage()
    finally:
        logger.removeHandler(records)
        routes_documents.write_audit = original
        _cleanup(env)


# --- ίδιο 404 παντού και logs χωρίς περιεχόμενο ----------------------------------


WARN_REASONS = ("outside_root", "hash_mismatch", "file_missing", "unreadable")


def test_all_refusals_identical_and_logs_carry_only_the_code():
    env = _make_env()
    records = _Records()
    app_logger = logging.getLogger("app")
    original_open = Path.open
    try:
        client = _client(env)
        secret = env.base / "outside" / "secret.pdf"
        (env.root / "p1" / "link.pdf").symlink_to(secret)
        env.write("p1/tampered.pdf", env.d1_bytes + b"% appended\n")
        text = b"%PDF-1.4 text\n"
        env.write("p1/note.txt", text)
        locked = _pdf("locked")
        locked_path = env.write("p1/locked.pdf", locked).resolve()

        def deny_locked(self, *args, **kwargs):
            if Path(self).resolve() == locked_path:
                raise PermissionError(13, "Permission denied", str(self))
            return original_open(self, *args, **kwargs)

        for doc_id, period, path in (
            (env.secret_id, "rel", "../outside/secret.pdf"),
            (env.secret_id, "abs", str(secret)),
            (env.secret_id, "link", "p1/link.pdf"),
            (env.d1, "gone", "p1/gone.pdf"),
            (_doc_id(text), "txt", "p1/note.txt"),
            (env.d1, "tampered", "p1/tampered.pdf"),
            (_doc_id(locked), "locked", "p1/locked.pdf"),
        ):
            env.insert(doc_id, P1, period, path)

        cases = [
            (P1, env.d3, PERIOD_2023, "not_found"),
            (P1, env.d1, PERIOD_2024, "not_found"),
            (P1, env.secret_id, "rel", "outside_root"),
            (P1, env.secret_id, "abs", "outside_root"),
            (P1, env.secret_id, "link", "outside_root"),
            (P1, env.d1, "gone", "file_missing"),
            (P1, _doc_id(text), "txt", "not_pdf"),
            (P1, env.d1, "tampered", "hash_mismatch"),
            (P1, _doc_id(locked), "locked", "unreadable"),
        ]
        Path.open = deny_locked
        app_logger.addHandler(records)
        responses = [_get_refused(client, env, *case) for case in cases]
        # Επιτυχία: κανένα record.
        assert client.get(_url(P1, env.d1), params={"period": PERIOD_2023}).status_code == 200

        # Ίδιο status, body και content-type σε όλες τις αρνήσεις.
        assert {(r.status_code, r.content, r.headers["content-type"]) for r in responses} == {
            (responses[0].status_code, responses[0].content, responses[0].headers["content-type"])
        }

        warnings = [r for r in records.records if r.levelno == logging.WARNING]
        assert sorted(r.getMessage() for r in warnings) == sorted(
            f"Άρνηση σερβιρίσματος εγγράφου ({reason})"
            for *_, reason in cases
            if reason in WARN_REASONS
        ), [r.getMessage() for r in records.records]
        # Κάθε κωδικός της λίστας εμφανίστηκε τουλάχιστον μία φορά, και το
        # not_found / not_pdf δεν έγραψαν τίποτα.
        assert {reason for *_, reason in cases} >= set(WARN_REASONS)
        assert len(warnings) == sum(1 for *_, reason in cases if reason in WARN_REASONS)
        assert all(r.levelno == logging.WARNING for r in records.records), [
            (r.levelname, r.getMessage()) for r in records.records
        ]

        forbidden = [P1, P2, env.d1, env.d3, env.secret_id, PERIOD_2023, str(env.base),
                     "secret", "d1.pdf", "tampered", "note.txt", "locked", "Permission denied"]
        for record in records.records:
            message = record.getMessage()
            for value in forbidden:
                assert value not in message, (value, message)
            assert record.exc_info is None
    finally:
        Path.open = original_open
        app_logger.removeHandler(records)
        _cleanup(env)


def run_all():
    tests = [
        test_serves_pdf_inline_no_store_with_one_audit_row,
        test_cross_person_is_404_with_audit_and_no_bytes,
        test_right_doc_id_wrong_period_is_404,
        test_traversal_in_db_path_is_refused,
        test_traversal_in_url_params_never_reaches_filesystem,
        test_missing_file_not_pdf_and_hash_mismatch_are_refused,
        test_too_large_is_refused_by_stat_before_read,
        test_docs_root_unset_is_404,
        test_missing_period_is_422_and_no_session_is_401_without_audit,
        test_failed_audit_on_success_path_returns_no_bytes,
        test_failed_audit_on_error_path_is_logged_and_still_404,
        test_all_refusals_identical_and_logs_carry_only_the_code,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
