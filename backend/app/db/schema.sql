PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS persons (
    person_id   TEXT PRIMARY KEY,  -- Α.Γ.Μ.
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Μία γραμμή ανά EvaluationEntry (περίοδος Ε.Α./Σ.Α.) της Ενότητας 7. Ένα
-- PDF (= ένα person_id) γεννά πολλές γραμμές εδώ, μία ανά περίοδο.
CREATE TABLE IF NOT EXISTS evaluations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id           TEXT NOT NULL REFERENCES persons(person_id),
    period              TEXT NOT NULL,  -- 'YYYY-MM-DD..YYYY-MM-DD'
    period_start        TEXT NOT NULL,
    period_end          TEXT NOT NULL,
    ea_type             TEXT NOT NULL CHECK (ea_type IN ('Ε.Α.', 'Σ.Α.')),
    characterization    TEXT NOT NULL,
    score               INTEGER CHECK (score IS NULL OR score BETWEEN 0 AND 100),
    unit                TEXT NOT NULL,
    duties              TEXT,  -- JSON array
    rank_at_time        TEXT,
    evaluator_rank      TEXT,
    evaluator_name      TEXT NOT NULL,
    evaluator_role      TEXT,
    gnomatevon_rank     TEXT,
    gnomatevon_name     TEXT,
    gnomatevon_role     TEXT,
    defects             TEXT,
    evaluator_notes     TEXT,
    gnomatevon_notes    TEXT,
    source_page         INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (person_id, period)
);

-- Αναλυτικά πεδία (ΠΕΔΙΟ/ΠΕΡΙΓΡΑΦΗ/ΒΑΘΜΟΛΟΓΙΑ) ανά evaluation entry.
-- value: '0'-'100' ή 'ΝΑΙ'/'ΟΧΙ', αποθηκεύεται ως TEXT (SQLite δεν έχει
-- ανάγκη ξεχωριστών στηλών· η ερμηνεία γίνεται στο application layer).
CREATE TABLE IF NOT EXISTS field_scores (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_id      INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    field_code   TEXT NOT NULL,
    description  TEXT,
    value        TEXT NOT NULL
);

-- Ένα PDF (doc_id) καλύπτει πολλές περιόδους: κάθε evaluation period +
-- η σύμβαση period='career' για τις υπόλοιπες (career-wide) ενότητες.
-- Composite PK: το ίδιο doc_id εμφανίζεται σε πολλές γραμμές, μία ανά period.
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT NOT NULL,
    person_id    TEXT NOT NULL REFERENCES persons(person_id),
    period       TEXT NOT NULL,
    path         TEXT NOT NULL,
    page_count   INTEGER,
    ingested_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (doc_id, period)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL DEFAULT (datetime('now')),
    user                TEXT NOT NULL,
    query               TEXT NOT NULL,
    retrieved_doc_ids   TEXT,
    mode                TEXT NOT NULL CHECK (mode IN ('structured', 'semantic')),
    prompt_version      TEXT,
    unsupported_ranks   TEXT,
    answer_text         TEXT
);

-- Τα δύο triggers μπλοκάρουν UPDATE/DELETE στο audit_log μέσω DML από την
-- εφαρμογή, ώστε το append-only trail να επιβάλλεται σε επίπεδο schema και
-- όχι μόνο σε επίπεδο convention. Δεν εμποδίζουν DDL (π.χ. ALTER TABLE για
-- migrations, δες _migrate_audit_log) και δεν προστατεύουν από κάποιον με
-- απευθείας filesystem access στο .db αρχείο.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE is not allowed');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE is not allowed');
END;

CREATE INDEX IF NOT EXISTS idx_evaluations_person_period ON evaluations(person_id, period);
CREATE INDEX IF NOT EXISTS idx_field_scores_eval_id ON field_scores(eval_id);
CREATE INDEX IF NOT EXISTS idx_documents_person_period ON documents(person_id, period);
