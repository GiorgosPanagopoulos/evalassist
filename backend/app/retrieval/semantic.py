"""RAG pipeline: embed query -> ChromaDB top-20 (scope-filtered server-side)
-> rerank top-5 -> grounded LLM prompt -> SemanticResult με citations.

Η isolation επιβάλλεται ΠΡΙΝ το query φτάσει στο ChromaDB (where filter από
`IsolationScope.build_chroma_where()`) — καμία isolation λογική δεν μπαίνει
στο prompt του LLM.
"""

import requests

from app.core.config import get_settings
from app.core.exceptions import LLMUnavailableError
from app.core.prompt_loader import load_prompt
from app.ingestion.embedder import Embedder
from app.ingestion.vectorstore import CHROMA_DIR, get_collection
from app.retrieval.isolation import IsolationScope
from app.retrieval.llm import OllamaClient
from app.retrieval.models import Citation, SemanticResult
from app.retrieval.reranker import Reranker

_settings = get_settings()
TOP_K_RETRIEVE = _settings.TOP_K_RETRIEVE
TOP_K_RERANK = _settings.TOP_K_RERANK

NO_DATA_ANSWER = (
    "Δεν βρέθηκαν δεδομένα εντός του καθορισμένου πεδίου (person_id/period) "
    "για να απαντηθεί το ερώτημα."
)


class SemanticRetriever:
    def __init__(
        self,
        embedder: Embedder | None = None,
        vectorstore=None,
        reranker: Reranker | None = None,
        llm: OllamaClient | None = None,
        chroma_dir=CHROMA_DIR,
    ):
        self.embedder = embedder or Embedder()
        self.vectorstore = vectorstore or get_collection(chroma_dir)
        self.reranker = reranker or Reranker()
        self.llm = llm or OllamaClient(model_name=_settings.resolved_gen_model)
        self.system_prompt, self.prompt_version = load_prompt("semantic_rag")

    def query(self, query_text: str, scope: IsolationScope) -> SemanticResult:
        where = scope.build_chroma_where()
        [query_embedding] = self.embedder.embed([query_text])
        results = self.vectorstore.query(
            query_embeddings=[query_embedding],
            n_results=TOP_K_RETRIEVE,
            where=where,
        )
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []

        if not documents:
            return SemanticResult(
                answer=NO_DATA_ANSWER,
                citations=[],
                retrieved_doc_ids=[],
                model=self.llm.model_name,
            )

        reranked = self.reranker.rerank(query_text, documents, top_k=TOP_K_RERANK)

        citations: list[Citation] = []
        excerpts: list[str] = []
        for idx, score in reranked:
            meta = metadatas[idx]
            citations.append(
                Citation(
                    doc_id=meta["doc_id"],
                    page=meta["page"],
                    section=meta["section"],
                    score=score,
                )
            )
            person_name = meta.get("person_name")
            label = f"[{meta['doc_id']} σελ.{meta['page']} - {meta['section']}"
            if person_name:
                label += f" - person_name: {person_name}"
            label += "]"
            excerpts.append(f"{label}\n{documents[idx]}")

        retrieved_doc_ids = sorted({c.doc_id for c in citations})
        user_prompt = f"Ερώτημα: {query_text}\n\nΑποσπάσματα:\n\n" + "\n\n---\n\n".join(excerpts)
        try:
            answer = self.llm.generate(self.system_prompt, user_prompt)
        except requests.RequestException as exc:
            # Η ανάκτηση πέτυχε -> το audit trail πρέπει να κρατήσει τα doc_ids
            # που ήδη ανακτήθηκαν, ακόμη κι αν η σύνθεση απάντησης αποτύχει.
            raise LLMUnavailableError(str(exc), retrieved_doc_ids=retrieved_doc_ids) from exc

        return SemanticResult(
            answer=answer,
            citations=citations,
            retrieved_doc_ids=retrieved_doc_ids,
            model=self.llm.model_name,
        )
