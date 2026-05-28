#!/usr/bin/env python3
"""Persist extracted/OCR page text into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.db import session_scope  # noqa: E402
from sl_legal_rag.page_persistence import load_pages_from_manifest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load extracted/OCR page text into Postgres.")
    parser.add_argument("--manifest", default=str(PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"))
    parser.add_argument("--ocr-register", default=str(PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"))
    parser.add_argument("--document-id", action="append", help="Limit to one or more document IDs.")
    parser.add_argument("--source-id", action="append", help="Limit to one or more source IDs.")
    parser.add_argument("--limit-documents", type=int, default=0, help="Maximum documents with pages to load. 0 means no limit.")
    parser.add_argument(
        "--allow-missing-documents",
        action="store_true",
        help="Attempt inserts even if documents are not already present in Postgres.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with session_scope() as session:
        result = load_pages_from_manifest(
            session=session,
            manifest_path=Path(args.manifest),
            ocr_register_path=Path(args.ocr_register),
            document_ids=set(args.document_id or []),
            source_ids=set(args.source_id or []),
            limit_documents=args.limit_documents,
            require_existing_documents=not args.allow_missing_documents,
        )
    print(json.dumps(result.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
