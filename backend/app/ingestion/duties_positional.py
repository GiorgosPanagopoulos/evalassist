"""Γεωμετρική εξαγωγή του πίνακα (ετικέτα, ημέρες) της Ενότητας 7
(ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ), θεσιακό (bare-anchor) layout - ίδιο
σκεπτικό/pattern με app.ingestion.duty_categories: ανεξάρτητο PDF pass με
fitz.open() + get_text("words"), ΠΡΙΝ από οποιαδήποτε ανασύνθεση σε
γραμμές κειμένου. Ο positional path του extractor
(_parse_evaluation_entry_positional) δουλεύει πάνω σε plain text (το
parser.py πετάει τις συντεταγμένες στο πρώτο βήμα, βλ.
private/prompts/IMPL_DUTIES.md ΦΑΣΗ 0) - η γεωμετρία ΔΕΝ φτάνει ποτέ ως
εκεί, οπότε η εξαγωγή των duties γίνεται εδώ, εντελώς ανεξάρτητα, και
προσαρτάται post-hoc στο ingestion pipeline (βλ. pipeline.py).

Οι σταθερές παρακάτω προέρχονται από μέτρηση επί του πραγματικού
private/perilhptiko2018.pdf (36 πραγματικά blocks Ε.Α./Σ.Α., βλ.
private/scripts/_recon_out.txt) - ΜΗΝ τις αλλάξεις χωρίς νέα μέτρηση.

Ιδιοτροπία γραμματοσειράς (επιβεβαιωμένη εμπειρικά, καθοριστική για τη
λογική εδώ): λέξεις με λατινικά ψηφία/χαρακτήρες (ημερομηνίες, αριθμοί
ημερών, μεμονωμένα λατινικά γράμματα όπως το "V" σε κωδικούς μονάδας)
τυπώνονται σε ΔΙΑΦΟΡΕΤΙΚΗ γραμματοσειρά από το ελληνικό κείμενο της ΙΔΙΑΣ
οπτικής γραμμής, με αποτέλεσμα y0 μικρότερο κατά ακριβώς 2.39 - το ΙΔΙΟ
offset που συνδέει ετικέτα με αριθμό ημερών. Άρα η διάκριση "λέξη
συνέχειας ετικέτας" έναντι "τιμή ημερών" ΔΕΝ μπορεί να γίνει με y0 μόνο -
γίνεται ΠΡΩΤΑ με x0/x-center (στήλη), το y0 χρησιμοποιείται ΜΟΝΟ για να
προσδιοριστεί ΠΟΙΑ ετικέτα ταιριάζει με ΠΟΙΟΝ αριθμό.
"""

import logging
import re
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

WordTuple = tuple[float, float, float, float, str]

# --- Γεωμετρικοί κανόνες (μετρημένοι σε 36 blocks πραγματικού PDF,
# private/perilhptiko2018.pdf - βλ. private/prompts/IMPL_DUTIES.md). ΜΗΝ
# τους αλλάξεις χωρίς νέα μέτρηση. ---
LABEL_X = 418.56  # στήλη ετικετών, σταθερό x0
LABEL_X_TOL = 2.0
DAYS_CENTER_X = 530.8  # στήλη ημερών, ΚΕΝΤΡΑΡΙΣΜΕΝΗ (όχι right-aligned)
DAYS_CENTER_X_TOL = 8.0
LABEL_DAYS_Y_OFFSET = 2.39  # number.y0 = label.y0 - 2.39 (βλ. docstring: font quirk)
LABEL_DAYS_Y_TOL = 1.0
LABEL_WRAP_Y_OFFSET = 9.0  # wrap ετικέτας: ίδιο x0, y0 + 9.0
LABEL_WRAP_Y_TOL = 1.5
# Ανοχή "ίδια οπτική γραμμή" για λέξεις συνέχειας μιας ετικέτας (π.χ.
# "ΓΕΝ/Β3-V" μετά "ΤΜΗΜΑΤΑΡΧΗΣ", ή "ΜΗΧΑΝΩΝ" μετά "ΕΠΙΣΤΑΣΙΑΣ") - πρέπει
# να καλύπτει το font-quirk offset (2.39) αλλά να ΜΗΝ φτάνει το wrap
# offset (9.0), ίδιο σκεπτικό με duty_categories.ROW_Y_TOLERANCE.
SAME_LINE_Y_TOL = 3.0
# Λέξεις συνέχειας ετικέτας βρίσκονται ΠΑΝΤΑ πριν τη στήλη ημερών
# (DAYS_CENTER_X - DAYS_CENTER_X_TOL = 522.8) - το όριο μπαίνει λίγο πιο
# αριστερά ώστε καμία λέξη ημερών να μην μπερδευτεί ποτέ ως συνέχεια.
LABEL_LINE_X_MAX = 520.0

