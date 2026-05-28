#!/usr/bin/env python3
"""Run the reproducible local quality gate for repo-owned backend work."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNFINISHED_PATTERNS = (
    "place" + "holder",
    "not " + "implemented",
    "wire " + "later",
    "tempor" + "ary",
    "TO" + "DO",
)
QUALITY_PATHS = (
    PROJECT_ROOT / "rag" / "sl_legal_rag",
    PROJECT_ROOT / "rag" / "sql",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "rag" / "README.md",
    PROJECT_ROOT / "rag" / "DB_SCHEMA.md",
    PROJECT_ROOT / "Docs" / "sl_legal_assist_production_build_roadmap.md",
    PROJECT_ROOT / "Docs" / "phase_reviews",
    PROJECT_ROOT / "web" / "src",
    PROJECT_ROOT / "web" / "next.config.ts",
    PROJECT_ROOT / "web" / "vitest.config.ts",
)
SKIP_DIR_NAMES = {".pytest_cache", "__pycache__"}
PYTHON_DEPENDENCIES = (
    "fastapi",
    "httpx",
    "pydantic",
    "pydantic-settings",
    "eval-type-backport",
    "sqlalchemy",
    "psycopg[binary]",
    "boto3",
    "pillow",
    "pypdfium2",
    "pytest",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-db-smoke", action="store_true")
    parser.add_argument("--skip-rag-health", action="store_true")
    parser.add_argument(
        "--require-rag-indexes",
        action="store_true",
        help="Require OpenSearch and Qdrant to match PostgreSQL retrieval chunks.",
    )
    return parser.parse_args(argv)


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def python_command(*args: str) -> list[str]:
    uv = shutil.which("uv")
    if not uv:
        return [sys.executable, *args]
    command = [uv, "run"]
    for dependency in PYTHON_DEPENDENCIES:
        command.extend(["--with", dependency])
    command.extend(["python", *args])
    return command


def iter_quality_files():
    for root in QUALITY_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(PROJECT_ROOT).parts):
                continue
            if path.suffix not in {".md", ".py", ".sql", ".txt", ".yml", ".yaml"}:
                continue
            yield path


def assert_no_unfinished_markers() -> None:
    findings: list[str] = []
    lowered_patterns = tuple(pattern.lower() for pattern in UNFINISHED_PATTERNS)
    for path in iter_quality_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            lower_line = line.lower()
            has_marker = any(
                re.search(r"\b" + ("tempor" + "ary") + r"\b", lower_line)
                if pattern == ("tempor" + "ary")
                else pattern in lower_line
                for pattern in lowered_patterns
            )
            if has_marker:
                findings.append(f"{path}:{line_number}: {line.strip()}")
    if findings:
        print("Unfinished-marker scan failed:", file=sys.stderr)
        for finding in findings:
            print(finding, file=sys.stderr)
        raise SystemExit(1)
    print("Unfinished-marker scan passed.")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    env["PYTHONPATH"] = "rag"

    run_command(python_command("-m", "compileall", "rag/sl_legal_rag"), env=env)
    run_command(python_command("scripts/check_no_plaintext_secrets.py"), env=env)
    assert_no_unfinished_markers()
    if not args.skip_db_smoke:
        run_command(python_command("scripts/check_postgres_schema.py"), env=env)
        run_command(python_command("scripts/smoke_test_postgres_schema.py"), env=env)
    if not args.skip_rag_health:
        health_command = python_command("scripts/check_rag_production_health.py")
        if args.require_rag_indexes:
            health_command.append("--require-search-indexes")
        run_command(health_command, env=env)
    if not args.skip_tests:
        run_command(python_command("-m", "pytest", "tests", "-q"), env=env)
    if (PROJECT_ROOT / "web" / "package.json").exists():
        run_command(["npm", "--prefix", "web", "run", "quality"], env=env)
    print("Quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
