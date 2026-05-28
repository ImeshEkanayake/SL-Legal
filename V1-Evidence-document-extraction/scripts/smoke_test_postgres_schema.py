#!/usr/bin/env python3
"""Run a rollback-only smoke test across the product database schema."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.rag.yml"


SMOKE_SQL = r"""
BEGIN;

INSERT INTO organizations (organization_id, name, slug)
VALUES ('org_smoke', 'Smoke Test Legal Team', 'smoke-test-legal-team');

INSERT INTO app_users (user_id, organization_id, email, display_name, role)
VALUES ('user_smoke_lawyer', 'org_smoke', 'smoke.lawyer@example.test', 'Smoke Lawyer', 'lawyer');

INSERT INTO organization_memberships (organization_id, user_id, role)
VALUES ('org_smoke', 'user_smoke_lawyer', 'owner');

INSERT INTO projects (project_id, organization_id, name, created_by_user_id)
VALUES ('project_smoke', 'org_smoke', 'Smoke Test Project', 'user_smoke_lawyer');

INSERT INTO cases (
    case_id, organization_id, project_id, case_number, title, jurisdiction,
    court, matter_type, created_by_user_id
)
VALUES (
    'case_smoke', 'org_smoke', 'project_smoke', 'SC/SMOKE/1',
    'Smoke Test Matter', 'Sri Lanka', 'Supreme Court', 'fundamental_rights',
    'user_smoke_lawyer'
);

INSERT INTO case_permissions (case_id, user_id, role, granted_by_user_id)
VALUES ('case_smoke', 'user_smoke_lawyer', 'owner', 'user_smoke_lawyer');

INSERT INTO case_parties (party_id, case_id, party_name, party_role)
VALUES ('party_smoke_client', 'case_smoke', 'Smoke Client', 'petitioner');

INSERT INTO case_raw_inputs (raw_input_id, case_id, input_type, content, submitted_by_user_id)
VALUES (
    'raw_smoke_facts', 'case_smoke', 'user_case_facts',
    'The employer refused to bargain with the trade union after the workers requested representation.',
    'user_smoke_lawyer'
);

INSERT INTO chat_threads (thread_id, organization_id, case_id, title, created_by_user_id)
VALUES ('thread_smoke', 'org_smoke', 'case_smoke', 'Smoke legal research thread', 'user_smoke_lawyer');

INSERT INTO chat_messages (message_id, thread_id, role, content, created_by_user_id)
VALUES ('msg_smoke_user', 'thread_smoke', 'user', 'Find law about refusing to bargain with a trade union.', 'user_smoke_lawyer');

INSERT INTO agent_runs (agent_run_id, organization_id, case_id, thread_id, agent_type, status, model)
VALUES ('agent_smoke_mece', 'org_smoke', 'case_smoke', 'thread_smoke', 'mece_case_structuring', 'complete', 'test-model');

INSERT INTO case_facts (
    fact_id, case_id, raw_input_id, fact_text, fact_category, certainty_label,
    materiality, disputed_status, source_span_start, source_span_end, source_quote,
    extracted_by_agent_run_id
)
VALUES (
    'fact_smoke_001', 'case_smoke', 'raw_smoke_facts',
    'The employer refused to bargain with the trade union.',
    'material_fact', 'explicitly_stated', 'high', 'unknown', 4, 58,
    'employer refused to bargain with the trade union', 'agent_smoke_mece'
);

INSERT INTO case_issues (issue_id, case_id, issue_text, issue_type, status, created_by_agent_run_id)
VALUES (
    'issue_smoke_001', 'case_smoke',
    'Whether refusing to bargain with the trade union is an unfair labour practice.',
    'statutory_issue', 'candidate', 'agent_smoke_mece'
);

INSERT INTO case_timeline_events (
    timeline_event_id, case_id, date_label, event_text, source_fact_id
)
VALUES (
    'timeline_smoke_001', 'case_smoke', 'date unknown',
    'Workers requested union representation and the employer refused to bargain.',
    'fact_smoke_001'
);

