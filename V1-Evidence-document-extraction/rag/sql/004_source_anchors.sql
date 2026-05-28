CREATE TABLE IF NOT EXISTS pack_item_source_anchors (
    anchor_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL REFERENCES research_packs(pack_id) ON DELETE CASCADE,
    pack_item_id TEXT NOT NULL REFERENCES research_pack_items(pack_item_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES pages(page_id) ON DELETE SET NULL,
    page_number INTEGER,
    anchor_index INTEGER NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    quote TEXT NOT NULL,
    match_method TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pack_item_id, anchor_index),
    CHECK (match_method IN ('exact_context', 'exact_page', 'normalized_context', 'normalized_page')),
    CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS pack_item_source_anchors_pack_idx
ON pack_item_source_anchors(pack_id, pack_item_id, anchor_index);

CREATE INDEX IF NOT EXISTS pack_item_source_anchors_page_idx
ON pack_item_source_anchors(page_id, page_number);

INSERT INTO schema_migrations (version, description)
VALUES ('004_source_anchors', 'Durable pack item source anchors for page-level citation highlighting')
ON CONFLICT (version) DO NOTHING;
