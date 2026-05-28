from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from sl_legal_rag.operations import build_release_artifact_report, load_release_artifact_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "rag" / "evals" / "phase9_release_artifacts_manifest.json"


def load_script():
    script = PROJECT_ROOT / "scripts" / "build_phase9_release_artifacts.py"
    spec = importlib.util.spec_from_file_location("build_phase9_release_artifacts", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase9_manifest_has_local_release_artifacts():
    payload = load_release_artifact_manifest(MANIFEST_PATH)
    ids = {item["id"] for item in payload["artifacts"]}

    assert {
        "phase8_requirements",
        "phase9_manifest",
        "phase9_contract",
        "phase9_runbook",
        "phase9_release_note",
    } <= ids


def test_phase9_artifact_report_records_hashes_for_present_files(tmp_path):
    manifest = {
        "schema_version": "phase9_release_artifacts.v1",
        "artifacts": [
            {
                "id": "sample",
                "title": "Sample",
                "path": "sample.txt",
                "required": True,
                "include_in_bundle": True,
                "evidence_scope": "local_release",
            }
        ],
    }
    (tmp_path / "sample.txt").write_text("evidence\n", encoding="utf-8")

    report = build_release_artifact_report(manifest, project_root=tmp_path)

    assert report["status"] == "complete"
    assert report["artifacts"][0]["size_bytes"] == len("evidence\n")
    assert len(report["artifacts"][0]["sha256"]) == 64


def test_phase9_artifact_report_marks_missing_required_files(tmp_path):
    manifest = {
        "schema_version": "phase9_release_artifacts.v1",
        "artifacts": [
            {
                "id": "missing",
                "title": "Missing",
                "path": "missing.json",
                "required": True,
                "include_in_bundle": True,
                "evidence_scope": "local_release",
            }
        ],
    }

    report = build_release_artifact_report(manifest, project_root=tmp_path)

    assert report["status"] == "incomplete"
    assert report["summary"]["required_missing"] == 1


def test_phase9_script_writes_report_and_bundle(tmp_path):
    module = load_script()
    module.PROJECT_ROOT = tmp_path
    manifest = tmp_path / "manifest.json"
    evidence = tmp_path / "evidence.md"
    output = tmp_path / "report.json"
    bundle = tmp_path / "bundle.tar.gz"
    evidence.write_text("release evidence\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "phase9_release_artifacts.v1",
                "artifacts": [
                    {
                        "id": "evidence",
                        "title": "Evidence",
                        "path": "evidence.md",
                        "required": True,
                        "include_in_bundle": True,
                        "evidence_scope": "local_release",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = module.main(
        [
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--bundle",
            str(bundle),
            "--write-bundle",
        ]
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert status == 0
    assert report["status"] == "complete"
    assert bundle.is_file()
