"""Δομημένη εξαγωγή της Ενότητας 2 («ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ») σε γραμμές
years/months/days, για persistence στον πίνακα service_time (SQLite) - ίδιο
σκεπτικό με το promotion_table.py: δομημένα δεδομένα ανήκουν στο structured
path, όχι μόνο στο ελεύθερο κείμενο που βλέπει το LLM.

ΔΥΟ PARSERS ΓΙΑ ΤΟΝ ΙΔΙΟ ΤΙΤΛΟ ΕΝΟΤΗΤΑΣ - ΕΝ ΓΝΩΣΕΙ ΜΑΣ, ΟΧΙ ΣΦΑΛΜΑ:
Υπάρχει ήδη _parse_service_time στο app.ingestion.extractor (γραμμή ~229),
που διαβάζει ένα pipe-delimited labeled format (μέσω _iter_pipe_rows(text,
"Κατηγορία"), π.χ. "Κατηγορία: X | Έτη: Y | Μήνες: Z | Ημέρες: W") και γεμίζει
το Pydantic SummaryNote.service_time. Αυτό το format δεν εμφανίζεται ποτέ στο
πραγματικό PDF - εξυπηρετεί αποκλειστικά τα synthetic fixtures του
test_ingestion_pipeline.py, όπου το layout είναι ήδη labeled. Στο πραγματικό
έγγραφο, η ενότητα είναι θεσιακή (αριθμός/μονάδα σε διαδοχικές γραμμές, χωρίς
καμία ετικέτα πεδίου) - το _parse_service_time επιστρέφει εκεί πάντα [].

Το module αυτό διαβάζει ΑΚΡΙΒΩΣ αυτό το θεσιακό format και γεμίζει τον πίνακα
service_time στο SQLite (structured path), όχι το SummaryNote. Οι δύο parsers
ΔΕΝ ενοποιούνται εδώ: η ενοποίηση είναι ανοιχτό item για όταν οριστικοποιηθεί
το επίσημο template εξαγωγής, ώστε να ξέρουμε ποιο από τα δύο formats (αν όχι
και τα δύο) πρέπει να υποστηρίζεται μόνιμα.

Καθαρό module: μόνο re-less string handling + logging, καμία εξάρτηση από
chunker/extractor.
"""

import logging

logger = logging.getLogger(__name__)

_SUBSECTION_A_PREFIX = "α."
_SUBSECTION_B_PREFIX = "β."
_SUBSECTION_C_PREFIX = "γ."

_LABEL_A = "ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ"

# Εξαιρείται ρητά: δεν είναι διάρκεια αλλά πεδίο ημερομηνίας (στο συγκεκριμένο
# έγγραφο κενό, 0/0/0) - βλ. ΥΠΟΧΡΕΩΤΙΚΕΣ ΑΠΟΦΑΣΕΙΣ στο prompt.
_EXCLUDED_LABEL = "ΗΜΕΡΟΜΗΝΙΑ ΟΛΟΚΛΗΡΩΣΗΣ ΠΡΟΣΟΝΤΩΝ"

_UNIT_YEARS = "Έτη"
_UNIT_MONTHS = "Μήνες"
_UNIT_DAYS = "Ημέρες"


def _iter_groups(lines: list[str]):
    """Χωρίζει τις γραμμές σε ομάδες μη κενών γραμμών, αγνοώντας τις κενές
    γραμμές ανάμεσά τους (ίδιο μοτίβο με promotion_table._iter_row_groups,
    εδώ πάνω σε ολόκληρο το κείμενο, όχι μόνο μετά από header)."""
    i = 0
    while i < len(lines):
        if lines[i].strip() == "":
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() != "":
            j += 1
        yield lines[i:j]
        i = j


