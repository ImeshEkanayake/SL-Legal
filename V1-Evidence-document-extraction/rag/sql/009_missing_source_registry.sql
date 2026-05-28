ALTER TABLE missing_sources
    ADD COLUMN IF NOT EXISTS external_missing_id TEXT,
    ADD COLUMN IF NOT EXISTS source_id TEXT,
    ADD COLUMN IF NOT EXISTS expected_coverage TEXT,
    ADD COLUMN IF NOT EXISTS known_available_coverage TEXT,
    ADD COLUMN IF NOT EXISTS legal_importance TEXT,
    ADD COLUMN IF NOT EXISTS risk_if_missing TEXT,
    ADD COLUMN IF NOT EXISTS probable_source TEXT,
    ADD COLUMN IF NOT EXISTS owner TEXT,
    ADD COLUMN IF NOT EXISTS last_checked TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS missing_sources_external_missing_id_idx
ON missing_sources (external_missing_id)
WHERE external_missing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS missing_sources_status_priority_idx
ON missing_sources (status, priority, updated_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('009_missing_source_registry', 'Missing-source registry metadata for corpus tracking imports')
ON CONFLICT (version) DO NOTHING;
