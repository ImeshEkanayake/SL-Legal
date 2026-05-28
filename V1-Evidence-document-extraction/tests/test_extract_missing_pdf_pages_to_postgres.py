from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_extract_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "extract_missing_pdf_pages_to_postgres.py"
    spec = importlib.util.spec_from_file_location("extract_missing_pdf_pages_to_postgres", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_filter_defaults_to_documents_without_pages():
    module = load_extract_module()
    args = module.parse_args(["--source-id", "GOV_GAZETTES", "--document-id", "doc_a", "--year", "1950"])

    where_sql, params = module.candidate_filter_sql(args)

    assert "NOT EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id)" in where_sql
    assert params == {
        "document_ids": ["doc_a"],
        "source_ids": ["GOV_GAZETTES"],
        "years": [1950],
    }


def test_candidate_filter_can_include_empty_page_documents():
    module = load_extract_module()
    args = module.parse_args(["--include-empty-page-docs"])

    where_sql, _params = module.candidate_filter_sql(args)

    assert "length(trim(p.text)) > 0" in where_sql


def test_page_text_quality_marks_empty_and_low_density_for_ocr():
    module = load_extract_module()

    empty_quality, empty_ocr, empty_flags = module.page_text_quality("", 3)
    low_quality, low_ocr, low_flags = module.page_text_quality("short", 10)
    good_quality, good_ocr, good_flags = module.page_text_quality("word " * 1000, 2)

    assert empty_quality == 0.0
    assert empty_ocr is True
    assert "empty_document_text" in empty_flags
    assert low_quality == 0.25
    assert low_ocr is True
    assert "low_text_density" in low_flags
    assert good_quality == 0.90
    assert good_ocr is False
    assert good_flags == ()


def test_quality_flags_for_page_identifies_empty_and_error():
    module = load_extract_module()

    flags = module.quality_flags_for_page("", "bad page")

    assert "page_extraction_error" in flags
    assert "empty_page_text" in flags
    assert "very_short_page_text" in flags


def test_extract_zip_pdf_pages_requires_pdf_members(tmp_path):
    module = load_extract_module()
    import zipfile

    archive_path = tmp_path / "empty_archive.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("readme.txt", "not a pdf")

    try:
        module.extract_zip_pdf_pages(archive_path)
    except RuntimeError as exc:
        assert "no PDF members" in str(exc)
    else:
        raise AssertionError("expected missing PDF member failure")


def test_extract_pdf_pages_falls_back_to_pymupdf(monkeypatch, tmp_path):
    module = load_extract_module()
    pdf_path = tmp_path / "recoverable.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def broken_reader(*_args, **_kwargs):
        raise RuntimeError("pypdf broken")

    class FakePdfium:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("pdfium broken")

    class FakePage:
        def get_text(self, *_args, **_kwargs):
            return "Recovered text"

    class FakeDocument:
        page_count = 1

        def load_page(self, index):
            assert index == 0
            return FakePage()

        def close(self):
            return None

    class FakeFitz:
        @staticmethod
        def open(*_args, **_kwargs):
            return FakeDocument()

    monkeypatch.setattr(module, "PdfReader", broken_reader)
    monkeypatch.setattr(module, "pdfium", type("FakePdfiumModule", (), {"PdfDocument": FakePdfium}))
    monkeypatch.setattr(module, "fitz", FakeFitz)

    extractor, pages = module.extract_pdf_pages(pdf_path)

    assert extractor == "pymupdf"
    assert pages == [{"page": "1", "text": "Recovered text", "error": ""}]
