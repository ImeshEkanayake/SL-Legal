from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_production_cutover_execution_plan_report,
    load_production_cutover_execution_plan_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase45_production_cutover_execution_plan.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase45_production_cutover_execution_plan.py"
    spec = importlib.util.spec_from_file_location("build_phase45_production_cutover_execution_plan", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def execution_plan_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase45_production_cutover_execution_plan.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "cutover_environment": "production",
        "forbidden_terms": ["postgres://", "final legal advice"],
        "prerequisites": [
            {
                "id": "phase44_manifest",
                "title": "Phase 44 manifest",
                "type": "file",
                "path": "rag/evals/phase44_production_cutover_dry_run.json",
            },
            {
                "id": "phase45_contract",
                "title": "Phase 45 contract",
                "type": "document",
                "path": "Docs/v2_phase_45_production_cutover_execution_plan_contract.md",
            },
        ],
        "dry_run_evidence": [
            {
                "id": "phase44_production_cutover_dry_run",
                "title": "Phase 44 dry run",
                "group": "dry_run",
                "type": "json_status",
                "path": "logs/readiness/phase44-production-cutover-dry-run.json",
                "accepted_statuses": ["production_cutover_dry_run_planned"],
                "pending_statuses": ["awaiting_production_cutover_readiness"],
                "required_fields": {
                    "production_execution_authorized": False,
                    "production_mutation_authorized": False,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                    "release_promotion_authorized": False,
                    "phase45_execution_plan_authorized": True,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            }
        ],
        "approval_gates": [
            {
                "id": "lawyer_owner_execution_plan_signoff",
                "title": "Lawyer-owner signoff",
                "group": "approval_gate",
                "type": "json_status",
                "path": "logs/production-cutover/phase45-lawyer-owner-execution-plan-signoff.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "reviewed_phase44_dry_run": True,
                    "reviewed_execution_commands": True,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                    "production_execution_authorized": False,
                },
            },
            {
                "id": "operator_execution_plan_signoff",
                "title": "Operator signoff",
                "group": "approval_gate",
                "type": "json_status",
                "path": "logs/production-cutover/phase45-operator-execution-plan-signoff.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "reviewed_phase44_dry_run": True,
                    "rollback_points_confirmed": True,
                    "production_execution_authorized": False,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                },
            },
            {
                "id": "legal_review_signoff",
                "title": "Legal review signoff",
                "group": "approval_gate",
                "type": "json_status",
                "path": "logs/production-cutover/phase45-legal-review-signoff.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                    "production_execution_authorized": False,
                },
            },
        ],
        "rollback_points": [
            {
                "id": "rollback_previous_deployment_alias",
                "title": "Rollback alias",
                "owner": "operator",
                "trigger": "Smoke verification fails.",
                "action": "Restore previous production deployment alias.",
                "expected_evidence": "logs/production-cutover/phase45-rollback-alias.json",
            }
        ],
        "execution_commands": [
            {
                "id": "preflight_readiness",
                "title": "Preflight readiness",
                "stage": "preflight",
                "owner": "operator",
                "command": ["scripts/run_detached_quality_gate.sh", "production-cutover-readiness-env", "phase45-env"],
                "expected_evidence": "logs/test-runs/phase45-env.log",
                "requires_explicit_execution_flag": False,
                "execution_approved": False,
                "mutates_production": False,
                "database_migration": False,
                "raw_data_upload": False,
                "index_mutation": False,
                "release_promotion": False,
            },
            {
                "id": "production_deploy",
                "title": "Production deploy",
                "stage": "cutover",
                "owner": "operator",
                "command": ["vercel", "deploy", "--prebuilt", "--prod", "--confirm-phase45-execution"],
                "expected_evidence": "logs/production-cutover/phase45-deploy.json",
                "requires_explicit_execution_flag": True,
                "explicit_execution_flag": "--confirm-phase45-execution",
                "execution_approved": False,
                "rollback_point_id": "rollback_previous_deployment_alias",
                "mutates_production": True,
                "database_migration": False,
                "raw_data_upload": False,
                "index_mutation": False,
                "release_promotion": True,
            },
        ],
        "observation_windows": [
            {
                "id": "first_hour_observation",
                "title": "First hour observation",
                "owner": "operator",
                "duration_minutes": 60,
                "metrics": ["api_health", "error_rate"],
                "expected_evidence": "logs/production-cutover/phase45-first-hour.json",
            }
        ],
        "evidence_handoff": [
            {
                "id": "release_note_handoff",
                "title": "Release note handoff",
                "source_path": "Docs/releases/v2_phase_44_production_cutover_dry_run.md",
                "owner": "operator",
                "timing": "before_execution",
            },
            {
                "id": "production_validation_handoff",
                "title": "Production validation handoff",
                "source_path": "logs/production-cutover/phase45-production-validation.json",
                "owner": "operator",
                "timing": "after_execution",
            },
        ],
    }


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase44_production_cutover_dry_run.json",
        "Docs/v2_phase_45_production_cutover_execution_plan_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_phase44_dry_run(
    root: Path,
    *,
    status: str = "production_cutover_dry_run_planned",
    execution_authorized: bool = False,
    note: str = "",
) -> None:
    write_json(
        root,
        "logs/readiness/phase44-production-cutover-dry-run.json",
        {
            "status": status,
            "production_execution_authorized": execution_authorized,
            "production_mutation_authorized": False,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
            "release_promotion_authorized": False,
            "phase45_execution_plan_authorized": True,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "note": note,
        },
    )


