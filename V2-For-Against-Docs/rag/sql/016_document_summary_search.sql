CREATE TABLE IF NOT EXISTS document_summaries (
    summary_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    text_version_id TEXT NOT NULL REFERENCES document_text_versions(text_version_id) ON DELETE CASCADE,
    summary_type TEXT NOT NULL,
    language TEXT,
    source_text_hash TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    source_char_count INTEGER NOT NULL,
    compression_ratio NUMERIC(8,6) NOT NULL,
    generation_method TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (summary_type IN ('extractive_10pct', 'llm_abstractive', 'manual')),
    CHECK (char_count >= 0),
    CHECK (source_char_count >= 0),
    CHECK (compression_ratio >= 0 AND compression_ratio <= 1),
    CHECK (source_text_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (text_version_id, summary_type, generation_method)
);

CREATE INDEX IF NOT EXISTS document_summaries_document_type_idx
ON document_summaries(document_id, summary_type, created_at DESC);

CREATE INDEX IF NOT EXISTS document_summaries_text_version_idx
ON document_summaries(text_version_id, summary_type);

CREATE INDEX IF NOT EXISTS document_summaries_text_search_idx
ON document_summaries
USING GIN (to_tsvector('simple', summary_text));

INSERT INTO schema_migrations (version, description)
VALUES ('016_document_summary_search', 'Document-level short summaries for low-cost high-recall search prefiltering')
ON CONFLICT (version) DO NOTHING;
