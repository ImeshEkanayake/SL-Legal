#!/usr/bin/env python3
"""Apply SL Legal Assist PostgreSQL schema files through Docker Compose.

This intentionally avoids a Python database dependency. It uses the `psql`
client inside the Postgres container and applies every `rag/sql/*.sql` file in
filename order.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.rag.yml"
SQL_DIR = PROJECT_ROOT / "rag" / "sql"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], check=check)


def wait_for_postgres(timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = compose(
            "exec",
            "-T",
            "rag-postgres",
            "pg_isready",
            "-U",
            "sl_legal",
            "-d",
            "sl_legal_assist",
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("Postgres did not become ready in time")


def apply_sql_file(sql_file: Path) -> None:
    container_path = f"/docker-entrypoint-initdb.d/{sql_file.name}"
    result = compose(
        "exec",
        "-T",
        "rag-postgres",
        "psql",
        "-U",
        "sl_legal",
        "-d",
        "sl_legal_assist",
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        container_path,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed applying {sql_file.name}:\n{result.stdout}")
    print(f"applied {sql_file.name}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply PostgreSQL schema migrations.")
    parser.add_argument("--no-start", action="store_true", help="Do not start the Postgres container first.")
    parser.add_argument("--timeout", type=int, default=90, help="Postgres readiness timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    sql_files = sorted(SQL_DIR.glob("*.sql"))
    if not sql_files:
        raise SystemExit(f"No SQL files found in {SQL_DIR}")

    if not args.no_start:
        result = compose("up", "-d", "rag-postgres", check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stdout)
        print(result.stdout.strip())

    wait_for_postgres(args.timeout)

    for sql_file in sql_files:
        apply_sql_file(sql_file)

    result = compose(
        "exec",
        "-T",
        "rag-postgres",
        "psql",
        "-U",
        "sl_legal",
        "-d",
        "sl_legal_assist",
        "-At",
        "-c",
        "SELECT version || ': ' || description FROM schema_migrations ORDER BY version;",
    )
    print("schema_migrations:")
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
