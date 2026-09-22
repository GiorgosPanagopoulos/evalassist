"""Post-processing grounding check.

Ελέγχει αν η απάντηση του LLM βασίζεται πραγματικά στα excerpts, μετρώντας
πόσα διακριτά bigrams (2 συνεχόμενες λέξεις >= 4 χαρακτήρων) από τα excerpts
εμφανίζονται στην απάντηση. Deterministic, χωρίς εξάρτηση από LLM ή stopwords.

Χρησιμοποιείται σαν safety net μετά την αφαίρεση της refusal instruction από
το system prompt (v4+), ώστε γνήσιες περιπτώσεις απουσίας πληροφορίας να
γυρνούν σαφή άρνηση αντί hallucination.
"""

import re

_WORD_RE = re.compile(r"[Α-Ωα-ωΆ-Ώά-ώA-Za-z0-9]{4,}")


def _bigrams(text: str) -> set[tuple[str, str]]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def is_grounded(answer: str, excerpts: str, min_overlap: int = 2) -> bool:
    """True αν η απάντηση μοιράζεται >= min_overlap διακριτά bigrams με τα excerpts."""
    if not answer.strip() or not excerpts.strip():
        return False
    answer_bg = _bigrams(answer)
    excerpts_bg = _bigrams(excerpts)
    overlap = answer_bg & excerpts_bg
    return len(overlap) >= min_overlap
