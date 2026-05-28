from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_release_signing_readiness_report,
    load_release_signing_readiness_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase14_release_signing_readiness.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase14_signing_readiness.py"
    spec = importlib.util.spec_from_file_location("build_phase14_signing_readiness", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_phase14_evidence(root: Path) -> None:
    (root / "Docs" / "releases").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "releases" / "v2_phase_13_release_attestation_envelope.md").write_text("release\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_13_release_attestation_contract.md").write_text("contract\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_13_release_attestation_runbook.md").write_text("runbook\n", encoding="utf-8")
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase13_release_attestation.json").write_text('{"schema_version":"phase13"}\n', encoding="utf-8")
    (root / "logs" / "release-artifacts").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "release-artifacts" / "phase13-release-attestation.json").write_text(
        json.dumps({"status": "verified"}),
        encoding="utf-8",
    )


def phase14_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase14_release_signing_readiness.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "approved_signing_modes": ["sigstore_keyless", "kms_hsm"],
        "signing_execution_approved": False,
        "environment_requirements": {
            "required_for_execution": ["SL_LEGAL_SIGNING_MODE", "SL_LEGAL_SIGNING_IDENTITY"]
        },
        "forbidden_secret_file_globs": ["**/release-signing.key", "**/id_rsa"],
        "evidence": [
            {
                "id": "attestation",
                "title": "Attestation",
                "type": "json_status",
                "path": "logs/release-artifacts/phase13-release-attestation.json",
                "expected_status": "verified",
            },
            {
                "id": "release",
                "title": "Release",
                "type": "document",
                "path": "Docs/releases/v2_phase_13_release_attestation_envelope.md",
            },
            {
                "id": "contract",
                "title": "Contract",
                "type": "document",
                "path": "Docs/v2_phase_13_release_attestation_contract.md",
            },
            {
                "id": "runbook",
                "title": "Runbook",
                "type": "document",
                "path": "Docs/v2_phase_13_release_attestation_runbook.md",
            },
            {
                "id": "manifest",
                "title": "Manifest",
                "type": "document",
                "path": "rag/evals/phase13_release_attestation.json",
            },
        ],
    }


def release_metadata() -> dict[str, object]:
    return {
        "tagName": "v1",
        "name": "V1",
        "url": "https://example.invalid/releases/v1",
        "isDraft": False,
        "isPrerelease": False,
    }


def git_metadata() -> dict[str, str]:
    return {"tag_commit": "abc", "remote_tag_commit": "abc"}


def test_phase14_manifest_loads():
    payload = load_release_signing_readiness_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-13-release-attestation-envelope"


def test_phase14_builds_ready_report(tmp_path):
    write_phase14_evidence(tmp_path)

    report = build_release_signing_readiness_report(
        phase14_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert report["status"] == "ready_for_signing_review"
    assert report["summary"]["verified_evidence"] == 5
    assert report["summary"]["forbidden_secret_file_matches"] == 0
    assert report["environment_requirements"]["execution_enabled"] is False


def test_phase14_blocks_forbidden_private_key_file(tmp_path):
    write_phase14_evidence(tmp_path)
    (tmp_path / "release-signing.key").write_text("secret\n", encoding="utf-8")

    report = build_release_signing_readiness_report(
        phase14_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert report["status"] == "blocked"
    assert report["summary"]["forbidden_secret_file_matches"] == 1


def test_phase14_blocks_unsupported_signing_mode(tmp_path):
    write_phase14_evidence(tmp_path)
    manifest = phase14_manifest()
    manifest["approved_signing_modes"] = ["local_private_key"]

    report = build_release_signing_readiness_report(
        manifest,
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert report["status"] == "blocked"
    assert any("unsupported signing mode" in item["summary"] for item in report["blockers"])


def test_phase14_script_writes_report_from_saved_metadata(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase14_evidence(tmp_path)
    manifest = tmp_path / "manifest.json"
    release = tmp_path / "release.json"
    git = tmp_path / "git.json"
    output = tmp_path / "signing-readiness.json"
    manifest.write_text(json.dumps(phase14_manifest()), encoding="utf-8")
    release.write_text(json.dumps(release_metadata()), encoding="utf-8")
    git.write_text(json.dumps(git_metadata()), encoding="utf-8")

    status = module.main(
        [
            "--manifest",
            str(manifest),
            "--release-json",
            str(release),
            "--git-json",
            str(git),
            "--output",
            str(output),
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "ready_for_signing_review"
