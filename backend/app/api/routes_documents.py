"""Document file endpoint: GET /person/{person_id}/documents/{doc_id}/file?period=...

Σερβίρει το PDF ενός εγγράφου μόνο όταν doc_id, person_id και period
αντιστοιχούν σε γραμμή του documents (φίλτρο μέσα στο SQL). Το path βγαίνει
μόνο από τη ΒΔ και πρέπει να βρίσκεται μέσα στο DOCS_ROOT· τα doc_id και
person_id του URL δεν φτάνουν ποτέ στο filesystem. Το περιεχόμενο πρέπει να
έχει sha256 που αντιστοιχεί στο doc_id (ίδιος κανόνας με το
app.ingestion.pipeline.compute_doc_id).

Κάθε άρνηση δίνει το ίδιο 404 με το ίδιο body (όχι 403), ώστε η απάντηση να
μη μαρτυρά αν ένα έγγραφο υπάρχει. Ο πραγματικός λόγος γράφεται μόνο στο
audit (refusal_reason). Ακριβώς μία γραμμή audit ανά κλήση, και στις
αποτυχίες· τα bytes επιστρέφονται μόνο αφού γίνει commit το audit."""

import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import get_db
from app.auth.deps import SessionUser, require_user
from app.core.audit import AuditEntry, write_audit
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.retrieval.models import RetrievalMode

router = APIRouter()
logger = logging.getLogger(__name__)

NOT_FOUND_DETAIL = "Δεν βρέθηκε το έγγραφο."

# Ενδείξεις αλλοίωσης ή κακής ρύθμισης, όχι κανονικές αποτυχίες: επιπλέον
# WARNING στο log, μόνο με τον κωδικό. Το not_found (λάθος αίτημα) δεν
# γράφεται στο log.
WARN_REASONS = ("outside_root", "hash_mismatch", "file_missing", "unreadable")


class DocumentRefusal(NotFoundError):
    """Άρνηση σερβιρίσματος. Το μήνυμα είναι πάντα το ίδιο· ο λόγος μένει
    στο `reason` για το audit."""

    def __init__(self, reason: str) -> None:
        super().__init__(NOT_FOUND_DETAIL)
        self.reason = reason


def _audit(
    conn: sqlite3.Connection,
    user: str,
    person_id: str,
    doc_id: str,
    period: str,
    doc_ids: list[str],
    refusal_reason: str | None = None,
) -> int:
    query = {"endpoint": "document_file", "person_id": person_id, "doc_id": doc_id, "period": period}
    audit_id = write_audit(
        conn,
        AuditEntry(
            user=user,
            query=json.dumps(query, ensure_ascii=False),
            retrieved_doc_ids=doc_ids,
            mode=RetrievalMode.STRUCTURED,
            refusal_reason=refusal_reason,
            person_id=person_id,
            period=period,
        ),
    )
    conn.commit()
    return audit_id


def _audit_error_path(*args, **kwargs) -> None:
    """Audit στο error path. Αν αποτύχει και αυτό, γίνεται log (μόνο ο τύπος)
    και ο caller κάνει re-raise το αρχικό σφάλμα: δεν επιστρέφονται δεδομένα."""
    try:
        _audit(*args, **kwargs)
    except Exception as exc:
        logger.error("Αποτυχία εγγραφής audit σε error path (%s)", type(exc).__name__)


def _read_document(
    conn: sqlite3.Connection, settings: Settings, person_id: str, doc_id: str, period: str
) -> bytes:
    if settings.DOCS_ROOT is None:
        raise DocumentRefusal("docs_disabled")
    row = conn.execute(
        "SELECT path FROM documents WHERE doc_id = ? AND person_id = ? AND period = ?",
        (doc_id, person_id, period),
    ).fetchone()
    if row is None:
        raise DocumentRefusal("not_found")

    root = settings.DOCS_ROOT.resolve()
    candidate = Path(row["path"])
    if not candidate.is_absolute():
        candidate = root / candidate
    # resolve() ακολουθεί και τα symlinks: ένα symlink μέσα στο root που
    # δείχνει έξω απορρίπτεται εδώ, όπως και ένα "../" στο path της ΒΔ.
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise DocumentRefusal("outside_root")
    if not resolved.is_file():
        raise DocumentRefusal("file_missing")
    if resolved.suffix.lower() != ".pdf":
        raise DocumentRefusal("not_pdf")

    # Μέγεθος με stat ΠΡΙΝ το read, και όριο και στο ίδιο το read (το αρχείο
    # μπορεί να μεγάλωσε στο μεταξύ).
    try:
        if resolved.stat().st_size > settings.MAX_DOC_BYTES:
            raise DocumentRefusal("too_large")
        with resolved.open("rb") as f:
            content = f.read(settings.MAX_DOC_BYTES + 1)
    except OSError as exc:
        raise DocumentRefusal("unreadable") from exc
    if len(content) > settings.MAX_DOC_BYTES:
        raise DocumentRefusal("too_large")

    if hashlib.sha256(content).hexdigest()[:16] != doc_id:
        raise DocumentRefusal("hash_mismatch")
    return content


@router.get("/person/{person_id}/documents/{doc_id}/file")
def document_file(
    person_id: str,
    doc_id: str,
    period: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: SessionUser = Depends(require_user),
) -> Response:
    try:
        content = _read_document(conn, settings, person_id, doc_id, period)
    except DocumentRefusal as exc:
        if exc.reason in WARN_REASONS:
            logger.warning("Άρνηση σερβιρίσματος εγγράφου (%s)", exc.reason)
        _audit_error_path(conn, user.username, person_id, doc_id, period, [], exc.reason)
        raise
    except Exception:
        _audit_error_path(conn, user.username, person_id, doc_id, period, [])
        raise

    _audit(conn, user.username, person_id, doc_id, period, [doc_id])
    # Το doc_id εδώ έχει ήδη ταιριάξει με το hash (16 hex), άρα είναι ασφαλές
    # στο header. Όχι το αρχικό όνομα αρχείου: μπορεί να περιέχει όνομα ατόμου.
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{doc_id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
