from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


def load_build_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_rag_chunks_from_postgres.py"
    spec = importlib.util.spec_from_file_location("build_rag_chunks_from_postgres", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_document_row_to_chunk_row_uses_database_document_date():
    module = load_build_module()

    row = module.document_row_to_chunk_row(
        {
            "document_id": "doc_1",
            "source_id": "PARL_ACTS",
            "source_document_id": "G1",
            "document_type": "Act",
            "title": "Test Act",
            "year": 2026,
            "number": "1",
            "document_date": date(2026, 5, 25),
            "language": "English",
            "source_url": "https://example.test/source",
            "download_url": "https://example.test/download",
            "local_path": "data/raw/test.pdf",
            "file_hash": "abc",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": False,
            "text_quality_score": 0.9,
            "legal_status": "to_verify",
        }
    )

    assert row["document_id"] == "doc_1"
    assert row["date"] == "2026-05-25"
    assert row["source_document_id"] == "G1"
    assert row["extraction_status"] == "text_extracted"


def test_select_best_pages_uses_best_non_empty_candidate_per_page():
    module = load_build_module()

    pages = module.select_best_pages(
        [
            module.PageCandidate(page_number=1, text="", extraction_method="text"),
            module.PageCandidate(page_number=1, text="short", extraction_method="ocr", ocr_confidence=88.0),
            module.PageCandidate(page_number=1, text="longer official text layer", extraction_method="text_layer"),
            module.PageCandidate(page_number=2, text="page two", extraction_method="ocr", ocr_confidence=72.0),
        ]
    )

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].text == "longer official text layer"
    assert pages[0].extraction_method == "text_layer"
    assert pages[1].confidence == 72.0


def test_translation_text_version_rows_become_unanchored_translation_pages():
    module = load_build_module()

    pages = module.pages_for_translation_text_version(
        {
            "document_id": "doc_translation",
            "full_text": "  Translated fallback paragraph.\n\nSecond paragraph.  ",
        }
    )

    assert len(pages) == 1
    assert pages[0].page_number == 0
    assert pages[0].extraction_method == "translation"
    assert pages[0].text == "Translated fallback paragraph.\nSecond paragraph."


def test_translation_row_eligibility_rejects_superseded_translations():
    module = load_build_module()
    args = module.parse_args(["--include-translation-text-versions", "--include-gazettes"])

    assert not module.translation_row_is_eligible(
        {
            "text_origin": "translation",
            "full_text": "Translated text",
            "translation_review_status": "superseded_by_official",
            "source_id": "GOV_GAZETTES",
            "document_type": "Gazette",
            "document_id": "doc_translation",
        },
        args,
    )


def test_postgres_chunk_builder_rejects_ocr_pending_and_low_quality_rows():
    module = load_build_module()
    args = module.parse_args(["--include-gazettes"])

    base = {
        "document_id": "doc_bad",
        "source_id": "GOV_GAZETTES",
        "acquisition_status": "downloaded",
        "language": "English",
        "text_quality_score": 0.9,
    }
    assert not module.row_is_eligible({**base, "extraction_status": "text_empty_needs_ocr"}, args)
    assert not module.row_is_eligible(
        {**base, "extraction_status": "text_extracted", "ocr_required": True},
        args,
    )
    assert not module.row_is_eligible(
        {**base, "extraction_status": "text_extracted", "ocr_required": False, "text_quality_score": 0.09},
        args,
    )


def test_postgres_chunk_builder_accepts_clean_translated_rows():
    module = load_build_module()
    args = module.parse_args(["--include-gazettes"])

    assert module.row_is_eligible(
        {
            "document_id": "doc_translated",
            "source_id": "GOV_GAZETTES",
            "acquisition_status": "downloaded",
            "language": "Sinhala",
            "extraction_status": "translated",
            "ocr_required": False,
            "text_quality_score": 0.9,
        },
        args,
    )


def test_only_translation_flag_implies_translation_chunking():
    module = load_build_module()
    args = module.parse_args(["--only-translation-text-versions"])

    assert args.only_translation_text_versions is True
    assert args.include_translation_text_versions is False
