#!/usr/bin/env python3
"""Build the Phase 33 hosted staging validation report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import (  # noqa: E402
    build_hosted_staging_validation_report,
    load_hosted_staging_validation_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase33_hosted_staging_validation.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase33-hosted-staging-validation.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_hosted_staging_validation_manifest(resolve_path(args.manifest))
    report = build_hosted_staging_validation_report(manifest, project_root=PROJECT_ROOT)
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    expected_statuses = {"awaiting_hosted_execution", "hosted_staging_validated"}
    return 0 if args.allow_blocked or report["status"] in expected_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
