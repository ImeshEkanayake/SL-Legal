from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_staging_cutover_dry_run,
    load_staging_cutover_dry_run_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase31_staging_cutover_dry_run.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase31_staging_cutover_dry_run.py"
    spec = importlib.util.spec_from_file_location("build_phase31_staging_cutover_dry_run", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase31_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase31_staging_cutover_dry_run.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "cutover_environment": "staging",
        "required_reports": [
            {
                "id": "phase30_readiness_report",
                "title": "Phase 30 readiness report",
                "type": "json_status",
                "path": "logs/readiness/phase30-ui-deployment-readiness.json",
                "accepted_statuses": ["ready_for_hosted_env_review", "ready_for_deployment_review"],
            },
            {
                "id": "phase30_manifest",
                "title": "Phase 30 manifest",
                "type": "file",
                "path": "rag/evals/phase30_ui_deployment_readiness.json",
            },
            {
                "id": "phase30_contract",
                "title": "Phase 30 contract",
                "type": "document",
                "path": "Docs/v2_phase_30_ui_deployment_readiness_contract.md",
            },
        ],
        "smoke_tests": [
            {
                "id": "hosted_env_gate",
                "title": "Hosted env gate",
                "command": ["scripts/run_detached_quality_gate.sh", "ui-deployment-readiness-env", "phase31-env"],
                "expected_evidence": "logs/test-runs/phase31-env.log",
                "requires_hosted_environment": True,
            },
            {
                "id": "browser_smoke",
                "title": "Browser smoke",
                "command": ["scripts/run_detached_quality_gate.sh", "phase29-browser-workflow", "phase31-browser"],
                "expected_evidence": "logs/test-runs/phase31-browser.log",
                "requires_hosted_environment": False,
            },
        ],
        "manual_approvals": [
            {"id": "owner_acceptance", "title": "Owner acceptance", "required": True},
        ],
        "rollback_steps": [
            {
                "id": "rollback_ui",
                "title": "Rollback UI",
                "action": "Restore previous deployment.",
                "owner": "operator",
            }
        ],
    }


def write_phase31_evidence(root: Path, *, phase30_status: str = "ready_for_hosted_env_review") -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase30-ui-deployment-readiness.json").write_text(
        json.dumps({"status": phase30_status}),
        encoding="utf-8",
    )
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase30_ui_deployment_readiness.json").write_text(
        json.dumps({"schema_version": "phase30_ui_deployment_readiness.v1"}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_30_ui_deployment_readiness_contract.md").write_text("contract\n", encoding="utf-8")


def test_phase31_manifest_loads():
    payload = load_staging_cutover_dry_run_manifest(MANIFEST_PATH)
    smoke_ids = {item["id"] for item in payload["smoke_tests"]}

    assert payload["target_release_tag"] == "v2-phase-30-ui-deployment-readiness"
    assert "phase31_hosted_env_gate" in smoke_ids
    assert "phase31_browser_smoke" in smoke_ids
    assert payload["cutover_environment"] == "staging"


def test_phase31_ready_for_hosted_env_setup_without_hosted_env(tmp_path):
    write_phase31_evidence(tmp_path, phase30_status="ready_for_hosted_env_review")

    report = build_staging_cutover_dry_run(phase31_manifest(), project_root=tmp_path)

    assert report["status"] == "ready_for_hosted_env_setup"
    assert report["summary"]["verified_reports"] == 3
    assert report["summary"]["hosted_smoke_tests"] == 1
    assert report["blockers"] == []
    assert any(item["status"] == "requires_hosted_environment" for item in report["smoke_tests"])


def test_phase31_ready_for_staging_cutover_with_hosted_env_report(tmp_path):
    write_phase31_evidence(tmp_path, phase30_status="ready_for_deployment_review")

    report = build_staging_cutover_dry_run(phase31_manifest(), project_root=tmp_path)

    assert report["status"] == "ready_for_staging_cutover"
    assert report["blockers"] == []


def test_phase31_blocks_missing_phase30_report(tmp_path):
    write_phase31_evidence(tmp_path)
    (tmp_path / "logs" / "readiness" / "phase30-ui-deployment-readiness.json").unlink()

    report = build_staging_cutover_dry_run(phase31_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert report["summary"]["missing_reports"] == 1
    assert any(item["id"] == "phase30_readiness_report" for item in report["blockers"])


def test_phase31_blocks_unaccepted_phase30_status(tmp_path):
    write_phase31_evidence(tmp_path, phase30_status="blocked")

    report = build_staging_cutover_dry_run(phase31_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase30_readiness_report" for item in report["blockers"])


def test_phase31_blocks_incomplete_rollback_step(tmp_path):
    write_phase31_evidence(tmp_path)
    manifest = phase31_manifest()
    manifest["rollback_steps"] = [{"id": "rollback", "title": "Rollback", "action": ""}]

    report = build_staging_cutover_dry_run(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "rollback_step" for item in report["blockers"])


def test_phase31_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase31_evidence(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "staging-cutover.json"
    manifest.write_text(json.dumps(phase31_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_hosted_env_setup"
