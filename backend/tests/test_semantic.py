"""Mini test/sample flow για το RAG semantic retrieval pipeline (Φάση 3).

Χρησιμοποιεί fakes (FakeEmbedder/FakeVectorStore/FakeReranker/FakeLLM) — καμία
εξάρτηση από πραγματικά ML μοντέλα ή τοπικό Ollama server. Καλύπτει:
  - isolation regression: το where filter που φτάνει στο vectorstore είναι
    ακριβώς `scope.build_chroma_where()`.
  - citations 1-προς-1 με τα top-5 reranked chunks που φτάνουν στο LLM.
  - άδειο scope (καμία εγγραφή στο scope) -> "no data" answer, καμία κλήση LLM.

Εκτελείται standalone: `python tests/test_semantic.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.isolation import IsolationScope  # noqa: E402
from app.retrieval.semantic import NO_DATA_ANSWER, SemanticRetriever  # noqa: E402


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectorStore:
    def __init__(self, documents: list[str], metadatas: list[dict]):
        self._documents = documents
        self._metadatas = metadatas
        self.last_where: dict | None = None
        self.last_n_results: int | None = None

    def query(self, query_embeddings, n_results, where):
        self.last_where = where
        self.last_n_results = n_results
        return {"documents": [self._documents], "metadatas": [self._metadatas]}


class FakeReranker:
    """Deterministic: κατατάσσει με βάση το μήκος του κειμένου (φθίνουσα)."""

    def rerank(self, query: str, docs: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        ranked = sorted(range(len(docs)), key=lambda i: len(docs[i]), reverse=True)
        return [(i, 1.0 - 0.01 * rank) for rank, i in enumerate(ranked[:top_k])]


class FakeLLM:
    model_name = "fake-llm"

    def __init__(self):
        self.calls = 0
        self.last_system: str | None = None
        self.last_user: str | None = None

    def generate(self, system: str, user: str) -> str:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        return "FAKE ANSWER"


def _make_chunks():
    documents = [
        "Σύντομο απόσπασμα.",
        "Ένα πολύ πιο εκτενές απόσπασμα με περισσότερες λεπτομέρειες για την αξιολόγηση.",
        "Μεσαίου μήκους απόσπασμα με κάποιες λεπτομέρειες.",
    ]
    metadatas = [
        {"doc_id": "doc1", "page": 1, "section": "Στοχοθεσία", "person_id": "p1", "period": "2025"},
        {
            "doc_id": "doc1",
            "page": 2,
            "section": "Ηγετική Ικανότητα",
            "person_id": "p1",
            "period": "2025",
        },
        {"doc_id": "doc2", "page": 1, "section": "Στοχοθεσία", "person_id": "p1", "period": "2025"},
    ]
    return documents, metadatas


def test_isolation_where_filter_matches_scope():
    documents, metadatas = _make_chunks()
    vectorstore = FakeVectorStore(documents, metadatas)
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=FakeLLM()
    )

    retriever.query("Πώς ήταν η στοχοθεσία;", scope)

    assert vectorstore.last_where == scope.build_chroma_where()
    assert vectorstore.last_n_results == 20


def test_citations_match_reranked_top_k():
    documents, metadatas = _make_chunks()
    vectorstore = FakeVectorStore(documents, metadatas)
    reranker = FakeReranker()
    llm = FakeLLM()
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=reranker, llm=llm
    )

    result = retriever.query("Πώς ήταν η στοχοθεσία;", scope)

    expected_order = reranker.rerank("Πώς ήταν η στοχοθεσία;", documents, top_k=5)
    assert len(result.citations) == len(expected_order)
    for citation, (idx, score) in zip(result.citations, expected_order):
        assert citation.doc_id == metadatas[idx]["doc_id"]
        assert citation.page == metadatas[idx]["page"]
        assert citation.section == metadatas[idx]["section"]
        assert citation.score == score

    assert result.answer == "FAKE ANSWER"
    assert result.model == "fake-llm"
    assert set(result.retrieved_doc_ids) == {"doc1", "doc2"}
    assert llm.calls == 1


def test_empty_scope_skips_llm_call():
    vectorstore = FakeVectorStore([], [])
    llm = FakeLLM()
    scope = IsolationScope(person_id="ghost", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    result = retriever.query("Ερώτημα χωρίς δεδομένα", scope)

    assert result.answer == NO_DATA_ANSWER
    assert result.citations == []
    assert result.retrieved_doc_ids == []
    assert llm.calls == 0
    assert vectorstore.last_where == scope.build_chroma_where()


def run_all():
    tests = [
        test_isolation_where_filter_matches_scope,
        test_citations_match_reranked_top_k,
        test_empty_scope_skips_llm_call,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