def _parse_values(value_lines: list[str]) -> tuple[int, int, int] | None:
    """value_lines πρέπει να είναι ΑΚΡΙΒΩΣ 6 γραμμές
    αριθμός/Έτη/αριθμός/Μήνες/αριθμός/Ημέρες (σε αυτή τη σειρά). Οτιδήποτε
    άλλο (λιγότερες/περισσότερες γραμμές, μη αριθμητικές τιμές, λάθος σειρά
    μονάδων) επιστρέφει None - η ομάδα αγνοείται σιωπηλά, δεν είναι σφάλμα.

    ΚΑΜΙΑ επικύρωση εύρους στους μήνες/ημέρες: το PDF γράφει πραγματικά '12
    Μήνες' (επιβεβαιωμένο, σελ.2) - οι τιμές αποθηκεύονται αυτούσιες, χωρίς
    άθροιση ή μετατροπή σε συνολικές ημέρες."""
    if len(value_lines) != 6:
        return None
    years, years_unit, months, months_unit, days, days_unit = (v.strip() for v in value_lines)
    if years_unit != _UNIT_YEARS or months_unit != _UNIT_MONTHS or days_unit != _UNIT_DAYS:
        return None
    if not (years.isdigit() and months.isdigit() and days.isdigit()):
        return None
    return int(years), int(months), int(days)


def _parse_rows(text: str) -> list[dict]:
    groups = list(_iter_groups(text.split("\n")))

    idx_a = next(
        (i for i, g in enumerate(groups) if g[0].strip().startswith(_SUBSECTION_A_PREFIX)), None
    )
    if idx_a is None:
        return []

    rows: list[dict] = []

    values = _parse_values(groups[idx_a][1:])
    if values is not None:
        years, months, days = values
        rows.append(
            {"subsection": "α", "label": _LABEL_A, "years": years, "months": months, "days": days}
        )

    idx_b = next(
        (
            i
            for i in range(idx_a + 1, len(groups))
            if groups[i][0].strip().startswith(_SUBSECTION_B_PREFIX)
        ),
        None,
    )
    if idx_b is None:
        return rows

    for group in groups[idx_b + 1 :]:
        label = group[0].strip()
        if label.startswith(_SUBSECTION_C_PREFIX):
            # Η υποενότητα γ ('Ανά Κατηγορία Καθήκοντος') είναι εκτός scope -
            # header χωρίς περιεχόμενο εδώ, σειρές της σε άλλο chunk (σελ.2)
            # με διαφορετική δομή (rank + unit). Σταματάμε εδώ, δεν
            # προσπαθούμε να διαβάσουμε παρακάτω (footer trailer κ.λπ.).
            break
        if label == _EXCLUDED_LABEL:
            continue
        values = _parse_values(group[1:])
        if values is None:
            continue
        years, months, days = values
        rows.append(
            {"subsection": "β", "label": label, "years": years, "months": months, "days": days}
        )

    return rows


def parse_service_time_rows(text: str) -> list[dict]:
    """Δομημένη εξαγωγή των εγγραφών της Ενότητας 2 («ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ
    ΥΠΗΡΕΣΙΑΣ»), θεσιακό parsing (καμία ετικέτα πεδίου στο πραγματικό PDF).

    Επιστρέφει λίστα από dicts με κλειδιά subsection ('α'/'β'), label,
    years/months/days (int, αυτούσιες τιμές όπως στο PDF). Δεν περιλαμβάνει
    row_index - το βάζει ο caller (repository.replace_service_time).

    Η υποενότητα α δίνει το πολύ μία εγγραφή με σταθερό label
    'ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ' (η ημερομηνία αναφοράς 'Έως ...' δεν
    αποθηκεύεται). Η υποενότητα β δίνει μία εγγραφή ανά ετικέτα κατηγορίας,
    εκτός από 'ΗΜΕΡΟΜΗΝΙΑ ΟΛΟΚΛΗΡΩΣΗΣ ΠΡΟΣΟΝΤΩΝ' (πεδίο ημερομηνίας, όχι
    διάρκεια) που εξαιρείται ρητά. Το parsing σταματά στην υποενότητα γ.

    Αν δεν βρεθεί καθόλου header υποενότητας α (π.χ. στο δεύτερο chunk της
    ενότητας, σελ.2, που έχει διαφορετική δομή) επιστρέφεται [].

    Σε οποιοδήποτε σφάλμα επιστρέφεται κενή λίστα - καταγράφεται πάντα, καμία
    σιωπηλή αποτυχία σε σύστημα με audit trail."""
    try:
        return _parse_rows(text)
    except Exception:
        logger.warning(
            "parse_service_time_rows: αποτυχία επεξεργασίας, επιστροφή κενής λίστας",
            exc_info=True,
        )
        return []
