from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_summary_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_document_short_summaries.py"
    spec = importlib.util.spec_from_file_location("build_document_short_summaries", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summary_builder_validates_ratio_and_character_bounds():
    module = load_summary_module()

    args = module.parse_args(["--target-ratio", "0.25", "--min-chars", "100", "--max-chars", "1000"])

    assert args.target_ratio == 0.25
    assert args.min_chars == 100
    assert args.max_chars == 1000


def test_summary_builder_sql_uses_text_version_uniqueness():
    module = load_summary_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "ON CONFLICT (text_version_id, summary_type, generation_method)" in source
    assert "concat_ws" in source
    assert "right(" in source


def test_summary_builder_defaults_to_spread_method_and_clean_extracts():
    module = load_summary_module()
    args = module.parse_args([])
    eligibility = module.eligibility_sql()

    assert args.generation_method == "deterministic_spread_10pct_v2"
    assert module.ELIGIBLE_EXTRACTION_STATUSES == ("text_extracted", "translated")
    assert "dtv.text_origin = 'source'" in eligibility
    assert "d.extraction_status = ANY" in eligibility
    assert "coalesce(d.ocr_required, false) IS FALSE" in eligibility


def test_replace_summary_type_requires_complete_run():
    module = load_summary_module()

    try:
        module.parse_args(["--replace-summary-type", "--limit", "10"])
    except SystemExit:
        return
    raise AssertionError("expected --replace-summary-type with --limit to fail")