_ANCHOR_TEXTS = {"Ε.Α.", "Σ.Α."}
_EVALUATOR_MARKER = "Αξιολογών:"
_DATE_TOKEN_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _parse_date_token(raw: str) -> date:
    day, month, year = raw.split("/")
    return date(int(year), int(month), int(day))


def _center(word: WordTuple) -> float:
    return (word[0] + word[2]) / 2


def _extract_block_duties(words: list[WordTuple]) -> list[tuple[str, int | None]]:
    """Pure συνάρτηση: `words` είναι ΗΔΗ scoped στο εύρος y0 ενός block
    (anchor -> "Αξιολογών:"). Καμία εξάρτηση από fitz/PDF I/O - testable με
    χειρόγραφα tuples.

    Επιστρέφει [(label, days), ...] με τη σειρά εμφάνισης (y0 αύξουσα).
    days=None όταν δεν βρέθηκε αριθμός για μια ετικέτα (LOG, όχι
    exception). [] είναι έγκυρο αποτέλεσμα (block χωρίς κανένα καθήκον,
    π.χ. μονοήμερη παρουσίαση - LOG, όχι exception)."""
    label_starts = sorted(
        (w for w in words if abs(w[0] - LABEL_X) <= LABEL_X_TOL),
        key=lambda w: w[1],
    )

    # Ομαδοποίηση σε λογικές εγγραφές: μια νέα label_start είναι WRAP της
    # τρέχουσας εγγραφής αν το y0 της απέχει ~+9.0 από την ΤΕΛΕΥΤΑΙΑ ήδη
    # προστεθείσα γραμμή της (όχι από την πρώτη - καλύπτει wraps 3+ γραμμών,
    # βλ. πραγματικό block "ΑΞΙΩΜΑΤΙΚΟΣ ΒΟΗΘΗΤΙΚΩΝ ΜΗΧΑΝΗΜΑΤΩΝ"). Διαφορετικά
    # ξεκινάει νέα εγγραφή.
    groups: list[list[WordTuple]] = []
    for w in label_starts:
        if groups and abs(w[1] - groups[-1][-1][1] - LABEL_WRAP_Y_OFFSET) <= LABEL_WRAP_Y_TOL:
            groups[-1].append(w)
        else:
            groups.append([w])

    entries: list[tuple[str, int | None]] = []
    for group in groups:
        line_texts: list[str] = []
        for anchor_word in group:
            # Λέξεις συνέχειας ΤΗΣ ΙΔΙΑΣ οπτικής γραμμής: δεξιά του anchor,
            # πριν τη στήλη ημερών, ΟΧΙ φιλτραρισμένες με βάση μήκος/κείμενο -
            # ΜΟΝΟ θέση (βλ. IMPL_DUTIES.md: "ΜΗΝ φιλτράρεις με βάση το μήκος").
            continuation = [
                w
                for w in words
                if w[0] > anchor_word[0]
                and w[0] < LABEL_LINE_X_MAX
                and abs(w[1] - anchor_word[1]) <= SAME_LINE_Y_TOL
                and w[4].strip()
            ]
            continuation.sort(key=lambda w: w[0])
            line_texts.append(" ".join([anchor_word[4].strip()] + [w[4].strip() for w in continuation]))
        label = " ".join(line_texts)

        target_y = group[0][1] - LABEL_DAYS_Y_OFFSET
        candidates = [
            w
            for w in words
            if abs(_center(w) - DAYS_CENTER_X) <= DAYS_CENTER_X_TOL
            and abs(w[1] - target_y) <= LABEL_DAYS_Y_TOL
            and w[4].strip().isdigit()
        ]
        if not candidates:
            logger.info(
                "extract_duties_positional_from_pdf: ετικέτα %r χωρίς αριθμό ημερών, days=None",
                label,
            )
            days = None
        else:
            if len(candidates) > 1:
                logger.warning(
                    "extract_duties_positional_from_pdf: %d υποψήφιοι αριθμοί ημερών για "
                    "ετικέτα %r, επιλέγεται ο εγγύτερος σε y0",
                    len(candidates),
                    label,
                )
            best = min(candidates, key=lambda w: abs(w[1] - target_y))
            days = int(best[4].strip())
        entries.append((label, days))

    if not entries:
        logger.info("extract_duties_positional_from_pdf: block χωρίς κανένα καθήκον (κενή λίστα)")
    return entries


