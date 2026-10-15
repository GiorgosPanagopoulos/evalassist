"""FastAPI dependency providers.

Όλα τα wiring (DB connection, SemanticRetriever singleton, settings) περνάνε
από εδώ ως `Depends(...)`, ώστε τα tests να μπορούν να τα κάνουν override
χωρίς να αγγίξουν τα routes.
"""

import sqlite3
from typing import Callable, Iterator

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.db.database import get_connection
from app.retrieval.semantic import SemanticRetriever


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    conn = get_connection(settings.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


_semantic_retriever: SemanticRetriever | None = None


def get_semantic_retriever() -> SemanticRetriever:
    """Lazy module-level singleton — bge-m3/reranker φορτώνονται μόνο στο
    πρώτο πραγματικό query, όχι στο import ή στο app startup."""
    global _semantic_retriever
    if _semantic_retriever is None:
        _semantic_retriever = SemanticRetriever()
    return _semantic_retriever


def get_semantic_retriever_factory() -> Callable[[], SemanticRetriever]:
    """Επιστρέφει τη συνάρτηση, ΟΧΙ τον retriever. Το /api/query/semantic
    ελέγχει πρώτα το SEMANTIC_ENABLED και μόνο μετά την καλεί, ώστε με το
    flag κλειστό να μη φορτώνονται ποτέ bge-m3/reranker. Ο έλεγχος δεν
    εξαρτάται από τη σειρά επίλυσης των dependencies."""
    return get_semantic_retriever
