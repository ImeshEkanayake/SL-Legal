from __future__ import annotations

from sl_legal_rag.chunking import PageRecord, chunk_pages, quality_flags_for_chunk


def test_quality_flags_for_low_confidence_ocr_chunk():
    flags = quality_flags_for_chunk(
        [PageRecord(page_number=1, text="uncertain text", confidence=64.0, extraction_method="ocr")],
        "uncertain text",
    )

    assert "ocr_text" in flags
    assert "low_confidence_ocr" in flags
    assert "very_short_chunk_text" in flags


def test_text_layer_quality_score_is_not_treated_as_ocr_confidence():
    flags = quality_flags_for_chunk(
        [PageRecord(page_number=1, text="official text layer", confidence=0.90, extraction_method="text_layer")],
        "official text layer with normal extractable text",
    )

    assert "low_confidence_ocr" not in flags
    assert "ocr_text" not in flags


def test_chunk_pages_carries_quality_flags_into_metadata():
    row = {
        "document_id": "doc_ocr",
        "source_id": "SC_OFFICIAL",
        "document_type": "Supreme Court Judgment",
        "title": "OCR Judgment",
        "year": "",
        "number": "",
        "date": "",
        "language": "unknown",
        "source_url": "",
        "local_path": "",
        "source_document_id": "",
        "legal_status": "official_court_material",
        "extraction_status": "text_empty_needs_ocr",
    }

    chunks = list(
        chunk_pages(
            row,
            [PageRecord(page_number=1, text="Recognised OCR text for a judgment.", confidence=65.0, extraction_method="ocr")],
        )
    )

    assert chunks[0].quality_flags == ["low_confidence_ocr", "ocr_text", "very_short_chunk_text"]
    assert chunks[0].metadata["quality_flags"] == chunks[0].quality_flags


def test_chunk_pages_labels_unreviewed_translation_fallbacks():
    row = {
        "document_id": "doc_translation",
        "source_id": "GOV_GAZETTES",
        "document_type": "Gazette",
        "title": "Translated Gazette",
        "year": "2026",
        "number": "",
        "date": "",
        "language": "English",
        "source_url": "",
        "local_path": "",
        "source_document_id": "2026-01-01:I:S",
        "legal_status": "official_source_translation_fallback",
        "extraction_status": "translated",
        "text_origin": "translation",
        "source_language": "Sinhala",
        "translated_from_language": "Sinhala",
        "translation_review_status": "machine_draft",
        "text_version_id": "dtv_translation_001",
    }

    chunks = list(
        chunk_pages(
            row,
            [PageRecord(page_number=1, text="Translated English fallback text for a Sinhala-only gazette source.")],
        )
    )

    assert "translated_text_fallback" in chunks[0].quality_flags
    assert "machine_translation_unreviewed" in chunks[0].quality_flags
    assert chunks[0].text_origin == "translation"
    assert chunks[0].translated_from_language == "Sinhala"
    assert chunks[0].metadata["translation_review_status"] == "machine_draft"


def test_chunk_pages_splits_single_oversized_translation_paragraph():
    row = {
        "document_id": "doc_translation_long",
        "source_id": "GOV_GAZETTES",
        "document_type": "Gazette",
        "title": "Long Translated Gazette",
        "year": "2026",
        "number": "",
        "date": "",
        "language": "English",
        "source_url": "",
        "local_path": "",
        "source_document_id": "",
        "legal_status": "official_source_translation_fallback",
        "extraction_status": "translated",
        "text_origin": "translation",
        "source_language": "Sinhala",
        "translated_from_language": "Sinhala",
        "translation_review_status": "machine_draft",
        "text_version_id": "dtv_translation_long",
        "page_anchor_status": "translation_full_text_no_page_map",
    }
    long_paragraph = " ".join(f"term{i}" for i in range(250))

    chunks = list(chunk_pages(row, [PageRecord(page_number=0, text=long_paragraph)], target_tokens=80, overlap_tokens=10))

    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 90 for chunk in chunks)
    assert all("missing_page_anchor" in chunk.quality_flags for chunk in chunks)
