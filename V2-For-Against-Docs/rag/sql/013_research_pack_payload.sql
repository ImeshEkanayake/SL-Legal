ALTER TABLE research_packs
    ADD COLUMN IF NOT EXISTS sealed_payload JSONB;

CREATE INDEX IF NOT EXISTS research_packs_sealed_payload_gin_idx
ON research_packs USING gin(sealed_payload)
WHERE sealed_payload IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('013_research_pack_payload', 'Persist sealed canonical research-pack payloads for server-side strategy drafting')
ON CONFLICT (version) DO NOTHING;
