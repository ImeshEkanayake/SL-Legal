#!/usr/bin/env python3
"""Build a non-mutating release signing execution plan."""

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

from sl_legal_rag.operations import build_release_signing_plan, load_release_signing_plan_manifest  # noqa: E402


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase15_release_signing_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "release-artifacts" / "phase15-signing-plan.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repo")
    parser.add_argument("--target-tag")
    parser.add_argument("--release-json", help="Use saved gh release JSON instead of calling gh.")
    parser.add_argument("--git-json", help="Use saved git metadata JSON instead of calling git/GitHub.")
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stdout.strip() or completed.returncode)
    return completed.stdout.strip()


def try_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def fetch_release_metadata(*, repo: str, target_tag: str) -> dict[str, Any]:
    payload = run_command(
        [
            "gh",
            "release",
            "view",
            target_tag,
            "--repo",
            repo,
            "--json",
            "tagName,name,url,isDraft,isPrerelease",
        ]
    )
    return json.loads(payload)


def fetch_remote_tag_commit(*, repo: str, target_tag: str) -> str:
    ref_payload = json.loads(run_command(["gh", "api", f"repos/{repo}/git/ref/tags/{target_tag}"]))
    tag_object = ref_payload.get("object") or {}
    tag_sha = str(tag_object.get("sha") or "")
    tag_type = str(tag_object.get("type") or "")
    if tag_type != "tag":
        return tag_sha
    tag_payload = json.loads(run_command(["gh", "api", f"repos/{repo}/git/tags/{tag_sha}"]))
    nested = tag_payload.get("object") or {}
    return str(nested.get("sha") or tag_sha)


def fetch_git_metadata(*, repo: str, target_tag: str) -> dict[str, Any]:
    tag_commit = try_command(["git", "rev-list", "-n", "1", target_tag])
    remote = try_command(["git", "ls-remote", "--tags", "origin", f"refs/tags/{target_tag}"])
    remote_tag_commit = remote.split()[0] if remote else ""
    if not remote_tag_commit:
        remote_tag_commit = fetch_remote_tag_commit(repo=repo, target_tag=target_tag)
    if not tag_commit:
        tag_commit = remote_tag_commit
    return {
        "repo": repo,
        "target_release_tag": target_tag,
        "tag_commit": tag_commit,
        "remote_tag_commit": remote_tag_commit,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_release_signing_plan_manifest(resolve_path(args.manifest))
    repo = args.repo or str(manifest.get("repo") or "")
    target_tag = args.target_tag or str(manifest.get("target_release_tag") or "")
    if not repo:
        raise SystemExit("repo is required")
    if not target_tag:
        raise SystemExit("target release tag is required")
    if args.release_json:
        release_metadata = json.loads(resolve_path(args.release_json).read_text(encoding="utf-8"))
    else:
        release_metadata = fetch_release_metadata(repo=repo, target_tag=target_tag)
    if args.git_json:
        git_metadata = json.loads(resolve_path(args.git_json).read_text(encoding="utf-8"))
    else:
        git_metadata = fetch_git_metadata(repo=repo, target_tag=target_tag)
    plan = build_release_signing_plan(
        {**manifest, "repo": repo, "target_release_tag": target_tag},
        project_root=PROJECT_ROOT,
        release_metadata=release_metadata,
        git_metadata=git_metadata,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0 if args.allow_blocked or plan["status"] in {"planned", "execution_ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
