from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_ui_deployment_readiness_report,
    load_ui_deployment_readiness_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase30_ui_deployment_readiness.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase30_ui_deployment_readiness.py"
    spec = importlib.util.spec_from_file_location("build_phase30_ui_deployment_readiness", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase30_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase30_ui_deployment_readiness.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "required_environment": [
            {
                "name": "SL_LEGAL_API_BASE_URL",
                "category": "api",
                "required": True,
                "url": True,
            },
            {
                "name": "SL_LEGAL_AUTH_HMAC_SECRET",
                "category": "api_auth",
                "required": True,
                "secret": True,
                "min_length": 32,
            },
            {
                "name": "SL_LEGAL_UI_SESSION_SECRET",
                "category": "session",
                "required": True,
                "secret": True,
                "min_length": 32,
            },
            {
                "name": "SL_LEGAL_UI_SESSION_COOKIE_NAME",
                "category": "session",
                "required": False,
            },
        ],
        "dev_only_environment": ["SL_LEGAL_UI_USER_ID"],
        "evidence": [
            {
                "id": "browser_workflow",
                "title": "Browser workflow",
                "type": "detached_log",
                "path": "logs/test-runs/phase29-browser-workflow-validation.log",
            },
            {
                "id": "browser_contract",
                "title": "Browser contract",
                "type": "document",
                "path": "Docs/v2_phase_29_browser_workflow_validation_contract.md",
            },
            {
                "id": "browser_release",
                "title": "Browser release",
                "type": "document",
                "path": "Docs/releases/v2_phase_29_browser_workflow_validation.md",
            },
            {
                "id": "npm_script",
                "title": "NPM script",
                "type": "package_script",
                "path": "web/package.json",
                "script_name": "phase29:e2e",
                "expected_contains": "run-phase29-browser-workflow.mjs",
            },
            {
                "id": "detached_mode",
                "title": "Detached mode",
                "type": "detached_mode",
                "path": "scripts/run_detached_quality_gate.sh",
                "mode_name": "phase29-browser-workflow",
                "expected_contains": "npm --prefix web run phase29:e2e",
            },
            {
                "id": "env_example",
                "title": "Environment example",
                "type": "file",
                "path": ".env.example",
            },
        ],
    }


def write_phase30_evidence(root: Path) -> None:
    (root / "logs" / "test-runs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "test-runs" / "phase29-browser-workflow-validation.log").write_text(
        "run_id=phase29-browser-workflow-validation\nexit_status=0\n",
        encoding="utf-8",
    )
    (root / "Docs" / "releases").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_29_browser_workflow_validation_contract.md").write_text("contract\n", encoding="utf-8")
    (root / "Docs" / "releases" / "v2_phase_29_browser_workflow_validation.md").write_text(
        "release\n",
        encoding="utf-8",
    )
    (root / "web").mkdir(parents=True, exist_ok=True)
    (root / "web" / "package.json").write_text(
        json.dumps({"scripts": {"phase29:e2e": "node scripts/run-phase29-browser-workflow.mjs"}}),
        encoding="utf-8",
    )
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "run_detached_quality_gate.sh").write_text(
        "phase29-browser-workflow)\n"
        "COMMAND=\"npm --prefix web ci; npm --prefix web run phase29:e2e -- --output-dir logs/phase29-browser-workflow\"\n",
        encoding="utf-8",
    )
    (root / ".env.example").write_text("SL_LEGAL_API_BASE_URL=http://127.0.0.1:8000\n", encoding="utf-8")


