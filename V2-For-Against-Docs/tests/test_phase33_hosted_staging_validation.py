from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_staging_validation_report,
    load_hosted_staging_validation_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase33_hosted_staging_validation.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase33_hosted_staging_validation.py"
    spec = importlib.util.spec_from_file_location("build_phase33_hosted_staging_validation", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase33_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase33_hosted_staging_validation.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "prerequisites": [
            {
                "id": "phase32_execution_pack",
                "title": "Phase 32 execution pack",
                "type": "json_status",
                "path": "logs/readiness/phase32-hosted-staging-execution-pack.json",
                "accepted_statuses": ["ready_for_hosted_configuration", "ready_for_hosted_staging_execution"],
            },
            {
                "id": "phase32_manifest",
                "title": "Phase 32 manifest",
                "type": "file",
                "path": "rag/evals/phase32_hosted_staging_execution.json",
            },
            {
                "id": "phase32_contract",
                "title": "Phase 32 contract",
                "type": "document",
                "path": "Docs/v2_phase_32_hosted_staging_execution_contract.md",
            },
        ],
        "hosted_evidence": [
            {
                "id": "phase30_hosted_env_readiness",
                "title": "Hosted Phase 30 env readiness",
                "type": "json_status",
                "path": "logs/readiness/phase30-ui-deployment-readiness-env.json",
                "accepted_statuses": ["ready_for_deployment_review"],
            },
            {
                "id": "phase31_hosted_cutover_dry_run",
                "title": "Hosted Phase 31 dry run",
                "type": "json_status",
                "path": "logs/readiness/phase31-staging-cutover-dry-run.json",
                "accepted_statuses": ["ready_for_staging_cutover"],
                "pending_statuses": ["ready_for_hosted_env_setup"],
            },
            {
                "id": "phase32_hosted_execution_pack",
                "title": "Hosted Phase 32 execution pack",
                "type": "json_status",
                "path": "logs/readiness/phase32-hosted-staging-execution-pack.json",
                "accepted_statuses": ["ready_for_hosted_staging_execution"],
                "pending_statuses": ["ready_for_hosted_configuration"],
            },
            {
                "id": "hosted_browser_smoke",
                "title": "Hosted browser smoke",
                "type": "detached_log",
                "path": "logs/test-runs/phase33-platform-browser-smoke.log",
            },
            {
                "id": "operator_secret_review",
                "title": "Operator secret review",
                "type": "json_status",
                "path": "logs/hosted-staging/phase33-operator-secret-review.json",
                "accepted_statuses": ["approved"],
            },
            {
                "id": "lawyer_owner_acceptance",
                "title": "Lawyer owner acceptance",
                "type": "json_status",
                "path": "logs/hosted-staging/phase33-lawyer-owner-acceptance.json",
                "accepted_statuses": ["accepted"],
            },
        ],
    }


def write_prerequisites(root: Path, *, phase32_status: str = "ready_for_hosted_configuration") -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase32-hosted-staging-execution-pack.json").write_text(
        json.dumps({"status": phase32_status}),
        encoding="utf-8",
    )
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase32_hosted_staging_execution.json").write_text(
        json.dumps({"schema_version": "phase32_hosted_staging_execution.v1"}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_32_hosted_staging_execution_contract.md").write_text("contract\n", encoding="utf-8")


def write_hosted_evidence(root: Path) -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "test-runs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "hosted-staging").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase30-ui-deployment-readiness-env.json").write_text(
        json.dumps({"status": "ready_for_deployment_review"}),
        encoding="utf-8",
    )
    (root / "logs" / "readiness" / "phase31-staging-cutover-dry-run.json").write_text(
        json.dumps({"status": "ready_for_staging_cutover"}),
        encoding="utf-8",
    )
    (root / "logs" / "readiness" / "phase32-hosted-staging-execution-pack.json").write_text(
        json.dumps({"status": "ready_for_hosted_staging_execution"}),
        encoding="utf-8",
    )
    (root / "logs" / "test-runs" / "phase33-platform-browser-smoke.log").write_text(
        "run_id=phase33-platform-browser-smoke\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "logs" / "hosted-staging" / "phase33-operator-secret-review.json").write_text(
        json.dumps({"status": "approved"}),
        encoding="utf-8",
    )
    (root / "logs" / "hosted-staging" / "phase33-lawyer-owner-acceptance.json").write_text(
        json.dumps({"status": "accepted"}),
        encoding="utf-8",
    )


def test_phase33_manifest_loads():
    payload = load_hosted_staging_validation_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["hosted_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-32-hosted-staging-execution"
    assert "phase30_hosted_env_readiness" in evidence_ids
    assert "lawyer_owner_acceptance" in evidence_ids


def test_phase33_awaits_hosted_execution_when_local_only(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_staging_validation_report(phase33_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_execution"
    assert report["summary"]["verified_prerequisites"] == 3
    assert report["summary"]["pending_hosted_evidence"] == 6
    assert report["blockers"] == []


def test_phase33_validates_when_all_hosted_evidence_exists(tmp_path):
    write_prerequisites(tmp_path)
    write_hosted_evidence(tmp_path)

    report = build_hosted_staging_validation_report(phase33_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_staging_validated"
    assert report["summary"]["verified_hosted_evidence"] == 6
    assert report["summary"]["pending_hosted_evidence"] == 0


def test_phase33_blocks_bad_hosted_status(tmp_path):
    write_prerequisites(tmp_path)
    write_hosted_evidence(tmp_path)
    (tmp_path / "logs" / "hosted-staging" / "phase33-lawyer-owner-acceptance.json").write_text(
        json.dumps({"status": "rejected"}),
        encoding="utf-8",
    )

    report = build_hosted_staging_validation_report(phase33_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "lawyer_owner_acceptance" for item in report["blockers"])


def test_phase33_blocks_missing_prerequisite(tmp_path):
    write_prerequisites(tmp_path)
    (tmp_path / "Docs" / "v2_phase_32_hosted_staging_execution_contract.md").unlink()

    report = build_hosted_staging_validation_report(phase33_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase32_contract" for item in report["blockers"])


def test_phase33_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "hosted-staging-validation.json"
    manifest.write_text(json.dumps(phase33_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_execution"
