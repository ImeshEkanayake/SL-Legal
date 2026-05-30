from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_staging_acceptance_decision_report,
    load_staging_acceptance_decision_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase42_staging_acceptance_decision.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase42_staging_acceptance_decision.py"
    spec = importlib.util.spec_from_file_location("build_phase42_staging_acceptance_decision", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def decision_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase42_staging_acceptance_decision.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "forbidden_terms": ["postgres://", "final legal advice"],
        "prerequisites": [
            {
                "id": "phase41_manifest",
                "title": "Phase 41 manifest",
                "type": "file",
                "path": "rag/evals/phase41_hosted_capture_execution_evidence.json",
            },
            {
                "id": "phase42_contract",
                "title": "Phase 42 contract",
                "type": "document",
                "path": "Docs/v2_phase_42_staging_acceptance_decision_contract.md",
            },
        ],
        "decision_evidence": [
            {
                "id": "phase33_hosted_validation",
                "title": "Phase 33 validation",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase33-hosted-staging-validation.json",
                "accepted_statuses": ["hosted_staging_validated"],
                "pending_statuses": ["awaiting_hosted_execution"],
            },
            {
                "id": "phase34_backend_db_validation",
                "title": "Phase 34 validation",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase34-backend-db-staging-validation.json",
                "accepted_statuses": ["backend_db_staging_validated"],
                "pending_statuses": ["awaiting_backend_db_staging_evidence"],
            },
            {
                "id": "phase37_capture_acceptance",
                "title": "Phase 37 acceptance",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase37-hosted-capture-acceptance.json",
                "accepted_statuses": ["hosted_capture_accepted"],
                "pending_statuses": ["awaiting_phase34_backend_db_validation"],
            },
            {
                "id": "phase38_execution_report",
                "title": "Phase 38 execution",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase38-hosted-capture-execution.json",
                "accepted_statuses": ["hosted_capture_execution_accepted"],
                "pending_statuses": ["ready_for_hosted_capture_execution"],
            },
            {
                "id": "phase40_dry_run_evidence",
                "title": "Phase 40 dry run",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase40-hosted-dry-run-evidence.json",
                "accepted_statuses": ["hosted_dry_run_validated"],
                "pending_statuses": ["awaiting_hosted_dry_run_evidence"],
            },
            {
                "id": "phase41_execution_evidence",
                "title": "Phase 41 execution evidence",
                "group": "hosted_staging",
                "type": "json_status",
                "path": "logs/readiness/phase41-hosted-capture-execution-evidence.json",
                "accepted_statuses": ["hosted_capture_execution_evidence_validated"],
                "pending_statuses": ["awaiting_hosted_capture_execution"],
            },
        ],
        "required_acceptance": [
            {
                "id": "lawyer_owner_acceptance",
                "title": "Lawyer-owner acceptance",
                "group": "owner_acceptance",
                "type": "json_status",
                "path": "logs/hosted-staging/phase42-lawyer-owner-acceptance.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "reviewed_phase41_evidence": True,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                    "production_execution_authorized": False,
                },
            },
            {
                "id": "operator_staging_acceptance",
                "title": "Operator acceptance",
                "group": "operator_acceptance",
                "type": "json_status",
                "path": "logs/hosted-staging/phase42-operator-staging-acceptance.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "reviewed_phase41_evidence": True,
                    "db_migration_applied": False,
                    "raw_data_uploaded": False,
                    "production_execution_authorized": False,
                },
            },
        ],
        "residual_risks": [
            {
                "id": "residual_risk_register",
                "title": "Risk register",
                "group": "risk_acceptance",
                "type": "json_status",
                "path": "logs/hosted-staging/phase42-residual-risk-register.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "unresolved_blockers": 0,
                    "production_execution_authorized": False,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            }
        ],
    }


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase41_hosted_capture_execution_evidence.json",
        "Docs/v2_phase_42_staging_acceptance_decision_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_decision_evidence(root: Path) -> None:
    statuses = {
        "logs/readiness/phase33-hosted-staging-validation.json": "hosted_staging_validated",
        "logs/readiness/phase34-backend-db-staging-validation.json": "backend_db_staging_validated",
        "logs/readiness/phase37-hosted-capture-acceptance.json": "hosted_capture_accepted",
        "logs/readiness/phase38-hosted-capture-execution.json": "hosted_capture_execution_accepted",
        "logs/readiness/phase40-hosted-dry-run-evidence.json": "hosted_dry_run_validated",
        "logs/readiness/phase41-hosted-capture-execution-evidence.json": (
            "hosted_capture_execution_evidence_validated"
        ),
    }
    for path_value, status in statuses.items():
        write_json(root, path_value, {"status": status})


