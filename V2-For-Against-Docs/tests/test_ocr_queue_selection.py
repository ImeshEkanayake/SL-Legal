from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_ocr_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "ocr_text_empty_pdfs.py"
    spec = importlib.util.spec_from_file_location("ocr_text_empty_pdfs", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ocr_queue_includes_empty_text_and_low_quality_text_layer():
    module = load_ocr_module()

    assert module.row_requires_ocr({"extraction_status": "text_empty_needs_ocr", "ocr_required": "false"})
    assert module.row_requires_ocr({"extraction_status": "text_extracted", "ocr_required": "true"})
    assert not module.row_requires_ocr({"extraction_status": "text_extracted", "ocr_required": "false"})


def test_force_ocr_still_respects_already_done_within_current_run():
    module = load_ocr_module()
    args = type(
        "Args",
        (),
        {
            "source_id": None,
            "document_id": None,
            "year": None,
            "parliament": False,
            "force": True,
            "limit": 0,
        },
    )()
    rows = [
        {
            "document_id": "doc_done",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": "true",
        },
        {
            "document_id": "doc_pending",
            "source_id": "SC_OFFICIAL",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": "true",
        },
    ]

    original_read_csv = module.read_csv
    try:
        module.read_csv = lambda _path: rows
        tasks = module.discover_tasks(args, {"doc_done"})
    finally:
        module.read_csv = original_read_csv

    assert [row["document_id"] for row in tasks] == ["doc_pending"]
