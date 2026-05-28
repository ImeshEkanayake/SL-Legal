from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_backfill_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "backfill_chunk_text_versions.py"
    spec = importlib.util.spec_from_file_location("backfill_chunk_text_versions", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_document_filter_scopes_to_document_ids():
    module = load_backfill_module()
    args = module.parse_args(["--document-id", "doc_1", "--document-id", "doc_2"])

    where_sql, params = module.document_filter(args, "rc")

    assert "rc.document_id = ANY" in where_sql
    assert params == [["doc_1", "doc_2"]]


def test_document_filter_uses_limit_only_without_document_ids():
    module = load_backfill_module()
    args = module.parse_args(["--limit", "25"])
    args.selected_document_ids = ["doc_7", "doc_8"]
    args.document_scope_resolved = True

    where_sql, params = module.document_filter(args, "rc")

    assert "rc.document_id = ANY" in where_sql
    assert params == [["doc_7", "doc_8"]]


def test_document_filter_rejects_unresolved_limit_scope():
    module = load_backfill_module()
    args = module.parse_args(["--limit", "25"])

    try:
        module.document_filter(args, "rc")
    except RuntimeError as exc:
        assert "document scope" in str(exc)
    else:
        raise AssertionError("Expected unresolved --limit scope to fail")
