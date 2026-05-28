from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "ocr_empty_pdf_pages_to_postgres.py"
    spec = importlib.util.spec_from_file_location("ocr_empty_pdf_pages_to_postgres", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pdf_sources_for_ocr_extracts_pdf_members_safely(tmp_path):
    module = load_module()
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../bad.pdf", b"%PDF-1.4\n")
        archive.writestr("notes.txt", b"not a pdf")
        archive.writestr("folder/good.pdf", b"%PDF-1.4\n")

    sources = module.pdf_sources_for_ocr(archive_path, tmp_path / "work")

    assert [name for name, _path in sources] == ["../bad.pdf", "folder/good.pdf"]
    assert all(path.is_file() for _name, path in sources)
    assert all((tmp_path / "work" / "zip_members") in path.parents for _name, path in sources)


def test_candidate_filter_can_include_previous_extraction_failures():
    module = load_module()

    args = module.parse_args(["--include-extraction-failed", "--tessdata-dir", "/tmp/tessdata"])
    where_sql, _params = module.candidate_filter_sql(args)

    assert "text_extraction_failed" in where_sql
    assert "ocr_failed" in where_sql
    assert args.tessdata_dir == "/tmp/tessdata"


def test_rendered_page_images_falls_back_to_pymupdf(monkeypatch, tmp_path):
    module = load_module()
    rendered_path = tmp_path / "fallback.png"

    def fail_pdfium(*_args, **_kwargs):
        raise RuntimeError("pdfium cannot open this PDF")

    def render_pymupdf(*_args, **kwargs):
        yield kwargs["start_page_number"], rendered_path

    monkeypatch.setattr(module, "_iter_pdfium_rendered_pages", fail_pdfium)
    monkeypatch.setattr(module, "_iter_pymupdf_rendered_pages", render_pymupdf)

    pages = list(
        module.iter_rendered_page_images(
            tmp_path / "source.pdf",
            tmp_path,
            scale=1.0,
            start_page_number=7,
        )
    )

    assert pages == [(7, rendered_path)]


def test_tsv_parser_accepts_decimal_confidence():
    module = load_module()
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t3\t1\t1\t1\t510\t777\t48\t21\t96.924393\tඅංක",
            "5\t1\t3\t1\t1\t2\t568\t771\t66\t25\t93.299522\t2,413",
        ]
    )

    text, confidence, word_count = module.tsv_to_text_and_confidence(tsv)

    assert text == "අංක 2,413"
    assert confidence > 95
    assert word_count == 2
