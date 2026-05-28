from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import build_release_signing_plan, load_release_signing_plan_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase15_release_signing_plan.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase15_signing_plan.py"
    spec = importlib.util.spec_from_file_location("build_phase15_signing_plan", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_phase15_artifacts(root: Path) -> None:
    artifact_dir = root / "logs" / "release-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "phase13-release-attestation.json").write_text(
        json.dumps({"status": "verified"}),
        encoding="utf-8",
    )
    (artifact_dir / "phase14-signing-readiness.json").write_text(
        json.dumps({"status": "ready_for_signing_review"}),
        encoding="utf-8",
    )


def phase15_manifest() -> dict[str, object]:
    return {
        "schema_version": "phase15_release_signing_plan.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "signing_mode": "sigstore_keyless",
        "signing_execution_approved": False,
        "readiness_report_path": "logs/release-artifacts/phase14-signing-readiness.json",
        "signature_output_dir": "logs/release-artifacts/signatures",
        "artifacts": [
            {
                "id": "attestation",
                "title": "Attestation",
                "path": "logs/release-artifacts/phase13-release-attestation.json",
                "label": "phase13-release-attestation.json",
            },
            {
                "id": "readiness",
                "title": "Readiness",
                "path": "logs/release-artifacts/phase14-signing-readiness.json",
                "label": "phase14-signing-readiness.json",
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


def test_phase15_manifest_loads():
    payload = load_release_signing_plan_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-14-release-signing-readiness"


def test_phase15_builds_non_executing_plan(tmp_path):
    write_phase15_artifacts(tmp_path)

    plan = build_release_signing_plan(
        phase15_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert plan["status"] == "planned"
    assert plan["signing_execution_approved"] is False
    assert plan["summary"]["planned_commands"] == 2
    assert "cosign sign-blob" in plan["commands"][0]["command_line"]


def test_phase15_blocks_missing_artifact(tmp_path):
    write_phase15_artifacts(tmp_path)
    (tmp_path / "logs" / "release-artifacts" / "phase13-release-attestation.json").unlink()

    plan = build_release_signing_plan(
        phase15_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert plan["status"] == "blocked"
    assert plan["summary"]["missing_artifacts"] == 1


def test_phase15_blocks_unready_readiness_report(tmp_path):
    write_phase15_artifacts(tmp_path)
    (tmp_path / "logs" / "release-artifacts" / "phase14-signing-readiness.json").write_text(
        json.dumps({"status": "blocked"}),
        encoding="utf-8",
    )

    plan = build_release_signing_plan(
        phase15_manifest(),
        project_root=tmp_path,
        release_metadata=release_metadata(),
        git_metadata=git_metadata(),
    )

    assert plan["status"] == "blocked"
    assert any(item["id"] == "signing_readiness" for item in plan["blockers"])


def test_phase15_script_writes_plan_from_saved_metadata(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    write_phase15_artifacts(tmp_path)
    manifest = tmp_path / "manifest.json"
    release = tmp_path / "release.json"
    git = tmp_path / "git.json"
    output = tmp_path / "signing-plan.json"
    manifest.write_text(json.dumps(phase15_manifest()), encoding="utf-8")
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
    assert payload["status"] == "planned"
