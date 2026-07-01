"""Parsing PDF εκθέσεων με PyMuPDF. Σελίδες χωρίς εξαγώγιμο text layer
(σαρωμένες εικόνες) περνούν από OCR fallback (βλ. app.ingestion.ocr)."""

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from app.ingestion.ocr import ocr_page

# Κάτω από αυτό το μήκος, η σελίδα θεωρείται "χωρίς αξιοποιήσιμο text layer".
MIN_TEXT_LEN = 20


@dataclass(frozen=True)
class ParsedPage:
    page: int  # 1-indexed
    text: str
    ocr_used: bool


def _extract_text_blocks(page: fitz.Page) -> str:
    """Κείμενο ανά block (παράγραφος/στήλη κειμένου), ενωμένο με κενή γραμμή
    ανάμεσα σε blocks — διατηρεί τα παραγραφικά όρια που χρειάζεται ο chunker
    (known-section headers ανά γραμμή, structural fallback ανά παράγραφο)."""
    blocks = page.get_text("blocks")
    paragraphs = [b[4].strip() for b in blocks if b[6] == 0 and b[4].strip()]
    return "\n\n".join(paragraphs)


def parse_pdf(pdf_path: Path) -> list[ParsedPage]:
    doc = fitz.open(pdf_path)
    try:
        pages: list[ParsedPage] = []
        for index in range(doc.page_count):
            page = doc[index]
            text = _extract_text_blocks(page)
            ocr_used = False
            if len(text) < MIN_TEXT_LEN:
                ocr_text = ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    ocr_used = True
            pages.append(ParsedPage(page=index + 1, text=text, ocr_used=ocr_used))
        return pages
    finally:
        doc.close()
