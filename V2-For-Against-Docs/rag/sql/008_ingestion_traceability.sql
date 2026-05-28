CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    pipeline_name TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    manifest_path TEXT,
    corpus_root TEXT,
    input_manifest_hash TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    document_count INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('queued', 'running', 'complete', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ingestion_runs_source_status_idx
ON ingestion_runs (source_id, status, started_at DESC);

CREATE TABLE IF NOT EXISTS document_ingestion_events (
    ingestion_event_id BIGSERIAL PRIMARY KEY,
    ingestion_run_id TEXT NOT NULL REFERENCES ingestion_runs(ingestion_run_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    source_id TEXT NOT NULL,
    source_document_id TEXT,
    local_path TEXT,
    file_hash TEXT,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    extraction_method TEXT,
    ocr_required BOOLEAN,
    ocr_engine TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    text_hash TEXT,
    text_quality_score NUMERIC(4,2),
    quality_flags TEXT[] NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('queued', 'downloaded', 'extracted', 'indexed', 'skipped', 'failed'))
);

CREATE INDEX IF NOT EXISTS document_ingestion_events_run_idx
ON document_ingestion_events (ingestion_run_id, created_at);

CREATE INDEX IF NOT EXISTS document_ingestion_events_document_idx
ON document_ingestion_events (document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS document_ingestion_events_status_idx
ON document_ingestion_events (status, stage, created_at DESC);

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS current_ingestion_run_id TEXT REFERENCES ingestion_runs(ingestion_run_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS last_ingested_at TIMESTAMPTZ;

ALTER TABLE document_versions
    ADD COLUMN IF NOT EXISTS ingestion_run_id TEXT REFERENCES ingestion_runs(ingestion_run_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS page_count INTEGER,
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER,
    ADD COLUMN IF NOT EXISTS quality_flags TEXT[] NOT NULL DEFAULT '{}';

INSERT INTO schema_migrations (version, description)
VALUES ('008_ingestion_traceability', 'Traceable ingestion runs and per-document extraction events')
ON CONFLICT (version) DO NOTHING;
