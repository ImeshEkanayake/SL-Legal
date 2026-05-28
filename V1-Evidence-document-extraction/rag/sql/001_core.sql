CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_document_id TEXT,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    number TEXT,
    document_date DATE,
    language TEXT,
    source_url TEXT,
    download_url TEXT,
    local_path TEXT,
    file_hash TEXT,
    acquisition_status TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    ocr_required BOOLEAN,
    text_quality_score NUMERIC(4,2),
    legal_status TEXT,
    missing_reason TEXT,
    next_action TEXT,
    last_checked TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version_label TEXT NOT NULL,
    file_hash TEXT,
    text_hash TEXT,
    extraction_method TEXT,
    ocr_confidence_band TEXT,
    source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, version_label)
);

CREATE TABLE IF NOT EXISTS pages (
    page_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    ocr_confidence NUMERIC(5,2),
    quality_flags TEXT[] NOT NULL DEFAULT '{}',
    layout JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, page_number, extraction_method)
);

CREATE TABLE IF NOT EXISTS legal_units (
    unit_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    unit_type TEXT NOT NULL,
    label TEXT,
    title TEXT,
    start_page INTEGER,
    end_page INTEGER,
    text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    unit_id TEXT REFERENCES legal_units(unit_id) ON DELETE SET NULL,
    source_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    authority_level INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    language TEXT,
    citation TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    text_hash TEXT NOT NULL,
    quality_flags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrieval_chunks_document_idx ON retrieval_chunks(document_id);
CREATE INDEX IF NOT EXISTS retrieval_chunks_type_year_idx ON retrieval_chunks(document_type, year);
CREATE INDEX IF NOT EXISTS retrieval_chunks_authority_idx ON retrieval_chunks(authority_level);
CREATE INDEX IF NOT EXISTS retrieval_chunks_text_trgm_idx ON retrieval_chunks USING gin(chunk_text gin_trgm_ops);

CREATE TABLE IF NOT EXISTS citations (
    citation_id BIGSERIAL PRIMARY KEY,
    from_document_id TEXT REFERENCES documents(document_id) ON DELETE CASCADE,
    from_unit_id TEXT REFERENCES legal_units(unit_id) ON DELETE SET NULL,
    to_document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    to_unit_id TEXT REFERENCES legal_units(unit_id) ON DELETE SET NULL,
    citation_text TEXT NOT NULL,
    citation_type TEXT NOT NULL,
    treatment TEXT,
    confidence NUMERIC(4,2),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS embedding_runs (
    embedding_run_id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    chunk_source_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS research_packs (
    pack_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    query_class TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieval_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    missing_source_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_pack_items (
    pack_item_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL REFERENCES research_packs(pack_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES retrieval_chunks(chunk_id) ON DELETE RESTRICT,
    rank INTEGER NOT NULL,
    fused_score NUMERIC(12,6) NOT NULL,
    keyword_score NUMERIC(12,6),
    vector_score NUMERIC(12,6),
    graph_score NUMERIC(12,6),
    selection_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pack_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS missing_sources (
    missing_source_id BIGSERIAL PRIMARY KEY,
    document_id TEXT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    reason TEXT NOT NULL,
    next_action TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS retrieval_events (
    retrieval_event_id BIGSERIAL PRIMARY KEY,
    pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    query_class TEXT,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    keyword_hits INTEGER NOT NULL DEFAULT 0,
    vector_hits INTEGER NOT NULL DEFAULT 0,
    graph_hits INTEGER NOT NULL DEFAULT 0,
    selected_items INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version, description)
VALUES ('001_core', 'Core corpus, retrieval, citation, and research-pack schema')
ON CONFLICT (version) DO NOTHING;
