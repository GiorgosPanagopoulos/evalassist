"""Query endpoints: structured (deterministic SQL) και semantic (RAG).

Κάθε handler περνάει πάντα από IsolationScope πριν αγγίξει SQLite/ChromaDB,
και γράφει ακριβώς μία γραμμή στο audit_log ανά κλήση — ακόμη και όταν η
επεξεργασία μετά την ανάκτηση αποτύχει (audit πριν το re-raise)."""

import sqlite3

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_db, get_semantic_retriever
from app.api.schemas import (
    SemanticQueryRequest,
    SemanticQueryResponse,
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from app.core.audit import AuditEntry, write_audit
from app.retrieval.isolation import IsolationScope
from app.retrieval.routing import route_query
from app.retrieval.semantic import SemanticRetriever
from app.retrieval.structured import compare_periods, get_scores, top_bottom_sections

router = APIRouter()


def _audit(
    conn: sqlite3.Connection,
    user: str,
    query: str,
    doc_ids: list[str],
    mode: str,
    prompt_version: str | None = None,
    unsupported_ranks: list[str] | None = None,
) -> int:
    audit_id = write_audit(
        conn,
        AuditEntry(
            user=user,
            query=query,
            retrieved_doc_ids=doc_ids,
            mode=mode,
            prompt_version=prompt_version,
            unsupported_ranks=unsupported_ranks,
        ),
    )
    conn.commit()
    return audit_id


@router.post("/structured", response_model=StructuredQueryResponse)
def query_structured(
    request: StructuredQueryRequest,
    conn: sqlite3.Connection = Depends(get_db),
    x_user: str = Header(default="anonymous", alias="X-User"),
) -> StructuredQueryResponse:
    doc_ids: list[str] = []
    try:
        scope = IsolationScope(person_id=request.person_id, period=request.period)
        if request.operation == "get_scores":
            result = get_scores(conn, scope)
        elif request.operation == "compare_periods":
            # compare_periods χτίζει το δικό του IsolationScope ανά period
            # εσωτερικά· περνάμε τις τιμές μέσα από το validated scope object.
            result = compare_periods(conn, scope.person_id, scope.period, request.other_period)
        else:  # top_bottom_sections
            result = top_bottom_sections(conn, scope, n=request.n or 3)
        doc_ids = result.retrieved_doc_ids
    except Exception as exc:
        if not doc_ids:
            doc_ids = getattr(exc, "retrieved_doc_ids", []) or []
        _audit(conn, x_user, request.model_dump_json(), doc_ids, "structured")
        raise

    audit_id = _audit(conn, x_user, request.model_dump_json(), doc_ids, "structured")
    return StructuredQueryResponse(result=result, audit_id=audit_id)


@router.post("/semantic", response_model=SemanticQueryResponse)
def query_semantic(
    request: SemanticQueryRequest,
    conn: sqlite3.Connection = Depends(get_db),
    retriever: SemanticRetriever = Depends(get_semantic_retriever),
    x_user: str = Header(default="anonymous", alias="X-User"),
) -> SemanticQueryResponse:
    doc_ids: list[str] = []
    try:
        scope = IsolationScope(person_id=request.person_id, period=request.period)
        # Η "no data in scope" περίπτωση επιστρέφει ήδη ένα valid SemanticResult
        # με retrieved_doc_ids=[] (όχι exception) — audit + 200 φυσικά, χωρίς
        # ειδική περίπτωση εδώ.
        result = retriever.query(request.question, scope)
        # Advisory routing hint (human-in-the-loop): δεν αλλάζει mode μόνο του,
        # μόνο ενημερώνει το frontend ώστε να προτείνει "Δομημένη αναζήτηση".
        result.routing_hint = route_query(request.question)
        doc_ids = result.retrieved_doc_ids
    except Exception as exc:
        if not doc_ids:
            doc_ids = getattr(exc, "retrieved_doc_ids", []) or []
        _audit(conn, x_user, request.question, doc_ids, "semantic", retriever.prompt_version)
        raise

    audit_id = _audit(
        conn,
        x_user,
        request.question,
        doc_ids,
        "semantic",
        result.prompt_version,
        result.unsupported_ranks,
    )
    return SemanticQueryResponse(result=result, audit_id=audit_id)