def test_phase30_manifest_loads_and_covers_ui_environment():
    payload = load_ui_deployment_readiness_manifest(MANIFEST_PATH)
    env_names = {item["name"] for item in payload["required_environment"]}
    evidence_ids = {item["id"] for item in payload["evidence"]}

    assert payload["target_release_tag"] == "v2-phase-29-browser-workflow-validation"
    assert "SL_LEGAL_API_BASE_URL" in env_names
    assert "SL_LEGAL_AUTH_HMAC_SECRET" in env_names
    assert "SL_LEGAL_UI_SESSION_SECRET" in env_names
    assert "SL_LEGAL_UI_USER_ID" in payload["dev_only_environment"]
    assert "phase29_browser_workflow" in evidence_ids
    assert "phase29_npm_script" in evidence_ids
    assert "phase29_detached_mode" in evidence_ids


def test_phase30_report_ready_for_hosted_env_review_without_secret_values(tmp_path):
    write_phase30_evidence(tmp_path)

    report = build_ui_deployment_readiness_report(
        phase30_manifest(),
        project_root=tmp_path,
        include_environment=False,
    )

    assert report["status"] == "ready_for_hosted_env_review"
    assert report["summary"]["verified_evidence"] == 6
    assert report["environment"]["included"] is False
    assert all(item["status"] == "not_evaluated" for item in report["environment"]["checks"])
    assert report["blockers"] == []


def test_phase30_report_blocks_missing_required_evidence(tmp_path):
    write_phase30_evidence(tmp_path)
    (tmp_path / "logs" / "test-runs" / "phase29-browser-workflow-validation.log").unlink()

    report = build_ui_deployment_readiness_report(
        phase30_manifest(),
        project_root=tmp_path,
        include_environment=False,
    )

    assert report["status"] == "blocked"
    assert report["summary"]["missing_evidence"] == 1
    assert any(item["id"] == "browser_workflow" for item in report["blockers"])


def test_phase30_report_blocks_missing_hosted_environment_when_included(tmp_path):
    write_phase30_evidence(tmp_path)

    report = build_ui_deployment_readiness_report(
        phase30_manifest(),
        project_root=tmp_path,
        environment={"SL_LEGAL_API_BASE_URL": "https://api.example.invalid"},
        include_environment=True,
        deployment_environment="staging",
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "env:SL_LEGAL_AUTH_HMAC_SECRET" for item in report["blockers"])
    assert any(item["id"] == "env:SL_LEGAL_UI_SESSION_SECRET" for item in report["blockers"])


def test_phase30_report_ready_for_deployment_review_with_hosted_environment(tmp_path):
    write_phase30_evidence(tmp_path)
    environment = {
        "SL_LEGAL_API_BASE_URL": "https://api.example.invalid",
        "SL_LEGAL_AUTH_HMAC_SECRET": "a" * 32,
        "SL_LEGAL_UI_SESSION_SECRET": "b" * 32,
    }

    report = build_ui_deployment_readiness_report(
        phase30_manifest(),
        project_root=tmp_path,
        environment=environment,
        include_environment=True,
        deployment_environment="staging",
    )

    assert report["status"] == "ready_for_deployment_review"
    assert report["environment"]["included"] is True
    assert report["summary"]["environment_checks"] == 4
    assert report["blockers"] == []


def test_phase30_report_blocks_dev_only_user_id_in_staging(tmp_path):
    write_phase30_evidence(tmp_path)
    environment = {
        "SL_LEGAL_API_BASE_URL": "https://api.example.invalid",
        "SL_LEGAL_AUTH_HMAC_SECRET": "a" * 32,
        "SL_LEGAL_UI_SESSION_SECRET": "b" * 32,
        "SL_LEGAL_UI_USER_ID": "local-dev-user",
    }

    report = build_ui_deployment_readiness_report(
        phase30_manifest(),
        project_root=tmp_path,
        environment=environment,
        include_environment=True,
        deployment_environment="staging",
    )

    assert report["status"] == "blocked"
    assert any(item["id"] == "dev_env:SL_LEGAL_UI_USER_ID" for item in report["blockers"])


def test_phase30_script_writes_report(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase30_evidence(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "ui-deployment-readiness.json"
    manifest.write_text(json.dumps(phase30_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_hosted_env_review"
