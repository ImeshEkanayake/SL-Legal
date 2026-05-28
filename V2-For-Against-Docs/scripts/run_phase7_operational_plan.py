#!/usr/bin/env python3
"""Render the Phase 7 deployment, data, and monitoring command plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import load_operational_manifest, operational_plan  # noqa: E402


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase7_deployment_monitoring_manifest.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--section",
        choices=["release_gates", "deployment_readiness", "hosted_data", "recurring_monitoring"],
        help="Render only one command section.",
    )
    parser.add_argument("--format", choices=["json", "shell", "markdown"], default="json")
    return parser.parse_args(argv)


def resolve_manifest(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def render_shell(plan: dict[str, object]) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for item in plan["commands"]:  # type: ignore[index]
        lines.append(f"# {item['name']} -> {item['evidence']}")
        lines.append(str(item["command_line"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(plan: dict[str, object]) -> str:
    lines = [f"# Phase 7 Operational Plan: {plan['section']}", ""]
    for item in plan["commands"]:  # type: ignore[index]
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- Section: `{item['section']}`",
                f"- Evidence: `{item['evidence']}`",
                f"- Requires production stack: `{item['requires_production_stack']}`",
                f"- Required for release: `{item['required_for_release']}`",
                "",
                "```bash",
                str(item["command_line"]),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_operational_manifest(resolve_manifest(args.manifest))
    plan = operational_plan(manifest, section=args.section)
    if args.format == "json":
        print(json.dumps(plan, indent=2))
    elif args.format == "shell":
        print(render_shell(plan), end="")
    else:
        print(render_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
