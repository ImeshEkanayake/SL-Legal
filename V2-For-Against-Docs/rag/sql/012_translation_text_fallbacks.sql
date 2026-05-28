ALTER TABLE document_text_versions
    ADD COLUMN IF NOT EXISTS text_origin TEXT NOT NULL DEFAULT 'source',
    ADD COLUMN IF NOT EXISTS source_language TEXT,
    ADD COLUMN IF NOT EXISTS translated_from_language TEXT,
    ADD COLUMN IF NOT EXISTS translation_provider TEXT,
    ADD COLUMN IF NOT EXISTS translation_model TEXT,
    ADD COLUMN IF NOT EXISTS translation_review_status TEXT,
    ADD COLUMN IF NOT EXISTS source_text_version_id TEXT,
    ADD COLUMN IF NOT EXISTS official_replacement_document_id TEXT,
    ADD COLUMN IF NOT EXISTS superseded_by_text_version_id TEXT,
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'document_text_versions'
          AND constraint_name = 'document_text_versions_source_text_version_id_fkey'
    ) THEN
        ALTER TABLE document_text_versions
            ADD CONSTRAINT document_text_versions_source_text_version_id_fkey
            FOREIGN KEY (source_text_version_id)
            REFERENCES document_text_versions(text_version_id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'document_text_versions'
          AND constraint_name = 'document_text_versions_official_replacement_document_id_fkey'
    ) THEN
        ALTER TABLE document_text_versions
            ADD CONSTRAINT document_text_versions_official_replacement_document_id_fkey
            FOREIGN KEY (official_replacement_document_id)
            REFERENCES documents(document_id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'document_text_versions'
          AND constraint_name = 'document_text_versions_superseded_by_text_version_id_fkey'
    ) THEN
        ALTER TABLE document_text_versions
            ADD CONSTRAINT document_text_versions_superseded_by_text_version_id_fkey
            FOREIGN KEY (superseded_by_text_version_id)
            REFERENCES document_text_versions(text_version_id)
            ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE document_text_versions
    DROP CONSTRAINT IF EXISTS document_text_versions_text_origin_check,
    ADD CONSTRAINT document_text_versions_text_origin_check
        CHECK (text_origin IN ('source', 'normalized_source', 'translation'));

ALTER TABLE document_text_versions
    DROP CONSTRAINT IF EXISTS document_text_versions_translation_review_status_check,
    ADD CONSTRAINT document_text_versions_translation_review_status_check
        CHECK (
            translation_review_status IS NULL OR translation_review_status IN (
                'not_applicable',
                'machine_draft',
                'needs_legal_review',
                'lawyer_approved',
                'superseded_by_official',
                'rejected'
            )
        );

ALTER TABLE document_text_versions
    DROP CONSTRAINT IF EXISTS document_text_versions_translation_contract_check,
    ADD CONSTRAINT document_text_versions_translation_contract_check
        CHECK (
            text_origin <> 'translation'
            OR (
                language IS NOT NULL
                AND source_text_version_id IS NOT NULL
                AND translated_from_language IS NOT NULL
                AND translation_provider IS NOT NULL
                AND translation_review_status IS NOT NULL
            )
        );

CREATE INDEX IF NOT EXISTS document_text_versions_origin_document_idx
ON document_text_versions(document_id, text_origin, language, created_at DESC);

CREATE INDEX IF NOT EXISTS document_text_versions_source_version_idx
ON document_text_versions(source_text_version_id)
WHERE source_text_version_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS document_text_versions_translation_replacement_idx
ON document_text_versions(official_replacement_document_id, translation_review_status)
WHERE official_replacement_document_id IS NOT NULL;

ALTER TABLE file_assets
    DROP CONSTRAINT IF EXISTS file_assets_asset_kind_check,
    ADD CONSTRAINT file_assets_asset_kind_check
    CHECK (asset_kind IN (
        'original',
        'extracted_text',
        'ocr_text',
        'translated_text',
        'page_jsonl',
        'thumbnail',
        'export',
        'case_upload',
        'other'
    ));

ALTER TABLE document_digests
    DROP CONSTRAINT IF EXISTS document_digests_digest_type_check,
    ADD CONSTRAINT document_digests_digest_type_check
    CHECK (digest_type IN (
        'original_file',
        'extracted_full_text',
        'translated_full_text',
        'page_text_set',
        'retrieval_chunk_set',
        'manifest_row',
        'other'
    ));

ALTER TABLE retrieval_chunks
    ADD COLUMN IF NOT EXISTS text_version_id TEXT,
    ADD COLUMN IF NOT EXISTS text_origin TEXT NOT NULL DEFAULT 'source',
    ADD COLUMN IF NOT EXISTS source_language TEXT,
    ADD COLUMN IF NOT EXISTS translated_from_language TEXT,
    ADD COLUMN IF NOT EXISTS translation_review_status TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'retrieval_chunks'
          AND constraint_name = 'retrieval_chunks_text_version_id_fkey'
    ) THEN
        ALTER TABLE retrieval_chunks
            ADD CONSTRAINT retrieval_chunks_text_version_id_fkey
            FOREIGN KEY (text_version_id)
            REFERENCES document_text_versions(text_version_id)
            ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE retrieval_chunks
    DROP CONSTRAINT IF EXISTS retrieval_chunks_text_origin_check,
    ADD CONSTRAINT retrieval_chunks_text_origin_check
        CHECK (text_origin IN ('source', 'normalized_source', 'translation'));

ALTER TABLE retrieval_chunks
    DROP CONSTRAINT IF EXISTS retrieval_chunks_translation_review_status_check,
    ADD CONSTRAINT retrieval_chunks_translation_review_status_check
        CHECK (
            translation_review_status IS NULL OR translation_review_status IN (
                'not_applicable',
                'machine_draft',
                'needs_legal_review',
                'lawyer_approved',
                'superseded_by_official',
                'rejected'
            )
        );

CREATE INDEX IF NOT EXISTS retrieval_chunks_text_origin_idx
ON retrieval_chunks(text_origin, language, authority_level);

CREATE INDEX IF NOT EXISTS retrieval_chunks_text_version_idx
ON retrieval_chunks(text_version_id)
WHERE text_version_id IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('012_translation_text_fallbacks', 'Explicit translated-text fallback provenance for text versions and retrieval chunks')
ON CONFLICT (version) DO NOTHING;
