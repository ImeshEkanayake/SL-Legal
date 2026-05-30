from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_environment_config_pack,
    load_hosted_environment_config_manifest,
    load_hosted_evidence_capture_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase39_hosted_environment_config.json"
PHASE35_MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase35_hosted_evidence_capture.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase39_hosted_environment_config_pack.py"
    spec = importlib.util.spec_from_file_location("build_phase39_hosted_environment_config_pack", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def copy_text(source: Path, root: Path) -> None:
    target = root / source.relative_to(PROJECT_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def prepare_project(root: Path) -> None:
    for source in [
        PROJECT_ROOT / "rag" / "evals" / "phase35_hosted_evidence_capture.json",
        PROJECT_ROOT / "rag" / "evals" / "phase38_hosted_capture_execution.json",
        PROJECT_ROOT / "rag" / "evals" / "phase39_hosted_environment_config.json",
    ]:
        copy_text(source, root)
    for path_value in [
        "Docs/v2_phase_38_hosted_capture_execution_contract.md",
        "Docs/v2_phase_38_hosted_capture_execution_runbook.md",
        "Docs/releases/v2_phase_38_hosted_capture_execution.md",
        "Docs/v2_phase_39_hosted_environment_config_contract.md",
        "scripts/run_phase38_hosted_capture_execution.py",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def hosted_environment() -> dict[str, str]:
    return {
        "SL_LEGAL_STAGING_API_BASE_URL": "https://staging.example.test",
        "SL_LEGAL_STAGING_USER_ID": "reviewer-user",
        "SL_LEGAL_AUTH_HMAC_SECRET": "x" * 40,
        "SL_LEGAL_STAGING_CASE_ID": "case-123",
        "SL_LEGAL_STAGING_DOCUMENT_ID": "doc-456",
        "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED": "true",
        "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT": "0",
        "SL_LEGAL_PHASE35_DB_MIGRATION_COUNT": "0",
        "SL_LEGAL_PHASE35_RAW_DATA_UPLOADED": "false",
    }


def test_phase39_manifest_loads():
    payload = load_hosted_environment_config_manifest(MANIFEST_PATH)
    command_ids = {item["id"] for item in payload["command_recipes"]}
    output_ids = {item["id"] for item in payload["evidence_outputs"]}

    assert payload["target_release_tag"] == "v2-phase-38-hosted-capture-execution"
    assert "hosted_phase38_dry_run" in command_ids
    assert "hosted_phase38_execution" in command_ids
    assert "phase38_execution" in output_ids


def test_phase39_local_pack_awaits_configuration(tmp_path):
    prepare_project(tmp_path)
    payload = load_hosted_environment_config_manifest(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json")
    phase35 = load_hosted_evidence_capture_manifest(tmp_path / "rag" / "evals" / "phase35_hosted_evidence_capture.json")

    report = build_hosted_environment_config_pack(
        payload,
        project_root=tmp_path,
        environment={},
        include_environment=False,
        phase35_payload=phase35,
    )

    assert report["status"] == "awaiting_hosted_environment_configuration"
    assert report["summary"]["verified_prerequisites"] == 6
    assert report["summary"]["execution_recipes"] == 1
    assert report["blockers"] == []


def test_phase39_hosted_environment_is_ready(tmp_path):
    prepare_project(tmp_path)
    payload = load_hosted_environment_config_manifest(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json")
    phase35 = load_hosted_evidence_capture_manifest(tmp_path / "rag" / "evals" / "phase35_hosted_evidence_capture.json")

    report = build_hosted_environment_config_pack(
        payload,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        phase35_payload=phase35,
    )

    assert report["status"] == "ready_for_hosted_capture_dry_run"
    assert all(item["status"] == "verified" for item in report["environment"]["checks"])
    assert all(not item["committable"] for item in report["evidence_outputs"])


def test_phase39_blocks_missing_environment(tmp_path):
    prepare_project(tmp_path)
    payload = load_hosted_environment_config_manifest(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json")
    phase35 = load_hosted_evidence_capture_manifest(tmp_path / "rag" / "evals" / "phase35_hosted_evidence_capture.json")
    environment = hosted_environment()
    environment.pop("SL_LEGAL_AUTH_HMAC_SECRET")

    report = build_hosted_environment_config_pack(
        payload,
        project_root=tmp_path,
        environment=environment,
        include_environment=True,
        phase35_payload=phase35,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "env:SL_LEGAL_AUTH_HMAC_SECRET" for item in report["blockers"])


def test_phase39_blocks_unsafe_execution_recipe(tmp_path):
    prepare_project(tmp_path)
    payload = load_hosted_environment_config_manifest(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json")
    phase35 = load_hosted_evidence_capture_manifest(tmp_path / "rag" / "evals" / "phase35_hosted_evidence_capture.json")
    broken = deepcopy(payload)
    for recipe in broken["command_recipes"]:
        if recipe["id"] == "hosted_phase38_execution":
            recipe["command"] = [part for part in recipe["command"] if part != "--execute"]

    report = build_hosted_environment_config_pack(
        broken,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        phase35_payload=phase35,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "hosted_phase38_execution" for item in report["blockers"])


def test_phase39_blocks_environment_drift_from_phase35(tmp_path):
    prepare_project(tmp_path)
    payload = load_hosted_environment_config_manifest(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json")
    phase35 = load_hosted_evidence_capture_manifest(tmp_path / "rag" / "evals" / "phase35_hosted_evidence_capture.json")
    drifted_phase35 = deepcopy(phase35)
    drifted_phase35["required_environment"] = drifted_phase35["required_environment"][:-1]

    report = build_hosted_environment_config_pack(
        payload,
        project_root=tmp_path,
        environment=hosted_environment(),
        include_environment=True,
        phase35_payload=drifted_phase35,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase35_environment_sync" for item in report["blockers"])


def test_phase39_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    prepare_project(tmp_path)
    output = tmp_path / "logs" / "readiness" / "phase39-hosted-environment-config-pack.json"

    status = module.main(["--manifest", str(tmp_path / "rag" / "evals" / "phase39_hosted_environment_config.json"), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_environment_configuration"