INSERT INTO documents (
    document_id, source_id, document_type, title, year, language,
    acquisition_status, extraction_status, legal_status
)
VALUES (
    'doc_smoke_retrieval', 'SMOKE_SOURCE', 'Act', 'Smoke Retrieval Act',
    2099, 'English', 'downloaded', 'text_extracted', 'test_fixture'
);

INSERT INTO case_documents (
    case_document_id, case_id, document_id, title, document_role,
    document_kind, local_path, file_hash
)
VALUES (
    'case_doc_smoke_001', 'case_smoke', 'doc_smoke_retrieval',
    'Smoke Retrieval Act', 'authority', 'official_pdf',
    'data/raw/smoke/smoke-retrieval-act.pdf',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
);

INSERT INTO file_assets (
    asset_id, document_id, case_document_id, asset_kind, storage_provider,
    storage_bucket, storage_key, storage_region, endpoint_url, content_type,
    byte_size, sha256, source_local_path, is_primary, metadata
)
VALUES (
    'asset_smoke_original_001', 'doc_smoke_retrieval', 'case_doc_smoke_001',
    'original', 'minio', 'sl-legal-corpus',
    'corpus/original/smoke_source/doc_smoke_retrieval/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf',
    'us-east-1', 'http://localhost:9000', 'application/pdf',
    12345, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'data/raw/smoke/smoke-retrieval-act.pdf', true, '{"smoke":true}'::jsonb
);

UPDATE documents
SET object_storage_provider = 'minio',
    object_storage_bucket = 'sl-legal-corpus',
    object_storage_key = 'corpus/original/smoke_source/doc_smoke_retrieval/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf',
    object_storage_uri = 'minio://sl-legal-corpus/corpus/original/smoke_source/doc_smoke_retrieval/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf',
    object_storage_synced_at = now(),
    primary_file_asset_id = 'asset_smoke_original_001'
WHERE document_id = 'doc_smoke_retrieval';

INSERT INTO retrieval_chunks (
    chunk_id, document_id, source_id, document_type, title, year,
    authority_level, page_start, page_end, chunk_index, chunk_text,
    token_estimate, language, citation, text_hash
)
VALUES (
    'chunk_smoke_retrieval_001', 'doc_smoke_retrieval', 'SMOKE_SOURCE',
    'Act', 'Smoke Retrieval Act', 2099, 1, 1, 1, 1,
    'No employer shall refuse to bargain with a qualifying trade union.',
    12, 'English', 'Smoke Retrieval Act s 1', 'sha256:smoke-retrieval-chunk'
);

INSERT INTO document_text_versions (
    text_version_id, document_id, source_asset_id, version_label,
    extraction_method, language, page_count, char_count, token_estimate,
    text_hash, full_text, text_quality_score, quality_flags, metadata
)
VALUES (
    'dtv_smoke_001', 'doc_smoke_retrieval', 'asset_smoke_original_001',
    'current-pages-v1', 'smoke_text_layer', 'English', 1, 66, 12,
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'No employer shall refuse to bargain with a qualifying trade union.',
    0.99, ARRAY[]::text[], '{"smoke":true}'::jsonb
);

INSERT INTO file_assets (
    asset_id, document_id, case_document_id, asset_kind, storage_provider,
    storage_bucket, storage_key, storage_region, endpoint_url, content_type,
    byte_size, sha256, source_local_path, is_primary, metadata
)
VALUES (
    'asset_smoke_translation_001', 'doc_smoke_retrieval', NULL,
    'translated_text', 'minio', 'sl-legal-corpus',
    'corpus/translations/smoke_source/doc_smoke_retrieval/english/translated_text_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.txt',
    'us-east-1', 'http://localhost:9000', 'text/plain; charset=utf-8',
    66, 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    'translation_pipeline', false,
    '{"smoke":true,"source_text_version_id":"dtv_smoke_001"}'::jsonb
);

