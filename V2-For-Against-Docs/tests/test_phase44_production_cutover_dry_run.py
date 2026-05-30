from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_production_cutover_dry_run_report,
    load_production_cutover_dry_run_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase44_production_cutover_dry_run.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase44_production_cutover_dry_run.py"
    spec = importlib.util.spec_from_file_location("build_phase44_production_cutover_dry_run", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dry_run_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase44_production_cutover_dry_run.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "cutover_environment": "production",
        "forbidden_terms": ["postgres://", "final legal advice"],
        "prerequisites": [
            {
                "id": "phase43_manifest",
                "title": "Phase 43 manifest",
                "type": "file",
                "path": "rag/evals/phase43_production_cutover_readiness.json",
            },
            {
                "id": "phase44_contract",
                "title": "Phase 44 contract",
                "type": "document",
                "path": "Docs/v2_phase_44_production_cutover_dry_run_contract.md",
            },
        ],
        "readiness_reports": [
            {
                "id": "phase43_production_cutover_readiness",
                "title": "Phase 43 readiness",
                "group": "production_readiness",
                "type": "json_status",
                "path": "logs/readiness/phase43-production-cutover-readiness.json",
                "accepted_statuses": ["ready_for_production_cutover_dry_run"],
                "pending_statuses": ["awaiting_staging_acceptance"],
                "required_fields": {
                    "production_execution_authorized": False,
                    "production_mutation_authorized": False,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                    "cutover_dry_run_authorized": True,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            }
        ],
        "dry_run_steps": [
            {
                "id": "preflight_tests",
                "title": "Preflight tests",
                "stage": "preflight",
                "owner": "operator",
                "execution_mode": "read_only_dry_run",
                "command": ["scripts/run_detached_quality_gate.sh", "tests", "phase44-tests"],
                "expected_evidence": "logs/test-runs/phase44-tests.log",
                "planned_only": False,
                "execution_approved": False,
                "mutates_production": False,
                "database_migration": False,
                "raw_data_upload": False,
                "index_mutation": False,
                "release_promotion": False,
            },
            {
                "id": "production_deploy_plan",
                "title": "Production deploy plan",
                "stage": "deployment",
                "owner": "operator",
                "execution_mode": "planned_only",
                "command": ["vercel", "deploy", "--prebuilt", "--prod"],
                "expected_evidence": "logs/production-cutover/phase44-deploy-plan.json",
                "planned_only": True,
                "execution_approved": False,
                "mutates_production": True,
                "database_migration": False,
                "raw_data_upload": False,
                "index_mutation": False,
                "release_promotion": True,
            },
        ],
        "owner_approvals": [
            {
                "id": "owner_acceptance",
                "title": "Owner acceptance",
                "owner": "lawyer_owner",
                "expected_evidence": "logs/production-cutover/phase44-owner-acceptance.json",
            }
        ],
        "rollback_steps": [
            {
                "id": "rollback_alias",
                "title": "Rollback alias",
                "owner": "operator",
                "action": "Restore previous production deployment alias.",
                "expected_evidence": "logs/production-cutover/phase44-rollback-alias.json",
                "planned_only": True,
                "execution_approved": False,
            }
        ],
    }


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase43_production_cutover_readiness.json",
        "Docs/v2_phase_44_production_cutover_dry_run_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_phase43_readiness(
    root: Path,
    *,
    status: str = "ready_for_production_cutover_dry_run",
    execution_authorized: bool = False,
    note: str = "",
) -> None:
    write_json(
        root,
        "logs/readiness/phase43-production-cutover-readiness.json",
        {
            "status": status,
            "production_execution_authorized": execution_authorized,
            "production_mutation_authorized": False,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
            "cutover_dry_run_authorized": True,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "note": note,
        },
    )


def test_phase44_manifest_loads():
    payload = load_production_cutover_dry_run_manifest(MANIFEST_PATH)
    step_ids = {item["id"] for item in payload["dry_run_steps"]}
    rollback_ids = {item["id"] for item in payload["rollback_steps"]}

    assert payload["target_release_tag"] == "v2-phase-43-production-cutover-readiness"
    assert "phase44_prebuilt_production_deploy" in step_ids
    assert "phase44_rollback_alias_plan" in rollback_ids


def test_phase44_local_report_awaits_production_readiness(tmp_path):
    write_prerequisites(tmp_path)

    report = build_production_cutover_dry_run_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_production_cutover_readiness"
    assert report["production_execution_authorized"] is False
    assert report["blockers"] == []


def test_phase44_plans_dry_run_after_phase43_ready(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path)

    report = build_production_cutover_dry_run_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "production_cutover_dry_run_planned"
    assert report["phase45_execution_plan_authorized"] is True
    assert report["summary"]["planned_only_steps"] == 1
    assert report["summary"]["read_only_dry_run_steps"] == 1


def test_phase44_blocks_production_execution_approval(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path, execution_authorized=True)

    report = build_production_cutover_dry_run_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase43_production_cutover_readiness" for item in report["blockers"])


def test_phase44_blocks_mutating_step_that_is_not_planned_only(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path)
    manifest = dry_run_manifest()
    manifest["dry_run_steps"][1]["planned_only"] = False

    report = build_production_cutover_dry_run_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "production_deploy_plan" for item in report["blockers"])


def test_phase44_blocks_step_execution_approval(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path)
    manifest = dry_run_manifest()
    manifest["dry_run_steps"][1]["execution_approved"] = True

    report = build_production_cutover_dry_run_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "production_deploy_plan" for item in report["blockers"])


def test_phase44_blocks_incomplete_rollback_step(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path)
    manifest = dry_run_manifest()
    manifest["rollback_steps"][0]["owner"] = ""

    report = build_production_cutover_dry_run_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "rollback_alias" for item in report["blockers"])


def test_phase44_blocks_forbidden_readiness_content(tmp_path):
    write_prerequisites(tmp_path)
    write_phase43_readiness(tmp_path, note="postgres://hidden")

    report = build_production_cutover_dry_run_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase43_production_cutover_readiness" for item in report["blockers"])


def test_phase44_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase44-production-cutover-dry-run.json"
    manifest.write_text(json.dumps(dry_run_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_production_cutover_readiness"
