#!/usr/bin/env python3
"""Backfill page-level source anchors for persisted research pack items."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.db import LegalWorkspaceRepository, session_scope  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill source anchors for research pack items.")
    parser.add_argument("--pack-id", help="Limit backfill to one pack.")
    parser.add_argument("--limit-items", type=int, default=0, help="Maximum pack items to process. 0 means no limit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with session_scope() as session:
        result = LegalWorkspaceRepository(session).backfill_source_anchors(
            pack_id=args.pack_id,
            limit_items=args.limit_items,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
