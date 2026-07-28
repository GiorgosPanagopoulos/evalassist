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


def _where_matches(where: dict, meta: dict) -> bool:
    """Ελαφρύ simulation του ChromaDB where filter ($and/$or/$eq) πάνω σε
    dict metadata, ώστε τα fake tests να ελέγχουν πραγματικό φιλτράρισμα
    (όχι μόνο το σχήμα του where dict). Άγνωστο operator -> ValueError,
    ΠΟΤΕ silent True (θα έκρυβε ψευδές isolation pass στα tests)."""
    if len(where) != 1:
        raise ValueError(f"unexpected where clause shape (expected single key): {where!r}")
    (key, value), = where.items()

    if key == "$and":
        return all(_where_matches(clause, meta) for clause in value)
    if key == "$or":
        return any(_where_matches(clause, meta) for clause in value)
    if key.startswith("$"):
        raise ValueError(f"unsupported operator in where clause: {key!r}")

    # key είναι όνομα πεδίου· value είτε literal είτε {"$eq": literal}
    if isinstance(value, dict):
        if set(value.keys()) != {"$eq"}:
            raise ValueError(f"unsupported condition for field {key!r}: {value!r}")
        expected = value["$eq"]
    else:
        expected = value
    return meta.get(key) == expected


class FakeFilteringVectorStore:
    """Σε αντίθεση με το FakeVectorStore, εφαρμόζει πραγματικά το where
    filter πάνω στα metadata, ώστε να ελέγχεται το isolation end-to-end
    (career widening χωρίς διαρροή σε άλλο πρόσωπο)."""

    def __init__(self, documents: list[str], metadatas: list[dict]):
        self._documents = documents
        self._metadatas = metadatas
        self.last_where: dict | None = None

    def query(self, query_embeddings, n_results, where):
        self.last_where = where
        matched_docs = []
        matched_metas = []
        for doc, meta in zip(self._documents, self._metadatas):
            if _where_matches(where, meta):
                matched_docs.append(doc)
                matched_metas.append(meta)
        return {"documents": [matched_docs[:n_results]], "metadatas": [matched_metas[:n_results]]}


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
    assert result.unsupported_ranks == []
    assert llm.calls == 0
    assert vectorstore.last_where == scope.build_chroma_where()


def test_system_prompt_contains_tightened_instructions():
    """Φάση B1: το system prompt (v2) πρέπει να περιέχει τις νέες οδηγίες
    σφιξίματος — απάντηση μόνο στο ζητούμενο, ρητή δήλωση όταν λείπει από τα
    αποσπάσματα, ονόματα/βαθμοί μόνο αυτούσια από αποσπάσματα ή person_name."""
    documents, metadatas = _make_chunks()
    vectorstore = FakeVectorStore(documents, metadatas)
    llm = FakeLLM()
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    retriever.query("Πώς ήταν η στοχοθεσία;", scope)

    assert retriever.prompt_version == "v2"
    assert "Δεν βρέθηκε στα διαθέσιμα αποσπάσματα." in llm.last_system
    assert "ΑΠΟΚΛΕΙΣΤΙΚΑ στο ερώτημα" in llm.last_system
    assert "person_name" in llm.last_system


def test_user_prompt_includes_person_name_metadata_when_present():
    """Φάση B1: όταν το ανακτημένο chunk έχει person_name στα metadata, το
    όνομα φτάνει αυτούσιο στο user prompt του LLM."""
    documents = ["Απόσπασμα με στοιχεία αξιολόγησης."]
    metadatas = [
        {
            "doc_id": "doc1",
            "page": 1,
            "section": "Στοχοθεσία",
            "person_id": "p1",
            "period": "2025",
            "person_name": "Παπαδόπουλος Γιώργος",
        }
    ]
    vectorstore = FakeVectorStore(documents, metadatas)
    llm = FakeLLM()
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    retriever.query("Πώς πήγε ο Παπαδόπουλος;", scope)

    assert "Παπαδόπουλος Γιώργος" in llm.last_user


def test_user_prompt_omits_person_name_when_absent_from_metadata():
    """Χωρίς person_name στα metadata (π.χ. παλαιότερα ingested chunks), η
    κατασκευή του prompt δεν πρέπει να σκάει (KeyError) ούτε να επινοεί όνομα."""
    documents, metadatas = _make_chunks()  # καμία έχει "person_name" key
    vectorstore = FakeVectorStore(documents, metadatas)
    llm = FakeLLM()
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    retriever.query("Πώς ήταν η στοχοθεσία;", scope)

    assert "person_name" not in llm.last_user


