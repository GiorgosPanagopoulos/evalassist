"""Ντετερμινιστικοί έλεγχοι ερωτήματος ΠΡΙΝ το retrieval — μόνο SQLite, κανένα
μοντέλο (ούτε LLM ούτε embeddings).

Τρεις έλεγχοι, με αυτή τη σειρά:

1. `validate_period`: το `request.period` πρέπει να υπάρχει στον πίνακα
   `documents` για το συγκεκριμένο person_id (καλύπτει και το `career`).
   Αλλιώς `InvalidPeriodError` -> 422. Είναι λάθος αιτήματος, όχι ερώτημα:
   το UI επιλέγει περίοδο από dropdown. Χωρίς αυτόν τον έλεγχο, μια ανύπαρκτη
   περίοδος περνούσε από το `$or` του `IsolationScope.build_chroma_where()`,
   ανακτούσε career chunks και το LLM απαντούσε.
2. `check_field_codes`: κωδικός πεδίου εκτός schema -> FIELD_OUT_OF_SCHEMA.
   Schema = κλειδιά του FIELD_CODE_LABELS ∪ DISTINCT field_code της βάσης.
3. `check_years`: έτος στο ερώτημα εκτός όλων των περιόδων αξιολόγησης του
   ατόμου -> YEAR_OUT_OF_RANGE, ή εκτός της επιλεγμένης περιόδου ->
   YEAR_OTHER_PERIOD (με τις περιόδους που το περιέχουν). Με επιλεγμένη
   περίοδο `career` γίνεται μόνο ο πρώτος έλεγχος.

Ο κωδικός πεδίου ελέγχεται πριν το έτος ώστε τα ψηφία του να αφαιρούνται από
την αναζήτηση ετών ("πεδίο 2003" είναι πεδίο, όχι έτος).

Κάθε κείμενο άρνησης ξεκινά με σταθερή πρόταση (εντοπίσιμη με LIKE στο
audit_log.answer_text) και λέει ρητά γιατί και πού να πάει ο χρήστης. Αυτό το
ξεχωρίζει από το σιωπηλό "δεν βρέθηκε" του B-09.

ΤΙ ΧΑΝΕΙ (γνωστοί περιορισμοί, σκόπιμα):
- Η ανίχνευση κωδικού πεδίου και έτους είναι regex. Δεκτό γιατί τα έτη και οι
  κωδικοί έχουν κλειστή μορφή που δεν αλλάζει με την παράφραση.
- Πεδία ζητούμενα με όνομα ("ικανότητα κολύμβησης") δεν ελέγχονται: η βάση
  δεν μπορεί να πει ότι ένα ελεύθερο όνομα δεν αντιστοιχεί σε κανένα πεδίο.
- Κωδικός χωρίς πρόθεμα ("τι πήρε στο 85;") δεν αναγνωρίζεται, θα συγχεόταν
  με βαθμολογία. Ελέγχεται μόνο ο πρώτος κωδικός του ερωτήματος.
- Έγκυρος κωδικός που λείπει από την επιλεγμένη περίοδο ΔΕΝ απορρίπτεται:
  μόνο λίγες περίοδοι έχουν γραμμές field_scores (κενό του extractor, Β6),
  άρα μια τέτοια άρνηση θα ξανάστηνε το B-09 σε κώδικα.
- Σχετικές και διψήφιες αναφορές χρόνου ("πέρσι", "στην πρώτη του έκθεση",
  "το '18") περνούν χωρίς έλεγχο.
- Πτυχία και τοποθετήσεις δεν έχουν πίνακα με ημερομηνίες στο SQLite. Έτος
  εκτός των περιόδων αξιολόγησης απορρίπτεται ως YEAR_OUT_OF_RANGE ακόμη κι
  αν το ερώτημα αφορά πτυχίο ή τοποθέτηση εκείνου του έτους ("Τι πτυχίο
  απέκτησε το 2003;"). Ψευδής άρνηση, αποδεκτή: το κείμενο δείχνει την
  παράκαμψη (διατύπωση χωρίς έτος). Κλειδωμένο με test ώστε μια αλλαγή να
  φανεί, όχι να συμβεί σιωπηλά.
- Σύγκριση δύο περιόδων σε semantic mode απορρίπτεται ως YEAR_OTHER_PERIOD
  και ανακατευθύνεται στη δομημένη αναζήτηση.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.core.exceptions import InvalidPeriodError
from app.models.evaluation import CAREER_PERIOD, FIELD_CODE_LABELS
from app.retrieval.isolation import IsolationScope

# Τιμή του SemanticResult.model όταν η απάντηση είναι άρνηση του precheck:
# δεν κλήθηκε κανένα LLM.
PRECHECK_MODEL = "precheck"

PERIOD_INVALID_TEXT = "Η περίοδος «{period}» δεν υπάρχει στον φάκελο {person_id}."
YEAR_OUT_OF_RANGE_TEXT = (
    "Δεν υπάρχει περίοδος αξιολόγησης για το {year}. "
    "Ο φάκελος καλύπτει {first} έως {last}. "
    "Αν το ερώτημα αφορά πτυχία ή τοποθετήσεις, διατυπώστε το χωρίς έτος."
)
YEAR_OTHER_PERIOD_TEXT = (
    "Το {year} δεν ανήκει στην επιλεγμένη περίοδο {period}. "
    "Περίοδοι που το περιέχουν: {periods}. "
    "Για σύγκριση περιόδων ή για τον πίνακα προαγωγών χρησιμοποιήστε τη "
    "δομημένη αναζήτηση."
)
FIELD_OUT_OF_SCHEMA_TEXT = (
    "Το πεδίο {code} δεν υπάρχει στο έντυπο αξιολόγησης. Υπάρχοντα πεδία: {codes}."
)

# Μετά το _normalize (χωρίς τόνους, πεζά). Πρόθεμα υποχρεωτικό. Ο κωδικός
# δέχεται έως 4 ψηφία ώστε το "πεδίο 2003" να πιαστεί ως πεδίο και όχι ως έτος·
# το (?!\w) αποκλείει μερικό ταίριασμα μέσα σε μεγαλύτερο αριθμό ή λέξη.
_FIELD_CODE_RE = re.compile(
    r"(?:πεδι(?:ο|ου|α|ων)|κωδικ\w*)\s*(\d{1,4})(?:\s?([αβγab]))?(?!\w)"
)
_LATIN_SUFFIX = str.maketrans({"a": "α", "b": "β"})
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


class RefusalReason(StrEnum):
    YEAR_OUT_OF_RANGE = "year_out_of_range"
    YEAR_OTHER_PERIOD = "year_other_period"
    FIELD_OUT_OF_SCHEMA = "field_out_of_schema"


@dataclass(frozen=True)
class PrecheckRefusal:
    reason: RefusalReason
    text: str


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.lower()


def validate_period(conn: sqlite3.Connection, person_id: str, period: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM documents WHERE person_id = ? AND period = ? LIMIT 1",
        (person_id, period),
    ).fetchone()
    if row is None:
        raise InvalidPeriodError(PERIOD_INVALID_TEXT.format(period=period, person_id=person_id))


def _code_sort_key(code: str) -> tuple[int, str]:
    digits = "".join(ch for ch in code if ch.isdigit())
    return int(digits), code[len(digits):]


def _schema_field_codes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT DISTINCT field_code FROM field_scores").fetchall()
    return set(FIELD_CODE_LABELS) | {row[0] for row in rows}


def check_field_codes(conn: sqlite3.Connection, normalized: str) -> PrecheckRefusal | None:
    match = _FIELD_CODE_RE.search(normalized)
    if match is None:
        return None
    code = match.group(1) + (match.group(2) or "").translate(_LATIN_SUFFIX)
    schema = _schema_field_codes(conn)
    if code in schema:
        return None
    return PrecheckRefusal(
        reason=RefusalReason.FIELD_OUT_OF_SCHEMA,
        text=FIELD_OUT_OF_SCHEMA_TEXT.format(
            code=code, codes=", ".join(sorted(schema, key=_code_sort_key))
        ),
    )


def _years_of(start: str, end: str) -> set[int]:
    return set(range(date.fromisoformat(start).year, date.fromisoformat(end).year + 1))


def check_years(
    conn: sqlite3.Connection, scope: IsolationScope, normalized: str
) -> PrecheckRefusal | None:
    years = sorted({int(y) for y in _YEAR_RE.findall(_FIELD_CODE_RE.sub(" ", normalized))})
    if not years:
        return None
    periods = conn.execute(
        "SELECT period, period_start, period_end FROM evaluations "
        "WHERE person_id = ? ORDER BY period_start",
        (scope.person_id,),
    ).fetchall()
    if not periods:
        return None

    years_by_period = {
        row["period"]: _years_of(row["period_start"], row["period_end"]) for row in periods
    }
    covered = set().union(*years_by_period.values())
    for year in years:
        if year not in covered:
            return PrecheckRefusal(
                reason=RefusalReason.YEAR_OUT_OF_RANGE,
                text=YEAR_OUT_OF_RANGE_TEXT.format(
                    year=year, first=periods[0]["period_start"], last=periods[-1]["period_end"]
                ),
            )

    selected = years_by_period.get(scope.period)
    if scope.period == CAREER_PERIOD or selected is None:
        return None
    for year in years:
        if year not in selected:
            containing = [p for p, ys in years_by_period.items() if year in ys]
            return PrecheckRefusal(
                reason=RefusalReason.YEAR_OTHER_PERIOD,
                text=YEAR_OTHER_PERIOD_TEXT.format(
                    year=year, period=scope.period, periods=", ".join(containing)
                ),
            )
    return None


def check_question(
    conn: sqlite3.Connection, scope: IsolationScope, question: str
) -> PrecheckRefusal | None:
    """Πεδίο πριν από έτος (βλ. docstring του module). None -> περνά στο retrieval."""
    normalized = _normalize(question)
    return check_field_codes(conn, normalized) or check_years(conn, scope, normalized)
