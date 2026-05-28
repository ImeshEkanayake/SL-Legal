#!/usr/bin/env python3
"""Redownload damaged corpus originals and reset them for extraction.

The script is intentionally DB-backed and resumable. It downloads to a staging
file, validates the replacement by extension, atomically replaces the local
file, updates the document file hash, and records ingestion events.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
RUN_VERSION = "2026-05-26"
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RedownloadResult:
    document_id: str
    source_id: str
    local_path: str
    url: str
    status: str
    old_size: int = 0
    new_size: int = 0
    old_sha256: str = ""
    new_sha256: str = ""
    error_code: str = ""
    error_message: str = ""


@dataclass
class RedownloadSummary:
    candidate_count: int = 0
    processed_count: int = 0
    redownloaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    bytes_downloaded: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: RedownloadResult) -> None:
        self.processed_count += 1
        if result.status == "redownloaded":
            self.redownloaded_count += 1
            self.bytes_downloaded += result.new_size
        elif result.status == "skipped":
            self.skipped_count += 1
        elif result.status == "failed":
            self.failed_count += 1
        if self.status_counts is None:
            self.status_counts = {}
        self.status_counts[result.status] = self.status_counts.get(result.status, 0) + 1
        if self.results_preview is None:
            self.results_preview = []
        if len(self.results_preview) < 20:
            self.results_preview.append(asdict(result))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument(
        "--language",
        action="append",
        help="Restrict repair to one or more document languages, for example English. Matches the normalized documents.language value case-insensitively.",
    )
    parser.add_argument("--status", action="append", default=["text_extraction_failed", "ocr_failed"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--commit-every", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--range-connections",
        type=int,
        default=1,
        help="Use parallel HTTP byte-range workers per file when the server advertises a content length.",
    )
    parser.add_argument(
        "--range-min-bytes",
        type=int,
        default=5 * 1024 * 1024,
        help="Minimum expected file size before enabling --range-connections.",
    )
    parser.add_argument(
        "--resume-from-local",
        dest="resume_from_local",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Seed the staged download with the existing local file and resume it when possible.",
    )
    parser.add_argument(
        "--trust-existing-valid-local",
        action="store_true",
        help="If the local file hash differs from Postgres, validate and record it without downloading again.",
    )
    parser.add_argument(
        "--preserve-failed-partial",
        dest="preserve_failed_partial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep a larger resumable partial file after a failed download so the next run can continue from it.",
    )
    parser.add_argument(
        "--validate-pdf-pages",
        action="store_true",
        help="Use pypdfium2 to verify repaired PDFs can open and contain at least one page.",
    )
    parser.add_argument("--min-speed-bytes", type=int, default=1024)
    parser.add_argument("--min-speed-time", type=int, default=30)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--report-path")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.commit_every < 1:
        parser.error("--commit-every must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")
    if args.retries < 0:
        parser.error("--retries must be zero or greater")
    if args.range_connections < 1:
        parser.error("--range-connections must be at least 1")
    if args.range_min_bytes < 0:
        parser.error("--range-min-bytes must be zero or greater")
    if args.min_speed_bytes < 0:
        parser.error("--min-speed-bytes must be zero or greater")
    if args.min_speed_time < 0:
        parser.error("--min-speed-time must be zero or greater")
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_download_url(row: dict[str, Any]) -> str:
    local_suffix = Path(str(row.get("local_path") or "")).suffix.lower()
    urls = [str(row.get("download_url") or ""), str(row.get("source_url") or "")]
    for url in urls:
        parsed_suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if url and parsed_suffix and parsed_suffix == local_suffix:
            return url
    for url in urls:
        parsed_suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if url and parsed_suffix in {".pdf", ".zip"}:
            return url
    return next((url for url in urls if url), "")


def validate_download(path: Path, expected_suffix: str, *, validate_pdf_pages: bool = False) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("downloaded file is empty")
    suffix = expected_suffix.lower()
    if suffix == ".pdf":
        with path.open("rb") as handle:
            header = handle.read(1024)
        if b"%PDF-" not in header[:256]:
            raise RuntimeError("downloaded file does not look like a PDF")
        if validate_pdf_pages:
            try:
                import pypdfium2 as pdfium

                pdf = pdfium.PdfDocument(str(path))
                try:
                    page_count = len(pdf)
                finally:
                    pdf.close()
            except ImportError as exc:
                raise RuntimeError("pypdfium2 is required for --validate-pdf-pages") from exc
            except Exception as exc:
                raise RuntimeError(f"downloaded PDF cannot be opened: {exc}") from exc
            if page_count < 1:
                raise RuntimeError("downloaded PDF has no pages")
    elif suffix == ".zip":
        if not zipfile.is_zipfile(path):
            raise RuntimeError("downloaded file does not look like a ZIP archive")


def can_seed_resume(path: Path, expected_suffix: str) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return False
    suffix = expected_suffix.lower()
    with path.open("rb") as handle:
        header = handle.read(256)
    if suffix == ".pdf":
        return b"%PDF-" in header
    if suffix == ".zip":
        return header.startswith(b"PK")
    return False


def seed_resume_target(source: Path, target: Path, expected_suffix: str, *, enabled: bool) -> bool:
    if not enabled or not can_seed_resume(source, expected_suffix):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def curl_command(
    url: str,
    target: Path,
    *,
    timeout: int,
    resume: bool,
    min_speed_bytes: int,
    min_speed_time: int,
) -> list[str]:
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "20",
        "--max-time",
        str(timeout),
        "--user-agent",
        "SL-Legal-Assist/1.0 corpus repair",
    ]
    if min_speed_bytes and min_speed_time:
        command.extend(["--speed-limit", str(min_speed_bytes), "--speed-time", str(min_speed_time)])
    if resume and target.exists() and target.stat().st_size > 0:
        command.extend(["--continue-at", "-"])
    command.extend(["--output", str(target), url])
    return command


def head_content_length(url: str, *, timeout: int) -> tuple[int, bool]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "SL-Legal-Assist/1.0 corpus repair"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", response.headers, None)
        length = int(response.headers.get("Content-Length") or "0")
        accepts_ranges = "bytes" in str(response.headers.get("Accept-Ranges") or "").lower()
        return length, accepts_ranges


def fetch_range_part(
    url: str,
    fd: int,
    *,
    start: int,
    end: int,
    timeout: int,
) -> int:
    headers = {
        "User-Agent": "SL-Legal-Assist/1.0 corpus repair",
        "Range": f"bytes={start}-{end}",
    }
    request = urllib.request.Request(url, headers=headers)
    written = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 206:
            raise RuntimeError(f"range request returned HTTP {status}, expected 206")
        offset = start
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            os.pwrite(fd, chunk, offset)
            offset += len(chunk)
            written += len(chunk)
    expected = end - start + 1
    if written != expected:
        raise RuntimeError(f"range {start}-{end} wrote {written} bytes, expected {expected}")
    return written


def fetch_url_ranges(
    url: str,
    target: Path,
    *,
    timeout: int,
    retries: int,
    range_connections: int,
    range_min_bytes: int,
) -> None:
    last_error = ""
    safe_prefix_size = target.stat().st_size if target.exists() else 0
    for attempt in range(retries + 1):
        try:
            total_size, accepts_ranges = head_content_length(url, timeout=min(timeout, 120))
            if not accepts_ranges or total_size < max(1, range_min_bytes):
                raise RuntimeError("server did not advertise usable byte ranges")
            existing_size = target.stat().st_size if target.exists() else 0
            if existing_size > total_size:
                target.unlink()
                existing_size = 0
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(target, os.O_RDWR | os.O_CREAT)
            try:
                os.ftruncate(fd, total_size)
                if existing_size >= total_size:
                    return
                missing_start = max(0, existing_size)
                missing = total_size - missing_start
                part_count = max(1, min(range_connections, missing))
                part_size = (missing + part_count - 1) // part_count
                ranges: list[tuple[int, int]] = []
                for index in range(part_count):
                    start = missing_start + index * part_size
                    if start >= total_size:
                        break
                    end = min(total_size - 1, start + part_size - 1)
                    ranges.append((start, end))
                with ThreadPoolExecutor(max_workers=part_count) as executor:
                    futures = [
                        executor.submit(fetch_range_part, url, fd, start=start, end=end, timeout=timeout)
                        for start, end in ranges
                    ]
                    for future in as_completed(futures):
                        future.result()
                return
            finally:
                os.close(fd)
        except Exception as exc:
            last_error = str(exc)
            if target.exists() and target.stat().st_size > safe_prefix_size:
                with target.open("r+b") as handle:
                    handle.truncate(safe_prefix_size)
            if attempt < retries:
                time.sleep(min(10, 2**attempt))
    partial_size = target.stat().st_size if target.exists() else 0
    raise RuntimeError(f"{last_error or 'range download failed'}; partial_size={partial_size}")


def fetch_url(
    url: str,
    target: Path,
    *,
    timeout: int,
    retries: int,
    resume: bool,
    min_speed_bytes: int,
    min_speed_time: int,
    range_connections: int = 1,
    range_min_bytes: int = 0,
) -> None:
    if range_connections > 1:
        try:
            fetch_url_ranges(
                url,
                target,
                timeout=timeout,
                retries=retries,
                range_connections=range_connections,
                range_min_bytes=range_min_bytes,
            )
            return
        except Exception:
            if not shutil.which("curl"):
                raise
    if shutil.which("curl"):
        last_error = ""
        for attempt in range(retries + 1):
            command = curl_command(
                url,
                target,
                timeout=timeout,
                resume=resume,
                min_speed_bytes=min_speed_bytes,
                min_speed_time=min_speed_time,
            )
            try:
                completed = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=timeout + 30,
                )
            except subprocess.TimeoutExpired as exc:
                last_error = f"curl subprocess timed out after {timeout + 30}s"
                if exc.stderr:
                    last_error = f"{last_error}: {exc.stderr.strip()}"
                if attempt < retries:
                    time.sleep(min(10, 2**attempt))
                    continue
                break
            if completed.returncode == 0:
                return
            last_error = (completed.stderr or completed.stdout or f"curl exited {completed.returncode}").strip()
            if completed.returncode == 33 and target.exists():
                target.unlink()
                last_error = f"{last_error}; removed non-resumable partial"
            if attempt < retries:
                time.sleep(min(10, 2**attempt))
        partial_size = target.stat().st_size if target.exists() else 0
        raise RuntimeError(f"{last_error}; partial_size={partial_size}")

    last_error = ""
    headers = {"User-Agent": "SL-Legal-Assist/1.0 corpus repair"}
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as handle:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise urllib.error.HTTPError(url, status, f"HTTP {status}", response.headers, None)
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(chunk)
            return
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
            if exc.code not in RETRYABLE_STATUS_CODES:
                break
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(min(10, 2**attempt))
    raise RuntimeError(last_error or "download failed")


def redownload_one(row: dict[str, Any], args: argparse.Namespace) -> RedownloadResult:
    document_id = str(row.get("document_id") or "")
    source_id = str(row.get("source_id") or "")
    local_path_value = str(row.get("local_path") or "")
    local_path = resolve_local_path(local_path_value)
    url = choose_download_url(row)
    if not url:
        return RedownloadResult(document_id, source_id, local_path_value, "", "failed", error_code="missing_url", error_message="missing source/download URL")
    if not local_path_value:
        return RedownloadResult(document_id, source_id, local_path_value, url, "failed", error_code="missing_local_path", error_message="missing local_path")
    old_size = local_path.stat().st_size if local_path.exists() else 0
    old_sha = sha256_file(local_path) if local_path.exists() and local_path.is_file() else ""
    db_sha = str(row.get("file_hash") or "")
    if args.execute and args.trust_existing_valid_local and old_sha and old_sha != db_sha:
        try:
            validate_download(local_path, local_path.suffix, validate_pdf_pages=args.validate_pdf_pages)
            return RedownloadResult(
                document_id,
                source_id,
                local_path_value,
                url,
                "redownloaded",
                old_size=old_size,
                new_size=old_size,
                old_sha256=db_sha,
                new_sha256=old_sha,
            )
        except Exception:
            pass
    tmp_path = local_path.with_suffix(local_path.suffix + f".redownload_{os.getpid()}_{time.time_ns()}.tmp")
    try:
        if not args.execute:
            return RedownloadResult(document_id, source_id, local_path_value, url, "skipped", old_size=old_size, old_sha256=old_sha)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        seed_resume_target(local_path, tmp_path, local_path.suffix, enabled=args.resume_from_local)
        fetch_url(
            url,
            tmp_path,
            timeout=args.timeout,
            retries=args.retries,
            resume=args.resume_from_local,
            min_speed_bytes=args.min_speed_bytes,
            min_speed_time=args.min_speed_time,
            range_connections=args.range_connections,
            range_min_bytes=args.range_min_bytes,
        )
        validate_download(tmp_path, local_path.suffix, validate_pdf_pages=args.validate_pdf_pages)
        new_size = tmp_path.stat().st_size
        new_sha = sha256_file(tmp_path)
        tmp_path.replace(local_path)
        return RedownloadResult(document_id, source_id, local_path_value, url, "redownloaded", old_size=old_size, new_size=new_size, old_sha256=old_sha, new_sha256=new_sha)
    except Exception as exc:
        if tmp_path.exists():
            partial_size = tmp_path.stat().st_size
            preserved = False
            if (
                args.resume_from_local
                and args.preserve_failed_partial
                and partial_size > old_size
                and can_seed_resume(tmp_path, local_path.suffix)
            ):
                tmp_path.replace(local_path)
                preserved = True
            else:
                tmp_path.unlink()
            suffix = f"; preserved_partial_bytes={partial_size}" if preserved else ""
        else:
            suffix = ""
        return RedownloadResult(document_id, source_id, local_path_value, url, "failed", old_size=old_size, old_sha256=old_sha, error_code="redownload_failed", error_message=f"{exc}{suffix}")


def candidate_filter_sql(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    clauses = [
        "d.acquisition_status = 'downloaded'",
        "d.local_path IS NOT NULL",
        "length(trim(d.local_path)) > 0",
        "NOT EXISTS (SELECT 1 FROM retrieval_chunks rc WHERE rc.document_id = d.document_id)",
        "d.extraction_status = ANY(%(statuses)s)",
    ]
    params: dict[str, Any] = {"statuses": sorted(set(args.status or []))}
    if args.document_ids_filter:
        clauses.append("d.document_id = ANY(%(document_ids)s)")
        params["document_ids"] = sorted(args.document_ids_filter)
    if args.source_id:
        clauses.append("d.source_id = ANY(%(source_ids)s)")
        params["source_ids"] = sorted(args.source_id)
    if args.language:
        normalized_languages = sorted({language.strip().lower() for language in args.language if language.strip()})
        if normalized_languages:
            clauses.append("lower(coalesce(d.language, '')) = ANY(%(languages)s)")
            params["languages"] = normalized_languages
    return " AND ".join(f"({clause})" for clause in clauses), params


def fetch_candidates(conn: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    where_sql, params = candidate_filter_sql(args)
    limit_sql = "LIMIT %(limit)s" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    query = f"""
        SELECT
            document_id, source_id, source_document_id, title, year, language,
            source_url, download_url, local_path, file_hash, extraction_status, notes
        FROM documents d
        WHERE {where_sql}
        ORDER BY d.source_id, d.year NULLS LAST, d.document_id
        {limit_sql}
    """
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def start_ingestion_run(conn: Any, *, args: argparse.Namespace, ingestion_run_id: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (
                ingestion_run_id, source_id, pipeline_name, pipeline_version,
                status, corpus_root, config
            )
            VALUES (
                %(ingestion_run_id)s, %(source_id)s, 'redownload_failed_corpus_documents',
                %(pipeline_version)s, 'running', %(corpus_root)s, CAST(%(config)s AS jsonb)
            )
            ON CONFLICT (ingestion_run_id) DO UPDATE SET
                status = 'running',
                completed_at = NULL,
                error = NULL,
                updated_at = now(),
                config = EXCLUDED.config
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "source_id": ",".join(sorted(args.source_id)) if args.source_id else "ALL",
                "pipeline_version": RUN_VERSION,
                "corpus_root": str(PROJECT_ROOT / "data" / "raw"),
                "config": json.dumps(
                    {
                        "limit": args.limit,
                        "workers": args.workers,
                        "statuses": args.status,
                        "commit_every": args.commit_every,
                        "resume_from_local": args.resume_from_local,
                        "trust_existing_valid_local": args.trust_existing_valid_local,
                        "validate_pdf_pages": args.validate_pdf_pages,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: RedownloadSummary) -> None:
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
                "status": "failed" if summary.failed_count else "complete",
                "document_count": summary.processed_count,
                "error_count": summary.failed_count,
                "ingestion_run_id": ingestion_run_id,
                "output": json.dumps(asdict(summary), ensure_ascii=False),
            },
        )


def update_document_and_event(conn: Any, *, row: dict[str, Any], result: RedownloadResult, ingestion_run_id: str) -> None:
    event_status = "downloaded" if result.status == "redownloaded" else "failed" if result.status == "failed" else "skipped"
    notes = str(row.get("notes") or "")
    if result.status == "redownloaded":
        note = f"redownloaded_for_repair={utc_now()}; old_bytes={result.old_size}; new_bytes={result.new_size}; repair_run={ingestion_run_id}"
        notes = f"{notes}; {note}" if notes else note
    elif result.status == "failed":
        note = f"redownload_failed={result.error_message}; repair_run={ingestion_run_id}"
        notes = f"{notes}; {note}" if notes else note
    with conn.cursor() as cursor:
        if result.status == "redownloaded":
            cursor.execute(
                """
                UPDATE documents
                SET file_hash = %(file_hash)s,
                    extraction_status = 'not_started',
                    ocr_required = NULL,
                    text_quality_score = NULL,
                    notes = %(notes)s,
                    current_ingestion_run_id = %(ingestion_run_id)s,
                    last_ingested_at = now(),
                    last_checked = now(),
                    updated_at = now()
                WHERE document_id = %(document_id)s
                """,
                {
                    "document_id": result.document_id,
                    "file_hash": result.new_sha256,
                    "notes": notes,
                    "ingestion_run_id": ingestion_run_id,
                },
            )
        else:
            cursor.execute(
                """
                UPDATE documents
                SET notes = %(notes)s,
                    current_ingestion_run_id = %(ingestion_run_id)s,
                    last_checked = now(),
                    updated_at = now()
                WHERE document_id = %(document_id)s
                """,
                {"document_id": result.document_id, "notes": notes, "ingestion_run_id": ingestion_run_id},
            )
        cursor.execute(
            """
            INSERT INTO document_ingestion_events (
                ingestion_run_id, document_id, source_id, source_document_id,
                local_path, file_hash, stage, status, extraction_method,
                quality_flags, error_code, error_message, metadata
            )
            VALUES (
                %(ingestion_run_id)s, %(document_id)s, %(source_id)s, %(source_document_id)s,
                %(local_path)s, %(file_hash)s, 'redownload_repair', %(status)s, 'http',
                %(quality_flags)s, %(error_code)s, %(error_message)s, CAST(%(metadata)s AS jsonb)
            )
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "document_id": result.document_id,
                "source_id": result.source_id,
                "source_document_id": row.get("source_document_id"),
                "local_path": result.local_path,
                "file_hash": result.new_sha256 or result.old_sha256 or row.get("file_hash"),
                "status": event_status,
                "quality_flags": ["redownloaded_original"] if result.status == "redownloaded" else ["redownload_failed"],
                "error_code": result.error_code or None,
                "error_message": result.error_message or None,
                "metadata": json.dumps(asdict(result), ensure_ascii=False),
            },
        )


