#!/usr/bin/env python3
"""Remove retrieval chunks for documents excluded from the searchable corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
ELIGIBLE_EXTRACTION_STATUSES = ("text_extracted", "translated")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Delete excluded chunks. Omit for dry-run counts.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument(
        "--min-text-quality-score",
        type=float,
        default=0.10,
        help="Keep only chunks whose parent document quality is at or above this score.",
    )
    parser.add_argument(
        "--include-ocr-required",
        action="store_true",
        help="Keep chunks for documents still marked OCR-required. Default discards them.",
    )
    args = parser.parse_args(argv)
    if args.min_text_quality_score < 0 or args.min_text_quality_score > 1:
        parser.error("--min-text-quality-score must be between 0 and 1")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def eligibility_sql(document_alias: str = "d") -> str:
    return f"""
        {document_alias}.acquisition_status = 'downloaded'
        AND {document_alias}.extraction_status = ANY(%(eligible_extraction_statuses)s)
        AND (%(include_ocr_required)s OR coalesce({document_alias}.ocr_required, false) IS FALSE)
        AND coalesce({document_alias}.text_quality_score, 0) >= %(min_text_quality_score)s
    """


def query_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "eligible_extraction_statuses": list(ELIGIBLE_EXTRACTION_STATUSES),
        "include_ocr_required": args.include_ocr_required,
        "min_text_quality_score": args.min_text_quality_score,
    }


def chunk_counts(conn: Any, args: argparse.Namespace) -> dict[str, int]:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                count(*) AS total_chunks,
                count(DISTINCT rc.document_id) AS total_documents,
                count(*) FILTER (WHERE {eligibility_sql()}) AS kept_chunks,
                count(DISTINCT rc.document_id) FILTER (WHERE {eligibility_sql()}) AS kept_documents,
                count(*) FILTER (WHERE NOT ({eligibility_sql()})) AS discarded_chunks,
                count(DISTINCT rc.document_id) FILTER (WHERE NOT ({eligibility_sql()})) AS discarded_documents,
                count(*) FILTER (
                    WHERE NOT ({eligibility_sql()})
                      AND EXISTS (
                          SELECT 1 FROM research_pack_items rpi WHERE rpi.chunk_id = rc.chunk_id
                      )
                ) AS referenced_discarded_chunks,
                count(*) FILTER (
                    WHERE NOT ({eligibility_sql()})
                      AND NOT EXISTS (
                          SELECT 1 FROM research_pack_items rpi WHERE rpi.chunk_id = rc.chunk_id
                      )
                ) AS prunable_discarded_chunks
            FROM retrieval_chunks rc
            JOIN documents d ON d.document_id = rc.document_id
            """,
            query_params(args),
        )
        row = cursor.fetchone()
    return {
        "total_chunks": int(row[0] or 0),
        "total_documents": int(row[1] or 0),
        "kept_chunks": int(row[2] or 0),
        "kept_documents": int(row[3] or 0),
        "discarded_chunks": int(row[4] or 0),
        "discarded_documents": int(row[5] or 0),
        "referenced_discarded_chunks": int(row[6] or 0),
        "prunable_discarded_chunks": int(row[7] or 0),
    }


def prune_chunks(conn: Any, args: argparse.Namespace) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM retrieval_chunks rc
            USING documents d
            WHERE d.document_id = rc.document_id
              AND NOT ({eligibility_sql()})
              AND NOT EXISTS (
                  SELECT 1 FROM research_pack_items rpi WHERE rpi.chunk_id = rc.chunk_id
              )
            """,
            query_params(args),
        )
        deleted = cursor.rowcount
    conn.commit()
    return int(deleted)


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        before = chunk_counts(conn, args)
        deleted = prune_chunks(conn, args) if args.execute else 0
        after = chunk_counts(conn, args)
    print(
        json.dumps(
            {
                "execute": args.execute,
                "before": before,
                "deleted": deleted,
                "after": after,
                "eligible_extraction_statuses": list(ELIGIBLE_EXTRACTION_STATUSES),
                "min_text_quality_score": args.min_text_quality_score,
                "include_ocr_required": args.include_ocr_required,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
