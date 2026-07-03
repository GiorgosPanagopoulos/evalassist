"""Τοπικό cross-encoder reranking με BAAI/bge-reranker-v2-m3.

Lazy import+φόρτωση μοντέλου (ίδιο pattern με app.ingestion.embedder) — δεν
καταναλώνει μνήμη/χρόνο εκκίνησης αν δεν χρησιμοποιηθεί.
"""

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

MODEL_NAME = get_settings().RERANKER_MODEL


class Reranker:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model: "CrossEncoder | None" = None

    @property
    def model(self) -> "CrossEncoder":
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, docs: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        """Επιστρέφει [(original_index, score), ...] φθίνουσα ταξινόμηση σκορ."""
        if not docs:
            return []
        pairs = [[query, doc] for doc in docs]
        scores = self.model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return [(idx, float(score)) for idx, score in ranked[:top_k]]
