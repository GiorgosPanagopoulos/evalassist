"""OCR fallback (ελληνικά) για σελίδες PDF χωρίς εξαγώγιμο text layer."""

import io
import logging

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

OCR_LANG = "ell"
OCR_ZOOM = 2.0  # ανάλυση rendering πριν το OCR


def ocr_page(page: fitz.Page) -> str:
    """Επιστρέφει το OCR-αναγνωρισμένο κείμενο της σελίδας, ή "" αν αποτύχει
    (π.χ. tesseract binary δεν είναι εγκατεστημένο) — δεν διακόπτει το pipeline."""
    try:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(OCR_ZOOM, OCR_ZOOM))
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=OCR_LANG).strip()
    except Exception:
        logger.warning("OCR απέτυχε για σελίδα %s", page.number, exc_info=True)
        return ""
