#!/usr/bin/env python3
"""Verify published GitHub release assets against approved local files."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import (  # noqa: E402
    build_release_asset_verification_report,
    load_release_publication_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase10_release_asset_publication.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "release-artifacts" / "phase11-asset-verification.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repo")
    parser.add_argument("--target-tag")
    parser.add_argument("--remote-assets-json", help="Use a saved gh release asset payload instead of calling gh.")
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def fetch_remote_assets(*, repo: str, target_tag: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["gh", "release", "view", target_tag, "--repo", repo, "--json", "assets"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stdout.strip() or completed.returncode)
    payload = json.loads(completed.stdout)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise SystemExit("GitHub release response did not include an assets array")
    return assets


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_release_publication_manifest(resolve_path(args.manifest))
    repo = args.repo or str(manifest.get("repo") or "")
    target_tag = args.target_tag or str(manifest.get("target_release_tag") or "")
    if args.remote_assets_json:
        payload = json.loads(resolve_path(args.remote_assets_json).read_text(encoding="utf-8"))
        remote_assets = payload.get("assets", payload)
        if not isinstance(remote_assets, list):
            raise SystemExit("remote assets JSON must be a list or object containing assets")
    else:
        remote_assets = fetch_remote_assets(repo=repo, target_tag=target_tag)
    report = build_release_asset_verification_report(
        manifest,
        project_root=PROJECT_ROOT,
        remote_assets=remote_assets,
        target_tag=target_tag,
        repo=repo,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if args.allow_failures or report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
