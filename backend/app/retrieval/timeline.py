"""Χρονογραμμή βαθμολογίας ενός προσώπου — ντετερμινιστικό SQL, καμία κλήση
σε LLM.

Ένα point ανά γραμμή του `evaluations`, ταξινομημένο κατά period_start. Το
score είναι το `evaluations.score` αυτούσιο (ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΣΤΟΝ ΚΑΤΕΧΟΜΕΝΟ
ΒΑΘΜΟ), όχι μέσος όρος και όχι COALESCE από field_scores. Οι Σ.Α. περίοδοι
δεν έχουν αριθμητική βαθμολογία και επιστρέφονται με score=None — καμία
interpolation, κανένα fill από γειτονικό point.

Το φίλτρο person_id μπαίνει πάντα parameterized μέσα στο SQL (server-side
isolation), ποτέ ως αφιλτράριστο query param.
"""

import sqlite3
from typing import Literal

from pydantic import BaseModel

from app.models.evaluation import KNOWN_SECTIONS

_EVALUATION_SECTION = KNOWN_SECTIONS[-1]  # "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ"


class TimelinePoint(BaseModel):
    period: str
    period_start: str
    # Το ea_type αυτούσιο, όπως είναι αποθηκευμένο (βλ. EvaluationEntry.ea_type).
    kind: Literal["Ε.Α.", "Σ.Α."]
    score: int | None
    doc_id: str
    page: int | None  # evaluations.source_page
    section: str


class TimelineResult(BaseModel):
    person_id: str
    points: list[TimelinePoint]
    retrieved_doc_ids: list[str]


def _doc_id_by_period(conn: sqlite3.Connection, person_id: str) -> dict[str, str]:
    """Αντιστοίχιση period -> doc_id για το πρόσωπο. Ακριβώς ένα έγγραφο ανά
    (person_id, period): δύο ή περισσότερα σημαίνουν διφορούμενη πηγή για το
    point και είναι σφάλμα — ποτέ σιωπηλό LIMIT 1."""
    rows = conn.execute(
        "SELECT period, doc_id FROM documents WHERE person_id = ? ORDER BY period, doc_id",
        (person_id,),
    ).fetchall()
    mapping: dict[str, str] = {}
    for row in rows:
        if row["period"] in mapping:
            raise ValueError(
                f"Περισσότερα από ένα έγγραφα για person_id={person_id!r} "
                f"period={row['period']!r}: {mapping[row['period']]!r}, {row['doc_id']!r}"
            )
        mapping[row["period"]] = row["doc_id"]
    return mapping


def get_timeline(conn: sqlite3.Connection, person_id: str) -> TimelineResult:
    rows = conn.execute(
        """
        SELECT period, period_start, ea_type, score, source_page
        FROM evaluations
        WHERE person_id = ?
        ORDER BY period_start, id
        """,
        (person_id,),
    ).fetchall()
    doc_by_period = _doc_id_by_period(conn, person_id)

    points: list[TimelinePoint] = []
    for row in rows:
        doc_id = doc_by_period.get(row["period"])
        if doc_id is None:
            raise ValueError(
                f"Κανένα έγγραφο για person_id={person_id!r} period={row['period']!r}"
            )
        points.append(
            TimelinePoint(
                period=row["period"],
                period_start=row["period_start"],
                kind=row["ea_type"],
                score=row["score"],
                doc_id=doc_id,
                page=row["source_page"],
                section=_EVALUATION_SECTION,
            )
        )

    # Μοναδικά doc_ids με σειρά πρώτης εμφάνισης — αυτά γράφονται στο audit_log.
    retrieved_doc_ids = list(dict.fromkeys(p.doc_id for p in points))
    return TimelineResult(person_id=person_id, points=points, retrieved_doc_ids=retrieved_doc_ids)
