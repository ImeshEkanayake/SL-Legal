ALTER TABLE research_packs
    ADD COLUMN IF NOT EXISTS schema_version TEXT NOT NULL DEFAULT 'legal_research_pack.v1',
    ADD COLUMN IF NOT EXISTS pack_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS parent_pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS token_count INTEGER,
    ADD COLUMN IF NOT EXISTS source_warning_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source_warnings TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS retrieval_trace JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE research_pack_items
    ADD COLUMN IF NOT EXISTS token_estimate INTEGER,
    ADD COLUMN IF NOT EXISTS scoring_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS retrieval_trace JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE retrieval_events
    ADD COLUMN IF NOT EXISTS retrieval_trace JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS parent_pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS pack_version INTEGER;

CREATE INDEX IF NOT EXISTS research_packs_parent_version_idx
ON research_packs(parent_pack_id, pack_version, created_at DESC);

CREATE INDEX IF NOT EXISTS research_packs_hash_idx
ON research_packs(pack_hash)
WHERE pack_hash IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('010_research_pack_contract', 'Immutable research-pack contract metadata, version lineage, and retrieval traces')
ON CONFLICT (version) DO NOTHING;
