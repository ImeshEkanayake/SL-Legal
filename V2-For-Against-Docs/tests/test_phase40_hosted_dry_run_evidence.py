from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_dry_run_evidence_report,
    load_hosted_dry_run_evidence_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase40_hosted_dry_run_evidence.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase40_hosted_dry_run_evidence.py"
    spec = importlib.util.spec_from_file_location("build_phase40_hosted_dry_run_evidence", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dry_run_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase40_hosted_dry_run_evidence.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "forbidden_terms": ["X-SL-Legal-Auth-Signature", "postgres://", "raw response body"],
        "prerequisites": [
            {
                "id": "phase39_manifest",
                "title": "Phase 39 manifest",
                "type": "file",
                "path": "rag/evals/phase39_hosted_environment_config.json",
            },
            {
                "id": "phase40_contract",
                "title": "Phase 40 contract",
                "type": "document",
                "path": "Docs/v2_phase_40_hosted_dry_run_evidence_contract.md",
            },
        ],
        "dry_run_evidence": [
            {
                "id": "phase39_config_pack",
                "title": "Phase 39 config pack",
                "type": "json_status",
                "path": "logs/readiness/phase39-hosted-environment-config-pack.json",
                "accepted_statuses": ["ready_for_hosted_capture_dry_run"],
                "pending_statuses": ["awaiting_hosted_environment_configuration"],
                "required_fields": {
                    "environment.included": True,
                    "summary.blockers": 0,
                    "summary.execution_recipes": 1,
                },
            },
            {
                "id": "phase38_hosted_dry_run",
                "title": "Phase 38 dry-run",
                "type": "json_status",
                "path": "logs/readiness/phase38-hosted-capture-execution.json",
                "accepted_statuses": ["ready_for_hosted_capture_execution"],
                "pending_statuses": ["awaiting_hosted_capture_configuration"],
                "required_fields": {
                    "execute": False,
                    "environment_included": True,
                    "summary.phase35_status": "ready_for_capture_execution",
                    "summary.phase36_status": "ready_for_hosted_capture_execution",
                    "summary.captured_evidence": 0,
                    "summary.blockers": 0,
                },
            },
        ],
    }


def write_prerequisites(root: Path) -> None:
    for path_value in [
        "rag/evals/phase39_hosted_environment_config.json",
        "Docs/v2_phase_40_hosted_dry_run_evidence_contract.md",
    ]:
        path = root / path_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("phase evidence\n", encoding="utf-8")


def write_phase39_report(root: Path, *, status: str = "ready_for_hosted_capture_dry_run") -> None:
    path = root / "logs" / "readiness" / "phase39-hosted-environment-config-pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": status,
                "environment": {"included": status == "ready_for_hosted_capture_dry_run"},
                "summary": {"blockers": 0, "execution_recipes": 1},
            }
        ),
        encoding="utf-8",
    )


def write_phase38_report(
    root: Path,
    *,
    status: str = "ready_for_hosted_capture_execution",
    execute: bool = False,
    captured_evidence: int = 0,
    extra: str = "",
) -> None:
    path = root / "logs" / "readiness" / "phase38-hosted-capture-execution.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "execute": execute,
        "environment_included": True,
        "summary": {
            "phase35_status": "ready_for_capture_execution",
            "phase36_status": "ready_for_hosted_capture_execution",
            "captured_evidence": captured_evidence,
            "blockers": 0,
        },
        "note": extra,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_phase40_manifest_loads():
    payload = load_hosted_dry_run_evidence_manifest(MANIFEST_PATH)
    evidence_ids = {item["id"] for item in payload["dry_run_evidence"]}

    assert payload["target_release_tag"] == "v2-phase-39-hosted-environment-config"
    assert "phase39_config_pack" in evidence_ids
    assert "phase38_hosted_dry_run" in evidence_ids


def test_phase40_local_report_awaits_configuration(tmp_path):
    write_prerequisites(tmp_path)

    report = build_hosted_dry_run_evidence_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_environment_configuration"
    assert report["summary"]["pending_dry_run_evidence"] == 2
    assert report["blockers"] == []


def test_phase40_awaits_dry_run_after_phase39_ready(tmp_path):
    write_prerequisites(tmp_path)
    write_phase39_report(tmp_path)

    report = build_hosted_dry_run_evidence_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "awaiting_hosted_dry_run_evidence"
    assert report["summary"]["verified_dry_run_evidence"] == 1


def test_phase40_validates_hosted_dry_run(tmp_path):
    write_prerequisites(tmp_path)
    write_phase39_report(tmp_path)
    write_phase38_report(tmp_path)

    report = build_hosted_dry_run_evidence_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "hosted_dry_run_validated"
    assert report["summary"]["verified_dry_run_evidence"] == 2


def test_phase40_blocks_if_phase38_executed_capture(tmp_path):
    write_prerequisites(tmp_path)
    write_phase39_report(tmp_path)
    write_phase38_report(tmp_path, execute=True, captured_evidence=7)

    report = build_hosted_dry_run_evidence_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase38_hosted_dry_run" for item in report["blockers"])


def test_phase40_blocks_forbidden_dry_run_content(tmp_path):
    write_prerequisites(tmp_path)
    write_phase39_report(tmp_path)
    write_phase38_report(tmp_path, extra="X-SL-Legal-Auth-Signature: value")

    report = build_hosted_dry_run_evidence_report(dry_run_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "phase38_hosted_dry_run" for item in report["blockers"])


def test_phase40_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_prerequisites(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "logs" / "readiness" / "phase40-hosted-dry-run-evidence.json"
    manifest.write_text(json.dumps(dry_run_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "awaiting_hosted_environment_configuration"
