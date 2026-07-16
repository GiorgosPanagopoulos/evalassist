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

import bisect
import re
from datetime import date

from app.ingestion.chunker import SectionChunk
from app.models.evaluation import (
    CHARACTERIZATIONS,
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


_LABEL_SPLIT_RE = re.compile(r"(\s*/\s*|\s+)")


def _label_pattern(label: str) -> str:
    """Whitespace-tolerant regex fragment για ένα label: προαιρετικά κενά γύρω
    από "/" σε σύνθετες ετικέτες (π.χ. "Όπλο/Σώμα" ταιριάζει και με "Όπλο /
    Σώμα" στο πραγματικό PDF), και ανεκτικό σε μεταβλητό πλήθος κενών ανάμεσα
    σε λέξεις (π.χ. "Οικογ. Κατάσταση" ταιριάζει και με πολλαπλά κενά) — το
    \\s* πριν το ':' προστίθεται χωριστά από κάθε caller (βλ. _field,
    _iter_pipe_rows). Σπάει το label σε tokens γύρω από "/" και whitespace
    ΠΡΙΝ το `re.escape` κάθε literal κομμάτι: το `re.escape` στη σύγχρονη
    Python κάνει escape το κενό (σε "\\ "), οπότε ένα naive
    `re.escape(label).replace(" ", r"\\s+")` θα άφηνε ένα ορφανό "\\" πριν
    το "\\s+" — εξ ου και το split σε tokens αντί για replace πάνω στο ήδη
    escaped string."""
    parts = []
    for token in _LABEL_SPLIT_RE.split(label):
        if not token:
            continue
        if _LABEL_SPLIT_RE.fullmatch(token):
            parts.append(r"\s*/\s*" if "/" in token else r"\s+")
        else:
            parts.append(re.escape(token))
    return "".join(parts)


def _field(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^{_label_pattern(label)}\s*:\s*(.+?)(?={_FIELD_STOP_LOOKAHEAD}|\Z)",
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


_LABEL_VALUE_LINE_RE = re.compile(r"^\s*([Α-Ωα-ωΆ-Ϋά-ώA-Za-z][^\n:]{0,60}?)\s*:\s*(.*)$")


def _parse_pipe_row(block_text: str) -> dict[str, str]:
    joined = " ".join(block_text.splitlines())
    row: dict[str, str] = {}
    for segment in joined.split("|"):
        if ":" not in segment:
            continue
        label, value = segment.split(":", 1)
        row[label.strip()] = value.strip()
    return row


def _parse_label_value_lines(block_text: str) -> dict[str, str]:
    """Fallback χωρίς "|": ομαδοποιεί διαδοχικές γραμμές "Ετικέτα: τιμή"
    (whitespace-tolerant, βλ. _label_pattern) σε ένα row."""
    row: dict[str, str] = {}
    for line in block_text.splitlines():
        match = _LABEL_VALUE_LINE_RE.match(line)
        if not match:
            continue
        label, value = match.group(1).strip(), match.group(2).strip()
        if label:
            row[label] = value
    return row


def _iter_pipe_rows(text: str, first_label: str) -> list[dict[str, str]]:
    """Κάθε εγγραφή πίνακα -> dict, σε δύο πιθανές μορφές:
      1. "Ετικέτα: τιμή | Ετικέτα: τιμή | ..." (μία γραμμή ανά εγγραφή).
      2. Χωρίς "|": διαδοχικές γραμμές "Ετικέτα: τιμή" (μία ετικέτα ανά
         γραμμή) μέχρι την επόμενη εγγραφή.

    Και στις δύο περιπτώσεις, οι εγγραφές οριοθετούνται από τη γραμμή που
    ξεκινάει με `first_label:` (το πρώτο πεδίο κάθε εγγραφής) αντί για literal
    γραμμή-ανά-εγγραφή: ανθεκτικό σε αναδίπλωση (wrap) μιας μακριάς τιμής σε
    >1 οπτικές γραμμές μέσα στο PDF (π.χ. μεγάλη περιγραφή στην Ενότητα 5).
    """
    boundary_re = re.compile(rf"^{_label_pattern(first_label)}\s*:", re.MULTILINE)
    starts = [m.start() for m in boundary_re.finditer(text)]
    rows: list[dict[str, str]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block_text = text[start:end].strip()
        row = _parse_pipe_row(block_text) if "|" in block_text else _parse_label_value_lines(block_text)
        if row:
            rows.append(row)
    return rows


def _first_known_section_index(text: str, start: int = 0) -> int:
    indices = [idx for name in KNOWN_SECTIONS if (idx := text.find(name, start)) != -1]
    return min(indices) if indices else -1


def _header_block(full_text: str) -> str:
    idx = full_text.find(_PERSON_BLOCK_MARKER)
    return full_text[:idx] if idx != -1 else full_text


def _person_block(full_text: str) -> str:
    """Το τμήμα κειμένου με τα ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ, δύο μορφές:
      1. Υπάρχει literal marker "ΣΤΟΙΧΕΙΑ ΑΤΟΜΟΥ" (synthetic PDFs, βλ.
         scripts/generate_synthetic_pdfs.py): το block ξεκινάει εκεί και
         τελειώνει στην πρώτη γνωστή ενότητα μετά.
      2. Χωρίς τον marker (πραγματικό PDF — δεν τον περιέχει καθόλου, τα
         PersonInfo πεδία εμφανίζονται ελεύθερα στη σελίδα 1): fallback σε
         ΟΛΟ το κείμενο πριν την πρώτη γνωστή ενότητα, ώστε τα labels να
         αναζητηθούν ανεξαρτήτως ορίου marker (A6)."""
    start = full_text.find(_PERSON_BLOCK_MARKER)
    if start == -1:
        end = _first_known_section_index(full_text)
        return full_text if end == -1 else full_text[:end]
    end = _first_known_section_index(full_text, start + len(_PERSON_BLOCK_MARKER))
    return full_text[start:] if end == -1 else full_text[start:end]


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
        family_status=_field(block, "Οικογενειακή Κατάσταση") or _field(block, "Οικογ. Κατάσταση"),
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


def _split_evaluation_blocks(text: str) -> list[tuple[str, str, str, int]]:
    """[(period_start_raw, period_end_raw, block_text, start_offset), ...]
    μέσα σε ένα (ενδεχομένως πολυσέλιδο) κείμενο της Ενότητας 7 — labeled
    μορφή ("Περίοδος: ..." boundary)."""
    matches = list(_PERIOD_HEADER_RE.finditer(text))
    blocks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(
            (match.group(1), match.group(2), text[match.start() : end].strip(), match.start())
        )
    return blocks


_BARE_ANCHOR_RE = re.compile(r"^(Ε\.Α\.|Σ\.Α\.)\s*$", re.MULTILINE)
_DATE_TOKEN_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_EVALUATOR_LABEL_RE = re.compile(r"^Αξιολογών\s*:\s*(.*)$")

# Font substitution σε πραγματικά PDF: κάποιοι Έλληνικοί χαρακτήρες
# εμφανίζονται ως λατινικά ομόγραφα (π.χ. "EΞΑΙΡΕΤΟΣ" με λατινικό "E").
# Απαραίτητο για να αναγνωριστεί ο χαρακτηρισμός έναντι του CHARACTERIZATIONS.
_LATIN_TO_GREEK_UPPER = str.maketrans(
    {
        "A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ",
        "M": "Μ", "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "Y": "Υ", "X": "Χ",
    }
)


def _split_positional_blocks(text: str) -> list[tuple[str, str, int]]:
    """[(ea_type, block_text, start_offset), ...] — fallback χωρίς labels
    (πραγματικό PDF layout): κάθε bare γραμμή "Ε.Α."/"Σ.Α." (ολόκληρη γραμμή,
    όχι substring — δεν μπερδεύεται με τη legend "α. Χαρακτηρισμός από Ε.Α. /
    Σ.Α. ...") είναι το anchor μιας εγγραφής, τα υπόλοιπα πεδία εξάγονται
    θεσιακά (βλ. _parse_evaluation_entry_positional)."""
    anchors = list(_BARE_ANCHOR_RE.finditer(text))
    blocks = []
    for i, match in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(text)
        blocks.append((match.group(1), text[match.start() : end], match.start()))
    return blocks


def _parse_evaluator_fallback(raw: str | None) -> EvaluatorInfo | None:
    """Real-PDF μορφή αξιολογούντος: "ΒΑΘΜΟΣ   Ονοματεπώνυμο - Ρόλος" (όχι
    comma-separated όπως στη labeled μορφή, βλ. _parse_evaluator)."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if " - " in raw:
        left, role = raw.rsplit(" - ", 1)
        role = role.strip() or None
    else:
        left, role = raw, None
    parts = left.split(None, 1)
    rank, name = (parts[0], parts[1].strip()) if len(parts) == 2 else (None, left.strip())
    return EvaluatorInfo(rank=rank, name=name, role=role) if name else None


def _parse_characterization_token(raw: str | None) -> tuple[str | None, int | None]:
    """Χαρακτηρισμός+βαθμολογία σε μία γραμμή, real-PDF μορφή (π.χ.
    "EΞΑΙΡΕΤΟΣ (100)"). Καλύπτει και bare "ΔΥ" (Σ.Α. περιόδους χωρίς
    αριθμητική βαθμολογία — score παραμένει None) αφού είναι μέλος του
    CHARACTERIZATIONS (single source of truth, βλ. models/evaluation.py).
    Επιστρέφει (None, None) μόνο αν δεν αντιστοιχεί σε κανέναν γνωστό
    χαρακτηρισμό — ο caller παραλείπει τέτοιες (πραγματικά άγνωστες)
    εγγραφές αντί να επινοήσει τιμή εκτός Literal."""
    if not raw:
        return None, None
    match = _CHARACTERIZATION_RE.match(raw.strip())
    text, score = (match.group(1).strip(), int(match.group(2))) if match else (raw.strip(), None)
    normalized = text.translate(_LATIN_TO_GREEK_UPPER)
    return (normalized, score) if normalized in CHARACTERIZATIONS else (None, None)


def _parse_field_scores_positional(block: str) -> list[FieldScore]:
    """Fallback χωρίς "ΠΕΔΙΟ: .. | ΠΕΡΙΓΡΑΦΗ: .. | ΒΑΘΜΟΛΟΓΙΑ: .." labels:
    σαρώνει τις γραμμές του block για bare κωδικούς πεδίου (γνωστοί από
    FIELD_CODE_LABELS, single source of truth) — κάθε match ακολουθείται από
    1+ γραμμές περιγραφής (πιθανό wrap) και μία γραμμή βαθμολογίας (αριθμός ή
    ΝΑΙ/ΟΧΙ)."""
    lines = block.splitlines()
    scores: list[FieldScore] = []
    i, n = 0, len(lines)
    while i < n:
        token = lines[i].strip()
        if token in FIELD_CODE_LABELS:
            code = token
            i += 1
            desc_lines: list[str] = []
            value = None
            while i < n:
                candidate = lines[i].strip()
                i += 1
                if not candidate:
                    continue
                if candidate.isdigit() or candidate in ("ΝΑΙ", "ΟΧΙ"):
                    value = candidate
                    break
                desc_lines.append(candidate)
            if value is not None:
                scores.append(
                    FieldScore(
                        field_code=code,
                        description=" ".join(desc_lines) or FIELD_CODE_LABELS.get(code),
                        value=_coerce_field_value(value),
                    )
                )
        else:
            i += 1
    return scores


def _parse_evaluation_entry_positional(ea_type: str, block: str, page: int) -> EvaluationEntry | None:
    """Θεσιακός (positional) parser για entries χωρίς labels (πραγματικό PDF
    layout, σελ. 4-8 του δείγματος): "Ε.Α./Σ.Α." anchor, μετά ημερομηνία /
    "-" / ημερομηνία, μετά "Χαρακτηρισμός (βαθμός)" σε μία γραμμή (ή bare
    "ΔΥ" χωρίς βαθμό, βλ. _parse_characterization_token), μετά
    μονάδα/καθήκοντα σε ελεύθερες γραμμές, μετά "Αξιολογών:" + η γραμμή με το
    ονοματεπώνυμο. Επιστρέφει None αν δεν αναγνωρίζεται έγκυρη περίοδος ή
    χαρακτηρισμός εκτός CHARACTERIZATIONS — τέτοιες (πραγματικά άγνωστες)
    εγγραφές παραλείπονται αντί να επινοηθεί μη-πραγματική τιμή."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return None
    idx = 1  # lines[0] == το ίδιο το anchor ("Ε.Α."/"Σ.Α.")

    def _take() -> str | None:
        nonlocal idx
        if idx >= len(lines):
            return None
        value = lines[idx]
        idx += 1
        return value

    d1, dash, d2 = _take(), _take(), _take()
    if not (d1 and _DATE_TOKEN_RE.match(d1) and dash == "-" and d2 and _DATE_TOKEN_RE.match(d2)):
        return None

    characterization, score = _parse_characterization_token(_take())
    if characterization is None:
        return None

    rest = lines[idx:]
    evaluator_idx = next((i for i, l in enumerate(rest) if _EVALUATOR_LABEL_RE.match(l)), len(rest))
    unit_lines = [l for l in rest[:evaluator_idx] if l != "-" and not l.isdigit()]
    unit = unit_lines[0] if unit_lines else ""

    evaluator_raw = None
    if evaluator_idx < len(rest):
        inline = _EVALUATOR_LABEL_RE.match(rest[evaluator_idx]).group(1).strip()
        evaluator_raw = inline or (rest[evaluator_idx + 1] if evaluator_idx + 1 < len(rest) else None)
    evaluator = _parse_evaluator_fallback(evaluator_raw) or EvaluatorInfo(name="")

    return EvaluationEntry(
        period_start=_parse_date(d1),
        period_end=_parse_date(d2),
        characterization=characterization,
        score=score,
        ea_type=ea_type,
        unit=unit,
        evaluator=evaluator,
        field_scores=_parse_field_scores_positional(block),
        source_page=page,
    )


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


def _concat_with_offsets(chunks: list[SectionChunk]) -> tuple[str, list[int], list[int]]:
    """Ενώνει τα per-page chunks μιας ενότητας σε ένα κείμενο, κρατώντας
    (starts, pages) ώστε να ανακτάται ποια αρχική σελίδα αντιστοιχεί σε κάθε
    offset — χρειάζεται στο πραγματικό PDF, όπου μια εγγραφή (σημειώσεις,
    field scores) μπορεί να συνεχίζεται πάνω από page break χωρίς να
    επαναλαμβάνεται το section header (βλ. chunker._known_section_chunks)."""
    parts, starts, pages = [], [], []
    pos = 0
    for chunk in chunks:
        starts.append(pos)
        pages.append(chunk.page)
        parts.append(chunk.text)
        pos += len(chunk.text) + 1  # +1: "\n" separator στο join
    return "\n".join(parts), starts, pages


def _page_for_offset(starts: list[int], pages: list[int], offset: int) -> int:
    i = bisect.bisect_right(starts, offset) - 1
    return pages[max(0, min(i, len(pages) - 1))]


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

    eval_text, eval_starts, eval_pages = _concat_with_offsets(by_section.get(_EVALUATION_SECTION, []))

    evaluations: list[EvaluationEntry] = []
    raw_texts: list[str] = []
    labeled_blocks = _split_evaluation_blocks(eval_text)
    if labeled_blocks:
        for period_start_raw, period_end_raw, block, start in labeled_blocks:
            page = _page_for_offset(eval_starts, eval_pages, start)
            evaluations.append(_parse_evaluation_entry(period_start_raw, period_end_raw, block, page))
            raw_texts.append(block)
    else:
        for ea_type, block, start in _split_positional_blocks(eval_text):
            page = _page_for_offset(eval_starts, eval_pages, start)
            entry = _parse_evaluation_entry_positional(ea_type, block, page)
            if entry is not None:
                evaluations.append(entry)
                raw_texts.append(block.strip())

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
