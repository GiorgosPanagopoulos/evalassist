"""Logs χωρίς περιεχόμενο: τίποτα από τα δεδομένα ενός αιτήματος δεν φτάνει
στο logging output ή στο stderr/stdout.

Το κύριο test τρέχει το app σε ΠΡΑΓΜΑΤΙΚΟ uvicorn (uvicorn.Server σε thread,
με lifespan), ώστε να ελεγχθούν η ρύθμιση logging του ίδιου του uvicorn, ο
access logger και το "Exception in ASGI application". Το sys.stdout/stderr
ανακατευθύνεται ΠΡΙΝ από το uvicorn.Config, άρα και οι handlers του uvicorn
γράφουν στη μνήμη. Επιπλέον handlers σε root, uvicorn, uvicorn.error και
uvicorn.access πιάνουν κάθε record σε DEBUG.

Μόνο συνθετικά δεδομένα. Εκτελείται standalone:
`python tests/test_logs_no_content.py`
"""

import asyncio
import io
import logging
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_helpers import TEST_PASSWORD, TEST_USERNAME, make_user  # noqa: E402
from db_helpers import remove_db  # noqa: E402

from app.api.deps import get_semantic_retriever_factory  # noqa: E402
from app.api.main import create_app  # noqa: E402
from app.core import log_safety  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.retrieval.models import SemanticResult  # noqa: E402

PERSON_ID = "P-LOGSENT-9931"
PERSON_NAME = "Λογκοσέντης Δοκιμάκης"
QUESTION_MARK = "ΖΑΦΟΡΙΣΤΙΚΟΛΟΓΙΑ"
QUESTION = f"Πώς ήταν η στοχοθεσία {QUESTION_MARK};"
SENTINEL = "SENTINEL-123"
PERIOD = "2025-01-01..2025-12-31"

FORBIDDEN = (PERSON_ID, PERSON_NAME, QUESTION_MARK, SENTINEL, TEST_PASSWORD)

CAPTURED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access")
# Ο httpx client του ΙΔΙΟΥ του test γράφει τα URLs που ζητά (INFO/DEBUG).
# Δεν είναι log του server, άρα σιγεί για να μη μολύνει το output.
CLIENT_LOGGERS = ("httpx", "httpcore")


class FakeSemanticRetriever:
    prompt_version = "v2"

    def __init__(self):
        self.questions: list[str] = []

    def query(self, query_text: str, scope) -> SemanticResult:
        self.questions.append(query_text)
        return SemanticResult(
            answer=f"Απάντηση για {PERSON_NAME}",
            citations=[],
            retrieved_doc_ids=["doc1"],
            model="fake-llm",
            prompt_version="v2",
            unsupported_ranks=["Σμχος"],
        )


class RaisingRetriever(FakeSemanticRetriever):
    def query(self, query_text: str, scope) -> SemanticResult:
        self.questions.append(query_text)
        raise RuntimeError(f"{SENTINEL} {PERSON_ID} {query_text}")


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO persons (person_id, name) VALUES (?, ?)", (PERSON_ID, PERSON_NAME))
    start, end = PERIOD.split("..")
    conn.execute(
        "INSERT INTO evaluations (person_id, period, period_start, period_end, ea_type, "
        "unit, evaluator_name) VALUES (?, ?, ?, ?, 'Ε.Α.', 'ΜΟΝΑΔΑ', 'ΑΞΙΟΛΟΓΗΤΗΣ')",
        (PERSON_ID, PERIOD, start, end),
    )
    conn.execute(
        "INSERT INTO documents (doc_id, person_id, period, path) VALUES ('doc1', ?, ?, '/d.pdf')",
        (PERSON_ID, PERIOD),
    )
    conn.commit()
    conn.close()
    return db_path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _fresh_app_with_env(**env: str):
    """create_app() με συγκεκριμένα env vars (το lifespan διαβάζει τα
    settings της δημιουργίας του app), και επαναφορά μετά."""
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    get_settings.cache_clear()
    try:
        yield create_app()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@contextmanager