class FakeLLMWithUnsupportedRank(FakeLLM):
    """Επιστρέφει βαθμό που ΔΕΝ υπάρχει στα ανακτημένα αποσπάσματα (real
    incident: ΠΧΗΣ στο context, "Υπλγού" στην απάντηση)."""

    def generate(self, system: str, user: str) -> str:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        return "με βαθμό Υπλγού"


def test_rank_validator_flags_unsupported_rank_in_real_pipeline():
    """Φάση 1 rank validator: επαλήθευση end-to-end μέσα από το πραγματικό
    SemanticRetriever.query() (όχι μόνο την απομονωμένη συνάρτηση), ώστε ένα
    regression στη σύνδεση semantic.py <-> rank_validator.py να πιάνεται εδώ."""
    documents, metadatas = _make_chunks()
    vectorstore = FakeVectorStore(documents, metadatas)
    llm = FakeLLMWithUnsupportedRank()
    scope = IsolationScope(person_id="p1", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    result = retriever.query("Πώς ήταν η στοχοθεσία;", scope)

    assert result.answer == "με βαθμό Υπλγού"
    assert result.unsupported_ranks == ["ΥΠΟΛΟΧΑΓΟΣ"]


def _make_two_person_career_chunks():
    """2 fake πρόσωπα (Μ-00000, Μ-00001). Το Μ-00000 έχει chunk στη ζητούμενη
    περίοδο (2025), career-wide chunk, ΚΑΙ chunk σε άλλη περίοδο (2024) που
    ΔΕΝ πρέπει να επιστραφεί. Το Μ-00001 έχει αντίστοιχα period + career
    chunks που δεν πρέπει ΠΟΤΕ να διαρρεύσουν στο query του Μ-00000."""
    documents = [
        "Μ-00000 - στοχοθεσία περιόδου 2025.",
        "Μ-00000 - career: κρίσεις προαγωγών, τοποθετήσεις.",
        "Μ-00000 - στοχοθεσία περιόδου 2024, ΔΕΝ πρέπει να επιστραφεί.",
        "Μ-00001 - στοχοθεσία περιόδου 2025, ΔΕΝ πρέπει να επιστραφεί.",
        "Μ-00001 - career: κρίσεις προαγωγών, ΔΕΝ πρέπει να επιστραφεί ποτέ.",
    ]
    metadatas = [
        {"doc_id": "docA-period", "page": 1, "section": "Στοχοθεσία", "person_id": "Μ-00000", "period": "2025"},
        {
            "doc_id": "docA-career",
            "page": 1,
            "section": "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ",
            "person_id": "Μ-00000",
            "period": "career",
        },
        {
            "doc_id": "docA-other-period",
            "page": 1,
            "section": "Στοχοθεσία",
            "person_id": "Μ-00000",
            "period": "2024",
        },
        {"doc_id": "docB-period", "page": 1, "section": "Στοχοθεσία", "person_id": "Μ-00001", "period": "2025"},
        {
            "doc_id": "docB-career",
            "page": 1,
            "section": "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ",
            "person_id": "Μ-00001",
            "period": "career",
        },
    ]
    return documents, metadatas


def test_career_chunks_included_without_leaking_other_person_or_period():
    documents, metadatas = _make_two_person_career_chunks()
    vectorstore = FakeFilteringVectorStore(documents, metadatas)
    llm = FakeLLM()
    scope = IsolationScope(person_id="Μ-00000", period="2025")
    retriever = SemanticRetriever(
        embedder=FakeEmbedder(), vectorstore=vectorstore, reranker=FakeReranker(), llm=llm
    )

    result = retriever.query("Ποιες ήταν οι τοποθετήσεις;", scope)

    assert set(result.retrieved_doc_ids) == {"docA-period", "docA-career"}


def run_all():
    tests = [
        test_isolation_where_filter_matches_scope,
        test_citations_match_reranked_top_k,
        test_empty_scope_skips_llm_call,
        test_rank_validator_flags_unsupported_rank_in_real_pipeline,
        test_system_prompt_contains_tightened_instructions,
        test_user_prompt_includes_person_name_metadata_when_present,
        test_user_prompt_omits_person_name_when_absent_from_metadata,
        test_career_chunks_included_without_leaking_other_person_or_period,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
