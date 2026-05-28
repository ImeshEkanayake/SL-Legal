#!/usr/bin/env python3
"""Prune old API rate-limit windows from PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.db import LegalWorkspaceRepository, session_scope  # noqa: E402


DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60
RETENTION_ENV = "SL_LEGAL_RATE_LIMIT_RETENTION_SECONDS"


def _default_retention_seconds() -> int:
    raw_value = os.getenv(RETENTION_ENV)
    if raw_value is None:
        return DEFAULT_RETENTION_SECONDS
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{RETENTION_ENV} must be an integer") from exc
    if value < 1:
        raise SystemExit(f"{RETENTION_ENV} must be at least 1")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune old API rate-limit windows.")
    parser.add_argument(
        "--retention-seconds",
        type=int,
        default=_default_retention_seconds(),
        help=f"Keep rows touched within this many seconds. Defaults to ${RETENTION_ENV} or 604800.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with session_scope() as session:
        result = LegalWorkspaceRepository(session).prune_expired_rate_limits(
            retention_seconds=args.retention_seconds,
        )
    print(
        json.dumps(
            {
                "retention_seconds": result.retention_seconds,
                "cutoff": result.cutoff.isoformat(),
                "deleted_count": result.deleted_count,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
