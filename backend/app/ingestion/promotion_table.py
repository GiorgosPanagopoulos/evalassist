"""Επισήμανση των στηλών του πίνακα της Ενότητας 1 («ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ») ώστε
το LLM να μην αποδίδει σιωπηλά την ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ ως ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ - η
διαφορά είναι αρχαιότητα, και το σφάλμα δεν είναι ορατό στον αξιολογητή γιατί
το citation είναι σωστό (live audit #123, #125).

Στο PDF πρόκειται για πίνακα 4 στηλών (ΒΑΘΜΟΣ, ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ, ΑΠΟΦΑΣΗ,
ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ) που το extraction ισοπεδώνει σε γυμνές γραμμές χωρίς καμία
ένδειξη στήλης - μία γραμμή ανά κελί, κενή γραμμή ανάμεσα σε κάθε σειρά.

Γεωμετρική επιβεβαίωση (PyMuPDF word-level dump, σελ.1, delta x0=0.00 σε όλες
τις γραμμές): τα wrapped tokens ("2020", "2014") βρίσκονται στο x0 της στήλης
ΑΠΟΦΑΣΗ, όχι της ΠΡΟΑΓΩΓΗΣ - καμία γραμμή συνέχειας δεν έχει token στη στήλη
ΒΑΘΜΟΣ. Άρα ο κανόνας είναι καθαρά κειμενικός πάνω στο chunk text, καμία
γεωμετρία δεν χρειάζεται στην υλοποίηση.

Καθαρό module: μόνο re + logging, καμία εξάρτηση από chunker/extractor.
"""

import logging

logger = logging.getLogger(__name__)

_HEADER_LABELS = ("ΒΑΘΜΟΣ", "ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ", "ΑΠΟΦΑΣΗ", "ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ")

# Idempotency: μια ήδη επισημασμένη ομάδα ξεκινάει πάντα με αυτό το prefix -
# βλ. _format_row.
_IDEMPOTENCY_PREFIX = f"{_HEADER_LABELS[0]}: "


def annotate_promotion_table(text: str) -> str:
    """Μετατρέπει κάθε σειρά του πίνακα ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ σε μία ρητά
    labeled γραμμή («ΒΑΘΜΟΣ: X | ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ: Y | ΑΠΟΦΑΣΗ: Z |
    ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ: W»), ώστε να μη χρειάζεται θεσιακό συμπερασμό το LLM
    για να ξεχωρίσει ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ από ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ.

    Βρίσκει τις τέσσερις διαδοχικές γραμμές επικεφαλίδας (ΒΑΘΜΟΣ,
    ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ, ΑΠΟΦΑΣΗ, ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ) - αν δεν βρεθούν, το text
    επιστρέφεται αμετάβλητο, καμία εικασία. Το κείμενο πριν και μαζί με τη
    γραμμή επικεφαλίδας μένει byte-identical, οι επικεφαλίδες δεν
    αφαιρούνται.

    Το υπόλοιπο χωρίζεται σε ομάδες με βάση τις κενές γραμμές. Ομάδα με
    λιγότερες από 4 μη κενές γραμμές (άγνωστη δομή) ή που ήδη περιέχει το
    "ΒΑΘΜΟΣ: " (idempotency) μένει αμετάβλητη. Σε κάθε έγκυρη ομάδα, η πρώτη
    γραμμή γίνεται ΒΑΘΜΟΣ, η δεύτερη ΗΜ/ΝΙΑ ΑΠΟΦΑΣΗΣ, η τελευταία
    ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ και όλες οι ενδιάμεσες ΑΠΟΦΑΣΗ (ενωμένες με κενό, εκτός
    αν η προηγούμενη τελειώνει σε "-", οπότε ενώνονται χωρίς κενό:
    "2019-" + "2020" -> "2019-2020").

    Σε οποιοδήποτε σφάλμα επιστρέφεται το text αυτούσιο - καταγράφεται πάντα,
    καμία σιωπηλή αποτυχία σε σύστημα με audit trail."""
    try:
        return _annotate(text)
    except Exception:
        logger.warning(
            "annotate_promotion_table: αποτυχία επεξεργασίας, επιστροφή text αυτούσιο",
            exc_info=True,
        )
        return text


def _find_header_end(lines: list[str]) -> int | None:
    """Επιστρέφει τον δείκτη της τελευταίας γραμμής επικεφαλίδας
    (ΗΜ/ΝΙΑ ΠΡΟΑΓΩΓΗΣ), ή None αν δεν βρεθούν οι τέσσερις διαδοχικές γραμμές
    ακριβώς (μετά από strip)."""
    n = len(_HEADER_LABELS)
    for i in range(len(lines) - n + 1):
        if tuple(lines[i + j].strip() for j in range(n)) == _HEADER_LABELS:
            return i + n - 1
    return None


