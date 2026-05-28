from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_audit_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "audit_full_corpus_searchability.py"
    spec = importlib.util.spec_from_file_location("audit_full_corpus_searchability", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_document_orders_missing_asset_before_text_gaps():
    module = load_audit_module()

    classification, priority, action, language_plan = module.classify_document(
        {
            "original_asset_count": 0,
            "page_count": 0,
            "text_page_count": 0,
            "text_version_count": 0,
            "chunk_count": 0,
        }
    )

    assert classification == "needs_original_asset"
    assert priority == "critical"
    assert "object storage" in action
    assert "English" in language_plan


def test_classify_document_distinguishes_ocr_from_chunking():
    module = load_audit_module()

    needs_ocr, _, _, _ = module.classify_document(
        {
            "original_asset_count": 1,
            "page_count": 10,
            "text_page_count": 0,
            "text_version_count": 0,
            "chunk_count": 0,
        }
    )
    needs_chunks, _, _, _ = module.classify_document(
        {
            "original_asset_count": 1,
            "page_count": 10,
            "text_page_count": 10,
            "text_version_count": 1,
            "chunk_count": 0,
        }
    )

    assert needs_ocr == "needs_ocr_or_text_recovery"
    assert needs_chunks == "needs_chunk_indexing"


def test_classify_document_marks_fully_searchable_only_with_all_layers():
    module = load_audit_module()

    classification, priority, action, _ = module.classify_document(
        {
            "original_asset_count": 1,
            "page_count": 10,
            "text_page_count": 10,
            "text_version_count": 1,
            "english_text_version_count": 1,
            "chunk_count": 5,
        }
    )

    assert classification == "fully_searchable"
    assert priority == "none"
    assert action == "No action required."


def test_non_english_document_requires_labelled_translation_fallback():
    module = load_audit_module()

    classification, priority, action, language_plan = module.classify_document(
        {
            "language": "Sinhala",
            "original_asset_count": 1,
            "page_count": 10,
            "text_page_count": 10,
            "text_version_count": 1,
            "english_text_version_count": 0,
            "translation_text_version_count": 0,
            "chunk_count": 5,
        }
    )

    assert classification == "needs_translation_fallback"
    assert priority == "normal"
    assert "text_origin='translation'" in action
    assert "official English" in language_plan


def test_unknown_language_document_requires_detection_not_blind_translation():
    module = load_audit_module()

    classification, priority, action, language_plan = module.classify_document(
        {
            "language": "unknown",
            "original_asset_count": 1,
            "page_count": 10,
            "text_page_count": 10,
            "text_version_count": 1,
            "english_text_version_count": 0,
            "translation_text_version_count": 0,
            "chunk_count": 5,
        }
    )

    assert classification == "fully_searchable"
    assert priority == "none"
    assert action == "No action required."
    assert "Detect the source language" in language_plan
