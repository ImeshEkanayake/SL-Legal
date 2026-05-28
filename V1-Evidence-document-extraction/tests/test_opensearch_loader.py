from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_opensearch_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "load_rag_chunks_opensearch.py"
    spec = importlib.util.spec_from_file_location("load_rag_chunks_opensearch", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sanitize_document_omits_empty_date_for_opensearch_mapping():
    module = load_opensearch_module()

    sanitized = module.sanitize_document({"chunk_id": "chunk_1", "date": "", "title": "Judgment"})

    assert "date" not in sanitized
    assert sanitized["chunk_id"] == "chunk_1"


def test_opensearch_loader_supports_recreate_for_full_clean_reloads():
    module = load_opensearch_module()
    args = module.parse_args(["--recreate"])

    assert args.recreate is True
