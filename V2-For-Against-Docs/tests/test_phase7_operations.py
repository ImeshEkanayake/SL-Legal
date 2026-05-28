from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    load_operational_manifest,
    operational_commands,
    operational_plan,
    render_command,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase7_deployment_monitoring_manifest.json"


def load_plan_script():
    script = PROJECT_ROOT / "scripts" / "run_phase7_operational_plan.py"
    spec = importlib.util.spec_from_file_location("run_phase7_operational_plan", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_snapshot_script():
    script = PROJECT_ROOT / "scripts" / "run_phase7_monitoring_snapshot.py"
    spec = importlib.util.spec_from_file_location("run_phase7_monitoring_snapshot", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase7_manifest_covers_release_deployment_data_and_monitoring_sections():
    manifest = load_operational_manifest(MANIFEST_PATH)

    assert set(manifest["sections"]) == {
        "release_gates",
        "deployment_readiness",
        "hosted_data",
        "recurring_monitoring",
    }
    assert any(item["name"] == "real_load_suite" for item in manifest["sections"]["deployment_readiness"])
    assert any(item["name"] == "object_storage_probe" for item in manifest["sections"]["hosted_data"])


def test_phase7_operational_plan_marks_production_stack_requirements():
    manifest = load_operational_manifest(MANIFEST_PATH)
    plan = operational_plan(manifest, section="deployment_readiness")

    assert plan["status"] == "planned"
    assert all(item["requires_production_stack"] for item in plan["commands"])
    assert all(item["required_for_release"] for item in plan["commands"])


def test_phase7_render_command_includes_environment_prefix():
    command = operational_commands(
        {
            "schema_version": "phase7_deployment_monitoring.v1",
            "sections": {
                "release_gates": [
                    {
                        "name": "sample",
                        "command": ["python", "script.py"],
                        "evidence": "terminal output",
                        "env": {"PYTHONPATH": "rag"},
                    }
                ]
            },
        },
        section="release_gates",
    )[0]

    assert render_command(command) == "PYTHONPATH=rag python script.py"


def test_phase7_operational_plan_script_renders_shell():
    module = load_plan_script()
    manifest = load_operational_manifest(MANIFEST_PATH)
    plan = operational_plan(manifest, section="release_gates")

    rendered = module.render_shell(plan)

    assert rendered.startswith("#!/usr/bin/env bash")
    assert "scripts/run_detached_quality_gate.sh tests phase7-tests" in rendered


def test_phase7_monitoring_snapshot_plan_writes_report(tmp_path):
    module = load_snapshot_script()
    output = tmp_path / "monitoring.json"

    status = module.main(["--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["schema_version"] == "phase7_monitoring_snapshot.v1"
    assert payload["mode"] == "plan"
    assert [item["name"] for item in payload["checks"]] == ["weekly_adverse_retrieval_eval"]
