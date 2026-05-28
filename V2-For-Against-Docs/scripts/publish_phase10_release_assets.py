#!/usr/bin/env python3
"""Plan or publish approved release assets to a GitHub release."""

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

from sl_legal_rag.operations import build_release_publication_plan, load_release_publication_manifest  # noqa: E402


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase10_release_asset_publication.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "release-artifacts" / "phase10-publication-plan.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repo")
    parser.add_argument("--target-tag")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--clobber", action="store_true")
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def publish_assets(plan: dict[str, Any], *, clobber: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in plan["assets"]:
        if item["status"] != "ready":
            results.append({"id": item["id"], "status": "skipped", "reason": item["status"]})
            continue
        command = [
            "gh",
            "release",
            "upload",
            str(plan["target_release_tag"]),
            str(resolve_path(str(item["path"]))),
            "--repo",
            str(plan["repo"]),
        ]
        if clobber:
            command.append("--clobber")
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        results.append(
            {
                "id": item["id"],
                "status": "published" if completed.returncode == 0 else "failed",
                "exit_status": completed.returncode,
                "output": completed.stdout.strip(),
            }
        )
    return results


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_release_publication_manifest(resolve_path(args.manifest))
    plan = build_release_publication_plan(
        manifest,
        project_root=PROJECT_ROOT,
        target_tag=args.target_tag,
        repo=args.repo,
    )
    plan["mode"] = "execute" if args.execute else "plan"
    if args.execute and (plan["status"] == "ready" or args.allow_blocked):
        plan["publication_results"] = publish_assets(plan, clobber=args.clobber)
        if any(item.get("status") == "failed" for item in plan["publication_results"]):
            plan["status"] = "failed"
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0 if args.allow_blocked or plan["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
