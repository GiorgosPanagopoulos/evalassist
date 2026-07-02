"""RAG pipeline: embed query -> ChromaDB top-20 (scope-filtered server-side)
-> rerank top-5 -> grounded LLM prompt -> SemanticResult με citations.

Η isolation επιβάλλεται ΠΡΙΝ το query φτάσει στο ChromaDB (where filter από
`IsolationScope.build_chroma_where()`) — καμία isolation λογική δεν μπαίνει
στο prompt του LLM.
"""

from app.ingestion.embedder import Embedder
from app.ingestion.vectorstore import CHROMA_DIR, get_collection
from app.retrieval.isolation import IsolationScope
from app.retrieval.llm import OllamaClient
from app.retrieval.models import Citation, SemanticResult
from app.retrieval.reranker import Reranker

TOP_K_RETRIEVE = 20
TOP_K_RERANK = 5

NO_DATA_ANSWER = (
    "Δεν βρέθηκαν δεδομένα εντός του καθορισμένου πεδίου (person_id/period) "
    "για να απαντηθεί το ερώτημα."
)

SYSTEM_PROMPT = (
    "Είσαι βοηθός αξιολογητή των Ελληνικών Ενόπλων Δυνάμεων. Απάντα ΜΟΝΟ με "
    "βάση τα παρακάτω αποσπάσματα εκθέσεων αξιολόγησης. Αν τα αποσπάσματα δεν "
    "επαρκούν για να απαντηθεί πλήρως το ερώτημα, δήλωσέ το ρητά. Μην "
    "επινοείς ποτέ βαθμολογίες ή γεγονότα που δεν αναφέρονται ρητά στα "
    "αποσπάσματα. Απάντα στα Ελληνικά. Η απάντησή σου είναι συμβουλευτική "
    "για τον ανθρώπινο αξιολογητή — δεν αποτελεί τελική απόφαση."
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
        self.llm = llm or OllamaClient()

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
            excerpts.append(
                f"[{meta['doc_id']} σελ.{meta['page']} - {meta['section']}]\n{documents[idx]}"
            )

        retrieved_doc_ids = sorted({c.doc_id for c in citations})
        user_prompt = f"Ερώτημα: {query_text}\n\nΑποσπάσματα:\n\n" + "\n\n---\n\n".join(excerpts)
        answer = self.llm.generate(SYSTEM_PROMPT, user_prompt)

        return SemanticResult(
            answer=answer,
            citations=citations,
            retrieved_doc_ids=retrieved_doc_ids,
            model=self.llm.model_name,
        )
