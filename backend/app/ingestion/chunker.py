"""Chunking PER SECTION (όχι fixed-size).

Section detection είναι config-driven: τα αναμενόμενα ονόματα τομέων
αντλούνται αποκλειστικά από `app.models.evaluation.KNOWN_SECTIONS` (single
source of truth, δίπλα στο SummaryNote schema — οι 7 ενότητες του
Περιληπτικού Σημειώματος) και εντοπίζονται στο κείμενο με fuzzy matching —
καμία σταθερά section header δεν υπάρχει εδώ.

Section detection είναι ανά σελίδα: αν μια ενότητα συνεχίζεται σε νέα
σελίδα, η επικεφαλίδα της πρέπει να επαναλαμβάνεται εκεί (σύμβαση που
ακολουθεί και ο synthetic PDF generator) ώστε να μη χαθεί περιεχόμενο.

Αν ένα PDF δεν έχει καμία αναγνωρίσιμη ενότητα (άγνωστο layout, θόρυβος OCR),
το chunking πέφτει σε structural fallback (chunking ανά παράγραφο/σελίδα) ώστε
να μη χαθεί περιεχόμενο και το έγγραφο να μην απορριφθεί.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass

from app.models.evaluation import KNOWN_SECTIONS

_FUZZY_THRESHOLD = 0.72
_MAX_HEADER_LINE_LEN = 80

MAX_CHUNK_CHARS = 1500
_sub_splitter = None  # lazy: αποφεύγει το βαρύ (torch/transformers) import chain
# του langchain_text_splitters όταν δεν υπάρχουν μεγάλα chunks προς sub-split.


def _get_sub_splitter():
    global _sub_splitter
    if _sub_splitter is None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        _sub_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return _sub_splitter


@dataclass(frozen=True)
class PageText:
    page: int  # 1-indexed
    text: str


@dataclass
class SectionChunk:
    doc_id: str
    page: int
    section: str | None  # None => structural fallback chunk (άγνωστη ενότητα)
    text: str
    fallback: bool = False


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


_KNOWN_SECTIONS_NORMALIZED = [(name, _normalize(name)) for name in KNOWN_SECTIONS]


def _match_known_section(line: str) -> str | None:
    """Fuzzy match μιας γραμμής επικεφαλίδας έναντι του KNOWN_SECTIONS config."""
    if not line or len(line) > _MAX_HEADER_LINE_LEN:
        return None
    normalized_line = _normalize(line)
    if not normalized_line:
        return None
    best_name, best_ratio = None, 0.0
    for canonical_name, normalized_name in _KNOWN_SECTIONS_NORMALIZED:
        ratio = difflib.SequenceMatcher(None, normalized_name, normalized_line).ratio()
        if normalized_name in normalized_line:
            ratio = max(ratio, 0.9)
        if ratio > best_ratio:
            best_name, best_ratio = canonical_name, ratio
    return best_name if best_ratio >= _FUZZY_THRESHOLD else None


def _find_known_section_boundaries(page_text: str) -> list[tuple[int, str]]:
    """[(char_offset, canonical_section_name), ...] μέσα στο κείμενο σελίδας."""
    boundaries: list[tuple[int, str]] = []
    offset = 0
    for line in page_text.splitlines(keepends=True):
        matched = _match_known_section(line.strip())
        if matched:
            boundaries.append((offset, matched))
        offset += len(line)
    return boundaries


def _known_section_chunks(pages: list[PageText], doc_id: str) -> list[SectionChunk]:
    chunks: list[SectionChunk] = []
    for page in pages:
        boundaries = _find_known_section_boundaries(page.text)
        for i, (start, section_name) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(page.text)
            body = page.text[start:end].strip()
            if not body:
                continue
            chunks.append(
                SectionChunk(
                    doc_id=doc_id,
                    page=page.page,
                    section=section_name,
                    text=body,
                    fallback=False,
                )
            )
    return chunks


def _structural_fallback_chunks(pages: list[PageText], doc_id: str) -> list[SectionChunk]:
    """Άγνωστο layout / θόρυβος OCR: chunking ανά παράγραφο (ή ολόκληρη σελίδα
    αν δεν υπάρχουν κενές γραμμές), χωρίς απώλεια περιεχομένου."""
    chunks: list[SectionChunk] = []
    for page in pages:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
        if not paragraphs and page.text.strip():
            paragraphs = [page.text.strip()]
        for paragraph in paragraphs:
            chunks.append(
                SectionChunk(
                    doc_id=doc_id,
                    page=page.page,
                    section=None,
                    text=paragraph,
                    fallback=True,
                )
            )
    return chunks


def split_text_if_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    return _get_sub_splitter().split_text(text)


def _split_long_chunks(chunks: list[SectionChunk]) -> list[SectionChunk]:
    result: list[SectionChunk] = []
    for chunk in chunks:
        for piece in split_text_if_long(chunk.text):
            result.append(
                SectionChunk(
                    doc_id=chunk.doc_id,
                    page=chunk.page,
                    section=chunk.section,
                    text=piece,
                    fallback=chunk.fallback,
                )
            )
    return result


def chunk_by_section(pages: list[PageText], doc_id: str) -> list[SectionChunk]:
    known_chunks = _known_section_chunks(pages, doc_id)
    if known_chunks:
        return _split_long_chunks(known_chunks)
    return _split_long_chunks(_structural_fallback_chunks(pages, doc_id))
