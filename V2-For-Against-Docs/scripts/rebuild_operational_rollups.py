#!/usr/bin/env python3
"""Rebuild daily operational metric rollups for compliance reporting."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.db import LegalWorkspaceRepository, session_scope  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild daily operational metric rollups.")
    parser.add_argument(
        "--date",
        default=(date.today() - timedelta(days=1)).isoformat(),
        help="Rollup date in YYYY-MM-DD format. Defaults to yesterday.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rollup_date = date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit("--date must be in YYYY-MM-DD format") from exc

    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        result = repo.rebuild_daily_operational_rollups(rollup_date=rollup_date)
        rows = repo.list_operational_metric_rollups(rollup_date=rollup_date)

    print(
        json.dumps(
            {
                "rollup_date": result.rollup_date.isoformat(),
                "source": result.source,
                "upserted_count": result.upserted_count,
                "rows": [
                    {
                        "metric_name": row["metric_name"],
                        "source": row["source"],
                        "labels": row["labels"],
                        "metric_value": row["metric_value"],
                    }
                    for row in rows
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
