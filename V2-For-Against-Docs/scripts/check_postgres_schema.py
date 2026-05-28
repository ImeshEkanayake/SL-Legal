#!/usr/bin/env python3
"""Print a compact PostgreSQL schema health report."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.rag.yml"


SCHEMA_QUERY = r"""
WITH tables AS (
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
),
indexes AS (
    SELECT schemaname, tablename, indexname
    FROM pg_indexes
    WHERE schemaname = 'public'
)
SELECT
    (SELECT count(*) FROM tables) AS table_count,
    (SELECT count(*) FROM indexes) AS index_count,
    (SELECT string_agg(version, ', ' ORDER BY version) FROM schema_migrations) AS migrations;
"""


TABLE_QUERY = r"""
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
"""


def compose_psql(query: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
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
            query,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout)
    return result.stdout.strip()


def main(_: list[str]) -> int:
    print("schema_health:")
    print(compose_psql(SCHEMA_QUERY))
    print("\ntables:")
    print(compose_psql(TABLE_QUERY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
