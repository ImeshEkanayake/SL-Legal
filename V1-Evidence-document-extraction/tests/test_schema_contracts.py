from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "rag" / "sql"
DB_SCHEMA_DOC = PROJECT_ROOT / "rag" / "DB_SCHEMA.md"
SCHEMA_SMOKE_TEST = PROJECT_ROOT / "scripts" / "smoke_test_postgres_schema.py"


REQUIRED_TABLES = {
    "documents",
    "document_versions",
    "ingestion_runs",
    "document_ingestion_events",
    "pages",
    "legal_units",
    "retrieval_chunks",
    "citations",
    "embedding_runs",
    "research_packs",
    "research_pack_items",
    "missing_sources",
    "retrieval_events",
    "organizations",
    "app_users",
    "organization_memberships",
    "projects",
    "cases",
    "case_permissions",
    "case_documents",
    "case_raw_inputs",
    "case_facts",
    "case_issues",
    "chat_threads",
    "chat_messages",
    "agent_runs",
    "tool_calls",
    "legal_claims",
    "legal_claim_citations",
    "drafts",
    "review_items",
    "background_jobs",
    "audit_events",
    "pack_item_source_anchors",
    "api_rate_limits",
    "operational_metric_rollups",
    "file_assets",
    "document_text_versions",
    "document_digests",
    "case_document_relevance",
}


def test_schema_migration_files_are_contiguous_and_documented():
    sql_files = sorted(path.name for path in SQL_DIR.glob("*.sql"))
    migration_numbers = [int(name.split("_", 1)[0]) for name in sql_files]

    assert migration_numbers == list(range(1, len(sql_files) + 1))

    db_schema_doc = DB_SCHEMA_DOC.read_text(encoding="utf-8")
    for sql_file in sql_files:
        assert sql_file in db_schema_doc


def test_required_phase_4_tables_are_created_by_migrations():
    migration_sql = "\n".join(path.read_text(encoding="utf-8") for path in SQL_DIR.glob("*.sql"))
    created_tables = {
        match.group(1)
        for match in re.finditer(
            r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            migration_sql,
        )
    }
    altered_tables = {
        match.group(1)
        for match in re.finditer(
            r"ALTER TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            migration_sql,
        )
    }

    assert REQUIRED_TABLES.difference(created_tables.union(altered_tables)) == set()


def test_translation_fallback_provenance_is_first_class_schema_contract():
    migration_sql = "\n".join(path.read_text(encoding="utf-8") for path in SQL_DIR.glob("*.sql"))

    for column_name in (
        "text_origin",
        "source_text_version_id",
        "translated_from_language",
        "translation_provider",
        "translation_review_status",
        "official_replacement_document_id",
    ):
        assert column_name in migration_sql

    assert "translated_text" in migration_sql
    assert "translated_full_text" in migration_sql
    assert "document_text_versions_translation_contract_check" in migration_sql
    assert "retrieval_chunks_text_origin_check" in migration_sql


def test_schema_smoke_test_is_rollback_only_and_covers_legal_workflow_tables():
    smoke_test = SCHEMA_SMOKE_TEST.read_text(encoding="utf-8")

    assert "BEGIN;" in smoke_test
    assert "ROLLBACK;" in smoke_test
    for table_name in (
        "case_facts",
        "research_pack_items",
        "legal_claim_citations",
        "ingestion_runs",
        "document_ingestion_events",
        "file_assets",
        "document_text_versions",
        "document_digests",
        "case_document_relevance",
        "translated_text",
        "translated_full_text",
        "text_origin",
        "audit_events",
    ):
        assert table_name in smoke_test
