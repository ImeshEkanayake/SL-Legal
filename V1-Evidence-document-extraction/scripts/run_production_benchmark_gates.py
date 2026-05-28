#!/usr/bin/env python3
"""Run production readiness gates for corpus search and workspace data."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--query", default="industrial disputes trade union bargaining")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--min-documents", type=int, default=100000)
    parser.add_argument("--min-chunks", type=int, default=1000000)
    parser.add_argument("--min-summary-coverage", type=float, default=0.95)
    parser.add_argument("--max-summary-search-ms", type=float, default=750)
    parser.add_argument("--max-chunk-search-ms", type=float, default=1500)
    parser.add_argument("--allow-failures", action="store_true")
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if not 0 <= args.min_summary_coverage <= 1:
        parser.error("--min-summary-coverage must be between 0 and 1")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return float(statistics.quantiles(values, n=20, method="inclusive")[18])


def timed_query(cursor: Any, sql: str, params: dict[str, Any], iterations: int) -> dict[str, float]:
    durations: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        cursor.execute(sql, params)
        cursor.fetchall()
        durations.append((time.perf_counter() - started) * 1000)
    return {
        "min_ms": round(min(durations), 3),
        "median_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile_95(durations), 3),
        "max_ms": round(max(durations), 3),
    }


def corpus_counts(cursor: Any) -> dict[str, int | float]:
    cursor.execute(
        """
        WITH counts AS (
            SELECT
                (SELECT count(*) FROM documents) AS documents,
                (SELECT count(*) FROM retrieval_chunks) AS chunks,
                (SELECT count(*) FROM retrieval_chunks WHERE text_version_id IS NULL) AS chunks_missing_text_version,
                (SELECT count(*) FROM document_text_versions WHERE char_count > 0) AS eligible_text_versions,
                (SELECT count(*) FROM document_summaries WHERE summary_type = 'extractive_10pct') AS short_summaries,
                (SELECT count(*) FROM case_document_relevance) AS relevance_rows
        )
        SELECT *
        FROM counts
        """
    )
    row = cursor.fetchone()
    eligible = int(row[3] or 0)
    summaries = int(row[4] or 0)
    return {
        "documents": int(row[0] or 0),
        "chunks": int(row[1] or 0),
        "chunks_missing_text_version": int(row[2] or 0),
        "eligible_text_versions": eligible,
        "short_summaries": summaries,
        "summary_coverage": round(summaries / eligible, 6) if eligible else 1.0,
        "relevance_rows": int(row[5] or 0),
    }


def evaluate_thresholds(counts: dict[str, int | float], timings: dict[str, dict[str, float]], args: argparse.Namespace) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    checks = [
        ("documents", counts["documents"], ">=", args.min_documents),
        ("chunks", counts["chunks"], ">=", args.min_chunks),
        ("chunks_missing_text_version", counts["chunks_missing_text_version"], "==", 0),
        ("summary_coverage", counts["summary_coverage"], ">=", args.min_summary_coverage),
        ("summary_search_p95_ms", timings["summary_search"]["p95_ms"], "<=", args.max_summary_search_ms),
        ("chunk_search_p95_ms", timings["chunk_search"]["p95_ms"], "<=", args.max_chunk_search_ms),
    ]
    for name, value, operator, expected in checks:
        passed = value >= expected if operator == ">=" else value <= expected if operator == "<=" else value == expected
        if not passed:
            failures.append({"check": name, "value": value, "operator": operator, "expected": expected})
    return failures


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        with conn.cursor() as cursor:
            counts = corpus_counts(cursor)
            timings = {
                "summary_search": timed_query(
                    cursor,
                    """
                    SELECT document_id
                    FROM document_summaries
                    WHERE to_tsvector('simple', summary_text) @@ plainto_tsquery('simple', %(query)s)
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    {"query": args.query},
                    args.iterations,
                ),
                "chunk_search": timed_query(
                    cursor,
                    """
                    SELECT chunk_id
                    FROM retrieval_chunks
                    WHERE chunk_text ILIKE %(pattern)s
                    LIMIT 20
                    """,
                    {"pattern": f"%{args.query.split()[0]}%"},
                    args.iterations,
                ),
            }
    failures = evaluate_thresholds(counts, timings, args)
    result = {"status": "pass" if not failures else "fail", "counts": counts, "timings": timings, "failures": failures}
    print(json.dumps(result, indent=2))
    return 0 if not failures or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
