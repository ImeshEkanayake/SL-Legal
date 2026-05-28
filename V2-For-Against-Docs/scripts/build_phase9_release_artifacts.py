#!/usr/bin/env python3
"""Build the Phase 9 release evidence artifact report and optional bundle."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import build_release_artifact_report, load_release_artifact_manifest  # noqa: E402


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase9_release_artifacts_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "release-artifacts" / "phase9-artifact-report.json"
DEFAULT_BUNDLE = PROJECT_ROOT / "logs" / "release-artifacts" / "phase9-release-evidence.tar.gz"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--include-production", action="store_true")
    parser.add_argument("--write-bundle", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_bundle(report: dict[str, Any], output_path: Path, bundle_path: Path) -> None:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle_path, "w:gz") as archive:
        archive.add(output_path, arcname=str(output_path.relative_to(PROJECT_ROOT)))
        for item in report["artifacts"]:
            if not item["include_in_bundle"] or not item["exists"]:
                continue
            source = resolve_path(str(item["path"]))
            archive.add(source, arcname=str(source.relative_to(PROJECT_ROOT)))


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_release_artifact_manifest(resolve_path(args.manifest))
    report = build_release_artifact_report(
        manifest,
        project_root=PROJECT_ROOT,
        include_production=args.include_production,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.write_bundle:
        bundle = resolve_path(args.bundle)
        write_bundle(report, output, bundle)
        report["bundle"] = str(bundle.relative_to(PROJECT_ROOT) if bundle.is_relative_to(PROJECT_ROOT) else bundle)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if args.allow_missing or report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
