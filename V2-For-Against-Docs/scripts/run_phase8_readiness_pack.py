#!/usr/bin/env python3
"""Build the Phase 8 deployment readiness evidence pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import build_readiness_pack, load_readiness_requirements  # noqa: E402


DEFAULT_REQUIREMENTS = PROJECT_ROOT / "rag" / "evals" / "phase8_deployment_readiness_evidence.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase8-readiness-pack.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-production", action="store_true")
    parser.add_argument("--allow-blockers", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    requirements = load_readiness_requirements(resolve_path(args.requirements))
    pack = build_readiness_pack(requirements, project_root=PROJECT_ROOT, include_production=args.include_production)
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(pack, indent=2, ensure_ascii=False))
    return 0 if args.allow_blockers or pack["decision"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
