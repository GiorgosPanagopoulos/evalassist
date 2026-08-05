"""Marker συνέχειας υποενότητας στο ΤΟΠΙΚΟ indexed text (ποτέ στο
SectionChunk.text), για chunks που αρχίζουν μέσα σε υποενότητα μορφής
`α. Τίτλος` .. `ε. Τίτλος` της οποίας ο header βρίσκεται σε προηγούμενο
chunk (π.χ. συνέχεια πάνω από page break). Χωρίς αυτό ο retriever δίνει στο
LLM ορφανές σειρές χωρίς κανένα συμφραζόμενο.

Δύο συναρτήσεις, ίδιο σχήμα με το context_header.py:
- resolve_subsection_carryforward: PURE, δουλεύει σε επίπεδο SectionChunk
  (πριν το split_text_if_long), γιατί ο carry-forward είναι θέμα θέσης μέσα
  στο έγγραφο - ποιος header προηγήθηκε σε ποιο chunk - όχι θέμα
  μεταγενέστερου τεμαχισμού. Το split χρειάζεται το ΑΠΟΤΕΛΕΣΜΑ αυτής της
  συνάρτησης εφαρμοσμένο ανά piece (βλ. pipeline.add_chunk), όχι αντίστροφα.
- annotate_subsection_continuation: prepend του marker σε ένα οποιοδήποτε
  string (chunk ή piece).

Καθαρό module: καμία εξάρτηση από chunker/extractor/pipeline - testable με
plain strings, χωρίς PDF και χωρίς ChromaDB.
"""

import logging
import re

logger = logging.getLogger(__name__)

_MARKER_PREFIX = "[ΣΥΝΕΧΕΙΑ ΥΠΟΕΝΟΤΗΤΑΣ:"

# Τελεία + ΕΝΑ Η ΠΕΡΙΣΣΟΤΕΡΑ κενά (\s+, όχι κενό-σταθερά): το πραγματικό PDF
# γράφει "α.  Τίτλος" με ΔΥΟ κενά (page.get_text spacing), όχι ένα - βλ.
# repr() σε real chunk στο recon. Τα "Ε.Α."/"Σ.Α." (ΚΕΦΑΛΑΙΑ) δεν πιάνονται
# γιατί η κλάση χαρακτήρων [α-ε] είναι αποκλειστικά πεζά ελληνικά.
_HEADER_RE = re.compile(r"^[α-ε]\.\s+\S")

_UNSET = object()


def _first_content_line(text: str) -> str | None:
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _find_headers(text: str) -> list[str]:
    """Όλοι οι subsection headers μέσα στο text, με τη σειρά εμφάνισης,
    ως αυτούσια (stripped) κείμενο της γραμμής - όχι κανονικοποιημένο
    whitespace, ώστε ο marker να ταιριάζει ακριβώς με το πραγματικό PDF
    (π.χ. "γ.  Ανά Κατηγορία Καθήκοντος" με τα δικά του δύο κενά)."""
    headers = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and _HEADER_RE.match(stripped):
            headers.append(stripped)
    return headers


def resolve_subsection_carryforward(
    chunk_texts: list[str], section_keys: list[str | None]
) -> list[str | None]:
    """Ανά chunk (ίδια σειρά/μήκος με chunk_texts), ο τίτλος της υποενότητας
    που "λείπει" από την αρχή του - δηλ. που πρέπει να μπει ως marker - ή
    None αν δεν χρειάζεται.

    PURE: καμία I/O, testable με χειρόγραφα strings. Ο caller περνάει
    section_keys[i] = SectionChunk.section (το top-level section, όχι
    subsection) στην ΙΔΙΑ σειρά εγγράφου (σελίδα, θέση) με chunk_texts[i] -
    βλ. pipeline.py, όπου καλείται πάνω σε career_chunks πριν το
    split_text_if_long.

    Κανόνες:
    - Αλλαγή top-level section (section_keys[i] != section_keys[i-1]) ->
      RESET: καμία υποενότητα "ενεργή" ακόμα σε αυτό το section.
    - Αν η ΠΡΩΤΗ μη-κενή γραμμή του chunk είναι η ίδια subsection header ->
      το chunk δεν χρειάζεται marker (None): ο αναγνώστης βλέπει τον header
      στην κορυφή. ΣΗΜΕΙΩΣΗ: αυτό είναι θεσιακό (η ΠΡΩΤΗ γραμμή), όχι "το
      chunk περιέχει οπουδήποτε έναν header" - πραγματικό chunk (η
      υποενότητα ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ, σελ.3 του perilhptiko2018.pdf)
      αρχίζει με ορφανές γραμμές συνέχειας του `δ. Κατάσταση Υγείας` της
      προηγούμενης σελίδας και ΜΟΝΟ στο τέλος του ίδιου chunk εμφανίζεται ο
      επόμενος header `ε. Ευαρέσκειες` - ένας "περιέχει οπουδήποτε" κανόνας
      θα έχανε λανθασμένα το marker ακριβώς εκεί που χρειάζεται περισσότερο.
    - Αλλιώς, αν υπάρχει ενεργός header από προηγούμενο chunk του ΙΔΙΟΥ
      top-level section -> επιστροφή αυτού.
    - Όποιοι headers βρεθούν μέσα στο chunk (σε οποιαδήποτε θέση) ενημερώνουν
      τον "ενεργό" header (ο τελευταίος που βρέθηκε) για τα ΕΠΟΜΕΝΑ chunks,
      ανεξάρτητα από το αν το ίδιο το chunk πήρε marker."""
    result: list[str | None] = []
    active_header: str | None = None
    active_section: object = _UNSET
    for text, section in zip(chunk_texts, section_keys):
        if section != active_section:
            active_header = None
            active_section = section

        first_line = _first_content_line(text)
        starts_with_header = first_line is not None and _HEADER_RE.match(first_line) is not None
        result.append(None if starts_with_header else active_header)

        headers = _find_headers(text)
        if headers:
            active_header = headers[-1]
    return result


def annotate_subsection_continuation(text: str, subsection_title: str | None) -> str:
    """Prepend του marker `[ΣΥΝΕΧΕΙΑ ΥΠΟΕΝΟΤΗΤΑΣ: <title>]` (ακολουθούμενο
    από κενή γραμμή) στην αρχή του text.

    subsection_title=None: το text επιστρέφεται αμετάβλητο.

    Idempotency: αν το text αρχίζει ήδη με τον marker prefix, επιστρέφεται
    αμετάβλητο - δεν διπλασιάζεται.

    Σε οποιοδήποτε σφάλμα επιστρέφεται το text αυτούσιο - καταγράφεται
    πάντα, καμία σιωπηλή αποτυχία σε σύστημα με audit trail."""
    try:
        return _annotate(text, subsection_title)
    except Exception:
        logger.warning(
            "annotate_subsection_continuation: αποτυχία επεξεργασίας, επιστροφή text αυτούσιο",
            exc_info=True,
        )
        return text


def _annotate(text: str, subsection_title: str | None) -> str:
    if subsection_title is None:
        return text
    if text.startswith(_MARKER_PREFIX):
        return text
    return f"{_MARKER_PREFIX} {subsection_title}]\n\n{text}"
