"""
ΠΡΟΣΩΡΙΝΟ/generic schema εξαγωγής στοιχείων από εκθέσεις αξιολόγησης.
Το επίσημο template θα δοθεί αργότερα και θα αντικαταστήσει αυτό το αρχείο.
Το extraction pipeline πρέπει να διαβάζει τα πεδία δυναμικά μέσω
`EvaluationReport.model_fields`, όχι με hardcoded αναφορές σε ονόματα πεδίων.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SectionScore(BaseModel):
    section: str = Field(
        description="Τομέας αξιολόγησης, π.χ. 'Στοχοθεσία', 'Ηγετική Ικανότητα'"
    )
    score: int = Field(ge=1, le=5, description="Βαθμολογία τομέα, κλίμακα 1-5")
    comment: Optional[str] = Field(
        default=None, description="Σχόλιο αξιολογητή για τον συγκεκριμένο τομέα"
    )


class EvaluationReport(BaseModel):
    person_name: str = Field(description="Ονοματεπώνυμο αξιολογούμενου")
    person_id: Optional[str] = Field(
        default=None, description="Μοναδικό αναγνωριστικό αξιολογούμενου"
    )
    period: str = Field(description="Περίοδος αξιολόγησης, π.χ. '2025'")
    gnmatefsi: Literal["A", "B"] = Field(description="Γνωμάτευση Α ή Β")
    sections: list[SectionScore] = Field(
        default_factory=list, description="Βαθμολογίες ανά τομέα αξιολόγησης"
    )
    overall_comment: Optional[str] = Field(
        default=None, description="Συνολικό σχόλιο αξιολογητή"
    )
