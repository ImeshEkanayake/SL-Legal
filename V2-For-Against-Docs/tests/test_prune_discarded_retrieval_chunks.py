from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_prune_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "prune_discarded_retrieval_chunks.py"
    spec = importlib.util.spec_from_file_location("prune_discarded_retrieval_chunks", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prune_defaults_keep_only_clean_extracted_or_translated_documents():
    module = load_prune_module()
    args = module.parse_args([])
    eligibility = module.eligibility_sql()

    assert module.ELIGIBLE_EXTRACTION_STATUSES == ("text_extracted", "translated")
    assert args.min_text_quality_score == 0.10
    assert "extraction_status = ANY" in eligibility
    assert "coalesce(d.ocr_required, false) IS FALSE" in eligibility
    assert "coalesce(d.text_quality_score, 0) >= %(min_text_quality_score)s" in eligibility


def test_prune_preserves_chunks_referenced_by_research_packs():
    module = load_prune_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "referenced_discarded_chunks" in source
    assert "research_pack_items rpi WHERE rpi.chunk_id = rc.chunk_id" in source
    assert "prunable_discarded_chunks" in source


def test_prune_rejects_invalid_quality_threshold():
    module = load_prune_module()

    try:
        module.parse_args(["--min-text-quality-score", "1.5"])
    except SystemExit:
        return
    raise AssertionError("expected invalid min-text-quality-score to fail")
