from __future__ import annotations

from sl_legal_rag.extraction_quality import (
    OcrConfidenceBand,
    aggregate_document_quality,
    confidence_band,
    evaluate_extracted_text,
)
from sl_legal_rag.models import LegalResearchPack
from sl_legal_rag.product_policy import source_reliability_warnings


def test_ocr_confidence_bands_are_stable():
    assert confidence_band(0.99) == OcrConfidenceBand.HIGH
    assert confidence_band(0.90) == OcrConfidenceBand.MEDIUM
    assert confidence_band(0.75) == OcrConfidenceBand.LOW
    assert confidence_band(0.50) == OcrConfidenceBand.UNUSABLE
    assert confidence_band(None) == OcrConfidenceBand.UNKNOWN


def test_empty_text_is_blocked_from_legal_answer_context():
    decision = evaluate_extracted_text("", extraction_method="pdf_text_layer")

    assert "empty_text" in decision.quality_flags
    assert not decision.legal_answer_eligible
    assert decision.requires_manual_review


def test_low_confidence_ocr_is_blocked_and_reviewable():
    decision = evaluate_extracted_text(
        "This OCR text is readable enough to have characters but confidence is too low for legal reliance.",
        extraction_method="tesseract_ocr",
        ocr_confidence=0.74,
    )

    assert decision.confidence_band == OcrConfidenceBand.LOW
    assert "low_confidence_ocr" in decision.quality_flags
    assert not decision.legal_answer_eligible
    assert decision.requires_manual_review


def test_high_confidence_text_layer_is_eligible():
    decision = evaluate_extracted_text(
        "This official legal text layer contains enough clean alphanumeric text to be eligible for retrieval context. "
        "The passage is not OCR-derived and has no replacement characters.",
        extraction_method="pdf_text_layer",
    )

    assert decision.legal_answer_eligible
    assert not decision.requires_manual_review
    assert decision.quality_score > 0.5


def test_document_quality_aggregates_blocked_pages():
    good = evaluate_extracted_text(
        "A clean extracted page with enough legal text to support retrieval and source inspection.",
        extraction_method="pdf_text_layer",
    )
    bad = evaluate_extracted_text("", extraction_method="pdf_text_layer")

    aggregate = aggregate_document_quality([good, bad])

    assert aggregate.page_count == 2
    assert aggregate.eligible_page_count == 1
    assert aggregate.blocked_page_count == 1
    assert not aggregate.legal_answer_eligible
    assert "empty_text" in aggregate.quality_flags


def test_pack_policy_warns_on_blocking_extraction_quality_flags():
    pack = LegalResearchPack.model_validate(
        {
            "pack_id": "pack_quality",
            "query": "gazette commencement",
            "query_class": "general_research",
            "filters": {},
            "retrieval_config": {},
            "items": [
                {
                    "pack_item_id": "pack_quality_item_001",
                    "chunk_id": "chunk_quality_001",
                    "document_id": "doc_quality_001",
                    "title": "Gazette Notice",
                    "document_type": "Gazette",
                    "source_id": "GOV_GAZETTES",
                    "authority_level": 2,
                    "citation": "Gazette Notice",
                    "text": "Low confidence OCR text.",
                    "fused_score": 1.0,
                    "selection_reason": "quality fixture",
                    "metadata": {"quality_flags": ["low_confidence_ocr"]},
                }
            ],
        }
    )

    warnings = source_reliability_warnings(pack)

    assert any("OCR quality" in warning or "quality flags" in warning for warning in warnings)


def test_pack_policy_warns_on_translated_fallback_text():
    pack = LegalResearchPack.model_validate(
        {
            "pack_id": "pack_translation",
            "query": "gazette commencement",
            "query_class": "general_research",
            "filters": {},
            "retrieval_config": {},
            "items": [
                {
                    "pack_item_id": "pack_translation_item_001",
                    "chunk_id": "chunk_translation_001",
                    "document_id": "doc_translation_001",
                    "title": "Gazette Notice",
                    "document_type": "Gazette",
                    "source_id": "GOV_GAZETTES",
                    "authority_level": 5,
                    "citation": "Gazette Notice",
                    "text": "Translated fallback text.",
                    "fused_score": 1.0,
                    "selection_reason": "translation fixture",
                    "metadata": {"quality_flags": ["translated_text_fallback", "machine_translation_unreviewed"]},
                }
            ],
        }
    )

    warnings = source_reliability_warnings(pack)

    assert any("translated fallback text" in warning for warning in warnings)
    assert any("machine translation" in warning for warning in warnings)
