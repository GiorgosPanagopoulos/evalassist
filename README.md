<div align="center">

<!-- docs/logo.svg placeholder: add a logo asset at this path to have it appear here -->

# EvalAssist

*AI-assisted retrieval for personnel evaluation reports. Fully offline, isolation-first, human-in-the-loop.*

![Python](https://img.shields.io/badge/Python-3.11%2B-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![React](https://img.shields.io/badge/React-19-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![Tailwind](https://img.shields.io/badge/Tailwind-v4-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![SQLite](https://img.shields.io/badge/SQLite-Structured%20Store-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![Ollama](https://img.shields.io/badge/Ollama-qwen2.5--14b-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![Embeddings](https://img.shields.io/badge/Embeddings-bge--m3-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)
![License](https://img.shields.io/badge/License-Proprietary-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227)

</div>

## About

EvalAssist helps evaluators inside the Hellenic Armed Forces find and verify evidence buried in long, densely written personnel evaluation reports, written in Greek, without ever sending sensitive personnel data outside the perimeter. It runs entirely offline and on-prem: the embedding model, the reranker and the language model all execute on local hardware, never a cloud API. Every retrieval, whether a deterministic lookup or a semantic RAG query, is scoped server-side in code before it reaches storage, so isolation between individuals is a structural guarantee rather than a prompt instruction. Every answer carries citations back to the exact document, page and section it came from, and every query is written to an append-only audit log. The system surfaces evidence for a human evaluator to review; it never decides anything on its own.

## Technology Stack

<div align="center">

<table>
<tr><td align="center" colspan="4"><b>Frontend</b></td></tr>
<tr>
<td align="center"><img src="https://cdn.simpleicons.org/react/61DAFB" width="48" height="48" alt="React"/><br/>React 19</td>
<td align="center"><img src="https://cdn.simpleicons.org/typescript/3178C6" width="48" height="48" alt="TypeScript"/><br/>TypeScript</td>
<td align="center"><img src="https://cdn.simpleicons.org/vite/646CFF" width="48" height="48" alt="Vite"/><br/>Vite</td>
<td align="center"><img src="https://cdn.simpleicons.org/tailwindcss/06B6D4" width="48" height="48" alt="Tailwind CSS"/><br/>Tailwind v4</td>
</tr>
<tr><td align="center" colspan="4"><b>Backend</b></td></tr>
<tr>
<td align="center"><img src="https://cdn.simpleicons.org/python/3776AB" width="48" height="48" alt="Python"/><br/>Python 3.11+</td>
<td align="center"><img src="https://cdn.simpleicons.org/fastapi/009688" width="48" height="48" alt="FastAPI"/><br/>FastAPI</td>
<td align="center"><img src="https://cdn.simpleicons.org/langchain/1C3C3C" width="48" height="48" alt="LangChain"/><br/>LangChain</td>
<td align="center"><img src="https://cdn.simpleicons.org/pydantic/E92063" width="48" height="48" alt="Pydantic"/><br/>Pydantic v2</td>
</tr>
<tr><td align="center" colspan="4"><b>ML Local</b></td></tr>
<tr>
<td align="center"><img src="https://cdn.simpleicons.org/huggingface/FFB000" width="48" height="48" alt="Hugging Face"/><br/>bge-m3</td>
<td align="center"><img src="https://cdn.simpleicons.org/huggingface/FFB000" width="48" height="48" alt="Hugging Face"/><br/>bge-reranker</td>
<td align="center"><img src="https://cdn.simpleicons.org/ollama/000000" width="48" height="48" alt="Ollama"/><br/>Ollama</td>
<td align="center"><img src="https://cdn.simpleicons.org/qwen/615CED" width="48" height="48" alt="Qwen"/><br/>qwen2.5:14b</td>
</tr>
<tr><td align="center" colspan="4"><b>Data and Ingestion</b></td></tr>
<tr>
<td align="center"><img src="https://cdn.simpleicons.org/sqlite/003B57" width="48" height="48" alt="SQLite"/><br/>SQLite</td>
<td align="center"><img src="https://img.shields.io/badge/ChromaDB-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227" alt="ChromaDB"/><br/>ChromaDB</td>
<td align="center"><img src="https://img.shields.io/badge/PyMuPDF-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227" alt="PyMuPDF"/><br/>PyMuPDF</td>
<td align="center"><img src="https://img.shields.io/badge/Tesseract-1B2A4A?style=for-the-badge&labelColor=1B2A4A&color=C9A227" alt="Tesseract"/><br/>Tesseract</td>
</tr>
</table>

**100% ON-PREM · ZERO CLOUD DEPENDENCIES · AIR-GAPPED READY**

</div>

## Features

| | Feature | Description |
|---|---|---|
| 🔍 | Structured Lookup | Deterministic SQL queries over scores and evaluation periods, no LLM involved, always reproducible |
| 🧠 | Semantic RAG with reranking | Embeds the question, retrieves candidates from ChromaDB, reranks with a cross-encoder, and grounds the LLM answer in only the top results |
| 🔒 | Isolation | Every query is scoped with a `where` filter applied server-side, in code, before it ever reaches SQLite or ChromaDB |
| 📎 | Citations | Every semantic answer points back to the exact `doc_id`, page and section it was drawn from |
| 🧾 | Audit Log | Every query, structured or semantic, is written to an append-only audit trail together with the retrieved document IDs |
| 🗂️ | Prompt Versioning | Prompts live as versioned files on disk and are resolved deterministically, so any answer can be traced to the exact prompt version used |
| 🇬🇷 | Greek OCR fallback | Scanned pages without a usable text layer fall back to Tesseract OCR with the Greek language pack |
| 🔌 | Fully Offline | No cloud APIs, no external model calls, everything runs on local hardware behind the perimeter |

## Example

**Structured lookup**

> Ερώτημα: *Ποια ήταν η βαθμολογία του Παπαδόπουλου Γιώργου στη Στοχοθεσία για το 2025;*
>
> Απάντηση: Γνωμάτευση Α. Στοχοθεσία: 4/5. Σχόλιο: "Ο εργαζόμενος πέτυχε τους στόχους του με συνέπεια." *(πηγή: doc a1b2c3d4e5f6, σελ. 1)*

**Semantic RAG**

> Ερώτημα: *Πώς αξιολογήθηκε η ηγετική ικανότητα του αξιολογούμενου το 2025;*
>
> Απάντηση: Σύμφωνα με την έκθεση, ο αξιολογούμενος επέδειξε συνεπή ηγετική ικανότητα κατά τη διάρκεια της περιόδου, με ιδιαίτερη αναφορά στη διαχείριση της ομάδας υπό πίεση. *(πηγές: doc a1b2c3d4e5f6, σελ. 2, ενότητα "Ηγετική Ικανότητα")*

*(fictional data, for illustration only)*

## Architecture

```mermaid
graph TD
    subgraph Ingestion Pipeline
        PDF[PDF Report] --> Parser["Parser: PyMuPDF + OCR fallback"]
        Parser --> Chunker["Chunker: per-section"]
        Chunker --> Extractor["Extractor: structured fields"]
        Extractor --> SQLite1[(SQLite)]
        Chunker --> Embedder["Embedder: bge-m3"]
        Embedder --> Chroma1[(ChromaDB)]
    end

    UI["React Frontend"] --> API["FastAPI"]
    API --> Isolation["IsolationScope"]
    Isolation --> SQL["SQLite: structured lookup"]
    Isolation --> Semantic["Semantic RAG"]
    Semantic --> Chroma2[(ChromaDB)]
    Chroma2 --> Reranker["Reranker: bge-reranker-v2-m3"]
    Reranker --> LLM["Ollama: qwen2.5:14b"]
    SQL --> Citations["Citations + Audit Log"]
    LLM --> Citations
```

## Architecture

| Technology | Role |
|---|---|
| ![Python](https://img.shields.io/badge/Python-3.11%2B-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Backend language |
| ![FastAPI](https://img.shields.io/badge/FastAPI-Backend-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | HTTP API layer, CORS, exception to HTTP status mapping |
| ![LangChain](https://img.shields.io/badge/LangChain-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | `RecursiveCharacterTextSplitter` for per-section chunking sub-splits |
| ![Pydantic](https://img.shields.io/badge/Pydantic-v2-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Schema validation, `pydantic-settings` for centralized config |
| ![SQLite](https://img.shields.io/badge/SQLite-Structured%20Store-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | persons, evaluations, scores, documents, audit_log |
| ![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Vector store for semantic chunks |
| ![bge-m3](https://img.shields.io/badge/BAAI-bge--m3-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Local dense embedding model |
| ![bge-reranker](https://img.shields.io/badge/BAAI-bge--reranker--v2--m3-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Local cross-encoder reranker |
| ![Ollama](https://img.shields.io/badge/Ollama-qwen2.5--14b-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Local LLM for grounded answer generation |
| ![PyMuPDF](https://img.shields.io/badge/PyMuPDF-Parsing-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | PDF parsing |
| ![Tesseract](https://img.shields.io/badge/Tesseract-Greek%20OCR-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | OCR fallback for scanned pages |
| ![React](https://img.shields.io/badge/React-19-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Frontend |
| ![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Frontend language |
| ![Tailwind](https://img.shields.io/badge/Tailwind-v4-1B2A4A?style=flat-square&labelColor=1B2A4A&color=C9A227) | Frontend styling |

Every model in this table runs locally. No layer of the system calls a cloud API.

## Quick Start

```bash
git clone https://github.com/GiorgosPanagopoulos/evalassist.git
cd evalassist

# 1. Backend virtual environment (Python 3.11+)
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure (defaults work out of the box, override only if needed)
cp backend/.env.example backend/.env

# 4. Install Tesseract OCR with the Greek language pack
brew install tesseract tesseract-lang
# Debian/Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-ell

# 5. Pull the local LLM
ollama pull qwen2.5:14b

# 6. Initialize the SQLite schema
cd backend
python -m app.db.database

# 7. Ingest a report
python -c "
from pathlib import Path
from app.ingestion.pipeline import run_ingestion
result = run_ingestion(Path('path/to/report.pdf'))
print(result.doc_id, result.person_id, result.period)
"
```

### Backend

```bash
cd backend
uvicorn app.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend && npm install && npm run dev
```

### Tests and evals

```bash
# Standalone backend tests (no real ML models or Ollama required, fakes throughout)
for f in backend/tests/test_*.py; do python "$f"; done

# RAG pipeline evals (isolation_leaks must be 0)
python evals/run_evals.py

# Frontend tests
cd frontend && npm test
```

## API Reference

Every endpoint is scoped through `IsolationScope` before it touches SQLite or ChromaDB, and every call, successful or not, is written to the append-only audit log. Pass the caller identity via the `X-User` header (default `anonymous`); it is recorded on the audit entry, it does not gate authorization.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/query/structured` | Deterministic SQL lookup, `get_scores`, `compare_periods` or `top_bottom_sections`, no LLM involved |
| POST | `/query/semantic` | Semantic RAG query: embed the question, retrieve from ChromaDB, rerank, generate a grounded, cited answer |
| GET | `/persons` | List all persons (`person_id`, `name`), unscoped, used to populate pickers |
| GET | `/persons/{person_id}/periods` | List evaluation periods available for a given person |
| GET | `/health` | Service health, including whether the local Ollama server is reachable |

Domain exceptions are mapped to HTTP status codes centrally in `app/api/main.py`: `NotFoundError` becomes 404, `IsolationError` becomes 400, `LLMUnavailableError` becomes 503.

## Environment Variables

All keys below live in `backend/.env.example`. Copy it to `backend/.env` and override only what you need; every value already matches the working default.

| Variable | Description | Required | Default |
|---|---|---|---|
| `DB_PATH` | Path to the SQLite database file | No | `backend/data/evalassist.db` |
| `CHROMA_PATH` | ChromaDB persistence directory | No | `backend/chroma_db` |
| `CHROMA_COLLECTION` | ChromaDB collection name | No | `evaluation_chunks` |
| `EMBEDDING_MODEL` | HuggingFace model id used for embeddings | No | `BAAI/bge-m3` |
| `RERANKER_MODEL` | HuggingFace model id used for the cross-encoder reranker | No | `BAAI/bge-reranker-v2-m3` |
| `OLLAMA_URL` | Base URL of the local Ollama server | No | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model tag used for generation | No | `qwen2.5:14b` |
| `TOP_K_RETRIEVE` | Chunks retrieved from ChromaDB before reranking | No | `20` |
| `TOP_K_RERANK` | Chunks kept after reranking, passed to the LLM | No | `5` |
| `ALLOWED_ORIGINS` | CORS origins allowed by the API | No | `["http://localhost:5173"]` |

## Project Structure

```
evalassist/
  .github/
    workflows/
      ci.yml                     backend tests + RAG evals + frontend build/test
  .pre-commit-config.yaml         ruff lint/format (backend), oxlint + tsc (frontend)
  backend/
    app/
      api/
        main.py                  FastAPI app factory, CORS, exception to HTTP mapping
        routes_query.py           /query/structured, /query/semantic
        routes_meta.py            /persons, /persons/{person_id}/periods, /health
        schemas.py                request/response models
        deps.py                   DB connection + retriever dependencies
      core/
        config.py           centralized settings (pydantic-settings)
        audit.py             AuditEntry, write_audit
        prompt_loader.py     versioned prompt loading (prompts/<name>/vN.txt)
        exceptions.py        domain exceptions (NotFoundError, IsolationError, LLMUnavailableError)
      prompts/
        semantic_rag/
          v1.txt              semantic RAG system prompt
      db/
        database.py           SQLite connection, init_db, schema migration
        repository.py          idempotent persistence
        schema.sql              persons, evaluations, scores, documents, audit_log
      ingestion/
        parser.py               PDF parsing (PyMuPDF)
        ocr.py                   OCR fallback for scanned pages
        chunker.py               per-section chunking, config-driven
        extractor.py             structured extraction into EvaluationReport
        embedder.py              lazy-loaded BAAI/bge-m3 wrapper
        vectorstore.py            ChromaDB collection helpers
        pipeline.py               end-to-end idempotent ingestion
      retrieval/
        isolation.py              IsolationScope, server-side query scoping
        models.py                  RetrievalMode, Citation, result types
        structured.py               deterministic SQL lookups, no LLM
        reranker.py                  lazy-loaded BAAI/bge-reranker-v2-m3 wrapper
        llm.py                        Ollama chat client wrapper
        semantic.py                    RAG pipeline (embed, retrieve, rerank, generate)
      models/
        evaluation.py                EvaluationReport, KNOWN_SECTIONS (provisional template)
    tests/                          standalone tests, no real ML models or Ollama required
    .env.example
    requirements.txt
    requirements-ci.txt           CI-only subset, excludes torch/transformers/sentence-transformers
  frontend/                        React 19 + TypeScript + Vite + Tailwind v4
    src/
      api/                         client.ts, types.ts, typed fetch wrapper for the backend API
      components/                  QueryForm, ResultsPanel, SemanticAnswer, CitationBadge, HealthIndicator
      test/                        vitest setup
      App.tsx
      main.tsx
  evals/
    run_evals.py                   RAG pipeline eval harness, isolation_leaks must be 0
    golden_set.json                 golden query/citation set
```

## Why EvalAssist?

| Decision | Rationale |
|---|---|
| Isolation enforced in code, not prompts | A prompt can be ignored or bypassed; a `where` filter applied before the query reaches SQLite or ChromaDB cannot |
| Single source of truth schema | `schema.sql` is the only place table structure is defined; changes are explicit and additive (see `_migrate_audit_log`) |
| LLM outputs are advisory, always cited | Every semantic answer is grounded in retrieved chunks and points back to `doc_id`/page/section; the human evaluator decides |
| File-based prompt versioning | Prompts live as files under `prompts/<name>/vN.txt`, resolved deterministically, so every answer can be traced to the exact prompt version used |
| Local-only models | Embedding, reranking and generation all run on local hardware; no request ever leaves the perimeter |
| `FakeEmbedder` test pattern | Tests substitute lightweight fakes for real ML models, so the suite runs in seconds without downloading multi-gigabyte weights |
| `isolation_leaks = 0` enforced in CI | `evals/run_evals.py` fails the build if any retrieved chunk crosses a person/period boundary; a CI gate, not a suggestion |

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | SQLite schema, Pydantic extraction models | Complete |
| 2 | Ingestion pipeline: parser, OCR, chunker, extractor, embedder, vectorstore | Complete (4 tests) |
| 3 | Retrieval layer: isolation, structured SQL lookups, semantic RAG, citations | Complete (11 tests) |
| Refactor | Core module (config, audit, prompt versioning, exceptions), README upgrade | Complete (8 tests) |
| 4 | FastAPI service layer, audit log persistence, HTTP error mapping | Complete |
| 5 | React frontend, golden set evals, pre-commit, CI | Complete |
| Future | `document_qa` mode, explicit objectives/duties fields | Planned |

## License

Proprietary. Internal system for the Hellenic Armed Forces, not licensed for external use or redistribution.

<div align="center">

---

Built by Georgios Panagopoulos

[![GitHub](https://img.shields.io/badge/GitHub-GiorgosPanagopoulos-1B2A4A?style=for-the-badge&logo=github&logoColor=C9A227&labelColor=1B2A4A&color=C9A227)](https://github.com/GiorgosPanagopoulos)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-1B2A4A?style=for-the-badge&logo=linkedin&logoColor=C9A227&labelColor=1B2A4A&color=C9A227)](https://www.linkedin.com)

*I build things I'd trust with something that matters.*

</div>
