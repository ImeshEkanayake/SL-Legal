#!/usr/bin/env python3
"""Build the Phase 30 UI deployment readiness report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import (  # noqa: E402
    build_ui_deployment_readiness_report,
    load_ui_deployment_readiness_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase30_ui_deployment_readiness.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase30-ui-deployment-readiness.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--deployment-environment",
        default="staging",
        choices=["local", "staging", "production"],
    )
    parser.add_argument(
        "--include-environment",
        action="store_true",
        help="Inspect process environment for hosted deployment variables without printing secret values.",
    )
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_ui_deployment_readiness_manifest(resolve_path(args.manifest))
    report = build_ui_deployment_readiness_report(
        manifest,
        project_root=PROJECT_ROOT,
        environment=dict(os.environ) if args.include_environment else {},
        include_environment=args.include_environment,
        deployment_environment=args.deployment_environment,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    expected_statuses = {"ready_for_hosted_env_review", "ready_for_deployment_review"}
    return 0 if args.allow_blocked or report["status"] in expected_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