INSERT INTO document_text_versions (
    text_version_id, document_id, source_asset_id, text_asset_id,
    version_label, extraction_method, language, page_count, char_count,
    token_estimate, text_hash, full_text, text_quality_score,
    quality_flags, text_origin, source_language, translated_from_language,
    translation_provider, translation_model, translation_review_status,
    source_text_version_id, metadata
)
VALUES (
    'dtv_smoke_translation_001', 'doc_smoke_retrieval',
    'asset_smoke_original_001', 'asset_smoke_translation_001',
    'translation-sinhala-to-english-v1', 'machine_translation',
    'English', 1, 66, 12,
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    'No employer shall refuse to bargain with a qualifying trade union.',
    0.80, ARRAY['translated_text_fallback','machine_translation_unreviewed']::text[],
    'translation', 'Sinhala', 'Sinhala', 'schema_smoke_provider',
    'schema-smoke-model', 'machine_draft', 'dtv_smoke_001',
    '{"smoke":true,"fallback_reason":"official_english_not_available"}'::jsonb
);

INSERT INTO document_digests (
    digest_id, document_id, file_asset_id, text_version_id, digest_type,
    algorithm, digest_value, byte_size, page_count, metadata
)
VALUES
(
    'digest_smoke_original_001', 'doc_smoke_retrieval',
    'asset_smoke_original_001', NULL, 'original_file', 'sha256',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    12345, NULL, '{"smoke":true}'::jsonb
),
(
    'digest_smoke_text_001', 'doc_smoke_retrieval',
    NULL, 'dtv_smoke_001', 'extracted_full_text', 'sha256',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    66, 1, '{"smoke":true}'::jsonb
),
(
    'digest_smoke_translation_001', 'doc_smoke_retrieval',
    'asset_smoke_translation_001', 'dtv_smoke_translation_001',
    'translated_full_text', 'sha256',
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    66, 1, '{"smoke":true}'::jsonb
);

INSERT INTO case_document_relevance (
    relevance_id, case_id, case_document_id, document_id,
    relevance_score, confidence_score, relevance_band, source,
    status, rationale, metadata
)
VALUES (
    'rel_smoke_case_doc_001', 'case_smoke', 'case_doc_smoke_001',
    'doc_smoke_retrieval', 1.0, 1.0, 'direct', 'case_attachment',
    'included', 'Attached smoke document is directly relevant.',
    '{"smoke":true}'::jsonb
);

INSERT INTO research_packs (
    pack_id, case_id, source_thread_id, source_agent_run_id, query, query_class,
    status, token_budget, retrieval_config
)
VALUES (
    'pack_smoke_001', 'case_smoke', 'thread_smoke', 'agent_smoke_mece',
    'industrial disputes trade union bargaining', 'statute_lookup',
    'complete', 12000, '{"mode":"smoke"}'::jsonb
);

INSERT INTO research_pack_items (
    pack_item_id, pack_id, chunk_id, rank, fused_score, selection_reason,
    selected_text, page_start, page_end
)
SELECT
    'pack_item_smoke_001', 'pack_smoke_001', chunk_id, 1, 1.0,
    'smoke test selected first available chunk',
    left(chunk_text, 500), page_start, page_end
FROM retrieval_chunks
ORDER BY chunk_id
LIMIT 1;

INSERT INTO case_research_packs (case_id, pack_id, purpose, created_by_agent_run_id, created_by_user_id)
VALUES ('case_smoke', 'pack_smoke_001', 'initial_research', 'agent_smoke_mece', 'user_smoke_lawyer');

INSERT INTO legal_claims (
    claim_id, case_id, thread_id, message_id, pack_id, claim_text, claim_type,
    support_status, created_by_agent_run_id
)
VALUES (
    'claim_smoke_001', 'case_smoke', 'thread_smoke', 'msg_smoke_user', 'pack_smoke_001',
    'The retrieved pack contains authority relevant to refusal to bargain with a trade union.',
    'research_finding', 'supported', 'agent_smoke_mece'
);

INSERT INTO legal_claim_citations (claim_id, pack_item_id)
VALUES ('claim_smoke_001', 'pack_item_smoke_001');

INSERT INTO drafts (
    draft_id, case_id, thread_id, pack_id, draft_type, title, content_markdown,
    created_by_agent_run_id, created_by_user_id
)
VALUES (
    'draft_smoke_001', 'case_smoke', 'thread_smoke', 'pack_smoke_001',
    'research_note', 'Smoke Research Note',
    'This draft is generated only inside a rollback smoke test.',
    'agent_smoke_mece', 'user_smoke_lawyer'
);

