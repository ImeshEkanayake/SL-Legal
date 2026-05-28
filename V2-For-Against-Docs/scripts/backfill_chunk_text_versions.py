#!/usr/bin/env python3
"""Backfill retrieval_chunks.text_version_id from document_text_versions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write updates. Omit for a dry-run summary.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--limit", type=int, default=0, help="Optional dry-run/report limit by document count. 0 means all.")
    parser.add_argument("--batch-size", type=int, default=50000, help="Chunks to update per transaction.")
    parser.add_argument("--progress-every", type=int, default=1, help="Print progress every N committed batches. 0 disables progress.")
    args = parser.parse_args(argv)
    args.selected_document_ids = []
    args.document_scope_resolved = False
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.batch_size <= 0:
        parser.error("--batch-size must be > 0")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def document_filter(args: argparse.Namespace, alias: str) -> tuple[str, list[Any]]:
    selected_document_ids = getattr(args, "selected_document_ids", [])
    if selected_document_ids:
        return f" AND {alias}.document_id = ANY(%s)", [selected_document_ids]
    if getattr(args, "document_scope_resolved", False) and args.limit:
        return " AND false", []
    if args.document_id:
        return f" AND {alias}.document_id = ANY(%s)", [args.document_id]
    if args.limit:
        raise RuntimeError("document scope must be resolved before applying --limit")
    return "", []


def resolve_document_scope(conn: Any, args: argparse.Namespace) -> None:
    if args.document_id:
        args.selected_document_ids = list(dict.fromkeys(args.document_id))
        args.document_scope_resolved = True
        return
    if not args.limit:
        args.document_scope_resolved = True
        return
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT document_id
            FROM retrieval_chunks
            WHERE text_version_id IS NULL
            ORDER BY document_id
            LIMIT %s
            """,
            [args.limit],
        )
        args.selected_document_ids = [row[0] for row in cursor.fetchall()]
    args.document_scope_resolved = True


def summarize(conn: Any, args: argparse.Namespace) -> dict[str, int]:
    where_sql, params = document_filter(args, "rc")
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            WITH preferred_text_versions AS (
                SELECT DISTINCT ON (document_id)
                    document_id, text_version_id, text_origin
                FROM document_text_versions
                WHERE text_origin = 'source'
                ORDER BY
                    document_id,
                    CASE WHEN version_label = 'current-pages-v1' THEN 0 ELSE 1 END,
                    created_at DESC,
                    text_version_id DESC
            )
            SELECT
                count(*) FILTER (WHERE rc.text_version_id IS NULL) AS chunks_missing_text_version,
                count(*) FILTER (WHERE rc.text_version_id IS NULL AND ptv.text_version_id IS NOT NULL) AS chunks_backfillable,
                count(DISTINCT rc.document_id) FILTER (WHERE rc.text_version_id IS NULL) AS documents_missing_text_version,
                count(DISTINCT rc.document_id) FILTER (WHERE rc.text_version_id IS NULL AND ptv.text_version_id IS NOT NULL) AS documents_backfillable
            FROM retrieval_chunks rc
            LEFT JOIN preferred_text_versions ptv ON ptv.document_id = rc.document_id
            WHERE true {where_sql}
            """,
            params,
        )
        row = cursor.fetchone()
    return {
        "chunks_missing_text_version": int(row[0] or 0),
        "chunks_backfillable": int(row[1] or 0),
        "documents_missing_text_version": int(row[2] or 0),
        "documents_backfillable": int(row[3] or 0),
    }


def create_preferred_text_versions_temp(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TEMP TABLE tmp_preferred_text_versions AS
            SELECT DISTINCT ON (document_id)
                document_id, text_version_id, text_origin, language,
                source_language, translated_from_language,
                translation_review_status
            FROM document_text_versions
            WHERE text_origin = 'source'
            ORDER BY
                document_id,
                CASE WHEN version_label = 'current-pages-v1' THEN 0 ELSE 1 END,
                created_at DESC,
                text_version_id DESC
            """
        )
        cursor.execute("CREATE INDEX ON tmp_preferred_text_versions(document_id)")
    conn.commit()


def backfill_batch(conn: Any, args: argparse.Namespace) -> int:
    where_sql, params = document_filter(args, "rc")
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            WITH batch AS (
                SELECT rc.chunk_id
                FROM retrieval_chunks rc
                JOIN tmp_preferred_text_versions ptv ON ptv.document_id = rc.document_id
                WHERE rc.text_version_id IS NULL
                  {where_sql}
                ORDER BY rc.chunk_id
                LIMIT %s
            )
            UPDATE retrieval_chunks rc
            SET text_version_id = ptv.text_version_id,
                text_origin = ptv.text_origin,
                source_language = COALESCE(ptv.source_language, ptv.language, rc.source_language),
                translated_from_language = ptv.translated_from_language,
                translation_review_status = ptv.translation_review_status
            FROM batch, tmp_preferred_text_versions ptv
            WHERE rc.chunk_id = batch.chunk_id
              AND ptv.document_id = rc.document_id
            """,
            [*params, args.batch_size],
        )
        updated = cursor.rowcount
    conn.commit()
    return int(updated)


def backfill(conn: Any, args: argparse.Namespace) -> int:
    create_preferred_text_versions_temp(conn)
    updated_total = 0
    batch_number = 0
    while True:
        updated = backfill_batch(conn, args)
        if updated == 0:
            break
        updated_total += updated
        batch_number += 1
        if args.progress_every and batch_number % args.progress_every == 0:
            print(json.dumps({"event": "progress", "batch": batch_number, "updated_chunks": updated_total}), flush=True)
    return updated_total


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        resolve_document_scope(conn, args)
        before = summarize(conn, args)
        updated = backfill(conn, args) if args.execute else 0
        after = summarize(conn, args)

    print(
        json.dumps(
            {
                "execute": args.execute,
                "before": before,
                "updated_chunks": updated,
                "after": after,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