def _merge_decision_lines(decision_lines: list[str]) -> str:
    merged = decision_lines[0].strip()
    for line in decision_lines[1:]:
        line = line.strip()
        merged = merged + line if merged.endswith("-") else merged + " " + line
    return merged


def _format_row(rank: str, decision_date: str, decision: str, promotion_date: str) -> str:
    return (
        f"{_HEADER_LABELS[0]}: {rank} | "
        f"{_HEADER_LABELS[1]}: {decision_date} | "
        f"{_HEADER_LABELS[2]}: {decision} | "
        f"{_HEADER_LABELS[3]}: {promotion_date}"
    )


def _parse_group(group: list[str]) -> dict | None:
    """Single source of truth για το τι είναι μία «έγκυρη» ομάδα γραμμών του
    πίνακα ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ: την καλούν και το annotate_promotion_table (μέσω
    _annotate) και το parse_promotion_rows (μέσω _parse_rows).

    Επιστρέφει None αν η ομάδα πρέπει να μείνει αμετάβλητη/αγνοηθεί (λιγότερες
    από 4 μη κενές γραμμές - άγνωστη δομή, ή ήδη επισημασμένη - idempotency).
    Αλλιώς επιστρέφει dict με κλειδιά rank/decision_date/decision/promotion_date
    (τιμές πάντα str, αυτούσιες όπως στο PDF)."""
    if len(group) < 4 or any(line.strip().startswith(_IDEMPOTENCY_PREFIX) for line in group):
        return None
    rank = group[0].strip()
    decision_date = group[1].strip()
    promotion_date = group[-1].strip()
    decision = _merge_decision_lines(group[2:-1])
    return {
        "rank": rank,
        "decision_date": decision_date,
        "decision": decision,
        "promotion_date": promotion_date,
    }


def _iter_row_groups(remainder: list[str]):
    """Χωρίζει τις γραμμές μετά την επικεφαλίδα σε ομάδες μη κενών γραμμών
    (μία ομάδα ανά σειρά πίνακα), αγνοώντας τις κενές γραμμές ανάμεσά τους."""
    i = 0
    while i < len(remainder):
        if remainder[i].strip() == "":
            i += 1
            continue
        j = i
        while j < len(remainder) and remainder[j].strip() != "":
            j += 1
        yield remainder[i:j]
        i = j


def _annotate(text: str) -> str:
    lines = text.split("\n")
    header_end = _find_header_end(lines)
    if header_end is None:
        return text

    prefix_lines = lines[: header_end + 1]
    remainder = lines[header_end + 1 :]

    out_lines: list[str] = []
    i = 0
    while i < len(remainder):
        if remainder[i].strip() == "":
            out_lines.append(remainder[i])
            i += 1
            continue

        j = i
        while j < len(remainder) and remainder[j].strip() != "":
            j += 1
        group = remainder[i:j]
        i = j

        parsed = _parse_group(group)
        if parsed is None:
            out_lines.extend(group)
            continue

        out_lines.append(_format_row(**parsed))

    return "\n".join(prefix_lines + out_lines)


def _parse_rows(text: str) -> list[dict]:
    lines = text.split("\n")
    header_end = _find_header_end(lines)
    if header_end is None:
        return []

    remainder = lines[header_end + 1 :]
    rows: list[dict] = []
    for group in _iter_row_groups(remainder):
        parsed = _parse_group(group)
        if parsed is not None:
            rows.append(parsed)
    return rows


def parse_promotion_rows(text: str) -> list[dict]:
    """Δομημένη εξαγωγή των σειρών του πίνακα ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ, χωρίς καμία
    μορφοποίηση - single source of truth για το ίδιο parsing που χρησιμοποιεί
    και η annotate_promotion_table.

    Επιστρέφει λίστα από dicts με κλειδιά rank/decision_date/decision/
    promotion_date, ΤΙΜΕΣ ΠΑΝΤΑ str αυτούσιες όπως στο PDF (καμία
    κανονικοποίηση μορφής ημερομηνίας, καμία μετατροπή σε datetime.date). Δεν
    περιλαμβάνει row_index - το βάζει ο caller. Ίδια validation με την
    annotate_promotion_table: header δεν βρέθηκε -> [], ομάδα με λιγότερες
    από 4 γραμμές -> αγνοείται, ομάδα ήδη επισημασμένη (idempotency prefix)
    -> αγνοείται, ώστε να μην παράγει διπλά αν κληθεί πάνω σε ήδη
    επισημασμένο κείμενο.

    Σε οποιοδήποτε σφάλμα επιστρέφεται κενή λίστα - καταγράφεται πάντα, καμία
    σιωπηλή αποτυχία σε σύστημα με audit trail."""
    try:
        return _parse_rows(text)
    except Exception:
        logger.warning(
            "parse_promotion_rows: αποτυχία επεξεργασίας, επιστροφή κενής λίστας",
            exc_info=True,
        )
        return []
