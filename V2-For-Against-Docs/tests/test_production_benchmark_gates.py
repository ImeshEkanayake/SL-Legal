from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_benchmark_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_production_benchmark_gates.py"
    spec = importlib.util.spec_from_file_location("run_production_benchmark_gates", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_percentile_95_for_single_value_is_stable():
    module = load_benchmark_module()

    assert module.percentile_95([42.0]) == 42.0


def test_evaluate_thresholds_reports_failed_gate():
    module = load_benchmark_module()
    args = argparse.Namespace(
        min_documents=10,
        min_chunks=10,
        min_summary_coverage=0.95,
        max_summary_search_ms=100,
        max_chunk_search_ms=100,
    )
    failures = module.evaluate_thresholds(
        {
            "documents": 11,
            "chunks": 9,
            "chunks_missing_text_version": 0,
            "summary_coverage": 1.0,
        },
        {"summary_search": {"p95_ms": 50}, "chunk_search": {"p95_ms": 50}},
        args,
    )

    assert failures == [{"check": "chunks", "value": 9, "operator": ">=", "expected": 10}]
