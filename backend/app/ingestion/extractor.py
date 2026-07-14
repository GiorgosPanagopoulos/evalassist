"""Structured εξαγωγή Περιληπτικού Σημειώματος -> SummaryNote.

Σύμβαση layout (κοινή με τον synthetic PDF generator,
scripts/generate_synthetic_pdfs.py):
  - Κάθε scalar πεδίο εμφανίζεται σε ΜΙΑ γραμμή "Ετικέτα: τιμή".
  - Οι πίνακες (Ενότητες 1-5) είναι μία γραμμή ανά εγγραφή, πεδία
    χωρισμένα με "|", π.χ. "Βαθμός: Χ | Ημ/νία Απόφασης: Υ | ...".
  - Η Ενότητα 7 (ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ) οριοθετεί κάθε
    EvaluationEntry με μία γραμμή "Περίοδος: ΗΗ/ΜΜ/ΕΕΕΕ - ΗΗ/ΜΜ/ΕΕΕΕ" και
    τα αναλυτικά πεδία της με γραμμές "ΠΕΔΙΟ: κωδικός | ΠΕΡΙΓΡΑΦΗ: ... |
    ΒΑΘΜΟΛΟΓΙΑ: ...". Αν το έγγραφο συνεχίζεται σε νέα σελίδα, η
    επικεφαλίδα της ενότητας επαναλαμβάνεται (ο chunker εντοπίζει
    ενότητες ανά σελίδα, βλ. app.ingestion.chunker).

Η εξαγωγή γίνεται σε δύο επίπεδα:
  1. `chunk_by_section` εντοπίζει τα όρια των 7 ενοτήτων μέσα στο κείμενο
     (KNOWN_SECTIONS, single source of truth στο app.models.evaluation).
  2. Ο κώδικας εδώ κάνει label-based regex parsing μέσα σε κάθε ενότητα.

`extract_summary_note` επιστρέφει επίσης το ακατέργαστο κείμενο κάθε
EvaluationEntry (ίδια σειρά/μήκος με `SummaryNote.evaluations`) — το
pipeline το χρησιμοποιεί ως κείμενο chunk για το ChromaDB, ώστε το
semantic retrieval να αναζητά στην πραγματική διατύπωση του εγγράφου.
"""

import re
from datetime import date

from app.ingestion.chunker import SectionChunk
from app.models.evaluation import (
    DegreeEntry,
    EvaluationEntry,
    EvaluatorInfo,
    FIELD_CODE_LABELS,
    FieldScore,
    HealthEntry,
    KNOWN_SECTIONS,
    PersonInfo,
    PostingEntry,
    PromotionEntry,
    ServiceTimeEntry,
    SummaryNote,
)

_EVALUATION_SECTION = KNOWN_SECTIONS[-1]
_PERSON_BLOCK_MARKER = "ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ"

_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_PERIOD_HEADER_RE = re.compile(
    r"^Περίοδος:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})\s*$", re.MULTILINE
)
_CHARACTERIZATION_RE = re.compile(r"^(.+?)\s*\((\d+)\)\s*$")
_FIELD_SCORE_RE = re.compile(
    r"^ΠΕΔΙΟ:\s*(\S+)\s*\|\s*ΠΕΡΙΓΡΑΦΗ:\s*(.*?)\s*\|\s*ΒΑΘΜΟΛΟΓΙΑ:\s*(.+)$", re.MULTILINE
)


# Όριο για πολυγραμμικά πεδία (π.χ. ελεύθερο κείμενο σημειώσεων που έχει
# αναδιπλωθεί σε >1 οπτικές γραμμές μέσα στο PDF λόγω wrap): σταματάει στην
# επόμενη γραμμή που μοιάζει με "Ετικέτα: ..." — όχι μόνο στο τέλος της
# τρέχουσας γραμμής, ώστε να μη χάνεται περιεχόμενο λόγω wrap. Σταματάει
# ΕΠΙΣΗΣ σε κενή γραμμή (παράγραφο boundary): ένα wrap ΔΕΝ έχει κενή γραμμή
# ανάμεσα, οπότε αυτό διακρίνει "συνέχεια της ίδιας τιμής" από "ελεύθερο
# κείμενο που ακολουθεί χωρίς ετικέτα" (π.χ. fallback layout).
_FIELD_STOP_LOOKAHEAD = r"\n[Α-Ωα-ωΆ-Ϋά-ώA-Za-z][^\n:]{0,40}:\s|\n[ \t]*\n"


