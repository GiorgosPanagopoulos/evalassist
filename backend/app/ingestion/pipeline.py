"""Ingestion pipeline: PDF -> parsing (+OCR) -> per-section εντοπισμός ->
δομημένη εξαγωγή (SummaryNote) -> persistence (SQLite + ChromaDB).

Idempotent σε doc_id: re-run του ίδιου PDF (ίδιο περιεχόμενο) ενημερώνει τις
υπάρχουσες εγγραφές/chunks αντί να τις διπλασιάζει.

1 PDF = 1 άτομο (Α.Γ.Μ. = person_id), N περίοδοι αξιολόγησης (Ε.Α./Σ.Α.):
κάθε EvaluationEntry της Ενότητας 7 γίνεται ξεχωριστή εγγραφή στο
`evaluations` (period = 'YYYY-MM-DD..YYYY-MM-DD') και ξεχωριστό chunk στο
Chroma, με το πραγματικό κείμενο της περιόδου (όχι synthesized). Οι
υπόλοιπες (career-wide, όχι per-period) ενότητες περνάνε με τη σύμβαση
period='career' (CAREER_PERIOD, single source of truth στο
app.models.evaluation).
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app.db import repository
from app.db.database import DB_PATH, get_connection, init_db
from app.ingestion.chunker import PageText, chunk_by_section, split_text_if_long
from app.ingestion.embedder import Embedder
from app.ingestion.extractor import extract_summary_note
from app.ingestion.form_markers import annotate_empty_section5_subfields
from app.ingestion.parser import parse_pdf
from app.ingestion.promotion_table import annotate_promotion_table
from app.ingestion.vectorstore import CHROMA_DIR, add_chunks, delete_by_doc_id, get_collection
from app.models.evaluation import CAREER_PERIOD, KNOWN_SECTIONS, SummaryNote

logger = logging.getLogger(__name__)

_EVALUATION_SECTION = KNOWN_SECTIONS[-1]  # "ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ"
_SUPPORTING_FACTORS_SECTION = KNOWN_SECTIONS[4]  # "ΣΤΟΙΧΕΙΑ ΣΥΝΗΓΟΡΟΥΝΤΑ Ή ΜΗ"
_PROMOTIONS_SECTION = KNOWN_SECTIONS[0]  # "ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ"


@dataclass
class IngestionResult:
    doc_id: str
    person_id: str
    periods: list[str]  # όλα τα period values που καταχωρήθηκαν (evaluations + 'career')
    page_count: int
    chunk_count: int
    fallback_used: bool
    summary_note: SummaryNote


def compute_doc_id(pdf_path: Path) -> str:
    """Ντετερμινιστικό doc_id = sha256 του περιεχομένου του PDF (16 hex chars).
    Ίδιο PDF -> ίδιο doc_id -> idempotent re-ingestion."""
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return digest[:16]


def run_ingestion(
    pdf_path: Path,
    embedder: Embedder | None = None,
    db_path: Path = DB_PATH,
    chroma_dir: Path = CHROMA_DIR,
) -> IngestionResult:
    pdf_path = Path(pdf_path)
    embedder = embedder or Embedder()
    doc_id = compute_doc_id(pdf_path)

    parsed_pages = parse_pdf(pdf_path)
    pages = [PageText(page=p.page, text=p.text) for p in parsed_pages]
    full_text = "\n".join(p.text for p in pages)

    section_chunks = chunk_by_section(pages, doc_id)
    fallback_used = bool(section_chunks) and section_chunks[0].fallback
    summary_note, eval_raw_texts = extract_summary_note(full_text, section_chunks)

    person_id = summary_note.person.agm

    periods: list[str] = []
    chunk_texts: list[str] = []
    chunk_metas: list[dict] = []

    def add_chunk(text: str, period: str, section: str, page: int, score: int = -1) -> None:
        for piece in split_text_if_long(text):
            chunk_texts.append(piece)
            chunk_metas.append(
                {
                    "person_id": person_id,
                    "person_name": summary_note.person.name,
                    "period": period,
                    "section": section,
                    "score": score,
                    "doc_id": doc_id,
                    "page": page,
                }
            )

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        repository.upsert_person(conn, person_id, summary_note.person.name)

        for entry, raw_text in zip(summary_note.evaluations, eval_raw_texts):
            eval_id = repository.upsert_evaluation(conn, person_id, entry)
            repository.replace_field_scores(conn, eval_id, entry.field_scores)
            repository.upsert_document(
                conn, doc_id, person_id, entry.period, str(pdf_path), len(pages)
            )
            periods.append(entry.period)
            add_chunk(
                raw_text,
                entry.period,
                _EVALUATION_SECTION,
                entry.source_page,
                score=entry.score if entry.score is not None else -1,
            )

        career_chunks = [c for c in section_chunks if c.section != _EVALUATION_SECTION]
        if career_chunks:
            repository.upsert_document(
                conn, doc_id, person_id, CAREER_PERIOD, str(pdf_path), len(pages)
            )
            periods.append(CAREER_PERIOD)
            for chunk in career_chunks:
                # Μαρκάρισμα κενών υποπεδίων Ενότητας 5 ΜΟΝΟ στο κείμενο που
                # πάει για indexing (indexed_text), ΠΟΤΕ στο chunk.text: το
                # extract_summary_note (και το _parse_health μέσα του) έχει
                # ήδη τρέξει παραπάνω πάνω στα ίδια section_chunks - αν
                # μολυνθεί το chunk.text θα χαλούσε το structured parsing.
                indexed_text = chunk.text
                if chunk.section == _SUPPORTING_FACTORS_SECTION:
                    indexed_text = annotate_empty_section5_subfields(indexed_text)
                if chunk.section == _PROMOTIONS_SECTION:
                    indexed_text = annotate_promotion_table(indexed_text)
                add_chunk(
                    indexed_text, CAREER_PERIOD, chunk.section or "Άγνωστη Ενότητα", chunk.page
                )

        conn.commit()
    finally:
        conn.close()

    collection = get_collection(chroma_dir)
    delete_by_doc_id(collection, doc_id)  # idempotency: καθαρισμός παλιάς εκδοχής

    ids = [f"{doc_id}:{i}" for i in range(len(chunk_texts))]
    embeddings = embedder.embed(chunk_texts)
    add_chunks(collection, ids, chunk_texts, embeddings, chunk_metas)

    return IngestionResult(
        doc_id=doc_id,
        person_id=person_id,
        periods=sorted(set(periods)),
        page_count=len(pages),
        chunk_count=len(chunk_texts),
        fallback_used=fallback_used,
        summary_note=summary_note,
    )
