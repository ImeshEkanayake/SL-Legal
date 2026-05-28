from __future__ import annotations

from sl_legal_rag.full_text_readiness import build_full_text_readiness_report


def test_full_text_readiness_counts_text_and_ocr_completion():
    rows = [
        {
            "document_id": "doc_text",
            "source_id": "PARL_ACTS",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.90",
            "local_path": "data/raw/doc_text.pdf",
        },
        {
            "document_id": "doc_ocr",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "extraction_status": "text_empty_needs_ocr",
            "ocr_required": "true",
            "local_path": "data/raw/doc_ocr.pdf",
        },
        {
            "document_id": "doc_pending",
            "source_id": "GOV_GAZETTES",
            "acquisition_status": "downloaded",
            "extraction_status": "not_started",
            "local_path": "data/raw/doc_pending.pdf",
        },
        {
            "document_id": "doc_image",
            "source_id": "ADMIN",
            "acquisition_status": "downloaded",
            "extraction_status": "not_started",
            "local_path": "data/raw/doc_image.jpg",
        },
    ]
    ocr_rows = {
        "doc_ocr": {
            "document_id": "doc_ocr",
            "ocr_status": "ocr_completed_high_confidence",
            "char_count": "1200",
        }
    }

    report = build_full_text_readiness_report(rows, ocr_rows)

    assert report.downloaded_documents == 4
    assert report.downloaded_pdfs == 3
    assert report.downloaded_non_pdfs == 1
    assert report.text_extracted_documents == 1
    assert report.text_empty_needs_ocr_documents == 1
    assert report.ocr_completed_documents == 1
    assert report.full_text_ready_documents == 2
    assert report.extraction_pending_documents == 2
    assert report.ocr_pending_documents == 0
    assert report.blocked_non_pdf_documents == 1


def test_low_quality_text_still_requires_ocr():
    rows = [
        {
            "document_id": "doc_low",
            "source_id": "PARL_ACTS",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": "true",
            "text_quality_score": "0.25",
            "local_path": "data/raw/doc_low.pdf",
        }
    ]

    report = build_full_text_readiness_report(rows, {})

    assert report.full_text_ready_documents == 0
    assert report.ocr_pending_documents == 1
    assert report.remaining_for_full_text == 1
