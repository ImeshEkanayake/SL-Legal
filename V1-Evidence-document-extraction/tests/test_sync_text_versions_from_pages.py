from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_text_sync_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "sync_text_versions_from_pages.py"
    spec = importlib.util.spec_from_file_location("sync_text_versions_from_pages", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_document_id_file_filter_ignores_blanks_and_comments(tmp_path):
    module = load_text_sync_module()
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("# comment\ndoc_one\n\n doc_two \n", encoding="utf-8")

    args = module.parse_args(["--document-id-file", str(document_id_file), "--document-id", "doc_three"])

    assert args.document_ids_filter == {"doc_one", "doc_two", "doc_three"}


def test_candidate_filter_sql_includes_page_text_guard():
    module = load_text_sync_module()
    args = module.parse_args(["--source-id", "PARL_ACTS", "--document-id", "doc_a"])

    where_sql, params = module.candidate_filter_sql(args)

    assert "EXISTS (SELECT 1 FROM pages p" in where_sql
    assert "length(btrim(p.text)) > 0" in where_sql
    assert params == {"document_ids": ["doc_a"], "source_ids": ["PARL_ACTS"]}


def test_summary_tracks_terminal_statuses():
    module = load_text_sync_module()
    summary = module.TextVersionSyncSummary(candidate_count=4)

    summary.add({"document_id": "a", "status": "synced", "byte_size": 10})
    summary.add({"document_id": "b", "status": "skipped_current"})
    summary.add({"document_id": "c", "status": "no_page_text"})
    summary.add({"document_id": "d", "status": "missing_source_asset"})

    assert summary.processed_count == 4
    assert summary.synced_count == 1
    assert summary.skipped_current_count == 1
    assert summary.skipped_no_page_text_count == 1
    assert summary.skipped_no_source_asset_count == 1
    assert summary.total_text_bytes == 10
    assert summary.status_counts == {
        "synced": 1,
        "skipped_current": 1,
        "no_page_text": 1,
        "missing_source_asset": 1,
    }
