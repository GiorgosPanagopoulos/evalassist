"""Heuristic query routing hint: βαθμολογικά ερωτήματα -> πρόταση "structured".

Καθαρά advisory — δεν αλλάζει ποτέ mode μόνο του (human-in-the-loop). Το
`route_query()` καλείται από το `/query/semantic` endpoint και το hint
προστίθεται στο `SemanticResult.routing_hint` (βλ. app.api.routes_query),
ώστε το frontend να προτείνει "Δομημένη αναζήτηση" χωρίς να παρακάμπτει
την επιλογή του χρήστη.

KNOWN_SECTIONS εισάγεται από το single source of truth
(app.models.evaluation) — όχι αντίγραφο της λίστας εδώ.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from app.models.evaluation import KNOWN_SECTIONS
from app.retrieval.models import RetrievalMode

_SCORE_KEYWORDS = (
    "βαθμ",  # στέλεχος: βαθμός/βαθμολογία/βαθμολογήθηκε/βαθμολογικό...
    "score",
    "ποσο πηρε",  # "πόσο πήρε" μετά το normalize
    "αξιολογηθηκε με",  # "αξιολογήθηκε με" μετά το normalize
)

_FUZZY_THRESHOLD = 0.75


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


_KNOWN_SECTIONS_NORMALIZED = [_normalize(name) for name in KNOWN_SECTIONS]


def _has_score_keyword(normalized_question: str) -> bool:
    return any(keyword in normalized_question for keyword in _SCORE_KEYWORDS)


def _mentions_known_section(normalized_question: str) -> bool:
    question_words = normalized_question.split()
    for section_normalized in _KNOWN_SECTIONS_NORMALIZED:
        if section_normalized in normalized_question:
            return True

        section_words = section_normalized.split()
        window = len(section_words)
        for start in range(len(question_words) - window + 1):
            candidate = " ".join(question_words[start : start + window])
            ratio = SequenceMatcher(None, candidate, section_normalized).ratio()
            if ratio >= _FUZZY_THRESHOLD:
                return True
    return False


def route_query(question: str) -> str | None:
    """Επιστρέφει "structured" hint αν το ερώτημα φαίνεται βαθμολογικό ΚΑΙ
    αναφέρεται σε γνωστή ενότητα, αλλιώς None. Ποτέ δεν πυροδοτεί αλλαγή mode
    από μόνο του — μόνο hint προς τον χρήστη."""
    normalized = _normalize(question)
    if _has_score_keyword(normalized) and _mentions_known_section(normalized):
        return str(RetrievalMode.STRUCTURED)
    return None
