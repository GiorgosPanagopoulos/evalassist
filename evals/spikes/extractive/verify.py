"""Quote verification for the extractive spike (EXTRACTIVE_DESIGN.md section 2).

Pure logic: stdlib only, no I/O, no torch, no chromadb. Input bodies are
excerpt texts with the ingestion headers already removed (section 2.1).
"""

import unicodedata
from dataclasses import dataclass, field

# Latin capitals that look like Greek capitals (section 2.2, step 4).
HOMOGLYPHS = {
    "A": "\u0391",
    "B": "\u0392",
    "E": "\u0395",
    "Z": "\u0396",
    "H": "\u0397",
    "I": "\u0399",
    "K": "\u039a",
    "M": "\u039c",
    "N": "\u039d",
    "O": "\u039f",
    "P": "\u03a1",
    "T": "\u03a4",
    "X": "\u03a7",
    "Y": "\u03a5",
}

REASONS = ("bad_excerpt_index", "no_alnum", "wrong_excerpt", "not_found", "partial_token")


@dataclass(frozen=True)
class Excerpt:
    body: str
    period: str
    doc_id: str = ""
    page: int = 0
    section: str = ""


@dataclass
class Display:
    display_text: str
    highlights: list[tuple[int, int]]
    doc_id: str
    page: int
    section: str
    period: str


@dataclass
class QuoteResult:
    excerpt: int
    text: str
    verified: bool
    reason: str | None = None
    positions: list[tuple[int, int]] = field(default_factory=list)
    quote_text: str | None = None
    displays: list[Display] = field(default_factory=list)
    found_in: list[int] = field(default_factory=list)


def locate_normalize_map(s: str) -> tuple[str, list[int], list[int]]:
    """Normalized string plus, per normalized char, the [start, end) span of
    the original chars it came from. Steps 1-5 of section 2.2, char by char."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for i, ch in enumerate(s):
        piece = unicodedata.normalize("NFD", ch)
        piece = "".join(c for c in piece if unicodedata.category(c) != "Mn")
        piece = piece.upper()
        piece = "".join(HOMOGLYPHS.get(c, c) for c in piece)
        if not piece:
            # A standalone combining mark: attach it to the preceding char so
            # quote_text keeps it.
            if ends:
                ends[-1] = i + 1
            continue
        for c in piece:
            if c.isspace():
                if out and out[-1] == " ":
                    ends[-1] = i + 1
                    continue
                c = " "
            out.append(c)
            starts.append(i)
            ends.append(i + 1)
    return "".join(out), starts, ends


def locate_normalize(s: str) -> str:
    return locate_normalize_map(s)[0]


def normalize_quote(text: str) -> str:
    # Step 6: strip applies to the quote only, never to the body.
    return locate_normalize(text).strip(" ")


def _find_all(haystack: str, needle: str) -> list[int]:
    found = []
    start = haystack.find(needle)
    while start != -1:
        found.append(start)
        start = haystack.find(needle, start + 1)
    return found


def _on_token_boundary(norm: str, start: int, end: int) -> bool:
    before_ok = start == 0 or not norm[start - 1].isalnum()
    after_ok = end == len(norm) or not norm[end].isalnum()
    return before_ok and after_ok


def _non_overlapping(starts: list[int], length: int) -> list[int]:
    picked: list[int] = []
    for s in starts:
        if not picked or s >= picked[-1] + length:
            picked.append(s)
    return picked


def build_displays(ex: Excerpt, positions: list[tuple[int, int]]) -> list[Display]:
    """Section 2.4: the display is always the whole excerpt body, with every
    match position highlighted."""
    return [Display(ex.body, list(positions), ex.doc_id, ex.page, ex.section, ex.period)]


def verify_quote(n: int, text: str, excerpts: list[Excerpt]) -> QuoteResult:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("excerpt index must be int; schema validation precedes verify")
    if not isinstance(text, str):
        raise TypeError("quote text must be str; schema validation precedes verify")

    # Rule 1
    if not 1 <= n <= len(excerpts):
        return QuoteResult(n, text, False, "bad_excerpt_index")

    needle = normalize_quote(text)
    # Rule 2
    if not any(c.isalnum() for c in needle):
        return QuoteResult(n, text, False, "no_alnum")

    ex = excerpts[n - 1]
    norm_body, starts, ends = locate_normalize_map(ex.body)
    occurrences = _find_all(norm_body, needle)
    # Rule 3
    if not occurrences:
        others = [
            m
            for m, other in enumerate(excerpts, start=1)
            if m != n and needle in locate_normalize(other.body)
        ]
        if others:
            return QuoteResult(n, text, False, "wrong_excerpt", found_in=others)
        return QuoteResult(n, text, False, "not_found")

    # Rule 4
    size = len(needle)
    valid = [s for s in occurrences if _on_token_boundary(norm_body, s, s + size)]
    if not valid:
        return QuoteResult(n, text, False, "partial_token")

    positions = [(starts[s], ends[s + size - 1]) for s in _non_overlapping(valid, size)]
    first_s, first_e = positions[0]
    return QuoteResult(
        excerpt=n,
        text=text,
        verified=True,
        positions=positions,
        quote_text=ex.body[first_s:first_e],
        displays=build_displays(ex, positions),
    )


def verify_quotes(quotes: list[tuple[int, str]], excerpts: list[Excerpt]) -> list[QuoteResult]:
    return [verify_quote(n, text, excerpts) for n, text in quotes]


def unique_displays(results: list[QuoteResult]) -> list[Display]:
    """Section 2.4 dedup: one display per (doc_id, page, display_text); the
    highlights of all quotes that land on it are merged."""
    merged: dict[tuple[str, int, str], Display] = {}
    for r in results:
        for d in r.displays:
            key = (d.doc_id, d.page, d.display_text)
            if key not in merged:
                merged[key] = Display(
                    d.display_text, [], d.doc_id, d.page, d.section, d.period
                )
            hl = merged[key].highlights
            hl.extend(h for h in d.highlights if h not in hl)
            hl.sort()
    return list(merged.values())