def write_report(handle: TextIO | None, result: RedownloadResult) -> None:
    if handle is None:
        return
    handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    handle.flush()


def open_report(path_value: str | None) -> TextIO | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


TRANSIENT_DB_SQLSTATES = {"40P01", "40001"}


def is_transient_db_error(exc: BaseException) -> bool:
    return str(getattr(exc, "sqlstate", "")) in TRANSIENT_DB_SQLSTATES


def persist_result_with_retry(
    conn: Any,
    *,
    row: dict[str, Any],
    result: RedownloadResult,
    ingestion_run_id: str,
    max_attempts: int = 5,
) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            update_document_and_event(conn, row=row, result=result, ingestion_run_id=ingestion_run_id)
            conn.commit()
            return
        except Exception as exc:
            conn.rollback()
            if not is_transient_db_error(exc) or attempt == max_attempts:
                raise
            time.sleep(min(2.0, 0.2 * attempt))


def process_batch(conn: Any, *, rows: list[dict[str, Any]], args: argparse.Namespace, ingestion_run_id: str, report: TextIO | None, summary: RedownloadSummary) -> None:
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(redownload_one, row, args): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            result = future.result()
            if args.execute:
                persist_result_with_retry(conn, row=row, result=result, ingestion_run_id=ingestion_run_id)
            summary.add(result)
            write_report(report, result)
            if args.progress_every and summary.processed_count % args.progress_every == 0:
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "processed": summary.processed_count,
                            "redownloaded": summary.redownloaded_count,
                            "failed": summary.failed_count,
                            "bytes_downloaded": summary.bytes_downloaded,
                            "latest": result.document_id,
                            "latest_status": result.status,
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
    if args.execute:
        conn.commit()


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    ingestion_run_id = "redownload_repair_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        candidates = fetch_candidates(conn, args)
        summary = RedownloadSummary(candidate_count=len(candidates))
        if not args.execute:
            print(
                json.dumps(
                    {
                        "candidate_count": len(candidates),
                        "execute": False,
                        "candidates_preview": [
                            {
                                "document_id": row.get("document_id"),
                                "source_id": row.get("source_id"),
                                "local_path": row.get("local_path"),
                                "url": choose_download_url(row),
                            }
                            for row in candidates[:20]
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        start_ingestion_run(conn, args=args, ingestion_run_id=ingestion_run_id)
        conn.commit()
        report = open_report(args.report_path)
        try:
            for start in range(0, len(candidates), args.batch_size):
                batch = candidates[start : start + args.batch_size]
                process_batch(conn, rows=batch, args=args, ingestion_run_id=ingestion_run_id, report=report, summary=summary)
        finally:
            if report is not None:
                report.close()
        finish_ingestion_run(conn, ingestion_run_id=ingestion_run_id, summary=summary)
        conn.commit()
    print(json.dumps(asdict(summary) | {"ingestion_run_id": ingestion_run_id}, indent=2, ensure_ascii=False))
    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
