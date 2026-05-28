#!/usr/bin/env python3
"""Build full-text document versions from persisted page text.

This is intentionally separate from original-file object sync. It only reads the
canonical `pages` table, writes extracted-text objects, and records
`document_text_versions` plus `document_digests`.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from sync_corpus_assets_to_object_storage import (  # noqa: E402
    AssetCandidate,
    StorageConfig,
    build_s3_client,
    build_text_version,
    candidate_from_db_row,
    ensure_bucket,
    text_storage_key,
    upload_bytes_if_needed,
    upsert_digest,
    upsert_file_asset,
    upsert_text_version,
)


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


@dataclass
class TextVersionSyncSummary:
    candidate_count: int = 0
    processed_count: int = 0
    synced_count: int = 0
    skipped_current_count: int = 0
    skipped_no_page_text_count: int = 0
    skipped_no_source_asset_count: int = 0
    error_count: int = 0
    total_text_bytes: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: dict[str, Any]) -> None:
        self.processed_count += 1
        status = str(result["status"])
        if self.status_counts is None:
            self.status_counts = {}
        self.status_counts[status] = self.status_counts.get(status, 0) + 1
        if status == "synced":
            self.synced_count += 1
            self.total_text_bytes += int(result.get("byte_size") or 0)
        elif status == "skipped_current":
            self.skipped_current_count += 1
        elif status == "no_page_text":
            self.skipped_no_page_text_count += 1
        elif status == "missing_source_asset":
            self.skipped_no_source_asset_count += 1
        elif status == "error":
            self.error_count += 1
        if self.results_preview is None:
            self.results_preview = []
        if len(self.results_preview) < 20:
            self.results_preview.append(result)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write text assets and database rows.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--provider", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PROVIDER", "minio"))
    parser.add_argument("--endpoint-url", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"))
    parser.add_argument("--bucket", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_BUCKET", "sl-legal-corpus"))
    parser.add_argument("--region", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_REGION", "us-east-1"))
    parser.add_argument("--access-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ACCESS_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_USER", "sl_legal_minio"))
    parser.add_argument("--secret-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_SECRET_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_PASSWORD", "sl_legal_minio_dev"))
    parser.add_argument("--prefix", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PREFIX", "corpus"))
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--limit", type=int, default=0, help="Maximum candidate documents to process. 0 means no limit.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--report-path", help="Optional JSONL path for per-document results.")
    parser.add_argument("--skip-upload", action="store_true", help="Record database rows without uploading text objects.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when current-pages-v1 already has the same text hash.")
    parser.add_argument("--ingestion-run-id", help="Optional existing ingestion run ID.")
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be zero or greater")
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    args.document_ids_filter = load_document_ids(args)
    return args


def load_document_ids(args: argparse.Namespace) -> set[str]:
    document_ids = set(args.document_id or [])
    for file_name in args.document_id_file or []:
        path = Path(file_name)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            normalized = line.strip()
            if normalized and not normalized.startswith("#"):
                document_ids.add(normalized)
    return document_ids


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def build_storage_config(args: argparse.Namespace) -> StorageConfig:
    return StorageConfig(
        provider=args.provider,
        endpoint_url=args.endpoint_url,
        bucket=args.bucket,
        region=args.region,
        access_key=args.access_key,
        secret_key=args.secret_key,
        prefix=args.prefix.strip("/"),
    )


def default_ingestion_run_id(args: argparse.Namespace) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source = "all" if not args.source_id else "_".join(sorted(source.lower() for source in args.source_id))
    return f"text_version_sync_{source}_{timestamp}"


def source_label(args: argparse.Namespace) -> str:
    return ",".join(sorted(args.source_id)) if args.source_id else "ALL"


def start_ingestion_run(conn: Any, *, args: argparse.Namespace, config: StorageConfig, ingestion_run_id: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (
                ingestion_run_id, source_id, pipeline_name, pipeline_version,
                status, corpus_root, config
            )
            VALUES (
                %(ingestion_run_id)s, %(source_id)s, 'document_text_version_sync',
                '2026-05-26', 'running', %(corpus_root)s, CAST(%(config)s AS jsonb)
            )
            ON CONFLICT (ingestion_run_id) DO UPDATE SET
                status = 'running',
                error = NULL,
                completed_at = NULL,
                updated_at = now(),
                config = EXCLUDED.config
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "source_id": source_label(args),
                "corpus_root": str(PROJECT_ROOT / "data" / "raw"),
                "config": json.dumps(
                    {
                        "bucket": config.bucket,
                        "provider": config.provider,
                        "prefix": config.prefix,
                        "skip_upload": args.skip_upload,
                        "force": args.force,
                        "batch_size": args.batch_size,
                        "limit": args.limit,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: TextVersionSyncSummary) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET status = %(status)s,
                completed_at = now(),
                document_count = %(document_count)s,
                error_count = %(error_count)s,
                output = CAST(%(output)s AS jsonb),
                updated_at = now()
            WHERE ingestion_run_id = %(ingestion_run_id)s
            """,
            {
                "status": "failed" if summary.error_count else "complete",
                "document_count": summary.processed_count,
                "error_count": summary.error_count,
                "ingestion_run_id": ingestion_run_id,
                "output": json.dumps(
                    {
                        "candidate_count": summary.candidate_count,
                        "processed_count": summary.processed_count,
                        "synced_count": summary.synced_count,
                        "skipped_current_count": summary.skipped_current_count,
                        "skipped_no_page_text_count": summary.skipped_no_page_text_count,
                        "skipped_no_source_asset_count": summary.skipped_no_source_asset_count,
                        "total_text_bytes": summary.total_text_bytes,
                        "status_counts": summary.status_counts or {},
                    },
                    ensure_ascii=False,
                ),
            },
        )


