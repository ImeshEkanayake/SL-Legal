from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_production_cutover_readiness_report,
    load_production_cutover_readiness_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase43_production_cutover_readiness.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase43_production_cutover_readiness.py"
    spec = importlib.util.spec_from_file_location("build_phase43_production_cutover_readiness", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def readiness_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase43_production_cutover_readiness.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "production_planning",
        "forbidden_terms": ["postgres://", "final legal advice"],
        "prerequisites": [
            {
                "id": "phase42_manifest",
                "title": "Phase 42 manifest",
                "type": "file",
                "path": "rag/evals/phase42_staging_acceptance_decision.json",
            },
            {
                "id": "phase43_contract",
                "title": "Phase 43 contract",
                "type": "document",
                "path": "Docs/v2_phase_43_production_cutover_readiness_contract.md",
            },
        ],
        "readiness_evidence": [
            {
                "id": "phase42_staging_acceptance",
                "title": "Phase 42 acceptance",
                "group": "staging_acceptance",
                "type": "json_status",
                "path": "logs/readiness/phase42-staging-acceptance-decision.json",
                "accepted_statuses": ["staging_accepted_for_production_planning"],
                "pending_statuses": ["awaiting_staging_execution_evidence"],
                "required_fields": {
                    "production_execution_authorized": False,
                    "lawyer_review_required": True,
                    "no_final_legal_advice": True,
                },
            },
            {
                "id": "release_provenance",
                "title": "Release provenance",
                "group": "release_governance",
                "type": "json_status",
                "path": "logs/release-artifacts/phase43-release-provenance-ledger.json",
                "accepted_statuses": ["verified"],
                "required_fields": {"target_release_tag": "v1"},
            },
            {
                "id": "signing_plan",
                "title": "Signing plan",
                "group": "release_governance",
                "type": "json_status",
                "path": "logs/release-artifacts/phase43-signing-plan.json",
                "accepted_statuses": ["planned"],
                "required_fields": {
                    "target_release_tag": "v1",
                    "signing_execution_approved": False,
                },
            },
            {
                "id": "schema_readiness",
                "title": "Schema readiness",
                "group": "production_preflight",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-schema-readiness.json",
                "accepted_statuses": ["ready"],
                "required_fields": {
                    "db_migration_applied": False,
                    "production_mutation_executed": False,
                },
            },
            {
                "id": "rag_index_health",
                "title": "RAG index health",
                "group": "production_preflight",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-rag-index-health.json",
                "accepted_statuses": ["healthy"],
                "required_fields": {
                    "documents_searchable": True,
                    "index_write_executed": False,
                    "production_mutation_executed": False,
                },
            },
            {
                "id": "signed_load_suite",
                "title": "Signed load suite",
                "group": "production_preflight",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-signed-load-suite.json",
                "accepted_statuses": ["passed"],
                "required_fields": {
                    "signed_requests": True,
                    "p95_within_target": True,
                    "error_rate_within_target": True,
                    "production_mutation_executed": False,
                },
            },
            {
                "id": "corpus_searchability",
                "title": "Corpus searchability",
                "group": "production_preflight",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-corpus-searchability.json",
                "accepted_statuses": ["passed"],
                "required_fields": {
                    "sample_queries_passed": True,
                    "raw_data_uploaded": False,
                    "production_mutation_executed": False,
                },
            },
        ],
        "rollback_evidence": [
            {
                "id": "rollback_schema_smoke",
                "title": "Rollback schema smoke",
                "group": "rollback_readiness",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-rollback-schema-smoke.json",
                "accepted_statuses": ["passed"],
                "required_fields": {
                    "rollback_only": True,
                    "migration_applied": False,
                    "production_mutation_executed": False,
                },
            },
            {
                "id": "rollback_checklist",
                "title": "Rollback checklist",
                "group": "rollback_readiness",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-rollback-checklist.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "rollback_owner_assigned": True,
                    "tested_rollback_only": True,
                    "production_execution_authorized": False,
                    "production_mutation_executed": False,
                },
            },
            {
                "id": "incident_response_checklist",
                "title": "Incident response checklist",
                "group": "incident_readiness",
                "type": "json_status",
                "path": "logs/production-cutover/phase43-incident-response-checklist.json",
                "accepted_statuses": ["accepted"],
                "required_fields": {
                    "incident_owner_assigned": True,
                    "monitoring_window_defined": True,
                    "lawyer_review_required": True,
                    "production_execution_authorized": False,
                },
            },
        ],
        "required_environment": [
            {
                "name": "SL_LEGAL_PUBLIC_APP_URL",
                "category": "routing",
                "required": True,
                "secret": False,
                "url": True,
            },
            {
                "name": "SL_LEGAL_PRODUCTION_MODE",
                "category": "safety",
                "required": True,
                "secret": False,
                "expected_value": "true",
            },
            {
                "name": "SL_LEGAL_AUTH_SECRET",
                "category": "security",
                "required": True,
                "secret": True,
                "min_length": 32,
            },
        ],
    }


def write_json(root: Path, path_value: str, payload: dict[str, object]) -> None:
    path = root / path_value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase42_staging_acceptance_decision.json",
        "Docs/v2_phase_43_production_cutover_readiness_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_phase42_acceptance(root: Path, status: str = "staging_accepted_for_production_planning") -> None:
    write_json(
        root,
        "logs/readiness/phase42-staging-acceptance-decision.json",
        {
            "status": status,
            "production_execution_authorized": False,
            "lawyer_review_required": True,
            "no_final_legal_advice": True,
        },
    )


