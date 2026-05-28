CREATE UNIQUE INDEX IF NOT EXISTS case_document_relevance_case_document_source_idx
ON case_document_relevance(case_id, document_id, source)
WHERE document_id IS NOT NULL AND case_document_id IS NULL;

CREATE INDEX IF NOT EXISTS case_document_relevance_pack_score_idx
ON case_document_relevance(research_pack_id, relevance_score DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('015_case_document_relevance_indexes', 'Uniqueness and lookup indexes for case document relevance scoring')
ON CONFLICT (version) DO NOTHING;
