from __future__ import annotations

import json
from pathlib import Path

from sl_legal_rag.operations import (
    load_scenarios,
    overall_load_status,
    scenario_from_mapping,
    substitute_tokens,
    summarize_load_results,
)


def test_phase6_load_scenario_fixture_covers_required_paths():
    scenario_path = Path(__file__).resolve().parents[1] / "rag" / "evals" / "phase6_load_scenarios.json"
    scenarios = load_scenarios(scenario_path)
    names = {scenario.name for scenario in scenarios}

    assert names >= {
        "workspace_snapshot",
        "research_pack_creation",
        "strategy_validation",
        "source_viewer",
        "review_queue",
    }
    assert all(scenario.concurrency >= 1 for scenario in scenarios)
    assert all(scenario.requests >= scenario.concurrency for scenario in scenarios)
    assert all(scenario.max_p95_ms > 0 for scenario in scenarios)


def test_phase6_token_substitution_handles_nested_payloads():
    payload = {
        "path": "/v1/cases/{case_id}/review/items",
        "body": {"pack_id": "{pack_id}", "claims": [{"pack_item_ids": ["{pack_item_id}"]}]},
    }

    resolved = substitute_tokens(
        payload,
        {"case_id": "case_1", "pack_id": "pack_1", "pack_item_id": "pack_1_item_001"},
    )

    assert resolved == {
        "path": "/v1/cases/case_1/review/items",
        "body": {"pack_id": "pack_1", "claims": [{"pack_item_ids": ["pack_1_item_001"]}]},
    }


def test_phase6_load_summary_enforces_latency_and_error_thresholds():
    scenario = scenario_from_mapping(
        {
            "name": "source_viewer",
            "method": "GET",
            "path": "/v1/research/packs/{pack_id}/items/{pack_item_id}/source",
            "concurrency": 2,
            "requests": 4,
            "max_p95_ms": 100,
            "max_error_rate": 0,
        }
    )

    passing = summarize_load_results(
        scenario,
        [
            {"elapsed_ms": 10, "status_code": 200},
            {"elapsed_ms": 20, "status_code": 200},
            {"elapsed_ms": 30, "status_code": 200},
            {"elapsed_ms": 40, "status_code": 200},
        ],
    )
    failing = summarize_load_results(
        scenario,
        [
            {"elapsed_ms": 10, "status_code": 200},
            {"elapsed_ms": 20, "status_code": 500, "error": "server error"},
            {"elapsed_ms": 30, "status_code": 200},
            {"elapsed_ms": 40, "status_code": 200},
        ],
    )

    assert passing["status"] == "pass"
    assert passing["latency_ms"]["p95"] <= 40
    assert failing["status"] == "fail"
    assert failing["error_count"] == 1
    assert overall_load_status([passing]) == "pass"
    assert overall_load_status([passing, failing]) == "fail"


def test_phase6_load_scenario_file_has_schema_version():
    scenario_path = Path(__file__).resolve().parents[1] / "rag" / "evals" / "phase6_load_scenarios.json"
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "phase6_load_scenarios.v1"
