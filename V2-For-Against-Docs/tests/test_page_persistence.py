from __future__ import annotations

from sl_legal_rag.chunking import PageRecord
from sl_legal_rag.page_persistence import quality_flags_for_page, stable_page_id


def test_stable_page_id_is_deterministic():
    first = stable_page_id("doc_1", "text", 3)
    second = stable_page_id("doc_1", "text", 3)

    assert first == second
    assert first.startswith("page_doc_1_text_00003_")


def test_quality_flags_for_empty_low_confidence_page():
    page = PageRecord(page_number=1, text="", error="extract failed", confidence=42.0, extraction_method="ocr")

    assert quality_flags_for_page(page) == [
        "page_extraction_error",
        "empty_page_text",
        "low_confidence_ocr",
        "very_short_page_text",
    ]
