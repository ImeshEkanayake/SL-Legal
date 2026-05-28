from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_release_publication_plan,
    is_allowed_publication_path,
    load_release_publication_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase10_release_asset_publication.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "publish_phase10_release_assets.py"
    spec = importlib.util.spec_from_file_location("publish_phase10_release_assets", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase10_manifest_targets_phase9_release():
    payload = load_release_publication_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-9-release-artifacts"
    assert payload["repo"] == "ImeshEkanayake/SL-Legal"
    assert {item["id"] for item in payload["assets"]} == {
        "phase9_local_evidence_bundle",
        "phase9_artifact_report",
    }


def test_phase10_publication_plan_hashes_ready_assets(tmp_path):
    bundle = tmp_path / "logs" / "release-artifacts" / "bundle.tar.gz"
    report = tmp_path / "logs" / "release-artifacts" / "report.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(b"bundle")
    report.write_text('{"status":"complete"}\n', encoding="utf-8")
    manifest = {
        "schema_version": "phase10_release_asset_publication.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "assets": [
            {
                "id": "bundle",
                "title": "Bundle",
                "path": "logs/release-artifacts/bundle.tar.gz",
                "label": "bundle.tar.gz",
            },
            {
                "id": "report",
                "title": "Report",
                "path": "logs/release-artifacts/report.json",
                "label": "report.json",
            },
        ],
    }

    plan = build_release_publication_plan(manifest, project_root=tmp_path)

    assert plan["status"] == "ready"
    assert plan["summary"] == {"total": 2, "ready": 2, "blocked": 0}
    assert all(len(item["sha256"]) == 64 for item in plan["assets"])


def test_phase10_publication_plan_blocks_raw_or_missing_assets(tmp_path):
    manifest = {
        "schema_version": "phase10_release_asset_publication.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "assets": [
            {
                "id": "raw",
                "title": "Raw",
                "path": "data/raw/file.pdf",
                "label": "file.pdf",
            },
            {
                "id": "missing",
                "title": "Missing",
                "path": "logs/release-artifacts/missing.tar.gz",
                "label": "missing.tar.gz",
            },
        ],
    }

    plan = build_release_publication_plan(manifest, project_root=tmp_path)

    assert plan["status"] == "blocked"
    assert plan["summary"] == {"total": 2, "ready": 0, "blocked": 2}
    assert not is_allowed_publication_path("data/raw/file.pdf")


def test_phase10_script_writes_plan(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    bundle = tmp_path / "logs" / "release-artifacts" / "bundle.tar.gz"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "plan.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(b"bundle")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "phase10_release_asset_publication.v1",
                "repo": "owner/repo",
                "target_release_tag": "v1",
                "assets": [
                    {
                        "id": "bundle",
                        "title": "Bundle",
                        "path": "logs/release-artifacts/bundle.tar.gz",
                        "label": "bundle.tar.gz",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = module.main(["--manifest", str(manifest), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["mode"] == "plan"
    assert payload["status"] == "ready"
