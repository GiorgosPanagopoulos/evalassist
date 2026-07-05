"""Mini test/sample flow για το POST /query/semantic (Φάση 4).

Χρησιμοποιεί FakeSemanticRetriever (dependency override) — καμία εξάρτηση
από πραγματικά ML μοντέλα ή τοπικό Ollama server. Καλύπτει:
  - η απάντηση ενσωματώνει το SemanticResult + audit_id.
  - η γραμμή audit_log έχει mode="semantic" και τα doc_ids των citations.
  - η "no data in scope" περίπτωση επιστρέφει 200 + audit row με άδεια doc_ids.

Εκτελείται standalone: `python tests/test_api_semantic.py`
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_semantic_retriever  # noqa: E402
from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.exceptions import LLMUnavailableError  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.retrieval.models import Citation, SemanticResult  # noqa: E402
from app.retrieval.semantic import NO_DATA_ANSWER  # noqa: E402


class FakeSemanticRetriever:
    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer="FAKE ANSWER",
            citations=[
                Citation(doc_id="doc1", page=1, section="Στοχοθεσία", score=0.9),
            ],
            retrieved_doc_ids=["doc1"],
            model="fake-llm",
        )


class FakeEmptySemanticRetriever:
    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer=NO_DATA_ANSWER,
            citations=[],
            retrieved_doc_ids=[],
            model="fake-llm",
        )


class FakeLLMFailureAfterRetrievalRetriever:
    """Η ανάκτηση πέτυχε (doc_ids γνωστά) αλλά η κλήση LLM απέτυχε."""

    def query(self, query_text: str, scope) -> SemanticResult:
        raise LLMUnavailableError("boom", retrieved_doc_ids=["DOC-1", "DOC-2"])


class FakePreRetrievalFailureRetriever:
    """Αποτυχία πριν καν ανακτηθεί οτιδήποτε -> doc_ids πρέπει να μείνουν άδεια."""

    def query(self, query_text: str, scope) -> SemanticResult:
        raise ValueError("δεν βρέθηκε έγκυρη πηγή δεδομένων")


def _make_temp_db() -> Path:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    return db_path


def _override_settings(db_path: Path) -> None:
    test_settings = Settings(_env_file=None, DB_PATH=db_path)
    app.dependency_overrides[get_settings] = lambda: test_settings


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _last_audit_row(db_path: Path) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row


def test_response_embeds_result_and_audit_id():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: FakeSemanticRetriever()
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": "2025", "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["answer"] == "FAKE ANSWER"
        assert body["result"]["citations"][0]["doc_id"] == "doc1"
        assert isinstance(body["audit_id"], int)
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_audit_row_has_semantic_mode_and_citation_doc_ids():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: FakeSemanticRetriever()
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": "2025", "question": "Πώς ήταν η στοχοθεσία;"},
        )
        audit_id = response.json()["audit_id"]

        row = _last_audit_row(db_path)
        assert row["id"] == audit_id
        assert row["mode"] == "semantic"
        assert json.loads(row["retrieved_doc_ids"]) == ["doc1"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_empty_scope_returns_200_with_empty_audit_doc_ids():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: FakeEmptySemanticRetriever()
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "ghost", "period": "2025", "question": "Ερώτημα χωρίς δεδομένα"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["answer"] == NO_DATA_ANSWER
        assert body["result"]["retrieved_doc_ids"] == []

        row = _last_audit_row(db_path)
        assert row["mode"] == "semantic"
        assert json.loads(row["retrieved_doc_ids"]) == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_llm_failure_after_retrieval_audits_retrieved_doc_ids():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: (
            FakeLLMFailureAfterRetrievalRetriever()
        )
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": "2025", "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 503

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_log").fetchall()
        conn.close()

        # ακριβώς μία γραμμή audit_log ανά κλήση, ακόμη και σε 503
        assert len(rows) == 1
        assert rows[0]["mode"] == "semantic"
        assert json.loads(rows[0]["retrieved_doc_ids"]) == ["DOC-1", "DOC-2"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_pre_retrieval_failure_audits_empty_doc_ids():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: (
            FakePreRetrievalFailureRetriever()
        )
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": "2025", "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 400

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_log").fetchall()
        conn.close()

        assert len(rows) == 1
        assert json.loads(rows[0]["retrieved_doc_ids"]) == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def run_all():
    tests = [
        test_response_embeds_result_and_audit_id,
        test_audit_row_has_semantic_mode_and_citation_doc_ids,
        test_empty_scope_returns_200_with_empty_audit_doc_ids,
        test_llm_failure_after_retrieval_audits_retrieved_doc_ids,
        test_pre_retrieval_failure_audits_empty_doc_ids,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
