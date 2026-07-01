"""Ingestion pipeline: PDF -> parsing (+OCR) -> per-section chunking ->
δομημένη εξαγωγή -> persistence (SQLite + ChromaDB).

Idempotent σε doc_id: re-run του ίδιου PDF (ίδιο περιεχόμενο) ενημερώνει τις
υπάρχουσες εγγραφές/chunks αντί να τις διπλασιάζει.
"""

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.db import repository
from app.db.database import DB_PATH, get_connection, init_db
from app.ingestion.chunker import PageText, chunk_by_section
from app.ingestion.embedder import Embedder
from app.ingestion.extractor import extract_report
from app.ingestion.parser import parse_pdf
from app.ingestion.vectorstore import CHROMA_DIR, add_chunks, delete_by_doc_id, get_collection
from app.models.evaluation import EvaluationReport

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    doc_id: str
    person_id: str
    period: str
    page_count: int
    chunk_count: int
    fallback_used: bool
    report: EvaluationReport


def compute_doc_id(pdf_path: Path) -> str:
    """Ντετερμινιστικό doc_id = sha256 του περιεχομένου του PDF (16 hex chars).
    Ίδιο PDF -> ίδιο doc_id -> idempotent re-ingestion."""
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return digest[:16]


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or hashlib.sha256(value.encode()).hexdigest()[:12]


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
    report = extract_report(full_text, section_chunks)

    person_id = report.person_id or _slugify(report.person_name)

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        repository.upsert_person(conn, person_id, report.person_name)
        eval_id = repository.upsert_evaluation(
            conn, person_id, report.period, report.gnmatefsi, report.overall_comment
        )
        repository.replace_scores(conn, eval_id, report.sections)
        repository.upsert_document(
            conn, doc_id, person_id, report.period, str(pdf_path), len(pages)
        )
        conn.commit()
    finally:
        conn.close()

    collection = get_collection(chroma_dir)
    delete_by_doc_id(collection, doc_id)  # idempotency: καθαρισμός παλιάς εκδοχής

    ids, documents, metadatas = [], [], []
    for i, chunk in enumerate(section_chunks):
        ids.append(f"{doc_id}:{i}")
        documents.append(chunk.text)
        metadatas.append(
            {
                "person_id": person_id,
                "person_name": report.person_name,
                "period": report.period,
                "gnmatefsi": report.gnmatefsi,
                "section": chunk.section or "Άγνωστη Ενότητα",
                "score": chunk.score if chunk.score is not None else -1,
                "doc_id": doc_id,
                "page": chunk.page,
                "fallback": chunk.fallback,
            }
        )
    embeddings = embedder.embed(documents)
    add_chunks(collection, ids, documents, embeddings, metadatas)

    return IngestionResult(
        doc_id=doc_id,
        person_id=person_id,
        period=report.period,
        page_count=len(pages),
        chunk_count=len(section_chunks),
        fallback_used=fallback_used,
        report=report,
    )
