from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_backend_db_staging_validation_report,
    load_backend_db_staging_validation_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase34_backend_db_staging_validation.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase34_backend_db_staging_validation.py"
    spec = importlib.util.spec_from_file_location("build_phase34_backend_db_staging_validation", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase34_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase34_backend_db_staging_validation.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "database_mode": "read_only_validation",
        "prerequisites": [
            {
                "id": "phase33_manifest",
                "title": "Phase 33 manifest",
                "type": "file",
                "path": "rag/evals/phase33_hosted_staging_validation.json",
            },
            {
                "id": "phase33_contract",
                "title": "Phase 33 contract",
                "type": "document",
                "path": "Docs/v2_phase_33_hosted_staging_validation_contract.md",
            },
            {
                "id": "phase34_contract",
                "title": "Phase 34 contract",
                "type": "document",
                "path": "Docs/v2_phase_34_backend_db_staging_validation_contract.md",
            },
        ],
        "staging_evidence": [
            {
                "id": "phase33_hosted_validation_report",
                "title": "Phase 33 hosted validation report",
                "type": "json_status",
                "path": "logs/readiness/phase33-hosted-staging-validation.json",
                "accepted_statuses": ["hosted_staging_validated"],
                "pending_statuses": ["awaiting_hosted_execution"],
            },
            {
                "id": "api_health_real_backend",
                "title": "API health",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-api-health.json",
                "accepted_statuses": ["healthy"],
                "required_fields": {
                    "runtime": "hosted_staging",
                    "backend": "real",
                    "database_connected": True,
                },
            },
            {
                "id": "signed_workspace_api_smoke",
                "title": "Signed workspace API smoke",
                "type": "detached_log",
                "path": "logs/test-runs/phase34-platform-signed-workspace-smoke.log",
            },
            {
                "id": "db_readonly_health",
                "title": "DB read-only health",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-db-readonly-health.json",
                "accepted_statuses": ["healthy"],
                "required_fields": {"access_mode": "read_only", "migration_applied": False},
            },
            {
                "id": "db_write_guard",
                "title": "DB write guard",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-db-write-guard.json",
                "accepted_statuses": ["no_unintended_writes"],
                "required_fields": {
                    "write_count": 0,
                    "migration_count": 0,
                    "raw_data_uploaded": False,
                },
            },
            {
                "id": "authority_workflow_real_backend",
                "title": "Authority workflow",
                "type": "detached_log",
                "path": "logs/test-runs/phase34-platform-authority-workflow.log",
            },
            {
                "id": "document_source_real_backend",
                "title": "Document source smoke",
                "type": "detached_log",
                "path": "logs/test-runs/phase34-platform-document-source-smoke.log",
            },
            {
                "id": "operator_db_acceptance",
                "title": "Operator acceptance",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-operator-db-acceptance.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "database_migrated": False,
                    "raw_data_uploaded": False,
                    "writes_reviewed": True,
                },
            },
        ],
    }


def write_prerequisites(root: Path) -> None:
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase33_hosted_staging_validation.json").write_text(
        json.dumps({"schema_version": "phase33_hosted_staging_validation.v1"}),
        encoding="utf-8",
    )
    (root / "Docs" / "releases").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_33_hosted_staging_validation_contract.md").write_text("contract\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_34_backend_db_staging_validation_contract.md").write_text("contract\n", encoding="utf-8")


def write_staging_evidence(root: Path, *, phase33_status: str = "hosted_staging_validated") -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "test-runs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "hosted-staging").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase33-hosted-staging-validation.json").write_text(
        json.dumps({"status": phase33_status}),
        encoding="utf-8",
    )
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
        "run_id=phase34-platform-signed-workspace-smoke\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "logs" / "hosted-staging" / "phase34-db-readonly-health.json").write_text(
        json.dumps({"status": "healthy", "access_mode": "read_only", "migration_applied": False}),
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
    (root / "logs" / "test-runs" / "phase34-platform-authority-workflow.log").write_text(
        "run_id=phase34-platform-authority-workflow\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "logs" / "test-runs" / "phase34-platform-document-source-smoke.log").write_text(
        "run_id=phase34-platform-document-source-smoke\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "logs" / "hosted-staging" / "phase34-operator-db-acceptance.json").write_text(
        json.dumps({"status": "accepted", "database_migrated": False, "raw_data_uploaded": False, "writes_reviewed": True}),
        encoding="utf-8",
    )


def test_phase34_manifest_loads():
    payload = load_backend_db_staging_validation_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["staging_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-33-hosted-staging-validation"
    assert "db_readonly_health" in evidence_ids
    assert "operator_db_acceptance" in evidence_ids


def test_phase34_awaits_backend_db_evidence_when_local_only(tmp_path):
    write_prerequisites(tmp_path)

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_backend_db_staging_evidence"
    assert report["summary"]["verified_prerequisites"] == 3
    assert report["summary"]["pending_staging_evidence"] == 8
    assert report["blockers"] == []


def test_phase34_validates_when_all_staging_evidence_exists(tmp_path):
    write_prerequisites(tmp_path)
    write_staging_evidence(tmp_path)

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)

    assert report["status"] == "backend_db_staging_validated"
    assert report["summary"]["verified_staging_evidence"] == 8
    assert report["summary"]["pending_staging_evidence"] == 0


def test_phase34_blocks_bad_db_write_guard_status(tmp_path):
    write_prerequisites(tmp_path)
    write_staging_evidence(tmp_path)
    (tmp_path / "logs" / "hosted-staging" / "phase34-db-write-guard.json").write_text(
        json.dumps(
            {
                "status": "writes_detected",
                "write_count": 1,
                "migration_count": 0,
                "raw_data_uploaded": False,
            }
        ),
        encoding="utf-8",
    )

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "db_write_guard" for item in report["blockers"])


def test_phase34_blocks_accepted_db_guard_with_nonzero_write_count(tmp_path):
    write_prerequisites(tmp_path)
    write_staging_evidence(tmp_path)
    (tmp_path / "logs" / "hosted-staging" / "phase34-db-write-guard.json").write_text(
        json.dumps(
            {
                "status": "no_unintended_writes",
                "write_count": 1,
                "migration_count": 0,
                "raw_data_uploaded": False,
            }
        ),
        encoding="utf-8",
    )

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)
    guard = next(item for item in report["staging_evidence"] if item["id"] == "db_write_guard")

    assert report["status"] == "blocked"
    assert guard["field_mismatches"][0]["field"] == "write_count"


def test_phase34_keeps_phase33_pending_as_awaiting_evidence(tmp_path):
    write_prerequisites(tmp_path)
    write_staging_evidence(tmp_path, phase33_status="awaiting_hosted_execution")

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_backend_db_staging_evidence"
    assert any(item["id"] == "phase33_hosted_validation_report" for item in report["pending_staging_evidence"])


def test_phase34_blocks_missing_prerequisite(tmp_path):
    write_prerequisites(tmp_path)
    (tmp_path / "Docs" / "v2_phase_34_backend_db_staging_validation_contract.md").unlink()

    report = build_backend_db_staging_validation_report(phase34_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase34_contract" for item in report["blockers"])


def test_phase34_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "backend-db-staging-validation.json"
    manifest.write_text(json.dumps(phase34_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_backend_db_staging_evidence"
