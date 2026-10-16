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


class StructuredCitation(BaseModel):
    """Προέλευση μιας δομημένης απάντησης, μόνο από ό,τι υπάρχει ήδη στη DB.
    page=None σημαίνει ότι η σελίδα δεν καταγράφηκε στη DB (π.χ. promotions,
    service_time δεν έχουν στήλη σελίδας) — ποτέ εικασία."""

    doc_id: str
    page: int | None
    section: str


class StructuredResult(BaseModel):
    mode: RetrievalMode = RetrievalMode.STRUCTURED
    data: dict[str, Any]
    citations: list[StructuredCitation]
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
    # Λόγος άρνησης του precheck (app.retrieval.precheck.RefusalReason) όταν το
    # ερώτημα απορρίφθηκε πριν το retrieval· None για κανονική απάντηση.
    refusal_reason: str | None = None
