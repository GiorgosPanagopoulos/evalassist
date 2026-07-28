"""Response types του retrieval layer.

`retrieved_doc_ids` υπάρχει πάντα και στα δύο mode results (ακόμη και άδειο)·
η Φάση 4 το περνάει αναλλοίωτο στο audit_log.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RetrievalMode(StrEnum):
    STRUCTURED = "structured"
    SEMANTIC = "semantic"


class Citation(BaseModel):
    doc_id: str
    page: int
    section: str
    score: float  # reranker relevance score


class StructuredResult(BaseModel):
    mode: RetrievalMode = RetrievalMode.STRUCTURED
    data: dict[str, Any]
    sources: list[dict[str, str]]
    retrieved_doc_ids: list[str]


class SemanticResult(BaseModel):
    mode: RetrievalMode = RetrievalMode.SEMANTIC
    answer: str
    citations: list[Citation]
    retrieved_doc_ids: list[str]
    model: str
    # Query-routing suggestion (π.χ. "structured") — μόνο hint, το API/frontend
    # δεν παρακάμπτει ποτέ την επιλογή mode του χρήστη· βλ. app.retrieval.routing.
    routing_hint: str | None = None
    # Έκδοση prompt που χρησιμοποιήθηκε (semantic only, structured -> None)
    prompt_version: str | None = None
    # Φάση 1 rank validator (μόνο logging): βαθμοί στην απάντηση χωρίς
    # κανένα variant τους στο context που πήγε στο LLM.
    unsupported_ranks: list[str] = Field(default_factory=list)