def _field(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^{re.escape(label)}:\s*(.+?)(?={_FIELD_STOP_LOOKAHEAD}|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    return value or None


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    match = _DATE_RE.match(raw.strip())
    if not match:
        return None
    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def _parse_int(raw: str | None) -> int | None:
    return int(raw) if raw is not None and raw.strip().isdigit() else None


def _iter_pipe_rows(text: str, first_label: str) -> list[dict[str, str]]:
    """Κάθε εγγραφή πίνακα "Ετικέτα: τιμή | Ετικέτα: τιμή | ..." -> dict.

    Οι εγγραφές οριοθετούνται από τη γραμμή που ξεκινάει με `first_label:`
    (το πρώτο πεδίο κάθε γραμμής πίνακα) αντί για literal γραμμή-ανά-εγγραφή:
    ανθεκτικό σε αναδίπλωση (wrap) μιας μακριάς τιμής σε >1 οπτικές γραμμές
    μέσα στο PDF (π.χ. μεγάλη περιγραφή στην Ενότητα 5).
    """
    boundary_re = re.compile(rf"^{re.escape(first_label)}:", re.MULTILINE)
    starts = [m.start() for m in boundary_re.finditer(text)]
    rows: list[dict[str, str]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = " ".join(text[start:end].strip().splitlines())
        row: dict[str, str] = {}
        for segment in block.split("|"):
            if ":" not in segment:
                continue
            label, value = segment.split(":", 1)
            row[label.strip()] = value.strip()
        if row:
            rows.append(row)
    return rows


def _header_block(full_text: str) -> str:
    idx = full_text.find(_PERSON_BLOCK_MARKER)
    return full_text[:idx] if idx != -1 else full_text


def _person_block(full_text: str) -> str:
    start = full_text.find(_PERSON_BLOCK_MARKER)
    if start == -1:
        return ""
    end = len(full_text)
    for name in KNOWN_SECTIONS:
        idx = full_text.find(name, start + len(_PERSON_BLOCK_MARKER))
        if idx != -1:
            end = min(end, idx)
    return full_text[start:end]


def _parse_person(full_text: str) -> PersonInfo:
    header = _header_block(full_text)
    block = _person_block(full_text)
    return PersonInfo(
        agm=_field(header, "Α.Γ.Μ.") or "",
        name=_field(block, "Ονοματεπώνυμο") or "",
        father_name=_field(block, "Όνομα Πατρός"),
        rank=_field(block, "Βαθμός"),
        corps=_field(block, "Όπλο/Σώμα"),
        service=_field(block, "Υπηρεσία"),
        family_status=_field(block, "Οικογενειακή Κατάσταση"),
        age=_parse_int(_field(block, "Ηλικία")),
        special_training=_field(block, "Ειδική Εκπαίδευση"),
    )


def _parse_promotions(text: str) -> list[PromotionEntry]:
    return [
        PromotionEntry(
            rank=row.get("Βαθμός", ""),
            decision_date=_parse_date(row.get("Ημ/νία Απόφασης")),
            decision=row.get("Απόφαση"),
            promotion_date=_parse_date(row.get("Ημ/νία Προαγωγής")),
        )
        for row in _iter_pipe_rows(text, "Βαθμός")
    ]


def _parse_service_time(text: str) -> list[ServiceTimeEntry]:
    return [
        ServiceTimeEntry(
            category=row.get("Κατηγορία", ""),
            years=_parse_int(row.get("Έτη")) or 0,
            months=_parse_int(row.get("Μήνες")) or 0,
            days=_parse_int(row.get("Ημέρες")) or 0,
        )
        for row in _iter_pipe_rows(text, "Κατηγορία")
    ]


def _parse_degrees(text: str) -> list[DegreeEntry]:
    return [
        DegreeEntry(
            degree=row.get("Πτυχίο", ""),
            year=_parse_int(row.get("Έτος")),
            grade=row.get("Βαθμολογία"),
        )
        for row in _iter_pipe_rows(text, "Πτυχίο")
    ]


def _parse_postings(text: str) -> list[PostingEntry]:
    entries = []
    for row in _iter_pipe_rows(text, "Α/Α"):
        k_or_a = row.get("(Κ/Α)")
        entries.append(
            PostingEntry(
                seq=_parse_int(row.get("Α/Α")),
                k_or_a=k_or_a if k_or_a in ("Κ", "Α") else None,
                unit=row.get("Μονάδα", ""),
                date_from=_parse_date(row.get("Από")),
                date_to=_parse_date(row.get("Έως")),
                days=_parse_int(row.get("Ημέρες")),
            )
        )
    return entries


def _parse_health(text: str) -> list[HealthEntry]:
    return [
        HealthEntry(
            category=row.get("Κατηγορία", ""),
            description=row.get("Περιγραφή", ""),
            date=_parse_date(row.get("Ημερομηνία")),
        )
        for row in _iter_pipe_rows(text, "Κατηγορία")
    ]


def _parse_evaluator(raw: str | None) -> EvaluatorInfo | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 3:
        return EvaluatorInfo(rank=parts[0], name=parts[1], role=parts[2])
    if len(parts) == 2:
        return EvaluatorInfo(rank=parts[0], name=parts[1])
    return EvaluatorInfo(name=parts[0]) if parts else None


def _coerce_field_value(raw: str) -> int | str:
    raw = raw.strip()
    if raw in ("ΝΑΙ", "ΟΧΙ"):
        return raw
    digits = re.search(r"\d+", raw)
    return int(digits.group()) if digits else raw


def _parse_field_scores(block: str) -> list[FieldScore]:
    scores = []
    for match in _FIELD_SCORE_RE.finditer(block):
        code, desc, value_raw = match.group(1), match.group(2).strip(), match.group(3)
        scores.append(
            FieldScore(
                field_code=code,
                description=desc or FIELD_CODE_LABELS.get(code),
                value=_coerce_field_value(value_raw),
            )
        )
    return scores


def _split_evaluation_blocks(text: str) -> list[tuple[str, str, str]]:
    """[(period_start_raw, period_end_raw, block_text), ...] μέσα σε ένα
    (ενδεχομένως πολυσέλιδο) κείμενο της Ενότητας 7."""
    matches = list(_PERIOD_HEADER_RE.finditer(text))
    blocks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((match.group(1), match.group(2), text[match.start() : end].strip()))
    return blocks


def _parse_evaluation_entry(
    period_start_raw: str, period_end_raw: str, block: str, page: int
) -> EvaluationEntry:
    char_raw = _field(block, "Χαρακτηρισμός") or ""
    match = _CHARACTERIZATION_RE.match(char_raw)
    characterization = match.group(1).strip() if match else char_raw.strip()
    score = int(match.group(2)) if match else None

    duties_raw = _field(block, "Καθήκοντα") or ""
    duties = [d.strip() for d in duties_raw.split(",") if d.strip()]

    defects_raw = _field(block, "Ελαττώματα")
    defects = None if not defects_raw or defects_raw == "Κανένα" else defects_raw

    return EvaluationEntry(
        period_start=_parse_date(period_start_raw),
        period_end=_parse_date(period_end_raw),
        characterization=characterization,
        score=score,
        ea_type=_field(block, "Τύπος") or "Ε.Α.",
        unit=_field(block, "Μονάδα") or "",
        duties=duties,
        rank_at_time=_field(block, "Βαθμός"),
        evaluator=_parse_evaluator(_field(block, "Αξιολογών")) or EvaluatorInfo(name=""),
        gnomatevon=_parse_evaluator(_field(block, "Γνωματεύων")),
        defects=defects,
        evaluator_notes=_field(block, "Σημειώσεις Αξιολογούντος"),
        gnomatevon_notes=_field(block, "Σημειώσεις Γνωματεύοντος"),
        field_scores=_parse_field_scores(block),
        source_page=page,
    )


def extract_summary_note(
    full_text: str, section_chunks: list[SectionChunk]
) -> tuple[SummaryNote, list[str]]:
    """Επιστρέφει (SummaryNote, raw_evaluation_texts) — το δεύτερο έχει την
    ίδια σειρά/μήκος με `SummaryNote.evaluations`, ένα raw κείμενο ανά entry."""
    by_section: dict[str, list[SectionChunk]] = {}
    for chunk in section_chunks:
        if chunk.section is not None:
            by_section.setdefault(chunk.section, []).append(chunk)

    def joined(section_name: str) -> str:
        return "\n".join(c.text for c in by_section.get(section_name, []))

    evaluations: list[EvaluationEntry] = []
    raw_texts: list[str] = []
    for chunk in by_section.get(_EVALUATION_SECTION, []):
        for period_start_raw, period_end_raw, block in _split_evaluation_blocks(chunk.text):
            evaluations.append(
                _parse_evaluation_entry(period_start_raw, period_end_raw, block, chunk.page)
            )
            raw_texts.append(block)

    summary_note = SummaryNote(
        person=_parse_person(full_text),
        doc_date=_parse_date(_field(_header_block(full_text), "Ημερομηνία")),
        promotions=_parse_promotions(joined(KNOWN_SECTIONS[0])),
        service_time=_parse_service_time(joined(KNOWN_SECTIONS[1])),
        degrees=_parse_degrees(joined(KNOWN_SECTIONS[2])),
        postings=_parse_postings(joined(KNOWN_SECTIONS[3])),
        health_entries=_parse_health(joined(KNOWN_SECTIONS[4])),
        evaluations=evaluations,
    )
    return summary_note, raw_texts
