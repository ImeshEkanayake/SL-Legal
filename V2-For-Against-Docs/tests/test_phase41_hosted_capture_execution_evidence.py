from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_capture_execution_evidence_report,
    load_hosted_capture_execution_evidence_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase41_hosted_capture_execution_evidence.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase41_hosted_capture_execution_evidence.py"
    spec = importlib.util.spec_from_file_location("build_phase41_hosted_capture_execution_evidence", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def execution_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase41_hosted_capture_execution_evidence.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "forbidden_terms": ["postgres://", "X-SL-Legal-Auth-Signature"],
        "prerequisites": [
            {
                "id": "phase40_manifest",
                "title": "Phase 40 manifest",
                "type": "file",
                "path": "rag/evals/phase40_hosted_dry_run_evidence.json",
            },
            {
                "id": "phase41_contract",
                "title": "Phase 41 contract",
                "type": "document",
                "path": "Docs/v2_phase_41_hosted_capture_execution_evidence_contract.md",
            },
        ],
        "execution_evidence": [
            {
                "id": "phase40_dry_run_evidence",
                "title": "Phase 40 dry-run evidence",
                "group": "control_report",
                "type": "json_status",
                "path": "logs/readiness/phase40-hosted-dry-run-evidence.json",
                "accepted_statuses": ["hosted_dry_run_validated"],
                "pending_statuses": ["awaiting_hosted_environment_configuration"],
            },
            {
                "id": "phase38_execution_report",
                "title": "Phase 38 execution report",
                "group": "control_report",
                "type": "json_status",
                "path": "logs/readiness/phase38-hosted-capture-execution.json",
                "accepted_statuses": [
                    "hosted_capture_executed_pending_backend_db_validation",
                    "hosted_capture_executed_pending_acceptance",
                    "hosted_capture_execution_accepted",
                ],
                "pending_statuses": ["ready_for_hosted_capture_execution"],
                "required_fields": {
                    "execute": True,
                    "environment_included": True,
                    "summary.phase36_status": "hosted_evidence_captured",
                    "summary.captured_evidence": 7,
                    "summary.blockers": 0,
                },
            },
            {
                "id": "phase36_capture_run",
                "title": "Phase 36 capture run",
                "group": "control_report",
                "type": "json_status",
                "path": "logs/readiness/phase36-hosted-evidence-capture-run.json",
                "accepted_statuses": ["hosted_evidence_captured"],
                "pending_statuses": ["ready_for_hosted_capture_execution"],
                "required_fields": {
                    "execute": True,
                    "environment_included": True,
                    "summary.captured_evidence": 7,
                    "summary.failed_captures": 0,
                    "summary.blockers": 0,
                },
            },
            {
                "id": "phase34_backend_db_validation",
                "title": "Phase 34 validation",
                "group": "control_report",
                "type": "json_status",
                "path": "logs/readiness/phase34-backend-db-staging-validation.json",
                "accepted_statuses": ["backend_db_staging_validated"],
                "pending_statuses": ["awaiting_backend_db_staging_evidence"],
            },
            {
                "id": "phase37_capture_acceptance",
                "title": "Phase 37 acceptance",
                "group": "control_report",
                "type": "json_status",
                "path": "logs/readiness/phase37-hosted-capture-acceptance.json",
                "accepted_statuses": ["hosted_capture_accepted"],
                "pending_statuses": ["awaiting_phase34_backend_db_validation"],
            },
            {
                "id": "api_health_real_backend",
                "title": "Hosted API health",
                "group": "captured_evidence",
                "type": "json_status",
                "path": "logs/hosted-staging/phase34-api-health.json",
                "accepted_statuses": ["healthy"],
                "required_fields": {
                    "runtime": "hosted_staging",
                    "backend": "real",
                    "database_connected": True,
                },
            },
        ],
    }


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase40_hosted_dry_run_evidence.json",
        "Docs/v2_phase_41_hosted_capture_execution_evidence_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_phase40(root: Path, status: str = "hosted_dry_run_validated") -> None:
    write_json(root, "logs/readiness/phase40-hosted-dry-run-evidence.json", {"status": status})


