ALTER TABLE embedding_runs
    ADD COLUMN IF NOT EXISTS qdrant_collection TEXT,
    ADD COLUMN IF NOT EXISTS chunk_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS chunk_source_path TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS embedding_runs_qdrant_collection_idx
ON embedding_runs(qdrant_collection, completed_at DESC);

CREATE INDEX IF NOT EXISTS embedding_runs_model_idx
ON embedding_runs(provider, model, dimensions);

INSERT INTO schema_migrations (version, description)
VALUES ('014_embedding_index_metadata', 'Record embedding model, dimensions, collection, and source metadata for vector index compatibility checks')
ON CONFLICT (version) DO NOTHING;
