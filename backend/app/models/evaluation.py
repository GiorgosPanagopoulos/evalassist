"""Schema Περιληπτικού Σημειώματος.

ΕΝΑ PDF ανά άτομο (κλειδί: Α.Γ.Μ.) συγκεντρώνει ΟΛΗ τη σταδιοδρομία:
πολλαπλές περιόδους αξιολόγησης Ε.Α./Σ.Α. στο ίδιο έγγραφο
("1 PDF = 1 άτομο, N περίοδοι"). Scores 0-100.

Το extraction pipeline (app.ingestion.extractor) και ο chunker
(app.ingestion.chunker) διαβάζουν τα ονόματα ενοτήτων αποκλειστικά από
KNOWN_SECTIONS — single source of truth, όχι hardcoded strings αλλού.
Ομοίως FIELD_CODE_LABELS είναι η single source of truth για τις
περιγραφές των αναλυτικών πεδίων (ΠΕΔΙΟ nnn) της Ενότητας 7, την οποία
χρησιμοποιούν τόσο ο extractor (backfill περιγραφής όταν λείπει από το
PDF) όσο και ο synthetic PDF generator (scripts/generate_synthetic_pdfs.py).
"""

import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

# Οι 7 ενότητες του Περιληπτικού Σημειώματος, με τη σειρά εμφάνισής τους
# στο πραγματικό έγγραφο.
KNOWN_SECTIONS: list[str] = [
    "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ",
    "ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ",
    "ΚΑΤΕΧΟΜΕΝΑ ΠΤΥΧΙΑ",
    "ΤΟΠΟΘΕΤΗΣΕΙΣ",
    "ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ",
    "ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΣΤΟΝ ΚΑΤΕΧΟΜΕΝΟ ΒΑΘΜΟ",
    "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ",
]

CHARACTERIZATIONS: list[str] = ["ΕΞΑΙΡΕΤΟΣ", "ΛΙΑΝ ΚΑΛΟΣ", "ΚΑΛΟΣ", "ΜΕΤΡΙΟΣ", "ΜΗ ΑΠΟΔΕΚΤΟΣ"]

# Περιγραφές των αναλυτικών πεδίων (ΠΕΔΙΟ/ΠΕΡΙΓΡΑΦΗ/ΒΑΘΜΟΛΟΓΙΑ) της
# Ενότητας 7. Οι κωδικοί/περιγραφές είναι ενδεικτικοί — δεν αντιστοιχούν σε
# επίσημη ονοματολογία, μόνο σε πλαύσιμο περιεχόμενο για το synthetic corpus.
FIELD_CODE_LABELS: dict[str, str] = {
    "51": "Επαγγελματική Ικανότητα",
    "62": "Φυσική Κατάσταση",
    "74": "Ηθική Ακεραιότητα",
    "75": "Πειθαρχία",
    "81": "Κρίση",
    "82": "Πρωτοβουλία",
    "83": "Προσαρμοστικότητα",
    "84": "Επικοινωνία",
    "85": "Ηγετική Ικανότητα",
    "86": "Οργανωτική Ικανότητα",
    "87": "Συνεργασία",
    "88": "Υπευθυνότητα",
    "91": "Απόδοση σε Επιχειρήσεις/Ασκήσεις",
    "93": "Τεχνική Κατάρτιση",
    "96": "Διοικητική Ικανότητα",
    "97": "Εκπαιδευτική Ικανότητα",
    "141": "Γενική Ικανότητα στον Κατεχόμενο Βαθμό",
    "142α": "Προτείνεται για Ταχύτερη Προαγωγή",
    "142β": "Προτείνεται για Απόταξη/Παραίτηση",
}


class PersonInfo(BaseModel):
    agm: str = Field(description="Αριθμός Γενικού Μητρώου — μοναδικό αναγνωριστικό, γίνεται person_id")
    name: str = Field(description="Ονοματεπώνυμο")
    father_name: Optional[str] = Field(default=None, description="Όνομα Πατρός")
    rank: Optional[str] = Field(default=None, description="Βαθμός")
    corps: Optional[str] = Field(default=None, description="Όπλο/Σώμα")
    service: Optional[str] = Field(default=None, description="Υπηρεσία")
    family_status: Optional[str] = Field(default=None, description="Οικογενειακή Κατάσταση")
    age: Optional[int] = Field(default=None, description="Ηλικία")
    special_training: Optional[str] = Field(default=None, description="Ειδική Εκπαίδευση")


