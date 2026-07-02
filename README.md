# EvalAssist

![Python](https://img.shields.io/badge/Python-3.12-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227)
![Offline](https://img.shields.io/badge/Deployment-Offline%20%2F%20On--Prem-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227)
![Human In The Loop](https://img.shields.io/badge/Decision-Human--in--the--Loop-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227)
![Phase](https://img.shields.io/badge/Phase-3%20of%205-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227)

AI assisted retrieval of evidence from Greek personnel evaluation reports, built fully offline and on-prem for the Hellenic Armed Forces. EvalAssist surfaces citable evidence for a human evaluator to review. It does not decide anything on its own; final judgment always stays with the human in the loop.

Based on the HNDGS/B8 concept "AI-Assisted Evaluation Reports System".

## Why it exists

Evaluators review long, densely written personnel evaluation reports (PDFs, in Greek) and need fast, trustworthy access to prior scores, comments and evidence, without sending sensitive personnel data to any external service. EvalAssist runs entirely inside the perimeter: no cloud APIs, no external model calls, full audit trail of every query and every document retrieved.

## Architecture overview

**Ingestion pipeline.** PDFs are parsed (with OCR fallback for scanned pages), chunked per evaluation section, structurally extracted into a Pydantic schema, embedded with a local dense embedding model and persisted idempotently into both SQLite (structured records) and ChromaDB (semantic chunks). Re-ingesting the same document updates records in place instead of duplicating them.

**Dual retrieval modes.**
- *Structured retrieval*: deterministic SQL lookups over scores and evaluation periods. No LLM involved, always reproducible.
- *Semantic retrieval (RAG)*: the user's question is embedded, the top candidates are pulled from ChromaDB, reranked with a cross-encoder, and only the top results are handed to a local LLM to compose a grounded, citation-backed answer.

**Isolation model.** Every retrieval call, structured or semantic, is scoped by an `IsolationScope` (person, evaluation period, optional document) that is enforced server-side, in code, before any query reaches SQLite or ChromaDB. Isolation is never left to the prompt. There is zero cross-person leakage by construction.

**Citations and audit.** Every semantic answer carries citations back to the exact document, page and section it was drawn from. Every query, structured or semantic, is written to an append-only audit log together with the IDs of every document retrieved.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API | FastAPI |
| Orchestration | LangChain |
| Vector store | ChromaDB |
| Relational store | SQLite |
| Embeddings | BAAI/bge-m3 |
| Reranker | BAAI/bge-reranker-v2-m3 |
| LLM | Ollama, qwen2.5:14b (local) |
| Frontend | React 19, TypeScript, Vite, Tailwind v4 |

## Project structure

```
evalassist/
  backend/
    app/
      db/
        database.py        SQLite connection
        repository.py       idempotent persistence
        schema.sql           persons, evaluations, scores, documents, audit_log
      ingestion/
        parser.py            PDF parsing (PyMuPDF)
        ocr.py                OCR fallback for scanned pages
        chunker.py            per-section chunking, config-driven
        extractor.py          structured extraction into EvaluationReport
        embedder.py           lazy-loaded BAAI/bge-m3 wrapper
        vectorstore.py        ChromaDB collection helpers
        pipeline.py           end-to-end idempotent ingestion
      retrieval/
        isolation.py          IsolationScope, server-side query scoping
        models.py              RetrievalMode, Citation, result types
        structured.py          deterministic SQL lookups, no LLM
        reranker.py             lazy-loaded BAAI/bge-reranker-v2-m3 wrapper
        llm.py                   Ollama chat client wrapper
        semantic.py              RAG pipeline (embed, retrieve, rerank, generate)
      models/
        evaluation.py         EvaluationReport, KNOWN_SECTIONS (provisional template)
    tests/                    standalone tests, no real ML models or Ollama required
    requirements.txt
  frontend/                   React 19 + TypeScript + Vite + Tailwind v4 (Phase 5)
```

## Setup

1. Create and activate a virtual environment with Python 3.12:
   ```
   python3.12 -m venv backend/.venv
   source backend/.venv/bin/activate
   ```
2. Install backend dependencies:
   ```
   pip install -r backend/requirements.txt
   ```
3. Install Tesseract OCR with the Greek language pack (used as an OCR fallback for scanned pages):
   ```
   brew install tesseract tesseract-lang
   ```
4. Install Ollama and pull the local LLM:
   ```
   ollama pull qwen2.5:14b
   ```
5. Run the standalone test suite (no real ML models or Ollama required, fakes are used throughout):
   ```
   cd backend
   python tests/test_isolation.py
   python tests/test_structured.py
   python tests/test_semantic.py
   python tests/test_chunker.py
   python tests/test_ingestion_pipeline.py
   ```

## Phase roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | SQLite schema, Pydantic extraction models | Done |
| 2 | Ingestion pipeline: parser, OCR, chunker, extractor, embedder, vectorstore | Done |
| 3 | Retrieval layer: isolation, structured SQL lookups, semantic RAG, citations | In progress |
| 4 | FastAPI service layer, audit log persistence | Planned |
| 5 | React frontend | Planned |

## Principles

- Fully offline, on-prem. No cloud APIs, no external model calls.
- The AI assists; the human evaluator decides.
- Every answer is traceable to a document, a page and a section.
- Isolation between persons is enforced in code, never in a prompt.

I build things I'd trust with something that matters.
