"""Με SEMANTIC_ENABLED=false το API δεν φορτώνει chromadb ούτε requests.

Το chromadb (και ό,τι φέρνει: onnxruntime, grpcio, opentelemetry κ.λπ.) και
το requests (μόνο για το Ollama) χρειάζονται μόνο στο semantic path. Ένα
structured-only deploy δεν πρέπει να τα απαιτεί ως εξαρτήσεις.

Ο έλεγχος τρέχει σε ξεχωριστό interpreter (subprocess): μέσα στο ίδιο pytest
process άλλα tests έχουν ήδη φορτώσει το app.retrieval.semantic, άρα το
sys.modules δεν θα έλεγε τίποτα. Ο child κάνει startup (lifespan), health,
login, μία structured και μία semantic κλήση (403), και τυπώνει ποια από τα
modules φορτώθηκαν. Καμία δικτυακή κλήση εκτός localhost.

Εκτελείται standalone: `python tests/test_lazy_imports.py`
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from db_helpers import remove_db  # noqa: E402

LAZY_MODULES = ["chromadb", "requests", "app.retrieval.semantic", "app.ingestion.vectorstore"]
# Δεν πρέπει να φορτώνονται ούτε με το flag ανοιχτό πριν από το πρώτο query,
# πόσο μάλλον κλειστό.
HEAVY_MODULES = ["torch", "sentence_transformers", "transformers"]

PERIOD = "2025-01-01..2025-12-31"

_CHILD = r"""
import json
import os
import sqlite3
import sys
from pathlib import Path

backend = Path(os.environ["LAZY_TEST_BACKEND"])
sys.path[:0] = [str(backend), str(backend / "tests")]
db_path = Path(os.environ["DB_PATH"])
period = os.environ["LAZY_TEST_PERIOD"]

from app.db.database import init_db

init_db(db_path)
conn = sqlite3.connect(db_path)
conn.execute("INSERT INTO persons (person_id, name) VALUES ('p1', 'Συνθετικός Αξιολογούμενος')")
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
conn.commit()
conn.close()

from app.api.main import app
from auth_helpers import logged_in_client

client = logged_in_client(app, db_path)
statuses = {}
with client:  # lifespan startup/shutdown
    statuses["health"] = client.get("/api/health").status_code
    statuses["structured"] = client.post(
        "/api/query/structured",
        json={"person_id": "p1", "period": period, "operation": "get_scores"},
    ).status_code
    statuses["semantic"] = client.post(
        "/api/query/semantic",
        json={"person_id": "p1", "period": period, "question": "Πώς ήταν η στοχοθεσία;"},
    ).status_code

watched = json.loads(os.environ["LAZY_TEST_WATCHED"])
print(json.dumps({
    "statuses": statuses,
    "loaded": sorted(m for m in watched if m in sys.modules),
}))
"""


def _run_child(semantic_enabled: str) -> dict:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    env = dict(os.environ)
    env.update(
        {
            "SEMANTIC_ENABLED": semantic_enabled,
            "DB_PATH": str(db_path),
            # Κλειστή θύρα: το health αποτυγχάνει αμέσως, χωρίς δίκτυο.
            "OLLAMA_URL": "http://127.0.0.1:9",
            "LAZY_TEST_BACKEND": str(BACKEND_DIR),
            "LAZY_TEST_PERIOD": PERIOD,
            "LAZY_TEST_WATCHED": json.dumps(LAZY_MODULES + HEAVY_MODULES),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", _CHILD],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        return json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        remove_db(db_path)


def test_disabled_never_imports_chromadb_or_requests():
    report = _run_child("false")

    assert report["statuses"] == {"health": 200, "structured": 200, "semantic": 403}, report
    assert "chromadb" not in report["loaded"], report
    assert "requests" not in report["loaded"], report
    assert report["loaded"] == [], report


def test_get_semantic_retriever_imports_lazily_and_stays_singleton():
    # Το semantic path με το flag ανοιχτό: το deps φτιάχνει τον retriever από
    # το app.retrieval.semantic τη στιγμή της πρώτης κλήσης, μία φορά.
    from app.api import deps
    from app.retrieval import semantic

    class FakeRetriever:
        instances = 0

        def __init__(self):
            FakeRetriever.instances += 1

    original_cls = semantic.SemanticRetriever
    original_singleton = deps._semantic_retriever
    semantic.SemanticRetriever = FakeRetriever
    deps._semantic_retriever = None
    try:
        factory = deps.get_semantic_retriever_factory()
        first = factory()
        second = factory()
        assert isinstance(first, FakeRetriever)
        assert first is second
        assert FakeRetriever.instances == 1
    finally:
        semantic.SemanticRetriever = original_cls
        deps._semantic_retriever = original_singleton


def run_all():
    tests = [
        test_disabled_never_imports_chromadb_or_requests,
        test_get_semantic_retriever_imports_lazily_and_stays_singleton,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
