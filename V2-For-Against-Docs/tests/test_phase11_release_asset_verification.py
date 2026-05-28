from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import (
    build_release_asset_verification_report,
    load_release_publication_manifest,
    normalize_release_asset_digest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase10_release_asset_publication.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "verify_phase11_release_assets.py"
    spec = importlib.util.spec_from_file_location("verify_phase11_release_assets", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase11_normalizes_github_sha256_digest():
    assert normalize_release_asset_digest("sha256:abc123") == "abc123"
    assert normalize_release_asset_digest("abc123") == "abc123"


def test_phase11_verifies_matching_remote_assets(tmp_path):
    asset = tmp_path / "logs" / "release-artifacts" / "asset.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text('{"ok":true}\n', encoding="utf-8")
    manifest = {
        "schema_version": "phase10_release_asset_publication.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "assets": [
            {
                "id": "asset",
                "title": "Asset",
                "path": "logs/release-artifacts/asset.json",
                "label": "asset.json",
            }
        ],
    }
    expected = build_release_asset_verification_report(
        manifest,
        project_root=tmp_path,
        remote_assets=[],
    )["assets"][0]
    report = build_release_asset_verification_report(
        manifest,
        project_root=tmp_path,
        remote_assets=[
            {
                "name": "asset.json",
                "digest": "sha256:" + expected["sha256"],
                "size": expected["size_bytes"],
                "url": "https://example.invalid/asset.json",
            }
        ],
    )

    assert report["status"] == "verified"
    assert report["summary"] == {"total": 1, "verified": 1, "failed": 0}


def test_phase11_reports_mismatch_for_wrong_remote_digest(tmp_path):
    asset = tmp_path / "logs" / "release-artifacts" / "asset.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text('{"ok":true}\n', encoding="utf-8")
    manifest = {
        "schema_version": "phase10_release_asset_publication.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "assets": [
            {
                "id": "asset",
                "title": "Asset",
                "path": "logs/release-artifacts/asset.json",
                "label": "asset.json",
            }
        ],
    }

    report = build_release_asset_verification_report(
        manifest,
        project_root=tmp_path,
        remote_assets=[{"name": "asset.json", "digest": "sha256:bad", "size": asset.stat().st_size}],
    )

    assert report["status"] == "failed"
    assert report["failures"][0]["verification_status"] == "mismatch"


def test_phase11_script_writes_report_from_saved_assets(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    asset = tmp_path / "logs" / "release-artifacts" / "asset.json"
    manifest = tmp_path / "manifest.json"
    remote = tmp_path / "remote.json"
    output = tmp_path / "verification.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text('{"ok":true}\n', encoding="utf-8")
    manifest_payload = {
        "schema_version": "phase10_release_asset_publication.v1",
        "repo": "owner/repo",
        "target_release_tag": "v1",
        "assets": [
            {
                "id": "asset",
                "title": "Asset",
                "path": "logs/release-artifacts/asset.json",
                "label": "asset.json",
            }
        ],
    }
    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
    expected = build_release_asset_verification_report(
        manifest_payload,
        project_root=tmp_path,
        remote_assets=[],
    )["assets"][0]
    remote.write_text(
        json.dumps({"assets": [{"name": "asset.json", "digest": "sha256:" + expected["sha256"], "size": expected["size_bytes"]}]}),
        encoding="utf-8",
    )

    status = module.main(["--manifest", str(manifest), "--remote-assets-json", str(remote), "--output", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert payload["status"] == "verified"


def test_phase11_manifest_still_loads_phase10_publication_manifest():
    payload = load_release_publication_manifest(MANIFEST_PATH)

    assert payload["target_release_tag"] == "v2-phase-9-release-artifacts"