def write_readiness_evidence(
    root: Path,
    *,
    signing_approved: bool = False,
    mutation_executed: bool = False,
    corpus_note: str = "",
) -> None:
    write_phase42_acceptance(root)
    write_json(root, "logs/release-artifacts/phase43-release-provenance-ledger.json", {"status": "verified", "target_release_tag": "v1"})
    write_json(
        root,
        "logs/release-artifacts/phase43-signing-plan.json",
        {
            "status": "planned",
            "target_release_tag": "v1",
            "signing_execution_approved": signing_approved,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-schema-readiness.json",
        {
            "status": "ready",
            "db_migration_applied": False,
            "production_mutation_executed": mutation_executed,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-rag-index-health.json",
        {
            "status": "healthy",
            "documents_searchable": True,
            "index_write_executed": False,
            "production_mutation_executed": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-signed-load-suite.json",
        {
            "status": "passed",
            "signed_requests": True,
            "p95_within_target": True,
            "error_rate_within_target": True,
            "production_mutation_executed": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-corpus-searchability.json",
        {
            "status": "passed",
            "sample_queries_passed": True,
            "raw_data_uploaded": False,
            "production_mutation_executed": False,
            "note": corpus_note,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-rollback-schema-smoke.json",
        {
            "status": "passed",
            "rollback_only": True,
            "migration_applied": False,
            "production_mutation_executed": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-rollback-checklist.json",
        {
            "status": "accepted",
            "rollback_owner_assigned": True,
            "tested_rollback_only": True,
            "production_execution_authorized": False,
            "production_mutation_executed": False,
        },
    )
    write_json(
        root,
        "logs/production-cutover/phase43-incident-response-checklist.json",
        {
            "status": "accepted",
            "incident_owner_assigned": True,
            "monitoring_window_defined": True,
            "lawyer_review_required": True,
            "production_execution_authorized": False,
        },
    )


def production_environment() -> dict[str, str]:
    return {
        "SL_LEGAL_PUBLIC_APP_URL": "https://sl-legal.example",
        "SL_LEGAL_PRODUCTION_MODE": "true",
        "SL_LEGAL_AUTH_SECRET": "x" * 32,
    }


def test_phase43_manifest_loads():
    payload = load_production_cutover_readiness_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["readiness_evidence"]}
    rollback_ids = {item["id"] for item in payload["rollback_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-42-staging-acceptance-decision"
    assert "phase42_staging_acceptance" in evidence_ids
    assert {"rollback_schema_smoke", "incident_response_checklist"} <= rollback_ids


def test_phase43_local_report_awaits_staging_acceptance(tmp_path):
    write_prerequisites(tmp_path)

    report = build_production_cutover_readiness_report(readiness_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_staging_acceptance"
    assert report["production_execution_authorized"] is False
    assert report["blockers"] == []


def test_phase43_awaits_production_readiness_evidence_after_phase42_acceptance(tmp_path):
    write_prerequisites(tmp_path)
    write_phase42_acceptance(tmp_path)

    report = build_production_cutover_readiness_report(readiness_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_production_readiness_evidence"
    assert report["summary"]["phase42_status"] == "staging_accepted_for_production_planning"


def test_phase43_awaits_environment_inventory_after_evidence_validates(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path)

    report = build_production_cutover_readiness_report(readiness_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_production_environment_inventory"
    assert report["summary"]["pending_readiness_evidence"] == 0
    assert report["production_environment"]["included"] is False


def test_phase43_ready_for_production_cutover_dry_run(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path)

    report = build_production_cutover_readiness_report(
        readiness_manifest(),
        project_root=tmp_path,
        environment=production_environment(),
        include_environment=True,
    )

    assert report["status"] == "ready_for_production_cutover_dry_run"
    assert report["cutover_dry_run_authorized"] is True
    assert report["production_mutation_authorized"] is False


def test_phase43_blocks_production_mutation_evidence(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path, mutation_executed=True)

    report = build_production_cutover_readiness_report(
        readiness_manifest(),
        project_root=tmp_path,
        environment=production_environment(),
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "schema_readiness" for item in report["blockers"])


def test_phase43_blocks_signing_execution_approval(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path, signing_approved=True)

    report = build_production_cutover_readiness_report(
        readiness_manifest(),
        project_root=tmp_path,
        environment=production_environment(),
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "signing_plan" for item in report["blockers"])


def test_phase43_blocks_forbidden_readiness_content(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path, corpus_note="postgres://hidden")

    report = build_production_cutover_readiness_report(
        readiness_manifest(),
        project_root=tmp_path,
        environment=production_environment(),
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "corpus_searchability" for item in report["blockers"])


def test_phase43_blocks_invalid_environment_inventory(tmp_path):
    write_prerequisites(tmp_path)
    write_readiness_evidence(tmp_path)

    report = build_production_cutover_readiness_report(
        readiness_manifest(),
        project_root=tmp_path,
        environment={"SL_LEGAL_PUBLIC_APP_URL": "https://sl-legal.example", "SL_LEGAL_PRODUCTION_MODE": "true"},
        include_environment=True,
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "env:SL_LEGAL_AUTH_SECRET" for item in report["blockers"])


def test_phase43_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase43-production-cutover-readiness.json"
    manifest.write_text(json.dumps(readiness_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_staging_acceptance"
