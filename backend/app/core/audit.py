"""Audit trail: κάθε query (structured ή semantic) γράφεται στον πίνακα
audit_log, μαζί με τα doc_ids που ανακτήθηκαν εντός του isolation scope και
την έκδοση του prompt που χρησιμοποιήθηκε (όπου εφαρμόζεται)."""

import json
import sqlite3

from pydantic import BaseModel


class AuditEntry(BaseModel):
    ts: str | None = None  # None -> αφήνει το SQLite DEFAULT (datetime('now'))
    user: str
    query: str
    retrieved_doc_ids: list[str]
    mode: str
    prompt_version: str | None = None


def write_audit(conn: sqlite3.Connection, entry: AuditEntry) -> int:
    """Επιστρέφει το autoincrement id (audit_id) της γραμμής που γράφτηκε."""
    cursor = conn.execute(
        """
        INSERT INTO audit_log (user, query, retrieved_doc_ids, mode, prompt_version)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            entry.user,
            entry.query,
            json.dumps(entry.retrieved_doc_ids),
            entry.mode,
            entry.prompt_version,
        ),
    )
    return cursor.lastrowid
