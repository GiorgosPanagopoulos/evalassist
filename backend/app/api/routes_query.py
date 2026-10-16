"""Query endpoints: structured (deterministic SQL) και semantic (RAG).

Κάθε handler περνάει πάντα από IsolationScope πριν αγγίξει SQLite/ChromaDB,
και γράφει ακριβώς μία γραμμή στο audit_log ανά κλήση — ακόμη και όταν η
επεξεργασία μετά την ανάκτηση αποτύχει (audit πριν το re-raise).

Πριν από οποιαδήποτε ανάκτηση τρέχουν οι ντετερμινιστικοί έλεγχοι του
app.retrieval.precheck: ανύπαρκτη περίοδος -> 422, και στο semantic endpoint
έτος/κωδικός πεδίου εκτός εύρους -> 200 με σταθερό κείμενο άρνησης, χωρίς
retrieval και χωρίς LLM."""

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Callable

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import get_db, get_semantic_retriever_factory
from app.api.schemas import (
    SemanticQueryRequest,
    SemanticQueryResponse,
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from app.auth.deps import SessionUser, require_user
from app.core.audit import AuditEntry, write_audit
from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidPeriodError
from app.models.evaluation import CAREER_PERIOD
from app.retrieval.isolation import IsolationScope
from app.retrieval.models import SemanticResult
from app.retrieval.precheck import PRECHECK_MODEL, PrecheckRefusal, check_question, validate_period
from app.retrieval.routing import route_query
from app.retrieval.structured import (
    compare_periods,
    get_promotions_table,
    get_scores,
    get_service_time_table,
    top_bottom_sections,
)

if TYPE_CHECKING:
    # Μόνο για type checking, βλ. app.api.deps: χωρίς chromadb/requests στο startup.
    from app.retrieval.semantic import SemanticRetriever

router = APIRouter()
logger = logging.getLogger(__name__)

SEMANTIC_DISABLED_CODE = "semantic_disabled"
SEMANTIC_DISABLED_DETAIL = "Η σημασιολογική αναζήτηση δεν είναι ενεργή σε αυτή την εγκατάσταση."
CAREER_WIDE_OPERATIONS = ("get_promotions_table", "get_service_time_table")


def _audit(
    conn: sqlite3.Connection,
    user: str,
    query: str,
    doc_ids: list[str],
    mode: str,
    prompt_version: str | None = None,
    unsupported_ranks: list[str] | None = None,
    answer_text: str | None = None,
    refusal_reason: str | None = None,
    *,
    person_id: str | None,
    period: str | None,
    other_period: str | None = None,
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
            answer_text=answer_text,
            refusal_reason=refusal_reason,
            person_id=person_id,
            period=period,
            other_period=other_period,
        ),
    )
    conn.commit()
    return audit_id


