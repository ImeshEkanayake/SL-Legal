#!/usr/bin/env python3
"""Export PostgreSQL retrieval chunks to the canonical JSONL index format."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "indexes" / "rag_chunks_from_postgres_clean.jsonl"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def serialize_chunk(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["quality_flags"] = list(payload.get("quality_flags") or [])
    payload["metadata"] = dict(payload.get("metadata") or {})
    if payload.get("year") is None:
        payload["year"] = ""
    return payload


def export_chunks(conn: Any, output_path: Path, batch_size: int) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    query = """
        SELECT
            chunk_id, document_id, source_id, document_type, title, year,
            authority_level, page_start, page_end, chunk_index, chunk_text,
            token_estimate, language, citation, source_url, local_path,
            text_hash, quality_flags, metadata, text_version_id, text_origin,
            source_language, translated_from_language, translation_review_status
        FROM retrieval_chunks
        ORDER BY chunk_id
    """
    with conn.cursor(name="export_rag_chunks") as cursor, output_path.open("w", encoding="utf-8") as handle:
        cursor.itersize = batch_size
        cursor.execute(query)
        column_names = [description.name for description in cursor.description]
        for row in cursor:
            handle.write(json.dumps(serialize_chunk(dict(zip(column_names, row))), ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        exported = export_chunks(conn, output_path, args.batch_size)
    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "chunks_exported": exported,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
