"""SEMANTIC_ENABLED: με το flag κλειστό το /api/query/semantic απαντά 403,
γράφει audit row με refusal_reason="semantic_disabled" και ΔΕΝ καλεί το
factory του SemanticRetriever (άρα δεν φορτώνονται bge-m3/reranker). Το
/api/auth/login και το /api/auth/me δηλώνουν features.semantic_enabled.

Εκτελείται standalone: `python tests/test_semantic_flag.py`
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_helpers import TEST_USERNAME, logged_in_client, login  # noqa: E402

from app.api import deps  # noqa: E402
from app.api.deps import get_semantic_retriever_factory  # noqa: E402
from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.retrieval.models import Citation, SemanticResult  # noqa: E402

PERIOD = "2025-01-01..2025-12-31"
QUESTION = "Πώς ήταν η στοχοθεσία;"
PAYLOAD = {"person_id": "p1", "period": PERIOD, "question": QUESTION}
DISABLED_DETAIL = "Η σημασιολογική αναζήτηση δεν είναι ενεργή σε αυτή την εγκατάσταση."


class FakeSemanticRetriever:
    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer="FAKE ANSWER",
            citations=[Citation(doc_id="doc1", page=1, section="Στοχοθεσία", score=0.9)],
            retrieved_doc_ids=["doc1"],
            model="fake-llm",
            prompt_version="v2",
            unsupported_ranks=[],
        )


class FactoryProbe:
    """Override του factory. Με explode=True κάνει raise αν κληθεί."""

    def __init__(self, explode: bool):
        self.explode = explode
        self.calls = 0

    def __call__(self) -> FakeSemanticRetriever:
        self.calls += 1
        if self.explode:
            raise AssertionError("το factory του SemanticRetriever κλήθηκε με το flag κλειστό")
        return FakeSemanticRetriever()


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO persons (person_id, name) VALUES ('p1', 'Συνθετικός Αξιολογούμενος')")
    start, end = PERIOD.split("..")
    conn.execute(
        "INSERT INTO evaluations (person_id, period, period_start, period_end, ea_type, "
        "unit, evaluator_name) VALUES ('p1', ?, ?, ?, 'Ε.Α.', 'ΜΟΝΑΔΑ', 'ΑΞΙΟΛΟΓΗΤΗΣ')",
        (PERIOD, start, end),
    )
    conn.execute(
        "INSERT INTO documents (doc_id, person_id, period, path) VALUES ('doc1', 'p1', ?, '/d.pdf')",
        (PERIOD,),
    )
    conn.commit()
    conn.close()
    return db_path


def _with_db(enabled: bool):
    def decorator(test):
        def wrapper():
            db_path = _make_temp_db()
            settings = Settings(_env_file=None, DB_PATH=db_path, SEMANTIC_ENABLED=enabled)
            app.dependency_overrides[get_settings] = lambda: settings
            try:
                test(db_path)
            finally:
                app.dependency_overrides.clear()
                os.remove(db_path)

        wrapper.__name__ = test.__name__
        return wrapper

    return decorator


def _audit_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    finally:
        conn.close()


def test_defaults_are_closed():
    settings = Settings(_env_file=None)
    assert settings.SEMANTIC_ENABLED is False
    assert settings.ACCESS_LOG is False


@_with_db(enabled=False)
def test_disabled_is_403_with_audit_and_factory_never_called(db_path):
    probe = FactoryProbe(explode=True)
    app.dependency_overrides[get_semantic_retriever_factory] = lambda: probe
    client = logged_in_client(app, db_path)

    response = client.post("/api/query/semantic", json=PAYLOAD)

    assert response.status_code == 403, response.text
    assert response.json() == {"detail": DISABLED_DETAIL, "code": "semantic_disabled"}
    assert probe.calls == 0
    rows = _audit_rows(db_path)
    assert len(rows) == 1, [dict(r) for r in rows]
    row = rows[0]
    assert row["mode"] == "semantic"
    assert json.loads(row["retrieved_doc_ids"]) == []
    assert row["refusal_reason"] == "semantic_disabled"
    assert row["user"] == TEST_USERNAME
    assert row["query"] == QUESTION
    assert row["prompt_version"] is None and row["answer_text"] is None


@_with_db(enabled=False)
def test_disabled_never_builds_the_real_retriever(db_path):
    # Χωρίς override: ο πραγματικός lazy singleton μένει None, άρα κανένα
    # μοντέλο δεν φορτώθηκε.
    deps._semantic_retriever = None
    client = logged_in_client(app, db_path)
    response = client.post("/api/query/semantic", json=PAYLOAD)
    assert response.status_code == 403
    assert deps._semantic_retriever is None


@_with_db(enabled=False)
def test_disabled_refuses_before_validation_of_scope(db_path):
    # Ανύπαρκτο άτομο/περίοδος: με το flag κλειστό η απάντηση είναι πάντα
    # 403, πριν από precheck ή IsolationScope.
    probe = FactoryProbe(explode=True)
    app.dependency_overrides[get_semantic_retriever_factory] = lambda: probe
    client = logged_in_client(app, db_path)
    response = client.post(
        "/api/query/semantic",
        json={"person_id": "nobody", "period": "1999-01-01..1999-12-31", "question": QUESTION},
    )
    assert response.status_code == 403
    assert probe.calls == 0
    assert [r["refusal_reason"] for r in _audit_rows(db_path)] == ["semantic_disabled"]


@_with_db(enabled=True)
def test_enabled_calls_factory_and_answers(db_path):
    probe = FactoryProbe(explode=False)
    app.dependency_overrides[get_semantic_retriever_factory] = lambda: probe
    client = logged_in_client(app, db_path)

    response = client.post("/api/query/semantic", json=PAYLOAD)

    assert response.status_code == 200, response.text
    assert response.json()["result"]["answer"] == "FAKE ANSWER"
    assert probe.calls == 1
    rows = _audit_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["refusal_reason"] is None
    assert json.loads(rows[0]["retrieved_doc_ids"]) == ["doc1"]


def _check_features(db_path: Path, expected: bool) -> None:
    client = logged_in_client(app, db_path)
    assert client.get("/api/auth/me").json()["features"] == {"semantic_enabled": expected}
    # Νέο login στον ίδιο client: το σώμα του login δηλώνει τα ίδια features.
    assert login(client, TEST_USERNAME).json()["features"] == {"semantic_enabled": expected}


@_with_db(enabled=False)
def test_me_and_login_report_semantic_disabled(db_path):
    _check_features(db_path, False)


@_with_db(enabled=True)
def test_me_and_login_report_semantic_enabled(db_path):
    _check_features(db_path, True)


def run_all():
    tests = [
        test_defaults_are_closed,
        test_disabled_is_403_with_audit_and_factory_never_called,
        test_disabled_never_builds_the_real_retriever,
        test_disabled_refuses_before_validation_of_scope,
        test_enabled_calls_factory_and_answers,
        test_me_and_login_report_semantic_disabled,
        test_me_and_login_report_semantic_enabled,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
