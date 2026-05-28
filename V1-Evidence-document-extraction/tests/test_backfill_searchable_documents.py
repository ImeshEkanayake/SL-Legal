from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path


def load_backfill_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "backfill_searchable_documents.py"
    spec = importlib.util.spec_from_file_location("backfill_searchable_documents", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_english_ocr_filter_uses_metadata_not_hash_suffixes():
    module = load_backfill_module()

    sql = module.english_ocr_filter_sql()

    assert "source_document_id" in sql
    assert "/english/" in sql
    assert "_e_" not in sql


def test_extract_candidate_query_requires_downloaded_pdf_without_pages():
    module = load_backfill_module()
    args = module.parse_args(["--source-id", "GOV_GAZETTES", "--batch-size-documents", "25"])
    params: dict[str, object] = {"limit": args.batch_size_documents}

    source_sql = module.source_filter_sql(args, params)
    assert not args.retry_failed_extraction

    assert "d.source_id = ANY" in source_sql
    assert params["source_ids"] == ["GOV_GAZETTES"]


def test_failed_extraction_retry_is_opt_in():
    module = load_backfill_module()
    default_args = module.parse_args([])
    retry_args = module.parse_args(["--retry-failed-extraction"])

    assert not default_args.retry_failed_extraction
    assert retry_args.retry_failed_extraction


def test_stage_commands_include_full_search_stack(tmp_path):
    module = load_backfill_module()
    args = module.parse_args(
        [
            "--execute",
            "--report-dir",
            str(tmp_path),
            "--stamp",
            "20260526T000000Z",
            "--embedding-provider",
            "sentence-transformers",
            "--embedding-model",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "--embedding-dimensions",
            "384",
        ]
    )
    plan = module.BatchPlan(
        batch_number=1,
        extract_ids=[],
        ocr_ids=[],
        index_ids=["doc_a"],
        extract_file="data/indexes/unused_extract.txt",
        ocr_file="data/indexes/unused_ocr.txt",
        index_file="data/indexes/index_ids.txt",
        chunks_file="data/indexes/chunks.jsonl",
    )

    commands = module.stage_commands(args, plan)
    flattened = [" ".join(command) for command in commands]

    assert any("sync_corpus_assets_to_object_storage.py" in command for command in flattened)
    assert any("sync_text_versions_from_pages.py" in command for command in flattened)
    assert any("build_rag_chunks_from_postgres.py" in command and "--include-gazettes" in command for command in flattened)
    assert any("load_rag_chunks_postgres.py" in command for command in flattened)
    assert any("load_rag_chunks_opensearch.py" in command for command in flattened)
    assert any("load_rag_chunks_qdrant.py" in command for command in flattened)


def test_ocr_command_passes_tessdata_dir(tmp_path):
    module = load_backfill_module()
    args = module.parse_args(
        [
            "--report-dir",
            str(tmp_path),
            "--stamp",
            "20260526T000000Z",
            "--ocr-language",
            "eng+sin+tam",
            "--ocr-tessdata-dir",
            ".codex_deps/tessdata_free",
        ]
    )
    plan = module.BatchPlan(
        batch_number=1,
        extract_ids=[],
        ocr_ids=["doc_a"],
        index_ids=[],
        extract_file="data/indexes/unused_extract.txt",
        ocr_file="data/indexes/ocr_ids.txt",
        index_file="data/indexes/unused_index.txt",
        chunks_file="data/indexes/unused_chunks.jsonl",
    )

    commands = module.stage_commands(args, plan)
    ocr_command = next(command for command in commands if "scripts/ocr_empty_pdf_pages_to_postgres.py" in command)

    assert "--language" in ocr_command
    assert "eng+sin+tam" in ocr_command
    assert "--tessdata-dir" in ocr_command
    assert ".codex_deps/tessdata_free" in ocr_command


def test_document_id_file_filter_is_applied(tmp_path):
    module = load_backfill_module()
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("doc_a\n", encoding="utf-8")
    args = module.parse_args(["--document-id-file", str(document_id_file)])
    params: dict[str, object] = {}

    sql = module.source_filter_sql(args, params)

    assert "d.document_id = ANY" in sql
    assert params["document_ids"] == ["doc_a"]


def test_ocr_all_languages_removes_english_only_filter():
    module = load_backfill_module()
    default_args = module.parse_args([])
    all_language_args = module.parse_args(["--ocr-all-languages"])

    assert not default_args.ocr_all_languages
    assert all_language_args.ocr_all_languages


def test_backfill_skips_ocr_failed_until_redownload_repairs_file():
    module = load_backfill_module()

    source = inspect.getsource(module.fetch_english_ocr_candidate_ids)

    assert "coalesce(d.extraction_status, '') <> 'ocr_failed'" in source


def test_partial_recovery_stages_are_allowed_to_continue():
    module = load_backfill_module()

    assert module.is_partial_recovery_stage(["python", "scripts/extract_missing_pdf_pages_to_postgres.py"])
    assert module.is_partial_recovery_stage(["python", "scripts/ocr_empty_pdf_pages_to_postgres.py"])
    assert not module.is_partial_recovery_stage(["python", "scripts/load_rag_chunks_qdrant.py"])
