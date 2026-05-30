from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_post_cutover_monitoring_handover_report,
    load_post_cutover_monitoring_handover_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase46_post_cutover_monitoring_handover.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase46_post_cutover_monitoring_handover.py"
    spec = importlib.util.spec_from_file_location("build_phase46_post_cutover_monitoring_handover", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def monitoring_handover_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase46_post_cutover_monitoring_handover.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "cutover_environment": "production",
        "forbidden_terms": ["postgres://", "final legal advice"],
        "prerequisites": [
            {
                "id": "phase45_manifest",
                "title": "Phase 45 manifest",
                "type": "file",
                "path": "rag/evals/phase45_production_cutover_execution_plan.json",
            },
            {
                "id": "phase46_contract",
                "title": "Phase 46 contract",
                "type": "document",
                "path": "Docs/v2_phase_46_post_cutover_monitoring_handover_contract.md",
            },
            {
                "id": "phase46_handover",
                "title": "Phase 46 handover",
                "type": "document",
                "path": "Docs/v2_phase_46_operational_handover.md",
            },
        ],
        "cutover_plan_evidence": [
            {
                "id": "phase45_production_cutover_execution_plan",
                "title": "Phase 45 execution plan",
                "group": "cutover_plan",
                "type": "json_status",
                "path": "logs/readiness/phase45-production-cutover-execution-plan.json",
                "accepted_statuses": ["production_cutover_execution_plan_ready"],
                "pending_statuses": ["awaiting_production_cutover_dry_run", "awaiting_execution_approvals"],
                "required_fields": {
                    "production_execution_authorized": False,
                    "production_mutation_authorized": False,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                    "release_promotion_authorized": False,
                    "phase46_monitoring_authorized": False,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            }
        ],
        "cutover_execution_evidence": [
            {
                "id": "phase46_cutover_execution_record",
                "title": "Cutover execution record",
                "group": "cutover_execution",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-cutover-execution-record.json",
                "accepted_statuses": ["production_cutover_executed"],
                "pending_statuses": ["awaiting_execution"],
                "required_fields": {
                    "reviewed_phase45_execution_plan": True,
                    "executed_under_phase45_approval": True,
                    "rollback_available": True,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            },
            {
                "id": "phase46_signed_smoke_record",
                "title": "Signed smoke record",
                "group": "cutover_execution",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-signed-smoke-record.json",
                "accepted_statuses": ["signed_smoke_passed"],
                "pending_statuses": ["awaiting_execution"],
                "required_fields": {
                    "signed_health_passed": True,
                    "workspace_smoke_passed": True,
                    "source_viewer_smoke_passed": True,
                    "review_queue_smoke_passed": True,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                },
            },
        ],
        "monitoring_evidence": [
            {
                "id": "api_health_monitoring",
                "title": "API health monitoring",
                "group": "monitoring",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-api-health-monitoring.json",
                "accepted_statuses": ["healthy"],
                "pending_statuses": ["collecting"],
                "required_fields": {
                    "window_completed": True,
                    "alerts_reviewed": True,
                    "p95_within_target": True,
                },
            },
            {
                "id": "retrieval_latency_monitoring",
                "title": "Retrieval latency monitoring",
                "group": "monitoring",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-retrieval-latency-monitoring.json",
                "accepted_statuses": ["within_target"],
                "pending_statuses": ["collecting"],
                "required_fields": {
                    "window_completed": True,
                    "p95_within_target": True,
                    "error_rate_within_target": True,
                },
            },
        ],
        "rollback_incident_evidence": [
            {
                "id": "rollback_readiness_review",
                "title": "Rollback readiness review",
                "group": "rollback_incident",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-rollback-readiness-review.json",
                "accepted_statuses": ["reviewed"],
                "pending_statuses": ["awaiting_review"],
                "required_fields": {
                    "rollback_points_reviewed": True,
                    "rollback_evidence_attached": True,
                    "operator_owner_confirmed": True,
                    "database_migration_authorized": False,
                    "raw_data_upload_authorized": False,
                },
            }
        ],
        "data_update_evidence": [
            {
                "id": "data_update_separation_review",
                "title": "Data update separation review",
                "group": "data_update",
                "type": "json_status",
                "path": "logs/production-cutover/phase46-data-update-separation-review.json",
                "accepted_statuses": ["accepted"],
                "pending_statuses": ["awaiting_review"],
                "required_fields": {
                    "data_updates_separate_from_git": True,
                    "raw_data_upload_authorized": False,
                    "database_migration_authorized": False,
                    "corpus_growth_requires_separate_plan": True,
                },
            }
        ],
        "dashboard_checks": [
            {
                "id": "api_health_dashboard_check",
                "title": "API health dashboard",
                "metric_name": "api_health.p95_ms",
                "target": "p95 below target",
                "owner": "operator",
                "severity": "critical",
                "evidence_id": "api_health_monitoring",
            },
            {
                "id": "retrieval_latency_dashboard_check",
                "title": "Retrieval latency dashboard",
                "metric_name": "retrieval.p95_ms",
                "target": "p95 below target",
                "owner": "operator",
                "severity": "high",
                "evidence_id": "retrieval_latency_monitoring",
            },
        ],
        "incident_response_templates": [
            {
                "id": "api_health_incident_template",
                "title": "API health incident",
                "owner": "operator",
                "severity": "critical",
                "trigger": "Health fails.",
                "rollback_decision": "Use deployment alias rollback.",
                "evidence_path": "logs/production-cutover/phase46-api-health-incident.json",
            }
        ],
        "handover_documents": [
            {
                "id": "support_handover",
                "title": "Support handover",
                "owner": "operator",
                "audience": "support",
                "path": "Docs/v2_phase_46_operational_handover.md",
                "section": "Support Handover",
                "required": True,
            }
        ],
    }


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase45_production_cutover_execution_plan.json",
        "Docs/v2_phase_46_post_cutover_monitoring_handover_contract.md",
        "Docs/v2_phase_46_operational_handover.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_phase45_plan(
    root: Path,
    *,
    status: str = "production_cutover_execution_plan_ready",
    production_execution_authorized: bool = False,
    note: str = "",
) -> None:
    write_json(
        root,
        "logs/readiness/phase45-production-cutover-execution-plan.json",
        {
            "status": status,
            "production_execution_authorized": production_execution_authorized,
            "production_mutation_authorized": False,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
            "release_promotion_authorized": False,
            "phase46_monitoring_authorized": False,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
            "note": note,
        },
    )


def write_cutover_execution(root: Path) -> None:
    write_json(
        root,
        "logs/production-cutover/phase46-cutover-execution-record.json",
        {
            "status": "production_cutover_executed",
            "reviewed_phase45_execution_plan": True,
            "executed_under_phase45_approval": True,
            "rollback_available": True,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase46-signed-smoke-record.json",
        {
            "status": "signed_smoke_passed",
            "signed_health_passed": True,
            "workspace_smoke_passed": True,
            "source_viewer_smoke_passed": True,
            "review_queue_smoke_passed": True,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
        },
    )


def write_monitoring(root: Path, *, note: str = "") -> None:
    write_json(
        root,
        "logs/production-cutover/phase46-api-health-monitoring.json",
        {
            "status": "healthy",
            "window_completed": True,
            "alerts_reviewed": True,
            "p95_within_target": True,
            "note": note,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase46-retrieval-latency-monitoring.json",
        {
            "status": "within_target",
            "window_completed": True,
            "p95_within_target": True,
            "error_rate_within_target": True,
        },
    )


def write_handover_evidence(root: Path, *, raw_data_upload_authorized: bool = False) -> None:
    write_json(
        root,
        "logs/production-cutover/phase46-rollback-readiness-review.json",
        {
            "status": "reviewed",
            "rollback_points_reviewed": True,
            "rollback_evidence_attached": True,
            "operator_owner_confirmed": True,
            "database_migration_authorized": False,
            "raw_data_upload_authorized": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase46-data-update-separation-review.json",
        {
            "status": "accepted",
            "data_updates_separate_from_git": True,
            "raw_data_upload_authorized": raw_data_upload_authorized,
            "database_migration_authorized": False,
            "corpus_growth_requires_separate_plan": True,
        },
    )


def test_phase46_manifest_loads():
    payload = load_post_cutover_monitoring_handover_manifest(MANIFEST_PATH)
    dashboard_ids = {item["id"] for item in payload["dashboard_checks"]}

    assert payload["target_release_tag"] == "v2-phase-45-production-cutover-execution-plan"
    assert "api_health_dashboard_check" in dashboard_ids


def test_phase46_local_report_awaits_execution_plan(tmp_path):
    write_prerequisites(tmp_path)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_production_cutover_execution_plan"
    assert report["production_execution_authorized"] is False
    assert report["production_operational_complete"] is False
    assert report["blockers"] == []


def test_phase46_awaits_cutover_execution_after_phase45_ready(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_cutover_execution_evidence"
    assert {item["id"] for item in report["pending_cutover_execution"]} == {
        "phase46_cutover_execution_record",
        "phase46_signed_smoke_record",
    }


def test_phase46_awaits_monitoring_after_cutover_execution(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)
    write_cutover_execution(tmp_path)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_monitoring_evidence"
    assert {item["id"] for item in report["pending_monitoring_evidence"]} == {
        "api_health_monitoring",
        "retrieval_latency_monitoring",
    }


def test_phase46_awaits_operational_handover_after_monitoring(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)
    write_cutover_execution(tmp_path)
    write_monitoring(tmp_path)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_operational_handover"
    assert {item["id"] for item in report["pending_handover_evidence"]} == {
        "rollback_readiness_review",
        "data_update_separation_review",
    }


def test_phase46_ready_after_all_evidence(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)
    write_cutover_execution(tmp_path)
    write_monitoring(tmp_path)
    write_handover_evidence(tmp_path)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "post_cutover_operational_handover_ready"
    assert report["production_operational_complete"] is True
    assert report["summary"]["verified_monitoring_evidence"] == 2


def test_phase46_blocks_execution_authorized_phase45_plan(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path, production_execution_authorized=True)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase45_production_cutover_execution_plan" for item in report["blockers"])


def test_phase46_blocks_forbidden_monitoring_content(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)
    write_cutover_execution(tmp_path)
    write_monitoring(tmp_path, note="postgres://hidden")

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "api_health_monitoring" for item in report["blockers"])


def test_phase46_blocks_dashboard_check_with_unknown_evidence(tmp_path):
    write_prerequisites(tmp_path)
    manifest = monitoring_handover_manifest()
    manifest["dashboard_checks"][0]["evidence_id"] = "missing_monitoring"

    report = build_post_cutover_monitoring_handover_report(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "api_health_dashboard_check" for item in report["blockers"])


def test_phase46_blocks_data_update_boundary_violation(tmp_path):
    write_prerequisites(tmp_path)
    write_phase45_plan(tmp_path)
    write_cutover_execution(tmp_path)
    write_monitoring(tmp_path)
    write_handover_evidence(tmp_path, raw_data_upload_authorized=True)

    report = build_post_cutover_monitoring_handover_report(monitoring_handover_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "data_update_separation_review" for item in report["blockers"])


def test_phase46_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase46-post-cutover-monitoring-handover.json"
    manifest.write_text(json.dumps(monitoring_handover_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_production_cutover_execution_plan"
