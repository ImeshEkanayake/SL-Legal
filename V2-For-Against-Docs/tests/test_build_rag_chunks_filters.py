from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_build_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_rag_chunks.py"
    spec = importlib.util.spec_from_file_location("build_rag_chunks", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_rag_chunks_filters_by_document_id():
    module = load_build_module()
    args = module.parse_args(["--document-id", "doc_allowed", "--source-id", "SC_OFFICIAL"])

    assert module.row_is_eligible(
        {
            "document_id": "doc_allowed",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "language": "English",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )
    assert not module.row_is_eligible(
        {
            "document_id": "doc_blocked",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "language": "English",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )


def test_official_court_sources_are_priority_eligible_by_default():
    module = load_build_module()
    args = module.parse_args([])

    assert module.row_is_eligible(
        {
            "document_id": "sc_doc",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "language": "English",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )
    assert module.row_is_eligible(
        {
            "document_id": "ca_doc",
            "source_id": "CA_OFFICIAL",
            "acquisition_status": "downloaded",
            "language": "English",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )


def test_unknown_language_extracted_official_document_is_eligible():
    module = load_build_module()
    args = module.parse_args(["--document-id", "sc_doc"])

    assert module.row_is_eligible(
        {
            "document_id": "sc_doc",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "language": "unknown",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )


def test_sinhala_and_tamil_downloaded_documents_are_eligible_for_indexing():
    module = load_build_module()
    args = module.parse_args(["--include-gazettes"])

    assert module.row_is_eligible(
        {
            "document_id": "gazette_si",
            "source_id": "GOV_GAZETTES",
            "acquisition_status": "downloaded",
            "language": "Sinhala",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )
    assert module.row_is_eligible(
        {
            "document_id": "gazette_ta",
            "source_id": "GOV_EXTRA_GAZETTES",
            "acquisition_status": "downloaded",
            "language": "Tamil",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )


def test_uva_health_statutes_are_priority_eligible_by_default():
    module = load_build_module()
    args = module.parse_args([])

    assert module.row_is_eligible(
        {
            "document_id": "uva_health_statute",
            "source_id": "UVA_HEALTH_STATUTES",
            "acquisition_status": "downloaded",
            "language": "English",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.9",
        },
        args,
    )


def test_ocr_pending_and_low_quality_documents_are_not_eligible():
    module = load_build_module()
    args = module.parse_args(["--include-gazettes"])

    base = {
        "document_id": "gazette_bad",
        "source_id": "GOV_GAZETTES",
        "acquisition_status": "downloaded",
        "language": "English",
        "text_quality_score": "0.9",
    }
    assert not module.row_is_eligible({**base, "extraction_status": "text_empty_needs_ocr"}, args)
    assert not module.row_is_eligible(
        {**base, "extraction_status": "text_extracted", "ocr_required": "true"},
        args,
    )
    assert not module.row_is_eligible(
        {**base, "extraction_status": "text_extracted", "ocr_required": "false", "text_quality_score": "0.09"},
        args,
    )


def test_document_id_file_filter(tmp_path):
    module = load_build_module()
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("# comment\ndoc_from_file\n\n", encoding="utf-8")

    args = module.parse_args(["--document-id-file", str(document_id_file)])

    assert args.document_ids_filter == {"doc_from_file"}


def test_normalize_text_removes_nul_bytes():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag"))
    from sl_legal_rag.chunking import normalize_text

    assert normalize_text("Act\x00\x01 section") == "Act section"
