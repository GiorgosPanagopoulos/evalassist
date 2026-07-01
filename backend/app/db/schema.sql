PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS persons (
    person_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evaluations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id         TEXT NOT NULL REFERENCES persons(person_id),
    period            TEXT NOT NULL,
    gnmatefsi         TEXT NOT NULL CHECK (gnmatefsi IN ('A', 'B')),
    overall_comment   TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (person_id, period)
);

CREATE TABLE IF NOT EXISTS scores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_id    INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    section    TEXT NOT NULL,
    score      INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment    TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    person_id    TEXT NOT NULL REFERENCES persons(person_id),
    period       TEXT NOT NULL,
    path         TEXT NOT NULL,
    page_count   INTEGER,
    ingested_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL DEFAULT (datetime('now')),
    user                TEXT NOT NULL,
    query               TEXT NOT NULL,
    retrieved_doc_ids   TEXT,
    mode                TEXT NOT NULL CHECK (mode IN ('structured', 'semantic'))
);

CREATE INDEX IF NOT EXISTS idx_evaluations_person_period ON evaluations(person_id, period);
CREATE INDEX IF NOT EXISTS idx_scores_eval_id ON scores(eval_id);
CREATE INDEX IF NOT EXISTS idx_documents_person_period ON documents(person_id, period);
