from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_export_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_rag_chunks_from_postgres.py"
    spec = importlib.util.spec_from_file_location("export_rag_chunks_from_postgres", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_serializes_provenance_fields():
    module = load_export_module()

    payload = module.serialize_chunk(
        {
            "chunk_id": "chunk_1",
            "year": None,
            "quality_flags": None,
            "metadata": {"text_version_id": "dtv_1"},
            "text_version_id": "dtv_1",
            "text_origin": "source",
            "source_language": "English",
            "translated_from_language": None,
            "translation_review_status": None,
        }
    )

    assert payload["year"] == ""
    assert payload["quality_flags"] == []
    assert payload["text_version_id"] == "dtv_1"
    assert payload["metadata"]["text_version_id"] == "dtv_1"


def test_export_rejects_invalid_batch_size():
    module = load_export_module()

    try:
        module.parse_args(["--batch-size", "0"])
    except SystemExit:
        return
    raise AssertionError("expected invalid batch size to fail")
