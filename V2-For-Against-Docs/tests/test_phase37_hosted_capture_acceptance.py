from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_capture_acceptance_report,
    load_hosted_capture_acceptance_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase37_hosted_capture_acceptance.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase37_hosted_capture_acceptance.py"
    spec = importlib.util.spec_from_file_location("build_phase37_hosted_capture_acceptance", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def acceptance_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase37_hosted_capture_acceptance.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "forbidden_terms": ["X-SL-Legal-Auth-Signature", "postgres://"],
        "prerequisites": [
            {
                "id": "phase36_capture_run",
                "title": "Phase 36 capture run",
                "type": "json_status",
                "path": "logs/readiness/phase36-hosted-evidence-capture-run.json",
                "accepted_statuses": ["hosted_evidence_captured"],
                "pending_statuses": ["ready_for_hosted_capture_runner_configuration", "ready_for_hosted_capture_execution"],
            },
            {
                "id": "phase34_backend_db_validation",
                "title": "Phase 34 validation",
                "type": "json_status",
                "path": "logs/readiness/phase34-backend-db-staging-validation.json",
                "accepted_statuses": ["backend_db_staging_validated"],
                "pending_statuses": ["awaiting_backend_db_staging_evidence"],
            },
            {
                "id": "phase36_contract",
                "title": "Phase 36 contract",
                "type": "document",
                "path": "Docs/v2_phase_36_hosted_evidence_capture_runner_contract.md",
            },
        ],
        "captured_evidence": [
            {
                "id": "api_health_real_backend",
                "title": "API health",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-api-health.json",
                "accepted_statuses": ["healthy"],
                "required_fields": {"runtime": "hosted_staging", "backend": "real", "database_connected": True},
            },
            {
                "id": "signed_workspace_api_smoke",
                "title": "Signed workspace",
                "type": "detached_log",
                "path": "logs/test-runs/phase34-platform-signed-workspace-smoke.log",
            },
            {
                "id": "db_write_guard",
                "title": "DB write guard",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-db-write-guard.json",
                "accepted_statuses": ["no_unintended_writes"],
                "required_fields": {"write_count": 0, "migration_count": 0, "raw_data_uploaded": False},
            },
        ],
    }


def write_prerequisites(
    root: Path,
    *,
    phase36_status: str = "ready_for_hosted_capture_runner_configuration",
    phase34_status: str = "awaiting_backend_db_staging_evidence",
) -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase36-hosted-evidence-capture-run.json").write_text(
        json.dumps({"status": phase36_status}),
        encoding="utf-8",
    )
    (root / "logs" / "readiness" / "phase34-backend-db-staging-validation.json").write_text(
        json.dumps({"status": phase34_status}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_36_hosted_evidence_capture_runner_contract.md").write_text(
        "contract\n",
        encoding="utf-8",
    )


def write_captured_evidence(root: Path) -> None:
    (root / "logs" / "hosted-staging").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "test-runs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "hosted-staging" / "phase34-api-health.json").write_text(
        json.dumps(
            {
                "status": "healthy",
                "runtime": "hosted_staging",
                "backend": "real",
                "database_connected": True,
            }
        ),
        encoding="utf-8",
    )
    (root / "logs" / "test-runs" / "phase34-platform-signed-workspace-smoke.log").write_text(
        "run_id=phase36-signed_workspace_snapshot_smoke\nhttp_status=200\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "logs" / "hosted-staging" / "phase34-db-write-guard.json").write_text(
        json.dumps(
            {
                "status": "no_unintended_writes",
                "write_count": 0,
                "migration_count": 0,
                "raw_data_uploaded": False,
            }
        ),
        encoding="utf-8",
    )


def test_phase37_manifest_loads():
    payload = load_hosted_capture_acceptance_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["captured_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-36-hosted-evidence-capture-runner"
    assert "api_health_real_backend" in evidence_ids
    assert "operator_db_acceptance" in evidence_ids


def test_phase37_awaits_hosted_capture_when_runner_is_dry(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_capture_acceptance_report(acceptance_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_capture_execution"
    assert report["summary"]["verified_prerequisites"] == 1
    assert report["summary"]["pending_prerequisites"] == 2
    assert report["blockers"] == []


def test_phase37_awaits_phase34_validation_after_capture(tmp_path):
    write_prerequisites(tmp_path, phase36_status="hosted_evidence_captured")
    write_captured_evidence(tmp_path)

    report = build_hosted_capture_acceptance_report(acceptance_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_phase34_backend_db_validation"
    assert report["summary"]["verified_captured_evidence"] == 3


def test_phase37_accepts_when_capture_and_phase34_are_validated(tmp_path):
    write_prerequisites(
        tmp_path,
        phase36_status="hosted_evidence_captured",
        phase34_status="backend_db_staging_validated",
    )
    write_captured_evidence(tmp_path)

    report = build_hosted_capture_acceptance_report(acceptance_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_capture_accepted"
    assert report["summary"]["pending_captured_evidence"] == 0


def test_phase37_blocks_forbidden_capture_content(tmp_path):
    write_prerequisites(
        tmp_path,
        phase36_status="hosted_evidence_captured",
        phase34_status="backend_db_staging_validated",
    )
    write_captured_evidence(tmp_path)
    (tmp_path / "logs" / "test-runs" / "phase34-platform-signed-workspace-smoke.log").write_text(
        "run_id=phase36-signed_workspace_snapshot_smoke\nX-SL-Legal-Auth-Signature: value\nexit_status=0\n",
        encoding="utf-8",
    )

    report = build_hosted_capture_acceptance_report(acceptance_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "signed_workspace_api_smoke" for item in report["blockers"])


def test_phase37_blocks_failed_phase36_status(tmp_path):
    write_prerequisites(tmp_path, phase36_status="blocked")

    report = build_hosted_capture_acceptance_report(acceptance_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase36_capture_run" for item in report["blockers"])


def test_phase37_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "hosted-capture-acceptance.json"
    manifest.write_text(json.dumps(acceptance_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_capture_execution"