def write_lawyer_acceptance(root: Path, *, production_authorized: bool = False, note: str = "") -> None:
    write_json(
        root,
        "logs/hosted-staging/phase42-lawyer-owner-acceptance.json",
        {
            "status": "accepted",
            "reviewed_phase41_evidence": True,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "production_execution_authorized": production_authorized,
            "note": note,
        },
    )


def write_operator_acceptance(root: Path) -> None:
    write_json(
        root,
        "logs/hosted-staging/phase42-operator-staging-acceptance.json",
        {
            "status": "accepted",
            "reviewed_phase41_evidence": True,
            "db_migration_applied": False,
            "raw_data_uploaded": False,
            "production_execution_authorized": False,
        },
    )


def write_risk_register(root: Path, *, unresolved_blockers: int = 0, note: str = "") -> None:
    write_json(
        root,
        "logs/hosted-staging/phase42-residual-risk-register.json",
        {
            "status": "accepted",
            "unresolved_blockers": unresolved_blockers,
            "production_execution_authorized": False,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "note": note,
        },
    )


def test_phase42_manifest_loads():
    payload = load_staging_acceptance_decision_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["decision_evidence"]}
    acceptance_ids = {item["id"] for item in payload["required_acceptance"]}

    assert payload["target_release_tag"] == "v2-phase-41-hosted-capture-execution-evidence"
    assert "phase41_execution_evidence" in evidence_ids
    assert {"lawyer_owner_acceptance", "operator_staging_acceptance"} <= acceptance_ids


def test_phase42_local_report_awaits_staging_execution_evidence(tmp_path):
    write_prerequisites(tmp_path)

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_staging_execution_evidence"
    assert report["decision"] == "wait_for_hosted_evidence"
    assert report["production_execution_authorized"] is False
    assert report["blockers"] == []


def test_phase42_awaits_required_acceptance_after_evidence_validates(tmp_path):
    write_prerequisites(tmp_path)
    write_decision_evidence(tmp_path)

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_required_acceptance"
    assert report["decision"] == "wait_for_acceptance"
    assert {item["id"] for item in report["pending_acceptance"]} == {
        "lawyer_owner_acceptance",
        "operator_staging_acceptance",
        "residual_risk_register",
    }


def test_phase42_accepts_staging_for_production_planning(tmp_path):
    write_prerequisites(tmp_path)
    write_decision_evidence(tmp_path)
    write_lawyer_acceptance(tmp_path)
    write_operator_acceptance(tmp_path)
    write_risk_register(tmp_path)

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "staging_accepted_for_production_planning"
    assert report["decision"] == "go_for_production_planning"
    assert report["lawyer_review_required"] is True
    assert report["no_final_legal_advice"] is True


def test_phase42_blocks_production_authorization_in_owner_acceptance(tmp_path):
    write_prerequisites(tmp_path)
    write_decision_evidence(tmp_path)
    write_lawyer_acceptance(tmp_path, production_authorized=True)
    write_operator_acceptance(tmp_path)
    write_risk_register(tmp_path)

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "lawyer_owner_acceptance" for item in report["blockers"])


def test_phase42_blocks_unresolved_residual_risks(tmp_path):
    write_prerequisites(tmp_path)
    write_decision_evidence(tmp_path)
    write_lawyer_acceptance(tmp_path)
    write_operator_acceptance(tmp_path)
    write_risk_register(tmp_path, unresolved_blockers=1)

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "residual_risk_register" for item in report["blockers"])


def test_phase42_blocks_forbidden_acceptance_content(tmp_path):
    write_prerequisites(tmp_path)
    write_decision_evidence(tmp_path)
    write_lawyer_acceptance(tmp_path)
    write_operator_acceptance(tmp_path)
    write_risk_register(tmp_path, note="final legal advice")

    report = build_staging_acceptance_decision_report(decision_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "residual_risk_register" for item in report["blockers"])


def test_phase42_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase42-staging-acceptance-decision.json"
    manifest.write_text(json.dumps(decision_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_staging_execution_evidence"
