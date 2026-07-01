"""Τοπικά dense embeddings με BAAI/bge-m3 (sentence-transformers).

Πλήρως offline μετά το πρώτο (one-off) download των βαρών του μοντέλου από
το HuggingFace Hub — καμία κλήση σε cloud API κατά το embedding.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"


class Embedder:
    """Wrapper γύρω από SentenceTransformer, με lazy import+φόρτωση του
    μοντέλου (δεν καταναλώνει μνήμη/χρόνο εκκίνησης, ούτε φορτώνει το βαρύ
    torch/transformers dependency chain, αν δεν χρησιμοποιηθεί)."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model: "SentenceTransformer | None" = None

    @property
    def model(self) -> "SentenceTransformer":
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
