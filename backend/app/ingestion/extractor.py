"""Structured εξαγωγή σε EvaluationReport.

Διαβάζει τα πεδία δυναμικά από `EvaluationReport.model_fields` — δεν υπάρχει
hardcoded αναφορά στα field names μέσα στο loop εξαγωγής. Το μοναδικό
config-driven στοιχείο είναι το προαιρετικό `FIELD_LABEL_HINTS` (labels
αναζήτησης ανά πεδίο)· αν ένα πεδίο δεν έχει entry εκεί, χρησιμοποιείται
αυτόματα το ίδιο το field name ως label, οπότε νέα πεδία στο (προσωρινό)
schema λειτουργούν χωρίς αλλαγή κώδικα εδώ.
"""

import re
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from app.ingestion.chunker import SectionChunk
from app.models.evaluation import EvaluationReport, SectionScore

FIELD_LABEL_HINTS: dict[str, list[str]] = {
    "person_name": ["Ονοματεπώνυμο", "Όνομα"],
    "person_id": ["Αριθμός Μητρώου", "Α.Μ.", "ΑΜ"],
    "period": ["Περίοδος Αξιολόγησης", "Περίοδος"],
    "gnmatefsi": ["Γνωμάτευση"],
    "overall_comment": ["Συνολικό Σχόλιο", "Γενικό Σχόλιο", "Σχόλιο Αξιολογητή"],
}

_GREEK_TO_LATIN = {"Α": "A", "Β": "B"}


def _list_item_model(field_info: FieldInfo) -> type[BaseModel] | None:
    if get_origin(field_info.annotation) is list:
        (inner,) = get_args(field_info.annotation)
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return inner
    return None


def _search_label(text: str, labels: list[str]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:\-]\s*(.+)", text)
        if match:
            value = match.group(1).splitlines()[0].strip()
            if value:
                return value
    return None


def _coerce(raw: str, field_info: FieldInfo) -> Any:
    if get_origin(field_info.annotation) is Literal:
        first_char = raw.strip()[:1].upper()
        return _GREEK_TO_LATIN.get(first_char, first_char)
    if field_info.annotation is int:
        digits = re.search(r"\d+", raw)
        return int(digits.group()) if digits else None
    return raw


def extract_report(full_text: str, section_chunks: list[SectionChunk]) -> EvaluationReport:
    values: dict[str, Any] = {}
    for field_name, field_info in EvaluationReport.model_fields.items():
        item_model = _list_item_model(field_info)
        if item_model is SectionScore:
            values[field_name] = [
                SectionScore(section=c.section, score=c.score, comment=None)
                for c in section_chunks
                if c.section is not None and c.score is not None
            ]
            continue
        labels = FIELD_LABEL_HINTS.get(field_name, [field_name])
        raw = _search_label(full_text, labels)
        if raw is not None:
            values[field_name] = _coerce(raw, field_info)
    return EvaluationReport(**values)
