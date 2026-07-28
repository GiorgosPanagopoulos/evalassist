"""Server-side isolation boundary.

Καμία query δεν επιτρέπεται να φτάσει σε ChromaDB ή SQLite χωρίς να περάσει
πρώτα από ένα IsolationScope. Ο φραγμός επιβάλλεται εδώ, στον κώδικα, ποτέ
μέσω prompt στο LLM.
"""

from app.models.evaluation import CAREER_PERIOD
from pydantic import BaseModel


class IsolationScope(BaseModel):
    person_id: str
    period: str
    doc_id: str | None = None  # προαιρετική στένωση σε συγκεκριμένο έγγραφο
    # (μελλοντικό document_qa mode - ίδιο pipeline, χωρίς refactor)

    def build_chroma_where(self) -> dict:
        # person_id είναι ΠΑΝΤΑ hard AND, ποτέ μέσα σε $or: αυτό είναι το
        # πραγματικό isolation. Το period διευρύνεται με career-wide chunks
        # (CAREER_PERIOD) του ΙΔΙΟΥ προσώπου, ώστε ενότητες όπως Τοποθετήσεις/
        # Κρίσεις Προαγωγών να μην αποκλείονται όταν ζητείται συγκεκριμένη
        # περίοδος αξιολόγησης.
        if self.period == CAREER_PERIOD:
            period_clause: dict = {"period": self.period}
        else:
            period_clause = {"$or": [{"period": self.period}, {"period": CAREER_PERIOD}]}

        clauses: list[dict] = [
            {"person_id": self.person_id},
            period_clause,
        ]
        if self.doc_id is not None:
            clauses.append({"doc_id": self.doc_id})
        return {"$and": clauses}

    def build_sql_where(self) -> tuple[str, list]:
        clauses = ["person_id = ?", "period = ?"]
        params: list = [self.person_id, self.period]
        if self.doc_id is not None:
            clauses.append("doc_id = ?")
            params.append(self.doc_id)
        return " AND ".join(clauses), params
