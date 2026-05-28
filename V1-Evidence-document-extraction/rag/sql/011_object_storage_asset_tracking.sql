CREATE TABLE IF NOT EXISTS file_assets (
    asset_id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(document_id) ON DELETE SET NULL,
    case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE SET NULL,
    asset_kind TEXT NOT NULL,
    storage_provider TEXT NOT NULL,
    storage_bucket TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    storage_region TEXT,
    endpoint_url TEXT,
    content_type TEXT,
    byte_size BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    etag TEXT,
    source_local_path TEXT,
    source_url TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT false,
    created_by_ingestion_run_id TEXT REFERENCES ingestion_runs(ingestion_run_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (asset_kind IN (
        'original',
        'extracted_text',
        'ocr_text',
        'page_jsonl',
        'thumbnail',
        'export',
        'case_upload',
        'other'
    )),
    CHECK (storage_provider IN ('minio', 's3', 'gcs', 'local_s3_compatible')),
    CHECK (byte_size >= 0),
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (storage_provider, storage_bucket, storage_key)
);

CREATE INDEX IF NOT EXISTS file_assets_document_kind_idx
ON file_assets(document_id, asset_kind, is_primary DESC);

CREATE INDEX IF NOT EXISTS file_assets_case_document_idx
ON file_assets(case_document_id, asset_kind);

CREATE INDEX IF NOT EXISTS file_assets_sha256_idx
ON file_assets(sha256);

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS object_storage_provider TEXT,
    ADD COLUMN IF NOT EXISTS object_storage_bucket TEXT,
    ADD COLUMN IF NOT EXISTS object_storage_key TEXT,
    ADD COLUMN IF NOT EXISTS object_storage_uri TEXT,
    ADD COLUMN IF NOT EXISTS object_storage_synced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS primary_file_asset_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'documents'
          AND constraint_name = 'documents_primary_file_asset_id_fkey'
    ) THEN
        ALTER TABLE documents
            ADD CONSTRAINT documents_primary_file_asset_id_fkey
            FOREIGN KEY (primary_file_asset_id)
            REFERENCES file_assets(asset_id)
            ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE case_documents
    ADD COLUMN IF NOT EXISTS file_asset_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'case_documents'
          AND constraint_name = 'case_documents_file_asset_id_fkey'
    ) THEN
        ALTER TABLE case_documents
            ADD CONSTRAINT case_documents_file_asset_id_fkey
            FOREIGN KEY (file_asset_id)
            REFERENCES file_assets(asset_id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS document_text_versions (
    text_version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    source_asset_id TEXT REFERENCES file_assets(asset_id) ON DELETE SET NULL,
    text_asset_id TEXT REFERENCES file_assets(asset_id) ON DELETE SET NULL,
    version_label TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    language TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    token_estimate INTEGER,
    text_hash TEXT NOT NULL,
    full_text TEXT NOT NULL,
    ocr_confidence_mean NUMERIC(5,2),
    ocr_confidence_band TEXT,
    text_quality_score NUMERIC(4,2),
    quality_flags TEXT[] NOT NULL DEFAULT '{}',
    created_by_ingestion_run_id TEXT REFERENCES ingestion_runs(ingestion_run_id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (page_count >= 0),
    CHECK (char_count >= 0),
    CHECK (text_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE (document_id, version_label)
);

CREATE INDEX IF NOT EXISTS document_text_versions_document_created_idx
ON document_text_versions(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS document_text_versions_text_hash_idx
ON document_text_versions(text_hash);

CREATE TABLE IF NOT EXISTS document_digests (
    digest_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    file_asset_id TEXT REFERENCES file_assets(asset_id) ON DELETE SET NULL,
    text_version_id TEXT REFERENCES document_text_versions(text_version_id) ON DELETE SET NULL,
    digest_type TEXT NOT NULL,
    algorithm TEXT NOT NULL DEFAULT 'sha256',
    digest_value TEXT NOT NULL,
    byte_size BIGINT,
    page_count INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (digest_type IN (
        'original_file',
        'extracted_full_text',
        'page_text_set',
        'retrieval_chunk_set',
        'manifest_row',
        'other'
    )),
    CHECK (algorithm IN ('sha256')),
    CHECK (digest_value ~ '^[0-9a-f]{64}$'),
    UNIQUE (document_id, digest_type, algorithm, digest_value)
);

CREATE INDEX IF NOT EXISTS document_digests_document_type_idx
ON document_digests(document_id, digest_type, created_at DESC);

CREATE TABLE IF NOT EXISTS case_document_relevance (
    relevance_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    case_document_id TEXT REFERENCES case_documents(case_document_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(document_id) ON DELETE CASCADE,
    relevance_score NUMERIC(8,6) NOT NULL,
    confidence_score NUMERIC(8,6),
    relevance_band TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    rationale TEXT NOT NULL,
    query_text TEXT,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    research_pack_id TEXT REFERENCES research_packs(pack_id) ON DELETE SET NULL,
    reviewed_by_user_id TEXT REFERENCES app_users(user_id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (relevance_score >= 0 AND relevance_score <= 1),
    CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CHECK (relevance_band IN ('direct', 'strong', 'moderate', 'weak', 'background', 'irrelevant', 'unknown')),
    CHECK (source IN ('case_attachment', 'retrieval', 'llm_review', 'lawyer_review', 'importer')),
    CHECK (status IN ('candidate', 'included', 'rejected', 'reviewed', 'superseded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS case_document_relevance_case_doc_source_idx
ON case_document_relevance(case_id, case_document_id, source)
WHERE case_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS case_document_relevance_case_score_idx
ON case_document_relevance(case_id, relevance_score DESC, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('011_object_storage_asset_tracking', 'Object-storage file assets, text versions, document digests, and case document relevance')
ON CONFLICT (version) DO NOTHING;
