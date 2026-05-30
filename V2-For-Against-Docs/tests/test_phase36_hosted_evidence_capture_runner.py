from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import load_hosted_evidence_capture_runner_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase36_hosted_evidence_capture_runner.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "run_phase36_hosted_evidence_capture.py"
    spec = importlib.util.spec_from_file_location("run_phase36_hosted_evidence_capture", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def runner_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase36_hosted_evidence_capture_runner.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "capture_manifest_path": "capture.json",
        "prerequisites": [
            {
                "id": "phase35_capture_plan_report",
                "title": "Phase 35 capture plan report",
                "type": "json_status",
                "path": "logs/readiness/phase35-hosted-evidence-capture-plan.json",
                "accepted_statuses": ["ready_for_hosted_capture_configuration", "ready_for_capture_execution"],
            },
            {
                "id": "phase35_contract",
                "title": "Phase 35 contract",
                "type": "document",
                "path": "Docs/v2_phase_35_hosted_evidence_capture_contract.md",
            },
        ],
        "response_expectations": [
            {"task_id": "api_health_capture", "expected_json_keys": ["status"]},
            {
                "task_id": "signed_workspace_snapshot_smoke",
                "expected_json_keys": ["activeCaseId", "documents", "drafts", "reviewItems"],
            },
            {
                "task_id": "document_source_status_smoke",
                "expected_json_keys": ["documentId", "title", "documentType", "sourceId"],
            },
        ],
    }


def capture_manifest() -> dict[str, object]:
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
        ],
        "required_environment": [
            {"name": "SL_LEGAL_STAGING_API_BASE_URL", "category": "staging_api", "required": True, "url": True},
            {"name": "SL_LEGAL_STAGING_USER_ID", "category": "staging_auth", "required": True},
            {
                "name": "SL_LEGAL_AUTH_HMAC_SECRET",
                "category": "staging_auth",
                "required": True,
                "secret": True,
                "min_length": 32,
            },
            {"name": "SL_LEGAL_STAGING_CASE_ID", "category": "staging_fixture", "required": True},
            {"name": "SL_LEGAL_STAGING_DOCUMENT_ID", "category": "staging_fixture", "required": True},
            {
                "name": "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED",
                "category": "db_operator_confirmation",
                "required": True,
                "expected_value": "true",
            },
            {
                "name": "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT",
                "category": "db_operator_confirmation",
                "required": True,
                "expected_value": "0",
            },
            {
                "name": "SL_LEGAL_PHASE35_DB_MIGRATION_COUNT",
                "category": "db_operator_confirmation",
                "required": True,
                "expected_value": "0",
            },
            {
                "name": "SL_LEGAL_PHASE35_RAW_DATA_UPLOADED",
                "category": "data_operator_confirmation",
                "required": True,
                "expected_value": "false",
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
                "id": "document_source_status_smoke",
                "title": "Document source",
                "type": "signed_http_check",
                "method": "GET",
                "path_template": "/v1/ui/cases/{case_id}/documents/{document_id}/status",
                "phase34_evidence_id": "document_source_real_backend",
                "evidence_output": "logs/test-runs/phase34-platform-document-source-smoke.log",
                "writes_database": True,
                "write_classification": "audit_event_only",
            },
            {
                "id": "db_readonly_health_template",
                "title": "DB read-only health",
                "type": "operator_json",
                "phase34_evidence_id": "db_readonly_health",
                "evidence_output": "logs/hosted-staging/phase34-db-readonly-health.json",
                "writes_database": False,
            },
            {
                "id": "db_write_guard_template",
                "title": "DB write guard",
                "type": "operator_json",
                "phase34_evidence_id": "db_write_guard",
                "evidence_output": "logs/hosted-staging/phase34-db-write-guard.json",
                "writes_database": False,
            },
            {
                "id": "operator_db_acceptance_template",
                "title": "Operator acceptance",
                "type": "operator_json",
                "phase34_evidence_id": "operator_db_acceptance",
                "evidence_output": "logs/hosted-staging/phase34-operator-db-acceptance.json",
                "writes_database": False,
            },
        ],
    }


def valid_environment() -> dict[str, str]:
    return {
        "SL_LEGAL_STAGING_API_BASE_URL": "https://staging.example.invalid",
        "SL_LEGAL_STAGING_USER_ID": "reviewer@example.invalid",
        "SL_LEGAL_AUTH_HMAC_SECRET": "a" * 32,
        "SL_LEGAL_STAGING_CASE_ID": "case-1",
        "SL_LEGAL_STAGING_DOCUMENT_ID": "doc-1",
        "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED": "true",
        "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT": "0",
        "SL_LEGAL_PHASE35_DB_MIGRATION_COUNT": "0",
        "SL_LEGAL_PHASE35_RAW_DATA_UPLOADED": "false",
    }


