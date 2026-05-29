from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_hosted_staging_execution_pack,
    load_hosted_staging_execution_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase32_hosted_staging_execution.json"
SESSION_MATERIAL = "phase32-" + ("x" * 32)


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase32_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase32_hosted_staging_execution.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "execution_environment": "staging",
        "required_reports": [
            {
                "id": "phase31_cutover_dry_run",
                "title": "Phase 31 dry run",
                "type": "json_status",
                "path": "logs/readiness/phase31-staging-cutover-dry-run.json",
                "accepted_statuses": ["ready_for_hosted_env_setup", "ready_for_staging_cutover"],
            },
            {
                "id": "phase31_manifest",
                "title": "Phase 31 manifest",
                "type": "file",
                "path": "rag/evals/phase31_staging_cutover_dry_run.json",
            },
            {
                "id": "phase31_contract",
                "title": "Phase 31 contract",
                "type": "document",
                "path": "Docs/v2_phase_31_staging_cutover_dry_run_contract.md",
            },
        ],
        "execution_steps": [
            {
                "id": "hosted_env_gate",
                "title": "Hosted env gate",
                "command": ["scripts/run_detached_quality_gate.sh", "ui-deployment-readiness-env", "phase32-env"],
                "expected_evidence": "logs/test-runs/phase32-env.log",
                "requires_hosted_environment": True,
            },
            {
                "id": "create_review_session_cookie",
                "title": "Create review cookie",
                "command": ["python3", "scripts/create_ui_session_token.py", "--user-id", "<reviewer-user-id>"],
                "expected_evidence": "private cookie value",
                "requires_hosted_environment": True,
                "requires_manual_action": True,
            },
            {
                "id": "browser_smoke",
                "title": "Browser smoke",
                "command": ["scripts/run_detached_quality_gate.sh", "phase29-browser-workflow", "phase32-browser"],
                "expected_evidence": "logs/test-runs/phase32-browser.log",
            },
        ],
        "manual_approvals": [
            {"id": "operator_secret_review", "title": "Operator secret review", "required": True},
        ],
        "rollback_steps": [
            {
                "id": "revoke_cookie",
                "title": "Revoke cookie",
                "action": "Rotate session secret.",
                "owner": "operator",
            }
        ],
    }


def write_phase32_evidence(root: Path, *, phase31_status: str = "ready_for_hosted_env_setup") -> None:
    (root / "logs" / "readiness").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "readiness" / "phase31-staging-cutover-dry-run.json").write_text(
        json.dumps({"status": phase31_status}),
        encoding="utf-8",
    )
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase31_staging_cutover_dry_run.json").write_text(
        json.dumps({"schema_version": "phase31_staging_cutover_dry_run.v1"}),
        encoding="utf-8",
    )
    (root / "Docs").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_31_staging_cutover_dry_run_contract.md").write_text("contract\n", encoding="utf-8")


def test_phase32_manifest_loads():
    payload = load_hosted_staging_execution_manifest(MANIFEST_PATH)
    step_ids = {item["id"] for item in payload["execution_steps"]}

    assert payload["target_release_tag"] == "v2-phase-31-staging-cutover-dry-run"
    assert "hosted_env_readiness" in step_ids
    assert "create_review_session_cookie" in step_ids
    assert "lawyer_review_acceptance" in step_ids


def test_phase32_ready_for_hosted_configuration_locally(tmp_path):
    write_phase32_evidence(tmp_path, phase31_status="ready_for_hosted_env_setup")

    report = build_hosted_staging_execution_pack(phase32_manifest(), project_root=tmp_path)

    assert report["status"] == "ready_for_hosted_configuration"
    assert report["summary"]["verified_reports"] == 3
    assert report["summary"]["hosted_execution_steps"] == 2
    assert report["blockers"] == []
    assert "phase32-test" not in json.dumps(report)


def test_phase32_ready_for_hosted_staging_execution_after_cutover_ready(tmp_path):
    write_phase32_evidence(tmp_path, phase31_status="ready_for_staging_cutover")

    report = build_hosted_staging_execution_pack(phase32_manifest(), project_root=tmp_path)

    assert report["status"] == "ready_for_hosted_staging_execution"
    assert report["blockers"] == []


def test_phase32_blocks_missing_phase31_report(tmp_path):
    write_phase32_evidence(tmp_path)
    (tmp_path / "logs" / "readiness" / "phase31-staging-cutover-dry-run.json").unlink()

    report = build_hosted_staging_execution_pack(phase32_manifest(), project_root=tmp_path)

    assert report["status"] == "blocked"
    assert report["summary"]["missing_reports"] == 1
    assert any(item["id"] == "phase31_cutover_dry_run" for item in report["blockers"])


def test_phase32_blocks_incomplete_execution_step(tmp_path):
    write_phase32_evidence(tmp_path)
    manifest = phase32_manifest()
    manifest["execution_steps"] = [
        {
            "id": "empty_step",
            "title": "Empty step",
            "required_before_exposure": True,
        }
    ]

    report = build_hosted_staging_execution_pack(manifest, project_root=tmp_path)

    assert report["status"] == "blocked"
    assert any(item["id"] == "empty_step" for item in report["blockers"])


def test_phase32_pack_script_writes_report(tmp_path):
    module = load_script(
        "build_phase32_hosted_staging_execution_pack",
        PROJECT_ROOT / "scripts" / "build_phase32_hosted_staging_execution_pack.py",
    )
    module.PROJECT_ROOT = tmp_path
    write_phase32_evidence(tmp_path)
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "hosted-staging-execution.json"
    manifest.write_text(json.dumps(phase32_manifest()), encoding="utf-8")

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_hosted_configuration"


def test_create_ui_session_token_matches_web_token_shape(capsys):
    module = load_script("create_ui_session_token", PROJECT_ROOT / "scripts" / "create_ui_session_token.py")
    token = module.create_token(user_id="reviewer@example.com", secret=SESSION_MATERIAL, now_seconds=1000, ttl_seconds=600)
    encoded_payload, signature = token.split(".")
    expected_signature = base64.urlsafe_b64encode(
        hmac.new(SESSION_MATERIAL.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    padded_payload = encoded_payload + ("=" * (-len(encoded_payload) % 4))
    payload = json.loads(base64.urlsafe_b64decode(padded_payload.encode("ascii")))

    assert signature == expected_signature
    assert payload == {
        "version": 1,
        "userId": "reviewer@example.com",
        "issuedAt": 1000,
        "expiresAt": 1600,
    }

    status = module.main(
        [
            "--user-id",
            "reviewer@example.com",
            "--secret",
            SESSION_MATERIAL,
            "--now-seconds",
            "1000",
            "--ttl-seconds",
            "600",
            "--output",
            "cookie",
        ]
    )
    captured = capsys.readouterr()

    assert status == 0
    assert captured.out.startswith("sl_legal_session=")
    assert "HttpOnly" in captured.out