class PromotionEntry(BaseModel):
    rank: str = Field(description="Βαθμός")
    decision_date: Optional[datetime.date] = Field(default=None, description="Ημ/νία Απόφασης")
    decision: Optional[str] = Field(default=None, description="Απόφαση")
    promotion_date: Optional[datetime.date] = Field(default=None, description="Ημ/νία Προαγωγής")


class ServiceTimeEntry(BaseModel):
    category: str = Field(description="Κατηγορία χρόνου υπηρεσίας")
    years: int = Field(default=0, ge=0)
    months: int = Field(default=0, ge=0)
    days: int = Field(default=0, ge=0)


class DegreeEntry(BaseModel):
    degree: str = Field(description="Πτυχίο")
    year: Optional[int] = Field(default=None, description="Έτος απόκτησης")
    grade: Optional[str] = Field(default=None, description="Βαθμολογία")


class PostingEntry(BaseModel):
    seq: Optional[int] = Field(default=None, description="Α/Α")
    k_or_a: Optional[Literal["Κ", "Α"]] = Field(default=None, description="(Κ)/(Α)")
    unit: str = Field(description="Μονάδα")
    date_from: Optional[datetime.date] = Field(default=None)
    date_to: Optional[datetime.date] = Field(default=None)
    days: Optional[int] = Field(default=None)


class HealthEntry(BaseModel):
    category: str = Field(description="π.χ. Κατάσταση Υγείας, Ευαρέσκεια, Συμβούλιο, Ποινή")
    description: str
    date: Optional[datetime.date] = Field(default=None)


class FieldScore(BaseModel):
    field_code: str = Field(description='π.χ. "141", "142α"')
    description: Optional[str] = Field(default=None)
    value: Union[int, Literal["ΝΑΙ", "ΟΧΙ"]]


class EvaluatorInfo(BaseModel):
    rank: Optional[str] = Field(default=None)
    name: str
    role: Optional[str] = Field(default=None)


class EvaluationEntry(BaseModel):
    period_start: datetime.date
    period_end: datetime.date
    characterization: Literal["ΕΞΑΙΡΕΤΟΣ", "ΛΙΑΝ ΚΑΛΟΣ", "ΚΑΛΟΣ", "ΜΕΤΡΙΟΣ", "ΜΗ ΑΠΟΔΕΚΤΟΣ"]
    score: Optional[int] = Field(default=None, ge=0, le=100)
    ea_type: Literal["Ε.Α.", "Σ.Α."]
    unit: str
    duties: list[str] = Field(default_factory=list)
    rank_at_time: Optional[str] = Field(default=None)
    evaluator: EvaluatorInfo
    gnomatevon: Optional[EvaluatorInfo] = Field(default=None)
    defects: Optional[str] = Field(default=None)
    evaluator_notes: Optional[str] = Field(default=None)
    gnomatevon_notes: Optional[str] = Field(default=None)
    field_scores: list[FieldScore] = Field(default_factory=list)
    source_page: int

    @property
    def period(self) -> str:
        """Σύμβαση period string: 'YYYY-MM-DD..YYYY-MM-DD' (SQLite/Chroma key)."""
        return f"{self.period_start.isoformat()}..{self.period_end.isoformat()}"


class SummaryNote(BaseModel):
    person: PersonInfo
    doc_date: Optional[datetime.date] = Field(
        default=None, description="Ημερομηνία έκδοσης σημειώματος"
    )
    promotions: list[PromotionEntry] = Field(default_factory=list)
    service_time: list[ServiceTimeEntry] = Field(default_factory=list)
    degrees: list[DegreeEntry] = Field(default_factory=list)
    postings: list[PostingEntry] = Field(default_factory=list)
    health_entries: list[HealthEntry] = Field(default_factory=list)
    evaluations: list[EvaluationEntry] = Field(default_factory=list)
