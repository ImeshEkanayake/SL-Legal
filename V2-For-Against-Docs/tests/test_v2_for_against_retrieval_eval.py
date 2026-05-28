from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_v2_for_against_retrieval_eval.py"
FIXTURE_PATH = PROJECT_ROOT / "rag" / "evals" / "v2_for_against_retrieval_fixture.json"


def load_module():
    spec = importlib.util.spec_from_file_location("run_v2_for_against_retrieval_eval", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v2_for_against_fixture_measures_supportive_and_adverse_recall():
    module = load_module()

    report = module.evaluate_fixture(FIXTURE_PATH, k=2, require_adverse=True)

    assert report["case_count"] == 3
    assert report["recall_by_label"]["supportive"] == 1.0
    assert report["recall_by_label"]["adverse"] == 1.0
    assert report["case_count_by_label"]["adverse"] == 2
    assert module.threshold_failures(report, min_supportive_recall=0.9, min_adverse_recall=0.9) == []


def test_v2_for_against_thresholds_fail_adverse_regression():
    module = load_module()
    report = {
        "recall_by_label": {
            "supportive": 1.0,
            "adverse": 0.5,
        }
    }

    assert module.threshold_failures(report, min_supportive_recall=0.9, min_adverse_recall=0.9) == [
        "adverse recall below 0.9"
    ]
