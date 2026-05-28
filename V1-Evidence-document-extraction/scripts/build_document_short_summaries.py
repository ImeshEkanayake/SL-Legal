#!/usr/bin/env python3
"""Build document-level short summaries for low-cost search prefiltering."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_GENERATION_METHOD = "deterministic_spread_10pct_v2"
ELIGIBLE_EXTRACTION_STATUSES = ("text_extracted", "translated")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write summaries. Omit for dry-run counts.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--limit", type=int, default=0, help="Maximum text versions to summarize. 0 means all missing summaries.")
    parser.add_argument("--target-ratio", type=float, default=0.10, help="Target summary size as fraction of source full text.")
    parser.add_argument("--min-chars", type=int, default=1200)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--summary-type", default="extractive_10pct")
    parser.add_argument("--generation-method", default=DEFAULT_GENERATION_METHOD)
    parser.add_argument(
        "--min-text-quality-score",
        type=float,
        default=0.10,
        help="Discard lower-quality extracts, including tiny OCR artifacts. Use 0 to disable.",
    )
    parser.add_argument(
        "--include-ocr-required",
        action="store_true",
        help="Include documents still marked OCR-required. Default discards them.",
    )
    parser.add_argument(
        "--replace-summary-type",
        action="store_true",
        help="After inserting this method, delete ineligible or older summaries for the same summary_type.",
    )
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if not 0 < args.target_ratio <= 1:
        parser.error("--target-ratio must be > 0 and <= 1")
    if args.min_chars < 0 or args.max_chars < 1 or args.min_chars > args.max_chars:
        parser.error("--min-chars and --max-chars must define a valid range")
    if args.min_text_quality_score < 0 or args.min_text_quality_score > 1:
        parser.error("--min-text-quality-score must be between 0 and 1")
    if args.replace_summary_type and args.limit:
        parser.error("--replace-summary-type requires --limit 0 so the replacement is complete")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def eligibility_sql(*, dtv_alias: str = "dtv", document_alias: str = "d") -> str:
    return f"""
        {dtv_alias}.text_origin = 'source'
        AND {dtv_alias}.version_label = 'current-pages-v1'
        AND {dtv_alias}.char_count > 0
        AND {dtv_alias}.full_text IS NOT NULL
        AND {document_alias}.acquisition_status = 'downloaded'
        AND {document_alias}.extraction_status = ANY(%(eligible_extraction_statuses)s)
        AND (%(include_ocr_required)s OR coalesce({document_alias}.ocr_required, false) IS FALSE)
        AND coalesce({document_alias}.text_quality_score, 0) >= %(min_text_quality_score)s
    """


def query_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "summary_type": args.summary_type,
        "generation_method": args.generation_method,
        "eligible_extraction_statuses": list(ELIGIBLE_EXTRACTION_STATUSES),
        "include_ocr_required": args.include_ocr_required,
        "min_text_quality_score": args.min_text_quality_score,
    }


def dry_run_summary(conn: Any, args: argparse.Namespace) -> dict[str, int]:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                count(*) FILTER (WHERE {eligibility_sql()}) AS eligible_text_versions,
                count(*) FILTER (
                    WHERE {eligibility_sql()}
                      AND ds.summary_id IS NULL
                ) AS missing_summaries,
                count(ds.summary_id) FILTER (WHERE {eligibility_sql()}) AS existing_summaries,
                count(ds.summary_id) FILTER (WHERE NOT ({eligibility_sql()})) AS ineligible_summaries
            FROM document_text_versions dtv
            JOIN documents d ON d.document_id = dtv.document_id
            LEFT JOIN document_summaries ds
              ON ds.text_version_id = dtv.text_version_id
             AND ds.summary_type = %(summary_type)s
             AND ds.generation_method = %(generation_method)s
            """,
            query_params(args),
        )
        row = cursor.fetchone()
    return {
        "eligible_text_versions": int(row[0] or 0),
        "missing_summaries": int(row[1] or 0),
        "existing_summaries": int(row[2] or 0),
        "ineligible_summaries": int(row[3] or 0),
    }


