from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import build_release_provenance_ledger, load_release_provenance_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase12_release_provenance.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase12_release_provenance.py"
    spec = importlib.util.spec_from_file_location("build_phase12_release_provenance", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_phase12_evidence(root: Path) -> None:
    (root / "Docs" / "releases").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "v2_phase_11_published_asset_verification_contract.md").write_text("contract\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_11_published_asset_verification_runbook.md").write_text("runbook\n", encoding="utf-8")
    (root / "Docs" / "releases" / "v2_phase_11_published_asset_verification.md").write_text("release\n", encoding="utf-8")
    (root / "logs" / "release-artifacts").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "release-artifacts" / "phase11-asset-verification.json").write_text(
        json.dumps({"status": "verified"}),
        encoding="utf-8",
    )
    log_dir = root / "logs" / "test-runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "phase11-tests-rerun.log",
        "phase11-frontend-rerun.log",
        "phase11-load-plan-rerun.log",
        "phase11-artifact-report-rerun.log",
        "phase11-asset-verification-rerun.log",
    ]:
        (log_dir / name).write_text("exit_status=0\n", encoding="utf-8")


def phase12_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase12_release_provenance.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "evidence": [
            {
                "id": "release_note",
                "title": "Release note",
                "type": "document",
                "path": "Docs/releases/v2_phase_11_published_asset_verification.md",
            },
            {
                "id": "contract",
                "title": "Contract",
                "type": "document",
                "path": "Docs/v2_phase_11_published_asset_verification_contract.md",
            },
            {
                "id": "runbook",
                "title": "Runbook",
                "type": "document",
                "path": "Docs/v2_phase_11_published_asset_verification_runbook.md",
            },
            {
                "id": "verification",
                "title": "Verification",
                "type": "json_status",
                "path": "logs/release-artifacts/phase11-asset-verification.json",
                "expected_status": "verified",
            },
            {
                "id": "tests",
                "title": "Tests",
                "type": "detached_log",
                "path": "logs/test-runs/phase11-tests-rerun.log",
            },
            {
                "id": "frontend",
                "title": "Frontend",
                "type": "detached_log",
                "path": "logs/test-runs/phase11-frontend-rerun.log",
            },
            {
                "id": "load_plan",
                "title": "Load plan",
                "type": "detached_log",
                "path": "logs/test-runs/phase11-load-plan-rerun.log",
            },
            {
                "id": "artifact_report",
                "title": "Artifact report",
                "type": "detached_log",
                "path": "logs/test-runs/phase11-artifact-report-rerun.log",
            },
            {
                "id": "asset_verification",
                "title": "Asset verification",
                "type": "detached_log",
                "path": "logs/test-runs/phase11-asset-verification-rerun.log",
            },
        ],
    }


def test_phase12_manifest_loads():
    payload = load_release_provenance_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-11-published-asset-verification"


def test_phase12_builds_verified_ledger(tmp_path):
    write_phase12_evidence(tmp_path)

    ledger = build_release_provenance_ledger(
        phase12_manifest(),
        project_root=tmp_path,
        git_metadata={"tag_commit": "abc", "remote_tag_commit": "abc"},
        release_metadata={
            "tagName": "v1",
            "name": "V1",
            "url": "https://example.invalid/releases/v1",
            "isDraft": False,
            "isPrerelease": False,
        },
    )

    assert ledger["status"] == "verified"
    assert ledger["summary"]["verified_evidence"] == 9


def test_phase12_blocks_missing_required_evidence(tmp_path):
    ledger = build_release_provenance_ledger(
        phase12_manifest(),
        project_root=tmp_path,
        git_metadata={"tag_commit": "abc", "remote_tag_commit": "abc"},
        release_metadata={
            "tagName": "v1",
            "name": "V1",
            "url": "https://example.invalid/releases/v1",
            "isDraft": False,
            "isPrerelease": False,
        },
    )

    assert ledger["status"] == "failed"
    assert ledger["summary"]["missing_evidence"] == 9


def test_phase12_blocks_draft_release(tmp_path):
    write_phase12_evidence(tmp_path)

    ledger = build_release_provenance_ledger(
        phase12_manifest(),
        project_root=tmp_path,
        git_metadata={"tag_commit": "abc", "remote_tag_commit": "abc"},
        release_metadata={
            "tagName": "v1",
            "name": "V1",
            "url": "https://example.invalid/releases/v1",
            "isDraft": True,
            "isPrerelease": False,
        },
    )

    assert ledger["status"] == "failed"
    assert any(item["id"] == "github_release" for item in ledger["failures"])


def test_phase12_script_writes_ledger_from_saved_metadata(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase12_evidence(tmp_path)
    manifest = tmp_path / "manifest.json"
    release = tmp_path / "release.json"
    git = tmp_path / "git.json"
    output = tmp_path / "ledger.json"
    manifest.write_text(json.dumps(phase12_manifest()), encoding="utf-8")
    release.write_text(
        json.dumps(
            {
                "tagName": "v1",
                "name": "V1",
                "url": "https://example.invalid/releases/v1",
                "isDraft": False,
                "isPrerelease": False,
            }
        ),
        encoding="utf-8",
    )
    git.write_text(json.dumps({"tag_commit": "abc", "remote_tag_commit": "abc"}), encoding="utf-8")

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
    assert payload["status"] == "verified"
