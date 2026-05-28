from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import build_readiness_pack, load_readiness_requirements


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "rag" / "evals" / "phase8_deployment_readiness_evidence.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "run_phase8_readiness_pack.py"
    spec = importlib.util.spec_from_file_location("run_phase8_readiness_pack", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase8_requirements_cover_local_and_production_evidence():
    payload = load_readiness_requirements(REQUIREMENTS_PATH)
    scopes = {item["scope"] for item in payload["requirements"]}
    evidence_ids = {item["id"] for item in payload["requirements"]}

    assert scopes == {"local_release", "production_stack"}
    assert {
        "backend_tests",
        "frontend_quality",
        "load_plan",
        "schema_check",
        "rag_health",
        "index_consistency",
        "real_load",
        "searchability_audit",
    } <= evidence_ids


def test_phase8_pack_is_ready_when_local_release_logs_pass(tmp_path):
    for name in ["phase8-tests.log", "phase8-frontend.log", "phase8-load-plan.log"]:
        path = tmp_path / "logs" / "test-runs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("finished_at_utc=2026-05-28T00:00:00Z\nexit_status=0\n", encoding="utf-8")
    requirements = load_readiness_requirements(REQUIREMENTS_PATH)

    pack = build_readiness_pack(requirements, project_root=tmp_path, include_production=False)

    assert pack["decision"] == "ready"
    assert pack["summary"] == {"total": 3, "passed": 3, "failed": 0, "missing": 0}


def test_phase8_pack_blocks_when_production_evidence_is_missing(tmp_path):
    for name in ["phase8-tests.log", "phase8-frontend.log", "phase8-load-plan.log"]:
        path = tmp_path / "logs" / "test-runs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("exit_status=0\n", encoding="utf-8")
    requirements = load_readiness_requirements(REQUIREMENTS_PATH)

    pack = build_readiness_pack(requirements, project_root=tmp_path, include_production=True)

    assert pack["decision"] == "blocked"
    assert pack["summary"]["missing"] == 6
    assert {item["id"] for item in pack["missing_production_evidence"]} == {
        "schema_check",
        "schema_smoke",
        "rag_health",
        "index_consistency",
        "real_load",
        "searchability_audit",
    }


def test_phase8_script_writes_pack(tmp_path):
    for name in ["phase8-tests.log", "phase8-frontend.log", "phase8-load-plan.log"]:
        path = tmp_path / "logs" / "test-runs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("exit_status=0\n", encoding="utf-8")
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    output = tmp_path / "pack.json"

    status = module.main(["--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["schema_version"] == "phase8_readiness_pack.v1"
    assert payload["decision"] == "ready"
