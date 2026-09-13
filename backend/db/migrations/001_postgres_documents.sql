-- AI Protocol Platform self-host persistence baseline.
--
-- The first PostgreSQL backend preserves the existing collection/document
-- identity while business modules are moved behind db.persistence. Hot domains
-- can later be normalized into dedicated relational tables without blocking
-- the Firestore -> Postgres migration.

CREATE TABLE IF NOT EXISTS platform_documents (
    collection TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection, doc_id)
);

CREATE INDEX IF NOT EXISTS idx_platform_documents_collection
    ON platform_documents (collection);

-- Supports future backend-specific JSONB predicates while the correctness-first
-- repository currently evaluates Firestore-compatible predicates in Python.
CREATE INDEX IF NOT EXISTS idx_platform_documents_data_gin
    ON platform_documents USING GIN (data);
