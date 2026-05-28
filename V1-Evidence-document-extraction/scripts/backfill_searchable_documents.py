#!/usr/bin/env python3
"""Backfill downloaded documents into the full searchable RAG path.

This runner is the DB-backed production bridge between acquisition and search:

1. Extract pages for downloaded files without page rows.
2. OCR English PDFs that have only empty page text.
3. Sync original assets to object storage tracking.
4. Create document text versions and digests from canonical pages.
5. Build RAG chunks and load Postgres, OpenSearch, and Qdrant.

Every stage is resumable because candidates are selected from Postgres state and
all writes are idempotent/upserts in the underlying stage scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "indexes" / "searchability_backfill"
INDEXABLE_EXTRACTION_STATUSES = {"text_extracted", "text_empty_needs_ocr"}


@dataclass
class BatchPlan:
    batch_number: int
    extract_ids: list[str]
    ocr_ids: list[str]
    index_ids: list[str]
    extract_file: str
    ocr_file: str
    index_file: str
    chunks_file: str


@dataclass
class BatchResult:
    batch_number: int
    extracted_candidates: int
    ocr_candidates: int
    indexed_candidates: int
    chunks_file: str
    dry_run: bool = False


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run stage commands. Without this, only writes candidate files.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--document-id", action="append", help="Limit to one or more document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--source-id", action="append", help="Limit to one or more source IDs.")
    parser.add_argument("--batch-size-documents", type=int, default=300)
    parser.add_argument("--max-batches", type=int, default=1, help="0 means keep running until idle limit is reached.")
    parser.add_argument("--poll-seconds", type=int, default=0, help="Sleep between idle rounds when waiting for repaired documents.")
    parser.add_argument("--max-idle-rounds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4, help="Workers for PDF text extraction.")
    parser.add_argument("--ocr-workers", type=int, default=2)
    parser.add_argument("--ocr-dpi", type=int, default=250)
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument(
        "--ocr-tessdata-dir",
        default=os.getenv("SL_LEGAL_TESSDATA_DIR", ""),
        help="Optional tessdata directory passed to Tesseract OCR, for example local Sinhala/Tamil traineddata.",
    )
    parser.add_argument("--ocr-document-timeout", type=int, default=900)
    parser.add_argument("--ocr-all-languages", action="store_true", help="OCR all selected empty-text PDFs, not only English-looking documents.")
    parser.add_argument("--skip-extraction", action="store_true")
    parser.add_argument(
        "--retry-failed-extraction",
        action="store_true",
        help="Also retry documents already marked text_extraction_failed. Default only processes repaired not_started files.",
    )
    parser.add_argument("--skip-english-ocr", action="store_true")
    parser.add_argument("--skip-object-sync", action="store_true")
    parser.add_argument("--skip-text-version-sync", action="store_true")
    parser.add_argument("--skip-postgres-chunks", action="store_true")
    parser.add_argument("--skip-opensearch", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument("--include-gazettes", action="store_true", default=True)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--opensearch-url", default=os.getenv("SL_LEGAL_OPENSEARCH_URL", "http://localhost:9200"))
    parser.add_argument("--qdrant-url", default=os.getenv("SL_LEGAL_QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--embedding-provider", default=os.getenv("SL_LEGAL_EMBEDDING_PROVIDER", "sentence-transformers"))
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("SL_LEGAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    )
    parser.add_argument("--embedding-dimensions", type=int, default=int(os.getenv("SL_LEGAL_EMBEDDING_DIMENSIONS", "384")))
    args = parser.parse_args(argv)
    if args.batch_size_documents < 1:
        parser.error("--batch-size-documents must be at least 1")
    if args.max_batches < 0:
        parser.error("--max-batches must be zero or greater")
    if args.max_idle_rounds < 1:
        parser.error("--max-idle-rounds must be at least 1")
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must be zero or greater")
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


def source_filter_sql(args: argparse.Namespace, params: dict[str, Any]) -> str:
    clauses: list[str] = []
    if args.source_id:
        params["source_ids"] = sorted(args.source_id)
        clauses.append("d.source_id = ANY(%(source_ids)s)")
    if args.document_ids_filter:
        params["document_ids"] = sorted(args.document_ids_filter)
        clauses.append("d.document_id = ANY(%(document_ids)s)")
    if not clauses:
        return ""
    return "AND " + " AND ".join(clauses)


def fetch_extract_candidate_ids(conn: Any, args: argparse.Namespace) -> list[str]:
    if args.skip_extraction:
        return []
    params: dict[str, Any] = {"limit": args.batch_size_documents}
    status_filter = "" if args.retry_failed_extraction else "AND d.extraction_status = 'not_started'"
    query = f"""
        SELECT d.document_id
        FROM documents d
        WHERE d.acquisition_status = 'downloaded'
          AND d.local_path IS NOT NULL
          AND length(trim(d.local_path)) > 0
          AND lower(d.local_path) LIKE '%%.pdf'
          AND NOT EXISTS (SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id)
          AND NOT EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id)
          {status_filter}
          {source_filter_sql(args, params)}
        ORDER BY d.source_id, d.year NULLS LAST, d.document_id
        LIMIT %(limit)s
    """
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return [str(row[0]) for row in cursor.fetchall()]


def english_ocr_filter_sql() -> str:
    return """
        (
            lower(coalesce(d.language, '')) IN ('english', 'eng', 'en', 'e')
            OR lower(d.local_path) LIKE '%%/english/%%'
            OR upper(coalesce(d.source_document_id, '')) LIKE '%%:E'
        )
    """


def fetch_english_ocr_candidate_ids(conn: Any, args: argparse.Namespace) -> list[str]:
    if args.skip_english_ocr:
        return []
    params: dict[str, Any] = {"limit": args.batch_size_documents}
    query = f"""
        SELECT d.document_id
        FROM documents d
        WHERE d.acquisition_status = 'downloaded'
          AND lower(d.local_path) LIKE '%%.pdf'
          AND coalesce(d.extraction_status, '') <> 'ocr_failed'
          AND NOT EXISTS (SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id)
          AND NOT EXISTS (
              SELECT 1 FROM pages p
              WHERE p.document_id = d.document_id
                AND p.extraction_method = 'ocr'
                AND length(trim(coalesce(p.text, ''))) > 0
          )
          AND (
              d.extraction_status = 'text_empty_needs_ocr'
              OR d.ocr_required IS TRUE
              OR (
                  EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id)
                  AND NOT EXISTS (
                      SELECT 1 FROM pages p
                      WHERE p.document_id = d.document_id
                        AND length(trim(coalesce(p.text, ''))) > 0
                  )
              )
          )
          {"AND " + english_ocr_filter_sql() if not args.ocr_all_languages else ""}
          {source_filter_sql(args, params)}
        ORDER BY d.source_id, d.year NULLS LAST, d.document_id
        LIMIT %(limit)s
    """
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return [str(row[0]) for row in cursor.fetchall()]


def fetch_index_candidate_ids(conn: Any, args: argparse.Namespace) -> list[str]:
    params: dict[str, Any] = {"limit": args.batch_size_documents}
    query = f"""
        SELECT DISTINCT d.document_id
        FROM documents d
        WHERE d.acquisition_status = 'downloaded'
          AND EXISTS (
              SELECT 1 FROM pages p
              WHERE p.document_id = d.document_id
                AND length(trim(coalesce(p.text, ''))) > 0
          )
          AND d.extraction_status = ANY(%(indexable_extraction_statuses)s)
          AND NOT EXISTS (SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id)
          {source_filter_sql(args, params)}
        ORDER BY d.document_id
        LIMIT %(limit)s
    """
    with conn.cursor() as cursor:
        params["indexable_extraction_statuses"] = sorted(INDEXABLE_EXTRACTION_STATUSES)
        cursor.execute(query, params)
        return [str(row[0]) for row in cursor.fetchall()]


def write_id_file(path: Path, ids: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
    return path_arg(path)


def path_arg(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_batch_plan(conn: Any, args: argparse.Namespace, batch_number: int) -> BatchPlan:
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = PROJECT_ROOT / report_dir
    batch_prefix = f"{args.stamp}_batch{batch_number:04d}"
    extract_ids = fetch_extract_candidate_ids(conn, args)
    ocr_ids = fetch_english_ocr_candidate_ids(conn, args)
    index_ids = fetch_index_candidate_ids(conn, args)
    extract_file = report_dir / f"{batch_prefix}_extract_ids.txt"
    ocr_file = report_dir / f"{batch_prefix}_ocr_english_ids.txt"
    index_file = report_dir / f"{batch_prefix}_index_ids.txt"
    chunks_file = report_dir / f"{batch_prefix}_chunks.jsonl"
    return BatchPlan(
        batch_number=batch_number,
        extract_ids=extract_ids,
        ocr_ids=ocr_ids,
        index_ids=index_ids,
        extract_file=write_id_file(extract_file, extract_ids),
        ocr_file=write_id_file(ocr_file, ocr_ids),
        index_file=write_id_file(index_file, index_ids),
        chunks_file=path_arg(chunks_file),
    )


def command_with_python(script: str, *args: str) -> list[str]:
    return [sys.executable, script, *args]


def stage_commands(args: argparse.Namespace, plan: BatchPlan) -> list[list[str]]:
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = PROJECT_ROOT / report_dir
    batch_prefix = f"{args.stamp}_batch{plan.batch_number:04d}"
    commands: list[list[str]] = []
    if plan.extract_ids and not args.skip_extraction:
        commands.append(
            command_with_python(
                "scripts/extract_missing_pdf_pages_to_postgres.py",
                "--execute",
                "--document-id-file",
                plan.extract_file,
                "--workers",
                str(args.workers),
                "--batch-size",
                str(args.batch_size_documents),
                "--progress-every",
                "50",
                "--report-path",
                path_arg(report_dir / f"{batch_prefix}_extract_report.jsonl"),
            )
        )
    if plan.ocr_ids and not args.skip_english_ocr:
        ocr_command = command_with_python(
            "scripts/ocr_empty_pdf_pages_to_postgres.py",
            "--execute",
            "--document-id-file",
            plan.ocr_file,
            "--workers",
            str(args.ocr_workers),
            "--batch-size",
            str(max(1, min(args.batch_size_documents, 20))),
            "--dpi",
            str(args.ocr_dpi),
            "--language",
            args.ocr_language,
            "--document-timeout",
            str(args.ocr_document_timeout),
            "--progress-every",
            "1",
            "--report-path",
            path_arg(report_dir / f"{batch_prefix}_ocr_report.jsonl"),
        )
        if args.ocr_tessdata_dir:
            ocr_command.extend(["--tessdata-dir", args.ocr_tessdata_dir])
        commands.append(ocr_command)
    if not plan.index_ids:
        return commands
    if not args.skip_object_sync:
        commands.append(
            command_with_python(
                "scripts/sync_corpus_assets_to_object_storage.py",
                "--execute",
                "--scope",
                "postgres",
                "--document-id-file",
                plan.index_file,
                "--batch-size",
                str(args.batch_size_documents),
                "--progress-every",
                str(args.batch_size_documents),
                "--allow-hash-mismatch",
                "--report-path",
                path_arg(report_dir / f"{batch_prefix}_asset_report.jsonl"),
            )
        )
    if not args.skip_text_version_sync:
        commands.append(
            command_with_python(
                "scripts/sync_text_versions_from_pages.py",
                "--execute",
                "--document-id-file",
                plan.index_file,
                "--batch-size",
                str(args.batch_size_documents),
                "--progress-every",
                str(args.batch_size_documents),
                "--report-path",
                path_arg(report_dir / f"{batch_prefix}_text_version_report.jsonl"),
            )
        )
    build = command_with_python(
        "scripts/build_rag_chunks_from_postgres.py",
        "--document-id-file",
        plan.index_file,
        "--output",
        plan.chunks_file,
    )
    if args.include_gazettes:
        build.append("--include-gazettes")
    commands.append(build)
    if not args.skip_postgres_chunks:
        commands.append(
            command_with_python(
                "scripts/load_rag_chunks_postgres.py",
                "--mode",
                "psycopg",
                "--chunks",
                plan.chunks_file,
                "--batch-size",
                "10000",
            )
        )
    if not args.skip_opensearch:
        commands.append(
            command_with_python(
                "scripts/load_rag_chunks_opensearch.py",
                "--chunks",
                plan.chunks_file,
                "--url",
                args.opensearch_url,
                "--batch-size",
                "2000",
            )
        )
    if not args.skip_qdrant:
        commands.append(
            command_with_python(
                "scripts/load_rag_chunks_qdrant.py",
                "--chunks",
                plan.chunks_file,
                "--url",
                args.qdrant_url,
                "--provider",
                args.embedding_provider,
                "--model",
                args.embedding_model,
                "--dimensions",
                str(args.embedding_dimensions),
                "--batch-size",
                "256",
                "--progress-every",
                "5000",
            )
        )
    return commands


def is_partial_recovery_stage(command: list[str]) -> bool:
    stage_names = {
        "scripts/extract_missing_pdf_pages_to_postgres.py",
        "scripts/ocr_empty_pdf_pages_to_postgres.py",
    }
    return any(part in stage_names for part in command)


def run_command(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = "rag" if not env.get("PYTHONPATH") else f"rag{os.pathsep}{env['PYTHONPATH']}"
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False)
    if completed.returncode != 0:
        if is_partial_recovery_stage(command):
            print(
                json.dumps(
                    {
                        "event": "stage_completed_with_recoverable_failures",
                        "returncode": completed.returncode,
                        "command": command,
                    },
                    indent=2,
                ),
                flush=True,
            )
            return
        raise SystemExit(completed.returncode)


def run_batch(conn: Any, args: argparse.Namespace, batch_number: int) -> BatchResult:
    plan = build_batch_plan(conn, args, batch_number)
    commands = stage_commands(args, plan)
    print(
        json.dumps(
            {
                "event": "batch_plan",
                "batch_number": batch_number,
                "extract_candidates": len(plan.extract_ids),
                "ocr_candidates": len(plan.ocr_ids),
                "index_candidates": len(plan.index_ids),
                "extract_file": plan.extract_file,
                "ocr_file": plan.ocr_file,
                "index_file": plan.index_file,
                "chunks_file": plan.chunks_file,
                "commands": commands,
                "execute": args.execute,
            },
            indent=2,
        ),
        flush=True,
    )
    if args.execute:
        for command in commands:
            run_command(command)
    return BatchResult(
        batch_number=batch_number,
        extracted_candidates=len(plan.extract_ids),
        ocr_candidates=len(plan.ocr_ids),
        indexed_candidates=len(plan.index_ids),
        chunks_file=plan.chunks_file,
        dry_run=not args.execute,
    )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    results: list[BatchResult] = []
    idle_rounds = 0
    batch_number = 1
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        while args.max_batches == 0 or batch_number <= args.max_batches:
            result = run_batch(conn, args, batch_number)
            conn.commit()
            results.append(result)
            had_work = any(
                [
                    result.extracted_candidates,
                    result.ocr_candidates,
                    result.indexed_candidates,
                ]
            )
            if had_work:
                idle_rounds = 0
                batch_number += 1
                continue
            idle_rounds += 1
            if idle_rounds >= args.max_idle_rounds:
                break
            if args.poll_seconds:
                time.sleep(args.poll_seconds)
            batch_number += 1
    print(json.dumps({"batches": [asdict(result) for result in results]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
