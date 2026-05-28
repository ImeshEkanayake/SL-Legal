from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import build_release_attestation, load_release_attestation_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase13_release_attestation.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase13_release_attestation.py"
    spec = importlib.util.spec_from_file_location("build_phase13_release_attestation", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_phase13_subjects(root: Path) -> None:
    (root / "Docs" / "releases").mkdir(parents=True, exist_ok=True)
    (root / "Docs" / "releases" / "v2_phase_12_release_provenance_ledger.md").write_text("release\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_12_release_provenance_contract.md").write_text("contract\n", encoding="utf-8")
    (root / "Docs" / "v2_phase_12_release_provenance_runbook.md").write_text("runbook\n", encoding="utf-8")
    (root / "rag" / "evals").mkdir(parents=True, exist_ok=True)
    (root / "rag" / "evals" / "phase12_release_provenance.json").write_text('{"schema_version":"phase12"}\n', encoding="utf-8")
    (root / "logs" / "release-artifacts").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "release-artifacts" / "phase12-release-provenance-ledger.json").write_text(
        json.dumps({"status": "verified"}),
        encoding="utf-8",
    )


def phase13_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase13_release_attestation.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "predicate_type": "https://example.invalid/predicate/v1",
        "builder_id": "pytest-builder",
        "subjects": [
            {
                "id": "ledger",
                "title": "Ledger",
                "type": "json_status",
                "path": "logs/release-artifacts/phase12-release-provenance-ledger.json",
                "expected_status": "verified",
            },
            {
                "id": "release",
                "title": "Release",
                "type": "document",
                "path": "Docs/releases/v2_phase_12_release_provenance_ledger.md",
            },
            {
                "id": "contract",
                "title": "Contract",
                "type": "document",
                "path": "Docs/v2_phase_12_release_provenance_contract.md",
            },
            {
                "id": "runbook",
                "title": "Runbook",
                "type": "document",
                "path": "Docs/v2_phase_12_release_provenance_runbook.md",
            },
            {
                "id": "manifest",
                "title": "Manifest",
                "type": "document",
                "path": "rag/evals/phase12_release_provenance.json",
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


def test_phase13_manifest_loads():
    payload = load_release_attestation_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-12-release-provenance-ledger"


def test_phase13_builds_verified_attestation(tmp_path):
    write_phase13_subjects(tmp_path)

    attestation = build_release_attestation(
        phase13_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert attestation["status"] == "verified"
    assert len(attestation["attestation_digest"]) == 64
    assert attestation["signature"]["signed"] is False
    assert attestation["summary"]["verified_subjects"] == 5


def test_phase13_attestation_digest_is_deterministic(tmp_path):
    write_phase13_subjects(tmp_path)

    first = build_release_attestation(
        phase13_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )
    second = build_release_attestation(
        phase13_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert first["attestation_digest"] == second["attestation_digest"]


def test_phase13_blocks_failed_ledger_status(tmp_path):
    write_phase13_subjects(tmp_path)
    (tmp_path / "logs" / "release-artifacts" / "phase12-release-provenance-ledger.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    attestation = build_release_attestation(
        phase13_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert attestation["status"] == "failed"
    assert attestation["summary"]["failed_subjects"] == 1


def test_phase13_script_writes_attestation_from_saved_metadata(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase13_subjects(tmp_path)
    manifest = tmp_path / "manifest.json"
    release = tmp_path / "release.json"
    git = tmp_path / "git.json"
    output = tmp_path / "attestation.json"
    manifest.write_text(json.dumps(phase13_manifest()), encoding="utf-8")
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
    assert payload["status"] == "verified"