@router.post("/structured", response_model=StructuredQueryResponse)
def query_structured(
    request: StructuredQueryRequest,
    conn: sqlite3.Connection = Depends(get_db),
    user: SessionUser = Depends(require_user),
) -> StructuredQueryResponse:
    doc_ids: list[str] = []
    # Το scope που εφαρμόζεται, για το audit: τα career-wide operations
    # αγνοούν το request.period και διαβάζουν πάντα CAREER_PERIOD.
    audit_scope = {
        "person_id": request.person_id,
        "period": CAREER_PERIOD if request.operation in CAREER_WIDE_OPERATIONS else request.period,
        "other_period": request.other_period if request.operation == "compare_periods" else None,
    }
    try:
        scope = IsolationScope(person_id=request.person_id, period=request.period)
        # Τα career-wide operations αγνοούν το request.period, άρα δεν το επικυρώνουν.
        if request.operation in ("get_scores", "compare_periods", "top_bottom_sections"):
            validate_period(conn, scope.person_id, scope.period)
        if request.operation == "compare_periods":
            validate_period(conn, scope.person_id, request.other_period)
        if request.operation == "get_scores":
            result = get_scores(conn, scope)
        elif request.operation == "compare_periods":
            # compare_periods χτίζει το δικό του IsolationScope ανά period
            # εσωτερικά· περνάμε τις τιμές μέσα από το validated scope object.
            result = compare_periods(conn, scope.person_id, scope.period, request.other_period)
        elif request.operation == "top_bottom_sections":
            result = top_bottom_sections(conn, scope, n=request.n or 3)
        elif request.operation == "get_promotions_table":
            # career-wide: το request.period αγνοείται, το scope χτίζεται πάντα
            # με CAREER_PERIOD (βλ. app.retrieval.isolation, app.models.evaluation).
            career_scope = IsolationScope(person_id=request.person_id, period=CAREER_PERIOD)
            result = get_promotions_table(conn, career_scope)
        else:  # get_service_time_table
            career_scope = IsolationScope(person_id=request.person_id, period=CAREER_PERIOD)
            result = get_service_time_table(conn, career_scope)
        doc_ids = result.retrieved_doc_ids
    except Exception as exc:
        if not doc_ids:
            doc_ids = getattr(exc, "retrieved_doc_ids", []) or []
        _audit(conn, user.username, request.model_dump_json(), doc_ids, "structured", **audit_scope)
        raise

    try:
        answer_text = json.dumps(result.data, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        # Fail safe: το audit record έχει προτεραιότητα έναντι του answer_text.
        # Μόνο ο τύπος: το μήνυμα της εξαίρεσης μπορεί να περιέχει δεδομένα.
        logger.warning("Αποτυχία serialization του result.data για audit (%s)", type(exc).__name__)
        answer_text = None
    audit_id = _audit(
        conn,
        user.username,
        request.model_dump_json(),
        doc_ids,
        "structured",
        answer_text=answer_text,
        **audit_scope,
    )
    return StructuredQueryResponse(result=result, audit_id=audit_id)


@router.post(
    "/semantic",
    response_model=SemanticQueryResponse,
    responses={status.HTTP_403_FORBIDDEN: {"description": SEMANTIC_DISABLED_DETAIL}},
)
def query_semantic(
    request: SemanticQueryRequest,
    conn: sqlite3.Connection = Depends(get_db),
    make_retriever: "Callable[[], SemanticRetriever]" = Depends(get_semantic_retriever_factory),
    settings: Settings = Depends(get_settings),
    user: SessionUser = Depends(require_user),
) -> SemanticQueryResponse | JSONResponse:
    if not settings.SEMANTIC_ENABLED:
        # Πριν από scope, precheck, retrieval ή LLM, και χωρίς να κληθεί το
        # factory: με το flag κλειστό τα μοντέλα δεν φορτώνονται ποτέ.
        _audit(
            conn,
            user.username,
            request.question,
            [],
            "semantic",
            refusal_reason=SEMANTIC_DISABLED_CODE,
            person_id=request.person_id,
            period=request.period,
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": SEMANTIC_DISABLED_DETAIL, "code": SEMANTIC_DISABLED_CODE},
        )

    retriever = make_retriever()
    doc_ids: list[str] = []
    refusal: PrecheckRefusal | None = None
    try:
        scope = IsolationScope(person_id=request.person_id, period=request.period)
        validate_period(conn, scope.person_id, scope.period)
        refusal = check_question(conn, scope, request.question)
        if refusal is None:
            # Η "no data in scope" περίπτωση επιστρέφει ήδη ένα valid SemanticResult
            # με retrieved_doc_ids=[] (όχι exception) — audit + 200 φυσικά, χωρίς
            # ειδική περίπτωση εδώ.
            result = retriever.query(request.question, scope)
            # Advisory routing hint (human-in-the-loop): δεν αλλάζει mode μόνο του,
            # μόνο ενημερώνει το frontend ώστε να προτείνει "Δομημένη αναζήτηση".
            result.routing_hint = route_query(request.question)
            doc_ids = result.retrieved_doc_ids
    except InvalidPeriodError:
        # Λάθος αιτήματος πριν από οποιαδήποτε ανάκτηση ή prompt.
        _audit(
            conn,
            user.username,
            request.question,
            [],
            "semantic",
            person_id=request.person_id,
            period=request.period,
        )
        raise
    except Exception as exc:
        if not doc_ids:
            doc_ids = getattr(exc, "retrieved_doc_ids", []) or []
        _audit(
            conn,
            user.username,
            request.question,
            doc_ids,
            "semantic",
            retriever.prompt_version,
            person_id=scope.person_id,
            period=scope.period,
        )
        raise

    if refusal is not None:
        # Τίποτα δεν ανακτήθηκε και κανένα prompt δεν χρησιμοποιήθηκε: doc_ids=[],
        # prompt_version/unsupported_ranks=NULL, answer_text = το κείμενο άρνησης,
        # refusal_reason = ο κωδικός άρνησης.
        audit_id = _audit(
            conn,
            user.username,
            request.question,
            [],
            "semantic",
            answer_text=refusal.text,
            refusal_reason=refusal.reason,
            person_id=scope.person_id,
            period=scope.period,
        )
        refused = SemanticResult(
            answer=refusal.text,
            citations=[],
            retrieved_doc_ids=[],
            model=PRECHECK_MODEL,
            refusal_reason=refusal.reason,
        )
        return SemanticQueryResponse(result=refused, audit_id=audit_id)

    audit_id = _audit(
        conn,
        user.username,
        request.question,
        doc_ids,
        "semantic",
        result.prompt_version,
        result.unsupported_ranks,
        answer_text=result.answer,
        person_id=scope.person_id,
        period=scope.period,
    )
    return SemanticQueryResponse(result=result, audit_id=audit_id)