def build_summaries(conn: Any, args: argparse.Namespace) -> int:
    limit_sql = "LIMIT %(limit)s" if args.limit else ""
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            WITH candidates AS (
                SELECT
                    dtv.document_id,
                    dtv.text_version_id,
                    dtv.language,
                    dtv.text_hash,
                    dtv.full_text,
                    char_length(dtv.full_text) AS source_char_count,
                    LEAST(
                        char_length(dtv.full_text),
                        GREATEST(
                            %(min_chars)s,
                            LEAST(%(max_chars)s, CEIL(char_length(dtv.full_text) * %(target_ratio)s)::int)
                        )
                    ) AS summary_budget
                FROM document_text_versions dtv
                JOIN documents d ON d.document_id = dtv.document_id
                LEFT JOIN document_summaries ds
                  ON ds.text_version_id = dtv.text_version_id
                 AND ds.summary_type = %(summary_type)s
                 AND ds.generation_method = %(generation_method)s
                WHERE {eligibility_sql()}
                  AND ds.summary_id IS NULL
                ORDER BY dtv.created_at ASC, dtv.text_version_id ASC
                {limit_sql}
            ),
            summaries AS (
                SELECT
                    'docsum_' || md5(text_version_id || ':' || %(summary_type)s || ':' || %(generation_method)s) AS summary_id,
                    document_id,
                    text_version_id,
                    language,
                    text_hash,
                    CASE
                        WHEN summary_budget + 18 >= source_char_count THEN full_text
                        ELSE concat_ws(
                            E'\n\n[...]\n\n',
                            left(full_text, GREATEST(1, floor(summary_budget / 3.0)::int)),
                            substr(
                                full_text,
                                GREATEST(
                                    1,
                                    floor((source_char_count / 2.0) - (summary_budget / 6.0))::int
                                ),
                                GREATEST(1, floor(summary_budget / 3.0)::int)
                            ),
                            right(
                                full_text,
                                GREATEST(
                                    1,
                                    summary_budget - (2 * GREATEST(1, floor(summary_budget / 3.0)::int))
                                )
                            )
                        )
                    END AS summary_text,
                    source_char_count
                FROM candidates
            ),
            normalized_summaries AS (
                SELECT
                    summary_id,
                    document_id,
                    text_version_id,
                    language,
                    text_hash,
                    summary_text,
                    char_length(summary_text) AS summary_char_count,
                    source_char_count
                FROM summaries
            )
            INSERT INTO document_summaries (
                summary_id, document_id, text_version_id, summary_type, language,
                source_text_hash, summary_text, char_count, source_char_count,
                compression_ratio, generation_method, metadata
            )
            SELECT
                summary_id, document_id, text_version_id, %(summary_type)s, language,
                text_hash, summary_text, summary_char_count, source_char_count,
                CASE
                    WHEN source_char_count = 0 THEN 0
                    ELSE LEAST(1, round((summary_char_count::numeric / source_char_count::numeric), 6))
                END,
                %(generation_method)s,
                jsonb_build_object(
                    'target_ratio', %(target_ratio)s,
                    'min_chars', %(min_chars)s,
                    'max_chars', %(max_chars)s,
                    'method_note', 'deterministic extractive 10 percent spread summary for document-level search prefiltering',
                    'excluded_ocr_required', NOT %(include_ocr_required)s,
                    'min_text_quality_score', %(min_text_quality_score)s
                )
            FROM normalized_summaries
            ON CONFLICT (text_version_id, summary_type, generation_method)
            DO NOTHING
            """,
            query_params(args)
            | {
                "limit": args.limit,
                "target_ratio": args.target_ratio,
                "min_chars": args.min_chars,
                "max_chars": args.max_chars,
            },
        )
        inserted = cursor.rowcount
    conn.commit()
    return int(inserted)


def prune_summaries(conn: Any, args: argparse.Namespace) -> int:
    """Remove stale or ineligible derived summaries for this summary type."""

    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM document_summaries ds
            USING document_text_versions dtv, documents d
            WHERE ds.text_version_id = dtv.text_version_id
              AND d.document_id = dtv.document_id
              AND ds.summary_type = %(summary_type)s
              AND (
                    ds.generation_method <> %(generation_method)s
                    OR NOT ({eligibility_sql()})
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
        before = dry_run_summary(conn, args)
        inserted = build_summaries(conn, args) if args.execute else 0
        pruned = prune_summaries(conn, args) if args.execute and args.replace_summary_type else 0
        after = dry_run_summary(conn, args)
    print(
        json.dumps(
            {
                "execute": args.execute,
                "before": before,
                "inserted": inserted,
                "pruned": pruned,
                "after": after,
                "summary_type": args.summary_type,
                "generation_method": args.generation_method,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
