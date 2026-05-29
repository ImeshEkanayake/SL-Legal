from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_evidence_capture_plan,
    load_hosted_evidence_capture_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase35_hosted_evidence_capture.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase35_hosted_evidence_capture_plan.py"
    spec = importlib.util.spec_from_file_location("build_phase35_hosted_evidence_capture_plan", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase35_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase35_hosted_evidence_capture.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "prerequisites": [
            {
                "id": "phase34_validation_gate",
                "title": "Phase 34 validation gate",
                "type": "json_status",
                "path": "logs/readiness/phase34-backend-db-staging-validation.json",
                "accepted_statuses": ["awaiting_backend_db_staging_evidence", "backend_db_staging_validated"],
            },
            {
                "id": "phase34_contract",
                "title": "Phase 34 contract",
                "type": "document",
                "path": "Docs/v2_phase_34_backend_db_staging_validation_contract.md",
            },
        ],
        "required_environment": [
            {
                "name": "SL_LEGAL_STAGING_API_BASE_URL",
                "category": "staging_api",
                "required": True,
                "url": True,
            },
            {
                "name": "SL_LEGAL_STAGING_USER_ID",
                "category": "staging_auth",
                "required": True,
            },
            {
                "name": "SL_LEGAL_AUTH_HMAC_SECRET",
                "category": "staging_auth",
                "required": True,
                "secret": True,
                "min_length": 32,
            },
            {
                "name": "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT",
                "category": "db_operator_confirmation",
                "required": True,
                "expected_value": "0",
            },
        ],
        "capture_tasks": [
            {
                "id": "api_health_capture",
                "title": "API health",
                "type": "http_check",
                "method": "GET",
                "path_template": "/health",
                "phase34_evidence_id": "api_health_real_backend",
                "evidence_output": "logs/hosted-staging/phase34-api-health.json",
                "writes_database": False,
            },
            {
                "id": "signed_workspace_snapshot_smoke",
                "title": "Signed workspace",
                "type": "signed_http_check",
                "method": "GET",
                "path_template": "/v1/ui/cases/{case_id}/workspace",
                "phase34_evidence_id": "signed_workspace_api_smoke",
                "evidence_output": "logs/test-runs/phase34-platform-signed-workspace-smoke.log",
                "writes_database": True,
                "write_classification": "audit_event_only",
            },
            {
                "id": "db_write_guard_template",
                "title": "DB write guard",
                "type": "operator_json",
                "phase34_evidence_id": "db_write_guard",
                "evidence_output": "logs/hosted-staging/phase34-db-write-guard.json",
                "writes_database": False,
            },
        ],
    }


def write_prerequisites(root: Path, *, phase34_status: str = "awaiting_backend_db_staging_evidence") -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase34-backend-db-staging-validation.json").write_text(
        json.dumps({"status": phase34_status}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_34_backend_db_staging_validation_contract.md").write_text("contract\n", encoding="utf-8")


def valid_environment() -> dict[str, str]:
    return {
        "SL_LEGAL_STAGING_API_BASE_URL": "https://staging.example.invalid",
        "SL_LEGAL_STAGING_USER_ID": "reviewer@example.invalid",
        "SL_LEGAL_AUTH_HMAC_SECRET": "a" * 32,
        "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT": "0",
    }


def test_phase35_manifest_loads():
    payload = load_hosted_evidence_capture_manifest(MANIFEST_PATH)
    task_ids = {item["id"] for item in payload["capture_tasks"]}

    assert payload["target_release_tag"] == "v2-phase-34-backend-db-staging-validation"
    assert "api_health_capture" in task_ids
    assert "signed_workspace_snapshot_smoke" in task_ids
    assert "db_write_guard_template" in task_ids


def test_phase35_ready_for_hosted_capture_configuration_without_env(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_evidence_capture_plan(phase35_manifest(), project_root=tmp_path)

    assert report["status"] == "ready_for_hosted_capture_configuration"
    assert report["summary"]["verified_prerequisites"] == 2
    assert report["environment"]["included"] is False
    assert report["blockers"] == []
    assert all(item["status"] == "requires_hosted_environment" for item in report["capture_tasks"])


def test_phase35_ready_for_capture_execution_with_valid_env(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_evidence_capture_plan(
        phase35_manifest(),
        project_root=tmp_path,
        environment=valid_environment(),
        include_environment=True,
    )

    assert report["status"] == "ready_for_capture_execution"
    assert report["summary"]["signed_capture_tasks"] == 1
    assert report["summary"]["db_writing_capture_tasks"] == 1
    assert all(item["status"] == "ready_for_hosted_execution" for item in report["capture_tasks"])


def test_phase35_blocks_missing_required_env(tmp_path):
    write_prerequisites(tmp_path)
    environment = valid_environment()
    environment.pop("SL_LEGAL_AUTH_HMAC_SECRET")

    report = build_hosted_evidence_capture_plan(
        phase35_manifest(),
        project_root=tmp_path,
        environment=environment,
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "env:SL_LEGAL_AUTH_HMAC_SECRET" for item in report["blockers"])


def test_phase35_blocks_db_writing_task_without_classification(tmp_path):
    write_prerequisites(tmp_path)
    manifest = phase35_manifest()
    manifest["capture_tasks"][1].pop("write_classification")

    report = build_hosted_evidence_capture_plan(
        manifest,
        project_root=tmp_path,
        environment=valid_environment(),
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "signed_workspace_snapshot_smoke" for item in report["blockers"])


def test_phase35_blocks_missing_phase34_prerequisite(tmp_path):
    write_prerequisites(tmp_path)
    (tmp_path / "logs" / "readiness" / "phase34-backend-db-staging-validation.json").unlink()

    report = build_hosted_evidence_capture_plan(phase35_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase34_validation_gate" for item in report["blockers"])


def test_phase35_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "hosted-evidence-capture-plan.json"
    manifest.write_text(json.dumps(phase35_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_hosted_capture_configuration"
