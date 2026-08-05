"""Προσθήκη ρητού section context marker στο ΤΟΠΙΚΟ indexed text (ποτέ στο
SectionChunk.text), ώστε ο reranker (bge-reranker-v2-m3) και το Krikri να
βλέπουν την ενότητα του chunk μέσα στο ίδιο το `documents` string της
ChromaDB. Σήμερα το section ζει ΜΟΝΟ στο metadata - αόρατο σε οτιδήποτε
διαβάζει μόνο το κείμενο (διάγνωση B2: 41/43 chunks φτάνουν ανώνυμα στο
μοντέλο, παρότι ο chunker κάνει ήδη σωστό carry-forward του section).

Καθαρό module: καμία εξάρτηση από chunker/extractor/pipeline - testable με
plain strings, χωρίς PDF και χωρίς ChromaDB.
"""

import logging

logger = logging.getLogger(__name__)

_MARKER_PREFIX = "[ΕΝΟΤΗΤΑ:"


def add_section_context_header(text: str, section: str | None) -> str:
    """Προθέτει `[ΕΝΟΤΗΤΑ: <canonical>]` (ακολουθούμενο από κενή γραμμή) στην
    αρχή του text, ώστε η ενότητα να γίνει μέρος του embedding space αντί να
    μένει αόρατη εκτός metadata.

    section=None (structural fallback chunk, άγνωστη ενότητα λόγω OCR
    θορύβου ή αγνώστου layout): το text επιστρέφεται αμετάβλητο - δεν
    υπάρχει canonical όνομα να μπει, και δεν πρέπει να επινοηθεί κανένα.

    Idempotency: αν το text αρχίζει ήδη με `[ΕΝΟΤΗΤΑ:` (π.χ. δεύτερο piece
    ενός ήδη split_text_if_long κομματιού, ή re-run πάνω σε ήδη annotated
    text), επιστρέφεται αμετάβλητο - δεν διπλασιάζεται ο marker.

    Σε οποιοδήποτε σφάλμα επιστρέφεται το text αυτούσιο - καταγράφεται
    πάντα, καμία σιωπηλή αποτυχία σε σύστημα με audit trail."""
    try:
        return _annotate(text, section)
    except Exception:
        logger.warning(
            "add_section_context_header: αποτυχία επεξεργασίας, επιστροφή text αυτούσιο",
            exc_info=True,
        )
        return text


def _annotate(text: str, section: str | None) -> str:
    if section is None:
        return text
    if text.startswith(_MARKER_PREFIX):
        return text
    return f"[ΕΝΟΤΗΤΑ: {section}]\n\n{text}"
