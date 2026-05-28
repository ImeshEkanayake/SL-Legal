#!/usr/bin/env python3
"""Run or plan the Phase 7 recurring monitoring snapshot."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import load_operational_manifest, operational_commands, render_command  # noqa: E402


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase7_deployment_monitoring_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "monitoring" / "phase7-monitoring-snapshot.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    parser.add_argument("--include-production-stack", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def run_command(command: list[str], env: dict[str, str] | None) -> dict[str, Any]:
    merged_env = dict(os.environ)
    merged_env["PYTHONPATH"] = "rag" if not merged_env.get("PYTHONPATH") else f"rag{os.pathsep}{merged_env['PYTHONPATH']}"
    if env:
        merged_env.update(env)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "exit_status": completed.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "output_tail": completed.stdout[-4000:],
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_operational_manifest(resolve_path(args.manifest))
    commands = operational_commands(manifest, section="recurring_monitoring")
    if not args.include_production_stack:
        commands = [command for command in commands if not command.requires_production_stack]

    results: list[dict[str, Any]] = []
    for command in commands:
        item = {
            "name": command.name,
            "cadence": command.cadence,
            "requires_production_stack": command.requires_production_stack,
            "command_line": render_command(command),
            "evidence": command.evidence,
            "status": "planned",
        }
        if args.execute:
            execution = run_command(list(command.command), command.env)
            item["execution"] = execution
            item["status"] = "passed" if execution["exit_status"] == 0 else "failed"
        results.append(item)

    report = {
        "schema_version": "phase7_monitoring_snapshot.v1",
        "mode": "execute" if args.execute else "plan",
        "include_production_stack": args.include_production_stack,
        "status": "passed" if results and all(item["status"] in {"planned", "passed"} for item in results) else "failed",
        "checks": results,
    }
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.allow_failures:
        return 0
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