def write_phase38(root: Path, status: str = "hosted_capture_executed_pending_backend_db_validation") -> None:
    write_json(
        root,
        "logs/readiness/phase38-hosted-capture-execution.json",
        {
            "status": status,
            "execute": True,
            "environment_included": True,
            "summary": {
                "phase36_status": "hosted_evidence_captured",
                "captured_evidence": 7,
                "blockers": 0,
            },
        },
    )


def write_phase36(root: Path) -> None:
    write_json(
        root,
        "logs/readiness/phase36-hosted-evidence-capture-run.json",
        {
            "status": "hosted_evidence_captured",
            "execute": True,
            "environment_included": True,
            "summary": {
                "captured_evidence": 7,
                "failed_captures": 0,
                "blockers": 0,
            },
        },
    )


def write_phase34(root: Path, status: str = "awaiting_backend_db_staging_evidence") -> None:
    write_json(root, "logs/readiness/phase34-backend-db-staging-validation.json", {"status": status})


def write_phase37(root: Path, status: str = "awaiting_phase34_backend_db_validation") -> None:
    write_json(root, "logs/readiness/phase37-hosted-capture-acceptance.json", {"status": status})


def write_captured_evidence(root: Path, *, extra: str = "") -> None:
    write_json(
        root,
        "logs/hosted-staging/phase34-api-health.json",
        {
            "status": "healthy",
            "runtime": "hosted_staging",
            "backend": "real",
            "database_connected": True,
            "note": extra,
        },
    )


def test_phase41_manifest_loads():
    payload = load_hosted_capture_execution_evidence_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["execution_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-40-hosted-dry-run-evidence"
    assert "phase38_execution_report" in evidence_ids
    assert "db_write_guard" in evidence_ids


def test_phase41_local_report_awaits_dry_run_validation(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_dry_run_validation"
    assert report["blockers"] == []


def test_phase41_awaits_capture_after_dry_run_validation(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_capture_execution"


def test_phase41_reports_pending_backend_validation(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)
    write_phase38(tmp_path, status="hosted_capture_executed_pending_backend_db_validation")
    write_phase36(tmp_path)
    write_phase34(tmp_path)
    write_phase37(tmp_path)
    write_captured_evidence(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_capture_executed_pending_backend_db_validation"


def test_phase41_reports_pending_acceptance(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)
    write_phase38(tmp_path, status="hosted_capture_executed_pending_acceptance")
    write_phase36(tmp_path)
    write_phase34(tmp_path, status="backend_db_staging_validated")
    write_phase37(tmp_path)
    write_captured_evidence(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_capture_executed_pending_acceptance"


def test_phase41_validates_full_execution_evidence(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)
    write_phase38(tmp_path, status="hosted_capture_execution_accepted")
    write_phase36(tmp_path)
    write_phase34(tmp_path, status="backend_db_staging_validated")
    write_phase37(tmp_path, status="hosted_capture_accepted")
    write_captured_evidence(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_capture_execution_evidence_validated"
    assert report["summary"]["verified_execution_evidence"] == 6


def test_phase41_blocks_forbidden_execution_content(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)
    write_phase38(tmp_path, status="hosted_capture_execution_accepted")
    write_phase36(tmp_path)
    write_phase34(tmp_path, status="backend_db_staging_validated")
    write_phase37(tmp_path, status="hosted_capture_accepted")
    write_captured_evidence(tmp_path, extra="postgres://secret")

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "api_health_real_backend" for item in report["blockers"])


def test_phase41_blocks_missing_captured_evidence_after_capture(tmp_path):
    write_prerequisites(tmp_path)
    write_phase40(tmp_path)
    write_phase38(tmp_path, status="hosted_capture_executed_pending_backend_db_validation")
    write_phase36(tmp_path)
    write_phase34(tmp_path)
    write_phase37(tmp_path)

    report = build_hosted_capture_execution_evidence_report(execution_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "api_health_real_backend" for item in report["blockers"])


def test_phase41_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase41-hosted-capture-execution-evidence.json"
    manifest.write_text(json.dumps(execution_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_dry_run_validation"
