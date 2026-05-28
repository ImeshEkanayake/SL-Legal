#!/usr/bin/env python3
"""Validate production invariants for the local RAG corpus and workspace data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


ZERO_COUNT_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "documents_without_pages",
        """
        SELECT count(*)
        FROM documents d
        WHERE EXISTS (
            SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id
        )
          AND NOT EXISTS (
            SELECT 1 FROM pages p WHERE p.document_id = d.document_id
        )
        """,
    ),
    (
        "documents_without_text_pages",
        """
        SELECT count(*)
        FROM documents d
        WHERE EXISTS (
            SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id
        )
          AND NOT EXISTS (
            SELECT 1
            FROM pages p
            WHERE p.document_id = d.document_id
              AND length(trim(p.text)) > 0
        )
        """,
    ),
    (
        "documents_without_chunks",
        """
        SELECT count(*)
        FROM documents d
        WHERE EXISTS (
            SELECT 1
            FROM pages p
            WHERE p.document_id = d.document_id
              AND length(trim(p.text)) > 0
        )
          AND NOT EXISTS (
            SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id
        )
        """,
    ),
    (
        "chunked_documents_without_text_pages",
        """
        SELECT count(DISTINCT rc.document_id)
        FROM retrieval_chunks rc
        WHERE NOT EXISTS (
            SELECT 1
            FROM pages p
            WHERE p.document_id = rc.document_id
              AND length(trim(p.text)) > 0
        )
        """,
    ),
    (
        "chunks_with_empty_text",
        "SELECT count(*) FROM retrieval_chunks WHERE length(trim(chunk_text)) = 0",
    ),
    (
        "chunks_missing_citation",
        "SELECT count(*) FROM retrieval_chunks WHERE citation IS NULL OR length(trim(citation)) = 0",
    ),
    (
        "chunks_missing_required_metadata",
        """
        SELECT count(*)
        FROM retrieval_chunks
        WHERE length(trim(document_id)) = 0
           OR length(trim(source_id)) = 0
           OR length(trim(document_type)) = 0
           OR length(trim(title)) = 0
           OR authority_level IS NULL
           OR token_estimate <= 0
        """,
    ),
    (
        "chunks_with_invalid_page_anchor",
        """
        SELECT count(*)
        FROM retrieval_chunks rc
        WHERE rc.page_start IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM pages p
            WHERE p.document_id = rc.document_id
              AND p.page_number BETWEEN rc.page_start AND COALESCE(rc.page_end, rc.page_start)
              AND length(trim(p.text)) > 0
          )
        """,
    ),
    (
        "active_research_packs_without_items",
        """
        SELECT count(*)
        FROM research_packs rp
        WHERE rp.status IN ('complete', 'active')
          AND NOT EXISTS (
            SELECT 1 FROM research_pack_items rpi WHERE rpi.pack_id = rp.pack_id
          )
        """,
    ),
    (
        "active_case_packs_with_inactive_pack",
        """
        SELECT count(*)
        FROM case_research_packs crp
        JOIN research_packs rp ON rp.pack_id = crp.pack_id
        WHERE crp.status = 'active'
          AND rp.status NOT IN ('complete', 'active')
        """,
    ),
    (
        "supported_claims_without_citations",
        """
        SELECT count(*)
        FROM legal_claims lc
        WHERE lc.support_status = 'supported'
          AND NOT EXISTS (
            SELECT 1 FROM legal_claim_citations lcc WHERE lcc.claim_id = lc.claim_id
          )
        """,
    ),
    (
        "documents_without_primary_file_asset",
        """
        SELECT count(*)
        FROM documents d
        WHERE NOT EXISTS (
            SELECT 1
            FROM file_assets fa
            WHERE fa.document_id = d.document_id
              AND fa.asset_kind = 'original'
              AND fa.is_primary = true
        )
        """,
    ),
    (
        "documents_without_object_storage_key",
        """
        SELECT count(*)
        FROM documents
        WHERE object_storage_provider IS NULL
           OR object_storage_bucket IS NULL
           OR object_storage_key IS NULL
           OR primary_file_asset_id IS NULL
        """,
    ),
    (
        "documents_without_original_digest",
        """
        SELECT count(*)
        FROM documents d
        WHERE NOT EXISTS (
            SELECT 1
            FROM document_digests dd
            WHERE dd.document_id = d.document_id
              AND dd.digest_type = 'original_file'
              AND dd.algorithm = 'sha256'
        )
        """,
    ),
    (
        "documents_with_text_pages_without_text_version",
        """
        SELECT count(*)
        FROM documents d
        WHERE EXISTS (
            SELECT 1
            FROM pages p
            WHERE p.document_id = d.document_id
              AND length(trim(p.text)) > 0
        )
          AND NOT EXISTS (
            SELECT 1
            FROM document_text_versions dtv
            WHERE dtv.document_id = d.document_id
              AND dtv.version_label = 'current-pages-v1'
        )
        """,
    ),
    (
        "text_versions_without_text_asset",
        """
        SELECT count(*)
        FROM document_text_versions
        WHERE text_asset_id IS NULL
        """,
    ),
    (
        "text_versions_without_text_digest",
        """
        SELECT count(*)
        FROM document_text_versions dtv
        WHERE NOT EXISTS (
            SELECT 1
            FROM document_digests dd
            WHERE dd.text_version_id = dtv.text_version_id
              AND dd.digest_type = 'extracted_full_text'
              AND dd.algorithm = 'sha256'
        )
        """,
    ),
)


@dataclass(frozen=True)
class HealthFailure:
    check: str
    value: object
    expected: object


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--min-documents", type=int, default=0)
    parser.add_argument("--min-pages", type=int, default=0)
    parser.add_argument("--min-chunks", type=int, default=0)
    parser.add_argument("--hash-check-limit", type=int, default=0, help="Maximum chunks to hash-check. 0 checks all chunks.")
    parser.add_argument("--skip-local-files", action="store_true")
    parser.add_argument("--require-search-indexes", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def scalar(cursor: Any, sql: str, params: dict[str, Any] | None = None) -> int:
    cursor.execute(sql, params or {})
    value = cursor.fetchone()[0]
    return int(value or 0)


def base_counts(cursor: Any) -> dict[str, int]:
    return {
        "documents": scalar(cursor, "SELECT count(*) FROM documents"),
        "pages": scalar(cursor, "SELECT count(*) FROM pages"),
        "retrieval_chunks": scalar(cursor, "SELECT count(*) FROM retrieval_chunks"),
        "chunked_documents": scalar(cursor, "SELECT count(DISTINCT document_id) FROM retrieval_chunks"),
        "file_assets": scalar(cursor, "SELECT count(*) FROM file_assets"),
        "original_file_assets": scalar(cursor, "SELECT count(*) FROM file_assets WHERE asset_kind = 'original'"),
        "asset_tracked_documents": scalar(cursor, "SELECT count(*) FROM documents WHERE primary_file_asset_id IS NOT NULL"),
        "documents_with_pages": scalar(cursor, "SELECT count(DISTINCT document_id) FROM pages"),
        "documents_with_text_pages": scalar(
            cursor,
            """
            SELECT count(DISTINCT document_id)
            FROM pages
            WHERE length(trim(text)) > 0
            """,
        ),
        "document_text_versions": scalar(cursor, "SELECT count(*) FROM document_text_versions"),
        "document_digests": scalar(cursor, "SELECT count(*) FROM document_digests"),
        "case_document_relevance": scalar(cursor, "SELECT count(*) FROM case_document_relevance"),
    }


def zero_count_results(cursor: Any) -> dict[str, int]:
    return {name: scalar(cursor, sql) for name, sql in ZERO_COUNT_CHECKS}


def missing_local_files(cursor: Any) -> list[str]:
    cursor.execute(
        """
        SELECT document_id, local_path
        FROM documents
        WHERE local_path IS NOT NULL
          AND length(trim(local_path)) > 0
        ORDER BY document_id
        """
    )
    missing: list[str] = []
    for document_id, local_path in cursor.fetchall():
        if not resolve_local_path(str(local_path)).is_file():
            missing.append(str(document_id))
    return missing


def invalid_chunk_hashes(cursor: Any, *, limit: int) -> list[str]:
    query = """
        SELECT chunk_id, chunk_text, text_hash
        FROM retrieval_chunks
        ORDER BY chunk_id
    """
    if limit > 0:
        query += " LIMIT %(limit)s"
        cursor.execute(query, {"limit": limit})
    else:
        cursor.execute(query)

    invalid: list[str] = []
    for chunk_id, chunk_text, text_hash in cursor.fetchall():
        expected = hashlib.sha256(str(chunk_text or "").encode("utf-8")).hexdigest()
        if str(text_hash or "") != expected:
            invalid.append(str(chunk_id))
    return invalid


def evaluate_minimums(counts: dict[str, int], args: argparse.Namespace) -> list[HealthFailure]:
    failures: list[HealthFailure] = []
    minimums = {
        "documents": args.min_documents,
        "pages": args.min_pages,
        "retrieval_chunks": args.min_chunks,
    }
    for key, minimum in minimums.items():
        if counts[key] < minimum:
            failures.append(HealthFailure(check=f"minimum_{key}", value=counts[key], expected=f">={minimum}"))
    return failures


def evaluate_zero_counts(results: dict[str, int]) -> list[HealthFailure]:
    return [
        HealthFailure(check=name, value=value, expected=0)
        for name, value in results.items()
        if value != 0
    ]


def run_index_consistency(args: argparse.Namespace) -> dict[str, object]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "check_rag_index_consistency.py"),
        "--dsn",
        args.dsn,
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        return {"status": "failed", "output": completed.stdout.strip()}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"raw_output": completed.stdout.strip()}
    payload["status"] = "passed"
    return payload


def build_health_report(args: argparse.Namespace) -> tuple[dict[str, object], list[HealthFailure]]:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    failures: list[HealthFailure] = []
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as connection:
        with connection.cursor() as cursor:
            counts = base_counts(cursor)
            zero_results = zero_count_results(cursor)
            failures.extend(evaluate_minimums(counts, args))
            failures.extend(evaluate_zero_counts(zero_results))

            invalid_hashes = invalid_chunk_hashes(cursor, limit=args.hash_check_limit)
            if invalid_hashes:
                failures.append(
                    HealthFailure(
                        check="chunks_with_invalid_text_hash",
                        value=invalid_hashes[:20],
                        expected="sha256(chunk_text)",
                    )
                )

            missing_files: list[str] = []
            if not args.skip_local_files:
                missing_files = missing_local_files(cursor)
                if missing_files:
                    failures.append(
                        HealthFailure(
                            check="documents_with_missing_local_file",
                            value=missing_files[:20],
                            expected="local file exists",
                        )
                    )

    search_index_consistency: dict[str, object] | None = None
    if args.require_search_indexes:
        search_index_consistency = run_index_consistency(args)
        if search_index_consistency.get("status") != "passed":
            failures.append(
                HealthFailure(
                    check="search_index_consistency",
                    value=search_index_consistency.get("output", search_index_consistency),
                    expected="Postgres/OpenSearch/Qdrant chunk IDs match",
                )
            )

    report: dict[str, object] = {
        "counts": counts,
        "zero_count_checks": zero_results,
        "invalid_chunk_hashes": invalid_hashes[:20],
        "missing_local_files": missing_files[:20] if not args.skip_local_files else "not_checked",
        "search_index_consistency": search_index_consistency or "not_required",
        "status": "failed" if failures else "passed",
        "failures": [failure.__dict__ for failure in failures],
    }
    return report, failures


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report, failures = build_health_report(args)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if args.allow_failures or not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
