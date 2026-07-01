"""ChromaDB collection για τα chunks.

Metadata schema έτοιμο για το isolation filter της Φάσης 3 (where σε
person_id + period): κάθε chunk αποθηκεύεται με person_id, person_name,
period, gnmatefsi, section, score, doc_id, page, fallback.
"""

from pathlib import Path

import chromadb

BASE_DIR = Path(__file__).resolve().parents[2]
CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "evaluation_chunks"


def get_collection(persist_dir: Path = CHROMA_DIR):
    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def delete_by_doc_id(collection, doc_id: str) -> None:
    """Καθαρίζει τυχόν προηγούμενη εκδοχή του εγγράφου — προαπαιτούμενο για
    idempotent re-ingestion (ο αριθμός chunks μπορεί να αλλάξει ανάμεσα σε runs)."""
    collection.delete(where={"doc_id": doc_id})


def add_chunks(
    collection,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    if not ids:
        return
    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