def write_prerequisites(root: Path) -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase35-hosted-evidence-capture-plan.json").write_text(
        json.dumps({"status": "ready_for_hosted_capture_configuration"}),
        encoding="utf-8",
    )
    (root / "logs" / "readiness" / "phase34-backend-db-staging-validation.json").write_text(
        json.dumps({"status": "awaiting_backend_db_staging_evidence"}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_35_hosted_evidence_capture_contract.md").write_text("contract\n", encoding="utf-8")


def simulated_http_client(method: str, url: str, headers: dict[str, str], timeout_seconds: int):
    module = load_script()
    assert method == "GET"
    assert timeout_seconds == 5
    if url.endswith("/health"):
        return module.HttpCaptureResponse(200, {"content-type": "application/json"}, b'{"status":"ok"}')
    if url.endswith("/workspace"):
        assert "X-SL-Legal-Auth-Signature" in headers
        return module.HttpCaptureResponse(
            200,
            {"content-type": "application/json"},
            b'{"activeCaseId":"case-1","documents":[],"drafts":[],"reviewItems":[]}',
        )
    return module.HttpCaptureResponse(
        200,
        {"content-type": "application/json"},
        b'{"documentId":"doc-1","title":"Doc","documentType":"authority","sourceId":"TEST"}',
    )


def test_phase36_manifest_loads():
    payload = load_hosted_evidence_capture_runner_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-35-hosted-evidence-capture-plan"
    assert payload["capture_manifest_path"] == "rag/evals/phase35_hosted_evidence_capture.json"
    assert len(payload["response_expectations"]) >= 3


def test_phase36_dry_run_ready_for_runner_configuration(tmp_path):
    module = load_script()
    write_prerequisites(tmp_path)

    report = module.run_capture_runner(
        runner_payload=runner_manifest(),
        capture_payload=capture_manifest(),
        project_root=tmp_path,
        environment={},
        include_environment=False,
        execute=False,
    )

    assert report["status"] == "ready_for_hosted_capture_runner_configuration"
    assert report["capture_results"] == []
    assert report["summary"]["verified_prerequisites"] == 2


def test_phase36_ready_for_execution_with_environment_but_no_execute(tmp_path):
    module = load_script()
    write_prerequisites(tmp_path)

    report = module.run_capture_runner(
        runner_payload=runner_manifest(),
        capture_payload=capture_manifest(),
        project_root=tmp_path,
        environment=valid_environment(),
        include_environment=True,
        execute=False,
    )

    assert report["status"] == "ready_for_hosted_capture_execution"
    assert report["capture_results"] == []


def test_phase36_execute_writes_scrubbed_evidence(tmp_path):
    module = load_script()
    write_prerequisites(tmp_path)

    report = module.run_capture_runner(
        runner_payload=runner_manifest(),
        capture_payload=capture_manifest(),
        project_root=tmp_path,
        environment=valid_environment(),
        include_environment=True,
        execute=True,
        timeout_seconds=5,
        http_client=simulated_http_client,
        now_utc="2026-05-30T00:00:00Z",
    )

    assert report["status"] == "hosted_evidence_captured"
    assert report["summary"]["captured_evidence"] == 6
    health = json.loads((tmp_path / "logs" / "hosted-staging" / "phase34-api-health.json").read_text())
    write_guard = json.loads((tmp_path / "logs" / "hosted-staging" / "phase34-db-write-guard.json").read_text())
    workspace_log = (tmp_path / "logs" / "test-runs" / "phase34-platform-signed-workspace-smoke.log").read_text()

    assert health["status"] == "healthy"
    assert health["database_connected"] is True
    assert write_guard["status"] == "no_unintended_writes"
    assert "exit_status=0" in workspace_log
    assert valid_environment()["SL_LEGAL_AUTH_HMAC_SECRET"] not in workspace_log
    assert "staging.example.invalid" not in workspace_log


def test_phase36_blocks_execute_without_environment(tmp_path):
    module = load_script()
    write_prerequisites(tmp_path)

    report = module.run_capture_runner(
        runner_payload=runner_manifest(),
        capture_payload=capture_manifest(),
        project_root=tmp_path,
        environment={},
        include_environment=False,
        execute=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "execute_requires_environment" for item in report["blockers"])


def test_phase36_blocks_missing_expected_json_keys(tmp_path):
    module = load_script()
    write_prerequisites(tmp_path)

    def bad_http_client(method: str, url: str, headers: dict[str, str], timeout_seconds: int):
        return module.HttpCaptureResponse(200, {"content-type": "application/json"}, b'{"status":"ok"}')

    report = module.run_capture_runner(
        runner_payload=runner_manifest(),
        capture_payload=capture_manifest(),
        project_root=tmp_path,
        environment=valid_environment(),
        include_environment=True,
        execute=True,
        timeout_seconds=5,
        http_client=bad_http_client,
        now_utc="2026-05-30T00:00:00Z",
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "signed_workspace_snapshot_smoke" for item in report["blockers"])


def test_phase36_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "runner.json"
    capture = tmp_path / "capture.json"
    output = tmp_path / "capture-run.json"
    manifest.write_text(json.dumps(runner_manifest()), encoding="utf-8")
    capture.write_text(json.dumps(capture_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_hosted_capture_runner_configuration"
