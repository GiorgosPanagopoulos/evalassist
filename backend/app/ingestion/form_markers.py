"""Μαρκάρισμα κενών υποπεδίων της Ενότητας 5 («ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ ή ΜΗ
ΓΙΑ ΠΡΟΑΓΩΓΗ ΚΑΤ' ΕΚΛΟΓΗΝ») ώστε ένα υποπεδίο χωρίς καμία τιμή στο PDF (α, β,
γ, γ(1), γ(2), γ(3)) να μη διαβαστεί από το LLM ως θετικός ισχυρισμός (π.χ.
οι επικεφαλίδες "Συνήθεις - Πειθαρχικές" / "Για Σοβαρά Παραπτώματα" /
"Πρόσκαιρη Παύση" ερμηνεύτηκαν ως λίστα πραγματικών ποινών). Επαληθεύτηκε
γεωμετρικά (PyMuPDF word-level dump): μηδέν token στη ζώνη y κάθε κενής
υποεπικεφαλίδας.

Το «δ. Κατάσταση Υγείας» δεν αγγίζεται ποτέ (χρησιμοποιείται μόνο ως
boundary anchor) - στο πραγματικό PDF έχει κανονικά τιμές από κάτω.

Καθαρό module: μόνο re + logging, καμία εξάρτηση από chunker/extractor.
"""

import logging
import re

logger = logging.getLogger(__name__)

_MARKER = "ΟΥΔΕΝ ΚΑΤΑΧΩΡΗΜΕΝΟ"

# Canonical labels με ΜΟΝΑ κενά· το πραγματικό PDF έχει μεταβλητό πλήθος
# κενών (π.χ. "α.  Παραπομπές" 2 κενά, "γ.   Ποινές" 3 κενά) - η ανοχή γίνεται
# στο matching (βλ. _tolerant_pattern), όχι εδώ.
_SECTION5_LEAF_LABELS: dict[str, str] = {
    "alpha": "α. Παραπομπές σε συμβούλια - Αποφάσεις συμβουλίων",
    "beta": "β. Δίκες - Αποφάσεις Δικαστηρίων (Πολιτικών - Στρατοδικείων)",
    "one": "(1) Συνήθεις - Πειθαρχικές",
    "two": "(2) Για Σοβαρά Παραπτώματα",
    "three": "(3) Πρόσκαιρη Παύση",
}

# CONTAINER, όχι LEAF: το "γ. Ποινές" δεν έχει δική του τιμή, είναι
# επικεφαλίδα των (1)(2)(3) - η ζώνη ανάμεσα σε αυτό και το "(1)" είναι
# ΠΑΝΤΑ κενή, ακόμα και όταν κάποιο παιδί έχει τιμή. Γι' αυτό μαρκάρεται μόνο
# αν ΚΑΙ τα τρία παιδιά είναι κενά ΚΑΙ η δική του ζώνη είναι κενή (βλ.
# annotate_empty_section5_subfields) - η πρώτη συνθήκη αποτρέπει
# "Ποινές: ΟΥΔΕΝ" δίπλα σε πραγματική ποινή σε παιδί, η δεύτερη δίπλα σε
# τιμή που άλλο PDF layout έγραψε στη ζώνη του ίδιου του "γ.".
_SECTION5_CONTAINER = "γ. Ποινές"
_SECTION5_CONTAINER_CHILDREN = ("one", "two", "three")

# ΜΟΝΟ boundary anchor - οριοθετεί τη ζώνη του "(3)" - ΠΟΤΕ target για
# μαρκάρισμα.
_SECTION5_BOUNDARY_ANCHOR = "δ. Κατάσταση Υγείας"

_ORDER = ["alpha", "beta", "container", "one", "two", "three", "boundary"]


def _label_for(key: str) -> str:
    if key == "container":
        return _SECTION5_CONTAINER
    if key == "boundary":
        return _SECTION5_BOUNDARY_ANCHOR
    return _SECTION5_LEAF_LABELS[key]


_TOLERANT_SPLIT_RE = re.compile(r"(\s*-\s*|\s+)")