INSERT INTO review_items (
    review_item_id, case_id, item_type, item_id, status, assigned_to_user_id
)
VALUES ('review_smoke_001', 'case_smoke', 'legal_claim', 'claim_smoke_001', 'pending', 'user_smoke_lawyer');

INSERT INTO app_tasks (task_id, organization_id, case_id, title, created_by_user_id)
VALUES ('task_smoke_001', 'org_smoke', 'case_smoke', 'Review smoke claim', 'user_smoke_lawyer');

INSERT INTO background_jobs (job_id, job_type, status, input)
VALUES ('job_smoke_001', 'schema_smoke_job', 'queued', '{"case_id":"case_smoke"}'::jsonb);

INSERT INTO ingestion_runs (
    ingestion_run_id, source_id, pipeline_name, pipeline_version, status,
    manifest_path, corpus_root, input_manifest_hash, config
)
VALUES (
    'ingest_smoke_001', 'SMOKE_SOURCE', 'schema_smoke_ingestion', '2026.05',
    'running', 'data/manifests/smoke.csv', 'data/raw/smoke',
    'sha256:smoke-manifest', '{"ocr":"disabled"}'::jsonb
);

INSERT INTO documents (
    document_id, source_id, source_document_id, document_type, title,
    year, language, source_url, local_path, file_hash, acquisition_status,
    extraction_status, ocr_required, text_quality_score,
    current_ingestion_run_id, last_ingested_at
)
VALUES (
    'doc_smoke_ingested', 'SMOKE_SOURCE', 'smoke-source-doc-001',
    'smoke_document', 'Smoke Ingested Document', 2026, 'en',
    'https://example.test/smoke-source-doc-001',
    'data/raw/smoke/smoke-source-doc-001.pdf', 'sha256:smoke-file',
    'downloaded', 'extracted', false, 0.99, 'ingest_smoke_001', now()
);

INSERT INTO document_ingestion_events (
    ingestion_run_id, document_id, source_id, source_document_id, local_path,
    file_hash, stage, status, extraction_method, ocr_required, page_count,
    chunk_count, text_hash, text_quality_score, quality_flags, metadata
)
VALUES (
    'ingest_smoke_001', 'doc_smoke_ingested', 'SMOKE_SOURCE',
    'smoke-source-doc-001', 'data/raw/smoke/smoke-source-doc-001.pdf',
    'sha256:smoke-file', 'page_extraction', 'extracted', 'smoke_text_layer',
    false, 2, 1, 'sha256:smoke-text', 0.99, ARRAY[]::text[],
    '{"smoke":true}'::jsonb
);

INSERT INTO document_versions (
    document_id, version_label, file_hash, text_hash, extraction_method,
    ocr_confidence_band, source_snapshot, ingestion_run_id, page_count,
    chunk_count, quality_flags
)
VALUES (
    'doc_smoke_ingested', 'smoke-v1', 'sha256:smoke-file',
    'sha256:smoke-text', 'smoke_text_layer', 'high',
    '{"smoke":true}'::jsonb, 'ingest_smoke_001', 2, 1, ARRAY[]::text[]
);

INSERT INTO audit_events (
    organization_id, case_id, user_id, event_type, entity_type, entity_id, after_state
)
VALUES (
    'org_smoke', 'case_smoke', 'user_smoke_lawyer',
    'schema_smoke_test', 'case', 'case_smoke', '{"ok":true}'::jsonb
);

SELECT
    (SELECT count(*) FROM cases WHERE case_id = 'case_smoke')::text
    || '|' ||
    (SELECT count(*) FROM case_facts WHERE case_id = 'case_smoke')::text
    || '|' ||
    (SELECT count(*) FROM research_pack_items WHERE pack_id = 'pack_smoke_001')::text
    || '|' ||
    (SELECT count(*) FROM legal_claim_citations WHERE claim_id = 'claim_smoke_001')::text
    AS smoke_counts;

ROLLBACK;
"""


def main(_: list[str]) -> int:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "rag-postgres",
            "psql",
            "-U",
            "sl_legal",
            "-d",
            "sl_legal_assist",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            SMOKE_SQL,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        return result.returncode
    for line in result.stdout.strip().splitlines():
        if line.count("|") == 3:
            print(line)
            return 0
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