def write_approvals(root: Path) -> None:
    write_json(
        root,
        "logs/production-cutover/phase45-lawyer-owner-execution-plan-signoff.json",
        {
            "status": "accepted",
            "reviewed_phase44_dry_run": True,
            "reviewed_execution_commands": True,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "production_execution_authorized": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase45-operator-execution-plan-signoff.json",
        {
            "status": "accepted",
            "reviewed_phase44_dry_run": True,
            "rollback_points_confirmed": True,
            "production_execution_authorized": False,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase45-legal-review-signoff.json",
        {
            "status": "accepted",
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "production_execution_authorized": False,
        },
    )


def test_phase45_manifest_loads():
    payload = load_production_cutover_execution_plan_manifest(MANIFEST_PATH)
    command_ids = {item["id"] for item in payload["execution_commands"]}
    approval_ids = {item["id"] for item in payload["approval_gates"]}

    assert payload["target_release_tag"] == "v2-phase-44-production-cutover-dry-run"
    assert "phase45_prebuilt_production_deploy" in command_ids
    assert "legal_review_signoff" in approval_ids


def test_phase45_local_report_awaits_dry_run(tmp_path):
    write_prerequisites(tmp_path)

    report = build_production_cutover_execution_plan_report(execution_plan_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_production_cutover_dry_run"
    assert report["production_execution_authorized"] is False
    assert report["blockers"] == []


def test_phase45_awaits_approvals_after_dry_run(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)

    report = build_production_cutover_execution_plan_report(execution_plan_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_execution_approvals"
    assert {item["id"] for item in report["pending_approvals"]} == {
        "lawyer_owner_execution_plan_signoff",
        "operator_execution_plan_signoff",
        "legal_review_signoff",
    }


def test_phase45_execution_plan_ready_after_approvals(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)
    write_approvals(tmp_path)

    report = build_production_cutover_execution_plan_report(execution_plan_manifest(), project_root=tmp_path)

    assert report["status"] == "production_cutover_execution_plan_ready"
    assert report["summary"]["mutating_commands"] == 1
    assert report["summary"]["commands_with_rollback_points"] == 1
    assert report["phase46_monitoring_authorized"] is False


def test_phase45_blocks_execution_authorized_dry_run(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path, execution_authorized=True)

    report = build_production_cutover_execution_plan_report(execution_plan_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase44_production_cutover_dry_run" for item in report["blockers"])


def test_phase45_blocks_missing_explicit_flag_for_mutating_command(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)
    manifest = execution_plan_manifest()
    manifest["execution_commands"][1]["requires_explicit_execution_flag"] = False

    report = build_production_cutover_execution_plan_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "production_deploy" for item in report["blockers"])


def test_phase45_blocks_missing_rollback_point(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)
    manifest = execution_plan_manifest()
    manifest["execution_commands"][1]["rollback_point_id"] = "missing_rollback"

    report = build_production_cutover_execution_plan_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "production_deploy" for item in report["blockers"])


def test_phase45_blocks_incomplete_observation_window(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)
    manifest = execution_plan_manifest()
    manifest["observation_windows"][0]["metrics"] = []

    report = build_production_cutover_execution_plan_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "first_hour_observation" for item in report["blockers"])


def test_phase45_blocks_incomplete_evidence_handoff(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path)
    manifest = execution_plan_manifest()
    manifest["evidence_handoff"][0]["timing"] = "later"

    report = build_production_cutover_execution_plan_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "release_note_handoff" for item in report["blockers"])


def test_phase45_blocks_forbidden_dry_run_content(tmp_path):
    write_prerequisites(tmp_path)
    write_phase44_dry_run(tmp_path, note="postgres://hidden")

    report = build_production_cutover_execution_plan_report(execution_plan_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase44_production_cutover_dry_run" for item in report["blockers"])


def test_phase45_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase45-production-cutover-execution-plan.json"
    manifest.write_text(json.dumps(execution_plan_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_production_cutover_dry_run"
