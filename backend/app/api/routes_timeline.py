"""Timeline endpoint: GET /person/{person_id}/timeline (structured mode μόνο).

Ίδιο συμβόλαιο με τα /query handlers: το person_id φιλτράρεται server-side
μέσα στο SQL, και γράφεται ακριβώς μία γραμμή στο audit_log ανά κλήση με
mode="structured" — ακόμη και όταν η ανάκτηση αποτύχει (audit πριν το
re-raise)."""

import json
import logging
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_db
from app.auth.deps import SessionUser, require_user
from app.core.audit import AuditEntry, write_audit
from app.retrieval.models import RetrievalMode
from app.retrieval.timeline import TimelineResult, get_timeline

router = APIRouter()
logger = logging.getLogger(__name__)


class TimelineResponse(BaseModel):
    result: TimelineResult
    audit_id: int


def _audit(
    conn: sqlite3.Connection,
    user: str,
    person_id: str,
    doc_ids: list[str],
    answer_text: str | None = None,
) -> int:
    audit_id = write_audit(
        conn,
        AuditEntry(
            user=user,
            query=json.dumps({"endpoint": "timeline", "person_id": person_id}, ensure_ascii=False),
            retrieved_doc_ids=doc_ids,
            mode=RetrievalMode.STRUCTURED,
            answer_text=answer_text,
        ),
    )
    conn.commit()
    return audit_id


@router.get("/person/{person_id}/timeline", response_model=TimelineResponse)
def person_timeline(
    person_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    user: SessionUser = Depends(require_user),
) -> TimelineResponse:
    doc_ids: list[str] = []
    try:
        result = get_timeline(conn, person_id)
        doc_ids = result.retrieved_doc_ids
    except Exception:
        _audit(conn, user.username, person_id, doc_ids)
        raise

    try:
        answer_text = json.dumps([p.model_dump() for p in result.points], ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        # Fail safe: το audit record έχει προτεραιότητα έναντι του answer_text.
        # Μόνο ο τύπος: το μήνυμα της εξαίρεσης μπορεί να περιέχει δεδομένα.
        logger.warning(
            "Αποτυχία serialization των timeline points για audit (%s)", type(exc).__name__
        )
        answer_text = None
    audit_id = _audit(conn, user.username, person_id, doc_ids, answer_text=answer_text)
    return TimelineResponse(result=result, audit_id=audit_id)