def _uvicorn_capturing_everything(app):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    port = _free_port()
    saved_streams = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = output
    server = thread = None
    root = logging.getLogger()
    saved_root_level = root.level
    saved_client_levels = {name: logging.getLogger(name).level for name in CLIENT_LOGGERS}
    for name in CLIENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        # Το dictConfig του uvicorn τρέχει εδώ και δένει τους handlers του
        # στο (ανακατευθυνμένο) sys.stderr/stdout.
        config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="on")
        for name in CAPTURED_LOGGERS:
            logging.getLogger(name).addHandler(handler)
        root.setLevel(logging.DEBUG)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "ο uvicorn δεν ξεκίνησε"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}", output
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(30)
        for name in CAPTURED_LOGGERS:
            logging.getLogger(name).removeHandler(handler)
        root.setLevel(saved_root_level)
        for name, level in saved_client_levels.items():
            logging.getLogger(name).setLevel(level)
        sys.stdout, sys.stderr = saved_streams


def test_no_request_content_in_any_log_or_stderr():
    db_path = _make_temp_db()
    make_user(db_path)
    state = {"enabled": False, "retriever": FakeSemanticRetriever()}
    try:
        with _fresh_app_with_env(ACCESS_LOG="false") as app:

            def settings_override() -> Settings:
                # COOKIE_SECURE=False: ο httpx client ξαναστέλνει το cookie σε http.
                return Settings(
                    _env_file=None,
                    DB_PATH=db_path,
                    COOKIE_SECURE=False,
                    SEMANTIC_ENABLED=state["enabled"],
                )

            app.dependency_overrides[get_settings] = settings_override
            app.dependency_overrides[get_semantic_retriever_factory] = lambda: (
                lambda: state["retriever"]
            )

            with _uvicorn_capturing_everything(app) as (base_url, output):
                with httpx.Client(base_url=base_url, timeout=30) as client:
                    statuses = {}
                    statuses["login"] = client.post(
                        "/api/auth/login",
                        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
                    ).status_code
                    persons = client.get("/api/persons")
                    statuses["persons"] = persons.status_code
                    statuses["periods"] = client.get(
                        f"/api/persons/{PERSON_ID}/periods"
                    ).status_code
                    statuses["timeline"] = client.get(
                        f"/api/person/{PERSON_ID}/timeline"
                    ).status_code
                    statuses["structured"] = client.post(
                        "/api/query/structured",
                        json={"person_id": PERSON_ID, "period": PERIOD, "operation": "get_scores"},
                    ).status_code
                    semantic = {"person_id": PERSON_ID, "period": PERIOD, "question": QUESTION}
                    statuses["semantic_off"] = client.post(
                        "/api/query/semantic", json=semantic
                    ).status_code

                    state["enabled"] = True
                    statuses["semantic_on"] = client.post(
                        "/api/query/semantic", json=semantic
                    ).status_code

                    raising = RaisingRetriever()
                    state["retriever"] = raising
                    boom = client.post("/api/query/semantic", json=semantic)
                    statuses["semantic_raise"] = boom.status_code
            captured = output.getvalue()
    finally:
        remove_db(db_path)

    # Τα αιτήματα έφτασαν πραγματικά στα δεδομένα: αλλιώς ένα καθαρό log
    # θα σήμαινε απλώς ότι δεν έγινε τίποτα.
    assert statuses["login"] == 200, statuses
    assert statuses["persons"] == 200 and PERSON_NAME in persons.text, statuses
    assert statuses["periods"] == 200, statuses
    assert statuses["timeline"] == 200 and statuses["structured"] == 200, statuses
    assert statuses["semantic_off"] == 403, statuses
    assert statuses["semantic_on"] == 200, statuses
    assert statuses["semantic_raise"] == 500, statuses
    assert boom.json() == {"detail": "Internal server error"}
    assert raising.questions == [QUESTION]

    # Η καταγραφή δουλεύει: ο uvicorn γράφει στο ίδιο output και η εξαίρεση
    # καταγράφεται με τύπο και αρχείο:γραμμή μέσα στο backend/app.
    assert "Application startup complete" in captured, captured
    assert "Unhandled builtins.RuntimeError at app/api/routes_query.py:" in captured, captured

    leaks = [s for s in FORBIDDEN if s in captured]
    assert not leaks, f"Διαρροή {leaks} στο log/stderr:\n{captured}"
    assert "Traceback" not in captured, captured
    assert "Exception in ASGI application" not in captured, captured
    assert logging.getLogger("uvicorn.access").disabled is True


