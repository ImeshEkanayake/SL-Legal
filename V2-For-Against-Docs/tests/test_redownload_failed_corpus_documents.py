from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_redownload_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "redownload_failed_corpus_documents.py"
    spec = importlib.util.spec_from_file_location("redownload_failed_corpus_documents", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_redownload_preserves_larger_resumable_partial(monkeypatch, tmp_path):
    module = load_redownload_module()
    local_pdf = tmp_path / "doc.pdf"
    local_pdf.write_bytes(b"%PDF-1.7\nold")

    def fake_fetch_url(_url, target, **_kwargs):
        target.write_bytes(b"%PDF-1.7\nold-but-larger-partial")
        raise RuntimeError("timeout")

    monkeypatch.setattr(module, "fetch_url", fake_fetch_url)
    args = argparse.Namespace(
        execute=True,
        resume_from_local=True,
        preserve_failed_partial=True,
        trust_existing_valid_local=False,
        validate_pdf_pages=False,
        timeout=1,
        retries=0,
        min_speed_bytes=0,
        min_speed_time=0,
    )

    result = module.redownload_one(
        {
            "document_id": "doc_1",
            "source_id": "SRC",
            "local_path": str(local_pdf),
            "download_url": "https://example.test/doc.pdf",
            "source_url": "",
            "file_hash": "",
        },
        args,
    )

    assert result.status == "failed"
    assert "preserved_partial_bytes=" in result.error_message
    assert local_pdf.read_bytes() == b"%PDF-1.7\nold-but-larger-partial"