def extract_duties_positional_from_pdf(
    pdf_path: str,
) -> dict[tuple[int, str], list[tuple[str, int | None]]]:
    """Ανοίγει το PDF ΞΕΧΩΡΙΣΤΑ (ίδιο ownership pattern με
    app.ingestion.duty_categories.extract_duty_categories_from_pdf - δικό
    του try/finally, κανένα fitz object δεν διαφεύγει), σαρώνει ΚΑΘΕ σελίδα
    για bare "Ε.Α."/"Σ.Α." anchors, ορίζει το εύρος κάθε block ως
    [anchor.y0, "Αξιολογών:".y0) και επιστρέφει τα (ετικέτα, ημέρες) του
    πίνακα καθηκόντων ανά block.

    Διαβάζει ΚΑΙ τις δύο ημερομηνίες περιόδου από τα ίδια words (ανεξάρτητα
    από τον extractor) για να χτίσει το κλειδί period = "YYYY-MM-DD..YYYY-MM-DD"
    (ΙΔΙΑ σύμβαση με EvaluationEntry.period, models/evaluation.py).

    Κλειδί: (page 1-indexed, period). Block χωρίς 2 αναγνωρίσιμες
    ημερομηνίες παραλείπεται (LOG) - δεν μπορεί να χτιστεί κλειδί."""
    result: dict[tuple[int, str], list[tuple[str, int | None]]] = {}
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page_num = page_index + 1
            words: list[WordTuple] = [
                (w[0], w[1], w[2], w[3], w[4]) for w in doc[page_index].get_text("words")
            ]

            anchors = sorted(
                (w for w in words if w[4].strip() in _ANCHOR_TEXTS), key=lambda w: w[1]
            )
            if not anchors:
                continue
            evaluator_rows = sorted(
                (w for w in words if w[4].strip() == _EVALUATOR_MARKER), key=lambda w: w[1]
            )

            for i, anchor in enumerate(anchors):
                next_anchor_y = anchors[i + 1][1] if i + 1 < len(anchors) else None
                candidates_y = [e[1] for e in evaluator_rows if e[1] > anchor[1]]
                if next_anchor_y is not None:
                    candidates_y = [y for y in candidates_y if y < next_anchor_y]
                if candidates_y:
                    boundary_y = min(candidates_y)
                elif next_anchor_y is not None:
                    boundary_y = next_anchor_y
                else:
                    boundary_y = float("inf")

                # anchor[1] - SAME_LINE_Y_TOL, ΟΧΙ anchor[1] απευθείας: το
                # ίδιο font-quirk (βλ. docstring) μετατοπίζει τις ημερομηνίες
                # στην ΙΔΙΑ οπτική γραμμή με το anchor κατά -2.39, οπότε ένα
                # αυστηρό ">= anchor.y0" θα τις έκοβε έξω από το block.
                block_words = [
                    w for w in words if anchor[1] - SAME_LINE_Y_TOL <= w[1] < boundary_y
                ]

                dates = sorted(
                    (w for w in block_words if _DATE_TOKEN_RE.match(w[4].strip())),
                    key=lambda w: (w[1], w[0]),
                )
                if len(dates) < 2:
                    logger.warning(
                        "extract_duties_positional_from_pdf: block χωρίς 2 ημερομηνίες "
                        "περιόδου (σελ. %d, anchor y0=%.2f), παραλείπεται",
                        page_num,
                        anchor[1],
                    )
                    continue
                period_start = _parse_date_token(dates[0][4].strip())
                period_end = _parse_date_token(dates[1][4].strip())
                period = f"{period_start.isoformat()}..{period_end.isoformat()}"

                duties = _extract_block_duties(block_words)

                key = (page_num, period)
                if key in result:
                    raise ValueError(
                        f"extract_duties_positional_from_pdf: διπλό κλειδί {key!r} - δύο "
                        f"blocks με την ίδια (σελίδα, περίοδο), αδύνατη η 1:1 αντιστοίχιση"
                    )
                result[key] = duties
    finally:
        doc.close()
    return result
