#!/usr/bin/env python3
"""Build the Phase 39 hosted environment configuration pack."""

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
    build_hosted_environment_config_pack,
    load_hosted_environment_config_manifest,
    load_hosted_evidence_capture_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase39_hosted_environment_config.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase39-hosted-environment-config-pack.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-environment", action="store_true")
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_hosted_environment_config_manifest(resolve_path(args.manifest))
    phase35_path = resolve_path(str(manifest.get("phase35_manifest_path") or "rag/evals/phase35_hosted_evidence_capture.json"))
    phase35_payload = load_hosted_evidence_capture_manifest(phase35_path)
    report = build_hosted_environment_config_pack(
        manifest,
        project_root=PROJECT_ROOT,
        environment=dict(os.environ) if args.include_environment else {},
        include_environment=args.include_environment,
        phase35_payload=phase35_payload,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    expected_statuses = {"awaiting_hosted_environment_configuration", "ready_for_hosted_capture_dry_run"}
    return 0 if args.allow_blocked or report["status"] in expected_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