def test_redaction_strips_exc_info_everywhere_including_last_resort():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    explicit = logging.getLogger("evalassist.test.explicit")
    explicit.addHandler(handler)
    explicit.propagate = False
    # Logger χωρίς handlers, ούτε στον root: πάει στο logging.lastResort,
    # που γράφει στο τρέχον sys.stderr.
    orphan = logging.getLogger("evalassist.test.orphan")
    saved_root_handlers = logging.getLogger().handlers[:]
    logging.getLogger().handlers.clear()
    try:
        with redirect_stderr(output):
            try:
                raise ValueError(f"{SENTINEL} {PERSON_ID}")
            except ValueError:
                explicit.warning("αποτυχία", exc_info=True)
                explicit.exception("αποτυχία με %s", "args")
                orphan.error("ορφανό", exc_info=True)
                orphan.warning("με stack", stack_info=True)
    finally:
        explicit.removeHandler(handler)
        logging.getLogger().handlers[:] = saved_root_handlers
    captured = output.getvalue()

    assert captured.count("[builtins.ValueError at <external>]") == 3, captured
    assert "αποτυχία με args" in captured and "ορφανό" in captured, captured
    assert "με stack" in captured, captured
    assert SENTINEL not in captured and PERSON_ID not in captured, captured
    assert "Traceback" not in captured and "Stack (most recent call last)" not in captured


def test_exception_location_points_into_backend_app():
    from app.core.exceptions import NotFoundError
    from app.retrieval.precheck import validate_period

    # Κενή βάση χωρίς σχήμα: η εξαίρεση γεννιέται μέσα στο precheck.py.
    conn = sqlite3.connect(":memory:")
    try:
        validate_period(conn, PERSON_ID, PERIOD)
    except Exception as exc:  # το ίδιο το μήνυμα δεν μας ενδιαφέρει
        location = log_safety.exception_location(exc)
    else:
        raise AssertionError("το validate_period πέρασε χωρίς σχήμα")
    finally:
        conn.close()
    assert location.split(" at ")[1].startswith("app/retrieval/precheck.py:"), location
    assert PERSON_ID not in location
    assert log_safety.exception_location(NotFoundError(SENTINEL)).endswith(" at <external>")
    assert SENTINEL not in log_safety.exception_location(NotFoundError(SENTINEL))


def test_middleware_reports_external_when_no_app_frame():
    """Εξαίρεση εκτός backend/app: το ίδιο το middleware δεν δηλώνεται ως
    σημείο της εξαίρεσης, και το μήνυμα δεν γράφεται."""

    async def failing_app(scope, receive, send):
        raise RuntimeError(f"{SENTINEL} {PERSON_ID}")

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    output = io.StringIO()
    handler = logging.StreamHandler(output)
    errors = logging.getLogger("app.errors")
    errors.addHandler(handler)
    try:
        middleware = log_safety.SafeErrorMiddleware(failing_app)
        asyncio.run(middleware({"type": "http", "method": "GET", "path": "/x"}, receive, send))
    finally:
        errors.removeHandler(handler)
    captured = output.getvalue()

    assert captured.strip() == "Unhandled builtins.RuntimeError at <external>", captured
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 500
    assert sent[1]["body"] == b'{"detail":"Internal server error"}'


def test_redaction_factory_chains_and_is_idempotent():
    original = logging.getLogRecordFactory()
    tagged: list[str] = []

    def tagging_factory(*args, **kwargs):
        record = logging.LogRecord(*args, **kwargs)
        tagged.append(record.getMessage())
        return record

    try:
        logging.setLogRecordFactory(tagging_factory)
        log_safety.install_log_redaction()
        installed = logging.getLogRecordFactory()
        assert installed is not tagging_factory

        # Πολλαπλά create_app()/install: κανένα νέο τύλιγμα.
        log_safety.install_log_redaction()
        create_app()
        create_app()
        assert logging.getLogRecordFactory() is installed

        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            record = logging.getLogger("evalassist.test.chain").makeRecord(
                "evalassist.test.chain", logging.ERROR, __file__, 1, "μήνυμα", (), sys.exc_info()
            )
        # Το προηγούμενο factory κλήθηκε ακριβώς μία φορά (chain, όχι
        # αντικατάσταση, και όχι διπλό τύλιγμα).
        assert tagged == ["μήνυμα"], tagged
        assert record.exc_info is None and record.exc_text is None
        assert record.getMessage() == "μήνυμα [builtins.RuntimeError at <external>]"
    finally:
        logging.setLogRecordFactory(original)


def run_all():
    tests = [
        test_no_request_content_in_any_log_or_stderr,
        test_redaction_strips_exc_info_everywhere_including_last_resort,
        test_exception_location_points_into_backend_app,
        test_middleware_reports_external_when_no_app_frame,
        test_redaction_factory_chains_and_is_idempotent,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
