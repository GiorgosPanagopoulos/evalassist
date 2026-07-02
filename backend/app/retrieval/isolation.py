"""Server-side isolation boundary.

Καμία query δεν επιτρέπεται να φτάσει σε ChromaDB ή SQLite χωρίς να περάσει
πρώτα από ένα IsolationScope. Ο φραγμός επιβάλλεται εδώ, στον κώδικα — ποτέ
μέσω prompt στο LLM.
"""

from pydantic import BaseModel


class IsolationScope(BaseModel):
    person_id: str
    period: str
    doc_id: str | None = None  # προαιρετική στένωση σε συγκεκριμένο έγγραφο
    # (μελλοντικό document_qa mode — ίδιο pipeline, χωρίς refactor)

    def build_chroma_where(self) -> dict:
        clauses: list[dict] = [
            {"person_id": self.person_id},
            {"period": self.period},
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
