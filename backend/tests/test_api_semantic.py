"""Mini test/sample flow για το POST /query/semantic (Φάση 4).

Χρησιμοποιεί FakeSemanticRetriever (dependency override) — καμία εξάρτηση
από πραγματικά ML μοντέλα ή τοπικό Ollama server. Καλύπτει:
  - η απάντηση ενσωματώνει το SemanticResult + audit_id.
  - η γραμμή audit_log έχει mode="semantic" και τα doc_ids των citations.
  - η "no data in scope" περίπτωση επιστρέφει 200 + audit row με άδεια doc_ids.
  - precheck: ανύπαρκτη περίοδος -> 422, έτος/πεδίο εκτός εύρους -> 200 με
    κείμενο άρνησης, και στις δύο περιπτώσεις ο retriever δεν καλείται.

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
from app.models.evaluation import CAREER_PERIOD  # noqa: E402
from app.retrieval.models import Citation, SemanticResult  # noqa: E402
from app.retrieval.precheck import PRECHECK_MODEL  # noqa: E402
from app.retrieval.semantic import NO_DATA_ANSWER  # noqa: E402

PERIOD = "2025-01-01..2025-12-31"
OTHER_PERIOD = "2024-01-01..2024-12-31"


class FakeSemanticRetriever:
    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer="FAKE ANSWER",
            citations=[
                Citation(doc_id="doc1", page=1, section="Στοχοθεσία", score=0.9),
            ],
            retrieved_doc_ids=["doc1"],
            model="fake-llm",
            prompt_version="v2",
            unsupported_ranks=[],
        )


class FakeEmptySemanticRetriever:
    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer=NO_DATA_ANSWER,
            citations=[],
            retrieved_doc_ids=[],
            model="fake-llm",
            prompt_version="v2",
            unsupported_ranks=[],
        )


class FakeUnsupportedRankSemanticRetriever:
    """Simulate Φάση 1 rank validator flag (μη τεκμηριωμένος βαθμός)."""

    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        return SemanticResult(
            answer="με βαθμό Υπλγού",
            citations=[
                Citation(doc_id="doc1", page=1, section="Στοχοθεσία", score=0.9),
            ],
            retrieved_doc_ids=["doc1"],
            model="fake-llm",
            prompt_version="v2",
            unsupported_ranks=["ΥΠΟΛΟΧΑΓΟΣ"],
        )


class FakeLLMFailureAfterRetrievalRetriever:
    """Η ανάκτηση πέτυχε (doc_ids γνωστά) αλλά η κλήση LLM απέτυχε."""

    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        raise LLMUnavailableError("boom", retrieved_doc_ids=["DOC-1", "DOC-2"])


class FakePreRetrievalFailureRetriever:
    """Αποτυχία πριν καν ανακτηθεί οτιδήποτε -> doc_ids πρέπει να μείνουν άδεια."""

    prompt_version = "v2"

    def query(self, query_text: str, scope) -> SemanticResult:
        raise ValueError("δεν βρέθηκε έγκυρη πηγή δεδομένων")


class RecordingRetriever(FakeSemanticRetriever):
    """Καταγράφει κλήσεις: στις αρνήσεις του precheck πρέπει να μείνει άδειο."""

    def __init__(self):
        self.calls: list[str] = []

    def query(self, query_text: str, scope) -> SemanticResult:
        self.calls.append(query_text)
        return super().query(query_text, scope)


def _make_temp_db() -> Path:
    """p1 με δύο περιόδους αξιολόγησης + career document (το precheck επικυρώνει
    την περίοδο έναντι του documents πριν από οποιοδήποτε retrieval)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO persons (person_id, name) VALUES ('p1', 'Παπαδόπουλος')")
    for period in (OTHER_PERIOD, PERIOD):
        start, end = period.split("..")
        conn.execute(
            "INSERT INTO evaluations (person_id, period, period_start, period_end, ea_type, "
            "unit, evaluator_name) VALUES ('p1', ?, ?, ?, 'Ε.Α.', 'ΜΟΝΑΔΑ', 'ΑΞΙΟΛΟΓΗΤΗΣ')",
            (period, start, end),
        )
        conn.execute(
            "INSERT INTO documents (doc_id, person_id, period, path) VALUES ('doc1', 'p1', ?, '/d.pdf')",
            (period,),
        )
    conn.execute(
        "INSERT INTO documents (doc_id, person_id, period, path) VALUES ('doc1', 'p1', ?, '/d.pdf')",
        (CAREER_PERIOD,),
    )
    conn.commit()
    conn.close()
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
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
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
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
        )
        audit_id = response.json()["audit_id"]

        row = _last_audit_row(db_path)
        assert row["id"] == audit_id
        assert row["mode"] == "semantic"
        assert json.loads(row["retrieved_doc_ids"]) == ["doc1"]
        assert row["prompt_version"] == "v2"
        assert json.loads(row["unsupported_ranks"]) == []
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_audit_row_records_unsupported_ranks_when_flagged():
    """Φάση 1 rank validator: το audit_log καταγράφει τους μη τεκμηριωμένους
    βαθμούς, χωρίς να αλλάζει την απάντηση προς τον χρήστη (logging only)."""
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: (
            FakeUnsupportedRankSemanticRetriever()
        )
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 200
        assert response.json()["result"]["answer"] == "με βαθμό Υπλγού"

        row = _last_audit_row(db_path)
        assert json.loads(row["unsupported_ranks"]) == ["ΥΠΟΛΟΧΑΓΟΣ"]
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
            # έγκυρη περίοδος, ο fake retriever προσομοιώνει άδειο Chroma για το scope
            json={"person_id": "p1", "period": PERIOD, "question": "Ερώτημα χωρίς δεδομένα"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["answer"] == NO_DATA_ANSWER
        assert body["result"]["retrieved_doc_ids"] == []

        row = _last_audit_row(db_path)
        assert row["mode"] == "semantic"
        assert json.loads(row["retrieved_doc_ids"]) == []
        assert row["prompt_version"] == "v2"
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
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
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
        assert rows[0]["prompt_version"] == "v2"
        assert rows[0]["unsupported_ranks"] is None
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
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 400

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_log").fetchall()
        conn.close()

        assert len(rows) == 1
        assert json.loads(rows[0]["retrieved_doc_ids"]) == []
        assert rows[0]["prompt_version"] == "v2"
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_routing_hint_present_when_question_matches_heuristic():
    """Φάση B2: το endpoint υπολογίζει το routing_hint από το ερώτημα ανεξάρτητα
    από τον retriever — human-in-the-loop, δεν αλλάζει mode μόνο του."""
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: FakeSemanticRetriever()
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={
                "person_id": "p1",
                "period": PERIOD,
                "question": "Ποιος ήταν ο βαθμός στις Τοποθετήσεις;",
            },
        )

        assert response.status_code == 200
        assert response.json()["result"]["routing_hint"] == "structured"
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_routing_hint_absent_when_question_does_not_match_heuristic():
    db_path = _make_temp_db()
    try:
        _override_settings(db_path)
        app.dependency_overrides[get_semantic_retriever] = lambda: FakeSemanticRetriever()
        client = TestClient(app)

        response = client.post(
            "/query/semantic",
            json={"person_id": "p1", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 200
        assert response.json()["result"]["routing_hint"] is None
    finally:
        _clear_overrides()
        os.remove(db_path)


def _post_with_recording_retriever(db_path: Path, payload: dict):
    _override_settings(db_path)
    retriever = RecordingRetriever()
    app.dependency_overrides[get_semantic_retriever] = lambda: retriever
    response = TestClient(app).post("/query/semantic", json=payload)
    return response, retriever


def _audit_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log").fetchall()
    conn.close()
    return rows


def test_unknown_period_is_422_audited_without_retrieval():
    db_path = _make_temp_db()
    try:
        response, retriever = _post_with_recording_retriever(
            db_path,
            {"person_id": "p1", "period": "2030-01-01..2030-12-31", "question": "Πώς ήταν η στοχοθεσία;"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Η περίοδος «2030-01-01..2030-12-31» δεν υπάρχει στον φάκελο p1."
        )
        assert retriever.calls == []

        rows = _audit_rows(db_path)
        assert len(rows) == 1
        assert rows[0]["mode"] == "semantic"
        assert json.loads(rows[0]["retrieved_doc_ids"]) == []
        assert rows[0]["prompt_version"] is None
        assert rows[0]["answer_text"] is None
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_unknown_person_is_422():
    db_path = _make_temp_db()
    try:
        response, retriever = _post_with_recording_retriever(
            db_path, {"person_id": "ghost", "period": PERIOD, "question": "Πώς ήταν η στοχοθεσία;"}
        )
        assert response.status_code == 422
        assert retriever.calls == []
        assert len(_audit_rows(db_path)) == 1
    finally:
        _clear_overrides()
        os.remove(db_path)


def _assert_precheck_refusal(db_path: Path, question: str, reason: str, text_prefix: str):
    response, retriever = _post_with_recording_retriever(
        db_path, {"person_id": "p1", "period": PERIOD, "question": question}
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["refusal_reason"] == reason
    assert result["answer"].startswith(text_prefix), result["answer"]
    assert result["citations"] == []
    assert result["retrieved_doc_ids"] == []
    assert result["model"] == PRECHECK_MODEL
    assert result["prompt_version"] is None
    assert retriever.calls == []

    rows = _audit_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["id"] == response.json()["audit_id"]
    assert rows[0]["mode"] == "semantic"
    assert json.loads(rows[0]["retrieved_doc_ids"]) == []
    assert rows[0]["prompt_version"] is None
    assert rows[0]["unsupported_ranks"] is None
    assert rows[0]["answer_text"] == result["answer"]


def test_year_out_of_range_refused_without_retrieval():
    db_path = _make_temp_db()
    try:
        _assert_precheck_refusal(
            db_path,
            "Τι έγραφε η έκθεση του 2003;",
            "year_out_of_range",
            "Δεν υπάρχει περίοδος αξιολόγησης για το 2003.",
        )
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_year_in_other_period_refused_with_redirect():
    db_path = _make_temp_db()
    try:
        _assert_precheck_refusal(
            db_path,
            "Τι χαρακτηρισμό πήρε το 2024;",
            "year_other_period",
            f"Το 2024 δεν ανήκει στην επιλεγμένη περίοδο {PERIOD}. "
            f"Περίοδοι που το περιέχουν: {OTHER_PERIOD}.",
        )
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_field_out_of_schema_refused_without_retrieval():
    db_path = _make_temp_db()
    try:
        _assert_precheck_refusal(
            db_path,
            "Ποια είναι η βαθμολογία του στο πεδίο 200;",
            "field_out_of_schema",
            "Το πεδίο 200 δεν υπάρχει στο έντυπο αξιολόγησης.",
        )
    finally:
        _clear_overrides()
        os.remove(db_path)


def test_question_passing_precheck_reaches_retriever():
    db_path = _make_temp_db()
    try:
        response, retriever = _post_with_recording_retriever(
            db_path,
            {"person_id": "p1", "period": PERIOD, "question": "Τι λέει το πεδίο 142β για το 2025;"},
        )
        assert response.status_code == 200
        assert response.json()["result"]["refusal_reason"] is None
        assert retriever.calls == ["Τι λέει το πεδίο 142β για το 2025;"]
    finally:
        _clear_overrides()
        os.remove(db_path)


def run_all():
    tests = [
        test_response_embeds_result_and_audit_id,
        test_audit_row_has_semantic_mode_and_citation_doc_ids,
        test_audit_row_records_unsupported_ranks_when_flagged,
        test_empty_scope_returns_200_with_empty_audit_doc_ids,
        test_llm_failure_after_retrieval_audits_retrieved_doc_ids,
        test_pre_retrieval_failure_audits_empty_doc_ids,
        test_routing_hint_present_when_question_matches_heuristic,
        test_routing_hint_absent_when_question_does_not_match_heuristic,
        test_unknown_period_is_422_audited_without_retrieval,
        test_unknown_person_is_422,
        test_year_out_of_range_refused_without_retrieval,
        test_year_in_other_period_refused_with_redirect,
        test_field_out_of_schema_refused_without_retrieval,
        test_question_passing_precheck_reaches_retriever,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