def _tolerant_pattern(label: str) -> str:
    """Whitespace/dash-tolerant regex fragment για ένα label: σπάει το label
    σε tokens γύρω από \\s+ και "-", και τα αντικαθιστά με \\s+ και \\s*-\\s*
    αντίστοιχα, με re.escape στα υπόλοιπα literal κομμάτια - ίδια φιλοσοφία
    με το _label_pattern στο extractor.py (το split σε tokens γίνεται ΠΡΙΝ
    το re.escape, όχι replace πάνω στο ήδη escaped string, γιατί το re.escape
    της σύγχρονης Python κάνει escape και το κενό)."""
    parts = []
    for token in _TOLERANT_SPLIT_RE.split(label):
        if not token:
            continue
        if _TOLERANT_SPLIT_RE.fullmatch(token):
            parts.append(r"\s*-\s*" if "-" in token else r"\s+")
        else:
            parts.append(re.escape(token))
    return "".join(parts)


def _line_anchored_regex(label: str) -> re.Pattern:
    """Anchored στην αρχή γραμμής (με ανοχή σε leading κενά/tabs) - όχι
    literal substring search, αλλιώς θα ματσάριζε τυχαία μέσα σε πρόταση."""
    return re.compile(rf"(?m)^[ \t]*{_tolerant_pattern(label)}")


def annotate_empty_section5_subfields(text: str) -> str:
    """Μαρκάρει με _MARKER τα υποπεδία της Ενότητας 5 που είναι όντως κενά
    στο PDF, ώστε το retrieval/LLM να μην τα ερμηνεύσει ως θετικό ισχυρισμό.

    LEAF (α, β, (1), (2), (3)): μαρκάρονται ανεξάρτητα το καθένα, αν η ζώνη
    ανάμεσα στο label τους και το αμέσως επόμενο (γνωστό, βρεθέν στο κείμενο
    κατά _ORDER) label είναι κενή μετά από strip.

    CONTAINER ("γ. Ποινές"): μαρκάρεται ΜΟΝΟ αν ΚΑΙ τα τρία παιδιά (1)(2)(3)
    είναι κενά ΚΑΙ η δική του ζώνη είναι κενή.

    "δ. Κατάσταση Υγείας" χρησιμοποιείται ΜΟΝΟ ως boundary anchor για τη
    ζώνη του "(3)" - ποτέ δεν μαρκάρεται.

    Label που δεν βρέθηκε καθόλου στο text δεν αγγίζεται. Αν δεν βρεθεί
    ΚΑΝΕΝΑ γνωστό label, ή σε οποιοδήποτε σφάλμα, επιστρέφεται το text
    αυτούσιο - βλ. except παρακάτω, καταγράφεται πάντα (καμία σιωπηλή
    αποτυχία σε σύστημα με audit trail)."""
    try:
        return _annotate(text)
    except Exception:
        logger.warning(
            "annotate_empty_section5_subfields: αποτυχία επεξεργασίας, επιστροφή text αυτούσιο",
            exc_info=True,
        )
        return text


def _annotate(text: str) -> str:
    results: list[tuple[str, re.Match]] = []
    for key in _ORDER:
        match = _line_anchored_regex(_label_for(key)).search(text)
        if match is not None:
            results.append((key, match))

    if not results:
        return text

    is_empty: dict[str, bool] = {}
    for i, (key, match) in enumerate(results):
        zone_end = results[i + 1][1].start() if i + 1 < len(results) else len(text)
        is_empty[key] = text[match.end() : zone_end].strip() == ""

    children_all_empty = all(is_empty.get(child, False) for child in _SECTION5_CONTAINER_CHILDREN)

    to_mark: dict[str, int] = {}  # key -> θέση εισαγωγής (match.end())
    for key, match in results:
        if key == "boundary":
            continue
        if key == "container":
            if is_empty.get("container", False) and children_all_empty:
                to_mark[key] = match.end()
            continue
        if is_empty.get(key, False):
            to_mark[key] = match.end()

    # φθίνουσα σειρά θέσης ώστε να μη μετατοπίζονται τα offsets των
    # προηγούμενων (μη ακόμα εφαρμοσμένων) insertions. Ο marker δένεται στην
    # ΙΔΙΑ γραμμή με το label ("ετικέτα: ΟΥΔΕΝ ΚΑΤΑΧΩΡΗΜΕΝΟ") αντί για δική
    # του παράγραφο, ώστε να μη χρειάζεται θεσιακό συμπερασμό (positional
    # inference) το LLM για να συνδέσει το ορφανό marker με το label του.
    for position in sorted(to_mark.values(), reverse=True):
        text = text[:position] + f": {_MARKER}" + text[position:]

    return text
