# RAG evals

Measures the retrieval pipeline used by `SemanticRetriever`
(embed, ChromaDB scope-filtered search, rerank, cite), not the quality of
the real embedding/reranker/LLM models. Everything in this script is a
deterministic fake, so results are stable across runs and require no
network access, no GPU, and no downloaded models.

## What is measured

`run_evals.py` seeds a temp SQLite database and a temp ChromaDB collection
with a small synthetic corpus of Greek evaluation documents (`CORPUS_DOCS`
in the script), then runs every case in `golden_set.json` through the real
`SemanticRetriever` with:

- a deterministic bag-of-words embedder (word-stem hashing, no ML model)
- a deterministic lexical-overlap reranker (no cross-encoder)
- an echo LLM that returns the grounded prompt verbatim (no generation)

Only the embedder/reranker/LLM are fakes. The `IsolationScope` where-filter
and the ChromaDB collection are the real production code path.

Per case and in aggregate:

- **citation_recall**: fraction of the expected doc_ids that were retrieved.
- **citation_precision**: fraction of retrieved doc_ids that were expected.
- **isolation_leaks**: retrieved doc_ids that truly belong to a different
  person_id or period than the one that was scoped, cross-checked against
  the seeded SQLite `documents` table (the source of truth, independent of
  the in-script corpus definition).
- **empty_scope_correct**: every case with an empty `expected_doc_ids` gets
  back empty citations, not an error and not leftover data from another scope.

The golden set includes isolation-bait cases on purpose: pairs of people (or
periods) with near-identical text, so a broken where-filter would show up as
a nonzero leak count instead of silently passing because the content itself
was easy to tell apart.

## Why isolation_leaks == 0 is a hard gate

This tool evaluates a system that serves per-person evaluation data. A
retrieval bug that returns even one document from the wrong person or the
wrong period is a data leak, not a quality regression. Recall and precision
are quality signals that are expected to move as real data and real models
are introduced; a leak is never acceptable at any stage, so it fails the run
regardless of how good the recall/precision numbers look.

## Running

```
python evals/run_evals.py
```

No pytest, no extra dependencies beyond what backend/requirements-ci.txt
already provides. Exit code is 0 only if isolation_leaks is 0 across every
case and every empty-scope case is handled correctly. Recall and precision
are printed for visibility but do not affect the exit code; numeric
thresholds will be added once the golden set is measured against real
ingested documents and real models.

## Updating the golden set

Add cases to `golden_set.json` and, if they reference new people, periods,
or documents, extend `CORPUS_DOCS` in `run_evals.py` so the case has
something to retrieve. Keep at least one isolation-bait pair and one
empty-scope case at all times.