def open_report(path_value: str | None) -> TextIO | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def write_report(report: TextIO | None, result: dict[str, Any]) -> None:
    if report is None:
        return
    report.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    report.flush()


def print_progress(summary: TextVersionSyncSummary, *, final: bool = False) -> None:
    print(
        json.dumps(
            {
                "event": "final" if final else "progress",
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "synced_count": summary.synced_count,
                "error_count": summary.error_count,
                "total_text_bytes": summary.total_text_bytes,
                "status_counts": summary.status_counts or {},
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def candidate_filter_sql(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    clauses = ["EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id AND length(btrim(p.text)) > 0)"]
    params: dict[str, Any] = {}
    if args.document_ids_filter:
        clauses.append("d.document_id = ANY(%(document_ids)s)")
        params["document_ids"] = sorted(args.document_ids_filter)
    if args.source_id:
        clauses.append("d.source_id = ANY(%(source_ids)s)")
        params["source_ids"] = sorted(args.source_id)
    return " AND ".join(clauses), params


def page_text_candidates(conn: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    where_sql, params = candidate_filter_sql(args)
    limit_sql = "LIMIT %(limit)s" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    query = f"""
        SELECT
            d.document_id, d.source_id, d.source_document_id, d.document_type,
            d.title, d.year, d.number, d.document_date, d.language,
            d.source_url, d.download_url, d.local_path, d.file_hash,
            d.acquisition_status, d.extraction_status, d.text_quality_score,
            d.legal_status, d.notes, d.primary_file_asset_id,
            dtv.text_hash AS existing_text_hash,
            dtv.text_asset_id AS existing_text_asset_id
        FROM documents d
        LEFT JOIN document_text_versions dtv
          ON dtv.document_id = d.document_id
         AND dtv.version_label = 'current-pages-v1'
        WHERE {where_sql}
        ORDER BY d.source_id, d.document_id
        {limit_sql}
    """
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def sync_text_version_candidate(
    conn: Any,
    *,
    row: dict[str, Any],
    config: StorageConfig,
    client: Any,
    execute: bool,
    skip_upload: bool,
    force: bool,
    ingestion_run_id: str | None,
) -> dict[str, Any]:
    candidate: AssetCandidate = candidate_from_db_row(row)
    source_asset_id = str(row.get("primary_file_asset_id") or "")
    if not source_asset_id:
        return {"document_id": candidate.document_id, "status": "missing_source_asset"}

    text_version = build_text_version(conn, candidate)
    if text_version is None:
        return {"document_id": candidate.document_id, "status": "no_page_text"}

    existing_hash = str(row.get("existing_text_hash") or "")
    existing_text_asset_id = str(row.get("existing_text_asset_id") or "")
    if not force and existing_hash == text_version.text_hash and existing_text_asset_id:
        return {
            "document_id": candidate.document_id,
            "status": "skipped_current",
            "text_hash": text_version.text_hash,
            "page_count": text_version.page_count,
        }

    text_payload = text_version.full_text.encode("utf-8")
    text_key = text_storage_key(config, candidate, text_version.text_hash)
    result = {
        "document_id": candidate.document_id,
        "status": "planned",
        "asset_key": text_key,
        "byte_size": len(text_payload),
        "text_hash": text_version.text_hash,
        "page_count": text_version.page_count,
        "char_count": text_version.char_count,
    }
    if not execute:
        return result

    text_etag = ""
    if not skip_upload:
        text_etag = upload_bytes_if_needed(
            client,
            bucket=config.bucket,
            key=text_key,
            payload=text_payload,
            content_type="text/plain; charset=utf-8",
            sha256=text_version.text_hash,
        )
    text_asset_id = upsert_file_asset(
        conn,
        candidate=candidate,
        config=config,
        asset_kind="extracted_text",
        key=text_key,
        content_type="text/plain; charset=utf-8",
        byte_size=len(text_payload),
        sha256=text_version.text_hash,
        etag=text_etag,
        source_local_path="pages",
        is_primary=False,
        ingestion_run_id=ingestion_run_id,
        metadata={"version_label": "current-pages-v1", "source_asset_id": source_asset_id},
    )
    text_version_id = upsert_text_version(
        conn,
        candidate=candidate,
        source_asset_id=source_asset_id,
        text_asset_id=text_asset_id,
        text_version=text_version,
        ingestion_run_id=ingestion_run_id,
    )
    digest_id = upsert_digest(
        conn,
        document_id=candidate.document_id,
        digest_type="extracted_full_text",
        digest_value=text_version.text_hash,
        byte_size=len(text_payload),
        page_count=text_version.page_count,
        file_asset_id=text_asset_id,
        text_version_id=text_version_id,
        metadata={"version_label": "current-pages-v1"},
    )
    return {
        **result,
        "status": "synced",
        "text_asset_id": text_asset_id,
        "text_version_id": text_version_id,
        "digest_id": digest_id,
    }


def record_ingestion_event(conn: Any, *, ingestion_run_id: str, row: dict[str, Any], result: dict[str, Any]) -> None:
    status = str(result["status"])
    if status == "synced":
        event_status = "indexed"
    elif status.startswith("skipped") or status in {"missing_source_asset", "no_page_text"}:
        event_status = "skipped"
    elif status == "error":
        event_status = "failed"
    else:
        event_status = "queued"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document_ingestion_events (
                ingestion_run_id, document_id, source_id, source_document_id,
                local_path, file_hash, stage, status, text_quality_score,
                error_code, error_message, metadata
            )
            VALUES (
                %(ingestion_run_id)s, %(document_id)s, %(source_id)s, %(source_document_id)s,
                %(local_path)s, %(file_hash)s, 'document_text_version_sync',
                %(status)s, %(text_quality_score)s, %(error_code)s, %(error_message)s,
                CAST(%(metadata)s AS jsonb)
            )
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "document_id": row["document_id"],
                "source_id": row["source_id"],
                "source_document_id": row.get("source_document_id"),
                "local_path": row.get("local_path"),
                "file_hash": row.get("file_hash"),
                "status": event_status,
                "text_quality_score": row.get("text_quality_score"),
                "error_code": status if event_status == "failed" else None,
                "error_message": result.get("error"),
                "metadata": json.dumps(result, ensure_ascii=False, default=str),
            },
        )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = build_storage_config(args)

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    client = None
    if args.execute and not args.skip_upload:
        client = build_s3_client(config)
        ensure_bucket(client, config.bucket)

    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        rows = page_text_candidates(conn, args)
        summary = TextVersionSyncSummary(candidate_count=len(rows))
        ingestion_run_id = args.ingestion_run_id
        if args.execute:
            ingestion_run_id = ingestion_run_id or default_ingestion_run_id(args)
            start_ingestion_run(conn, args=args, config=config, ingestion_run_id=ingestion_run_id)
            conn.commit()

        report_handle = open_report(args.report_path)
        report_context = report_handle if report_handle is not None else nullcontext(None)
        with report_context as report:
            for row in rows:
                try:
                    result = sync_text_version_candidate(
                        conn,
                        row=row,
                        config=config,
                        client=client,
                        execute=args.execute,
                        skip_upload=args.skip_upload,
                        force=args.force,
                        ingestion_run_id=ingestion_run_id,
                    )
                except Exception as exc:  # pragma: no cover - exercised in production runs.
                    result = {"document_id": row.get("document_id"), "status": "error", "error": str(exc)}
                summary.add(result)
                write_report(report, result)
                if args.execute and ingestion_run_id:
                    record_ingestion_event(conn, ingestion_run_id=ingestion_run_id, row=row, result=result)
                if args.execute and summary.processed_count % args.batch_size == 0:
                    conn.commit()
                if args.progress_every and summary.processed_count % args.progress_every == 0:
                    print_progress(summary)

            if args.execute and ingestion_run_id:
                finish_ingestion_run(conn, ingestion_run_id=ingestion_run_id, summary=summary)
                conn.commit()

    print_progress(summary, final=True)
    print(
        json.dumps(
            {
                "execute": args.execute,
                "bucket": config.bucket,
                "provider": config.provider,
                "ingestion_run_id": ingestion_run_id,
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "synced_count": summary.synced_count,
                "skipped_current_count": summary.skipped_current_count,
                "skipped_no_page_text_count": summary.skipped_no_page_text_count,
                "skipped_no_source_asset_count": summary.skipped_no_source_asset_count,
                "error_count": summary.error_count,
                "total_text_bytes": summary.total_text_bytes,
                "status_counts": summary.status_counts or {},
                "results_preview": summary.results_preview or [],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if summary.error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
