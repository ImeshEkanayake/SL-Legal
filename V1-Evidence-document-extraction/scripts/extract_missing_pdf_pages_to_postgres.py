#!/usr/bin/env python3
"""Extract PDF text for documents that do not yet have pages in Postgres.

This is the production corpus backfill path. It is DB-backed, resumable,
parallel, and writes both extraction artifacts and canonical `pages` rows.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import logging
import mimetypes
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
LOCAL_DEPS = PROJECT_ROOT / ".codex_deps" / "ocr"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

from sl_legal_rag.chunking import normalize_text, stable_hash  # noqa: E402


try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - runtime dependency is validated by CLI execution.
    PdfReader = None  # type: ignore[assignment]

try:
    import pypdfium2 as pdfium
except Exception:  # pragma: no cover - fallback is optional.
    pdfium = None

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - fallback is optional.
    fitz = None


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
TEXT_DIR = PROJECT_ROOT / "data" / "extracted" / "text"
RUN_VERSION = "2026-05-26"
CONTROL_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._=-]+")
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass(frozen=True)
class ExtractionResult:
    document_id: str
    source_id: str
    source_document_id: str
    local_path: str
    status: str
    stage_status: str
    extraction_method: str = ""
    page_count: int = 0
    char_count: int = 0
    text_path: str = ""
    pages_path: str = ""
    text_quality_score: float | None = None
    ocr_required: bool | None = None
    text_hash: str = ""
    quality_flags: tuple[str, ...] = ()
    error_code: str = ""
    error_message: str = ""


@dataclass
class ExtractionSummary:
    candidate_count: int = 0
    processed_count: int = 0
    extracted_count: int = 0
    empty_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    pages_upserted: int = 0
    chars_extracted: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: ExtractionResult, *, pages_upserted: int) -> None:
        self.processed_count += 1
        self.pages_upserted += pages_upserted
        self.chars_extracted += result.char_count
        if result.stage_status == "extracted":
            if result.status == "text_empty_needs_ocr":
                self.empty_count += 1
            else:
                self.extracted_count += 1
        elif result.stage_status == "skipped":
            self.skipped_count += 1
        elif result.stage_status == "failed":
            self.failed_count += 1
        if self.status_counts is None:
            self.status_counts = {}
        self.status_counts[result.status] = self.status_counts.get(result.status, 0) + 1
        if self.results_preview is None:
            self.results_preview = []
        if len(self.results_preview) < 20:
            self.results_preview.append(asdict(result) | {"pages_upserted": pages_upserted})


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run extraction and write Postgres rows.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--year", action="append")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--report-path")
    parser.add_argument("--force", action="store_true", help="Re-extract selected PDFs even if pages already exist.")
    parser.add_argument(
        "--include-empty-page-docs",
        action="store_true",
        help="Also select documents that have only empty page text.",
    )
    parser.add_argument(
        "--allow-non-pdf",
        action="store_true",
        help="Attempt extraction even when local_path extension/content-type is not PDF.",
    )
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be zero or greater")
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


def slug(value: str) -> str:
    return CONTROL_FILENAME_RE.sub("_", value.strip()).strip("._") or "unknown"


def stable_page_id(document_id: str, extraction_method: str, page_number: int) -> str:
    raw = f"{document_id}:{extraction_method}:{page_number}"
    digest = stable_hash(raw)[:12]
    return f"page_{document_id}_{extraction_method}_{page_number:05d}_{digest}"


def resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def page_text_quality(text: str, page_count: int) -> tuple[float, bool, tuple[str, ...]]:
    chars = len(text.strip())
    flags: list[str] = []
    if chars == 0:
        return 0.0, True, ("empty_document_text",)
    if page_count <= 0:
        return 0.5, False, ("missing_page_count",)
    chars_per_page = chars / page_count
    if chars_per_page < 100:
        flags.append("low_text_density")
        return 0.25, True, tuple(flags)
    if chars_per_page < 500:
        flags.append("medium_text_density")
        return 0.60, False, tuple(flags)
    return 0.90, False, tuple(flags)


def extract_with_pypdf(pdf_path: Path) -> list[dict[str, str]]:
    if PdfReader is None:
        raise RuntimeError("pypdf is unavailable")
    reader = PdfReader(str(pdf_path), strict=False)
    pages: list[dict[str, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = normalize_text(str(page.extract_text() or ""))
            pages.append({"page": str(index), "text": text, "error": ""})
        except Exception as exc:
            pages.append({"page": str(index), "text": "", "error": str(exc)})
    return pages


def extract_with_pdfium(pdf_path: Path) -> list[dict[str, str]]:
    if pdfium is None:
        raise RuntimeError("pypdfium2 fallback is unavailable")
    pdf = pdfium.PdfDocument(str(pdf_path))
    pages: list[dict[str, str]] = []
    try:
        for index in range(len(pdf)):
            page_number = index + 1
            page = None
            textpage = None
            try:
                page = pdf[index]
                textpage = page.get_textpage()
                text = normalize_text(str(textpage.get_text_range() or ""))
                pages.append({"page": str(page_number), "text": text, "error": ""})
            except Exception as exc:
                pages.append({"page": str(page_number), "text": "", "error": str(exc)})
            finally:
                if textpage is not None:
                    textpage.close()
                if page is not None:
                    page.close()
    finally:
        pdf.close()
    return pages


def extract_with_pymupdf(pdf_path: Path) -> list[dict[str, str]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF fallback is unavailable")
    document = fitz.open(str(pdf_path))
    pages: list[dict[str, str]] = []
    try:
        for index in range(int(document.page_count)):
            page_number = index + 1
            try:
                page = document.load_page(index)
                text = normalize_text(str(page.get_text("text") or ""))
                pages.append({"page": str(page_number), "text": text, "error": ""})
            except Exception as exc:
                pages.append({"page": str(page_number), "text": "", "error": str(exc)})
    finally:
        document.close()
    return pages


def require_extracted_pages(extractor: str, pages: list[dict[str, str]]) -> list[dict[str, str]]:
    if pages:
        return pages
    raise RuntimeError(f"{extractor} returned zero pages")


def extract_pdf_pages(pdf_path: Path) -> tuple[str, list[dict[str, str]]]:
    errors: list[str] = []
    try:
        return "pypdf", require_extracted_pages("pypdf", extract_with_pypdf(pdf_path))
    except Exception as exc:
        errors.append(f"pypdf={exc}")
    try:
        return "pypdfium2", require_extracted_pages("pypdfium2", extract_with_pdfium(pdf_path))
    except Exception as exc:
        errors.append(f"pypdfium2={exc}")
    try:
        return "pymupdf", require_extracted_pages("pymupdf", extract_with_pymupdf(pdf_path))
    except Exception as exc:
        errors.append(f"pymupdf={exc}")
        raise RuntimeError("; ".join(errors)) from exc


def extract_zip_pdf_pages(zip_path: Path) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as archive, tempfile.TemporaryDirectory(prefix=f"sllegal_zip_extract_{zip_path.stem}_") as tmp_name:
        tmp_dir = Path(tmp_name)
        pdf_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir() and Path(info.filename).suffix.lower() == ".pdf"
        ]
        if not pdf_infos:
            raise RuntimeError("zip archive contains no PDF members")
        next_page = 1
        for info in sorted(pdf_infos, key=lambda item: item.filename.lower()):
            member_path = tmp_dir / Path(info.filename).name
            with archive.open(info) as source, member_path.open("wb") as target:
                target.write(source.read())
            try:
                _extractor, member_pages = extract_pdf_pages(member_path)
            except Exception as exc:
                pages.append(
                    {
                        "page": str(next_page),
                        "text": "",
                        "error": f"archive_member={info.filename}; {exc}",
                    }
                )
                next_page += 1
                continue
            for page in member_pages:
                text_value = str(page.get("text") or "")
                member_label = f"Archive member: {info.filename}"
                pages.append(
                    {
                        "page": str(next_page),
                        "text": normalize_text(f"{member_label}\n{text_value}") if text_value else "",
                        "error": str(page.get("error") or ""),
                    }
                )
                next_page += 1
    return pages


def extract_document(row: dict[str, Any], *, allow_non_pdf: bool) -> ExtractionResult:
    document_id = str(row["document_id"])
    source_id = str(row.get("source_id") or "")
    source_document_id = str(row.get("source_document_id") or "")
    local_path = str(row.get("local_path") or "")
    try:
        pdf_path = resolve_local_path(local_path)
        content_type = mimetypes.guess_type(pdf_path.name)[0] or ""
        if not pdf_path.is_file():
            return ExtractionResult(
                document_id=document_id,
                source_id=source_id,
                source_document_id=source_document_id,
                local_path=local_path,
                status="text_extraction_failed",
                stage_status="failed",
                error_code="missing_local_file",
                error_message=local_path,
                quality_flags=("missing_local_file",),
            )
        is_pdf = pdf_path.suffix.lower() == ".pdf" or content_type == "application/pdf"
        is_zip = pdf_path.suffix.lower() == ".zip"
        if not allow_non_pdf and not is_pdf:
            return ExtractionResult(
                document_id=document_id,
                source_id=source_id,
                source_document_id=source_document_id,
                local_path=local_path,
                status="unsupported_file_type",
                stage_status="skipped",
                error_code="unsupported_file_type",
                error_message=pdf_path.suffix.lower() or content_type or "unknown",
                quality_flags=("unsupported_file_type",),
            )

        try:
            if is_zip:
                extractor = "zip_pdf_text"
                pages = extract_zip_pdf_pages(pdf_path)
            else:
                extractor, pages = extract_pdf_pages(pdf_path)
        except Exception as exc:
            return ExtractionResult(
                document_id=document_id,
                source_id=source_id,
                source_document_id=source_document_id,
                local_path=local_path,
                status="text_extraction_failed",
                stage_status="failed",
                extraction_method="zip_pdf_text" if is_zip else "pypdfium2",
                error_code="extractor_failed",
                error_message=str(exc),
                quality_flags=("text_extraction_failed",),
            )

        combined = "\n\n".join(page["text"] for page in pages if page.get("text")).strip()
        text_hash = stable_hash(combined) if combined else ""
        text_path = TEXT_DIR / f"{slug(document_id)}.txt"
        pages_path = TEXT_DIR / f"{slug(document_id)}.pages.jsonl"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(combined, encoding="utf-8")
        with pages_path.open("w", encoding="utf-8") as handle:
            for page in pages:
                handle.write(json.dumps(page, ensure_ascii=False) + "\n")
        quality, needs_ocr, quality_flags = page_text_quality(combined, len(pages))
        status = "text_extracted" if combined else "text_empty_needs_ocr"
        return ExtractionResult(
            document_id=document_id,
            source_id=source_id,
            source_document_id=source_document_id,
            local_path=local_path,
            status=status,
            stage_status="extracted",
            extraction_method=extractor,
            page_count=len(pages),
            char_count=len(combined),
            text_path=relative_path(text_path),
            pages_path=relative_path(pages_path),
            text_quality_score=quality,
            ocr_required=needs_ocr,
            text_hash=text_hash,
            quality_flags=quality_flags,
        )
    except Exception as exc:  # pragma: no cover - defensive guard for production workers.
        return ExtractionResult(
            document_id=document_id,
            source_id=source_id,
            source_document_id=source_document_id,
            local_path=local_path,
            status="text_extraction_failed",
            stage_status="failed",
            error_code="unexpected_error",
            error_message=str(exc),
            quality_flags=("text_extraction_failed",),
        )


def candidate_filter_sql(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    clauses = [
        "d.acquisition_status = 'downloaded'",
        "d.local_path IS NOT NULL",
        "length(trim(d.local_path)) > 0",
    ]
    params: dict[str, Any] = {}
    if not args.force:
        if args.include_empty_page_docs:
            clauses.append(
                """
                (
                    NOT EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id)
                    OR NOT EXISTS (
                        SELECT 1 FROM pages p
                        WHERE p.document_id = d.document_id
                          AND length(trim(p.text)) > 0
                    )
                )
                """
            )
        else:
            clauses.append("NOT EXISTS (SELECT 1 FROM pages p WHERE p.document_id = d.document_id)")
    if args.document_ids_filter:
        clauses.append("d.document_id = ANY(%(document_ids)s)")
        params["document_ids"] = sorted(args.document_ids_filter)
    if args.source_id:
        clauses.append("d.source_id = ANY(%(source_ids)s)")
        params["source_ids"] = sorted(args.source_id)
    if args.year:
        clauses.append("d.year = ANY(%(years)s)")
        params["years"] = [int(year) for year in args.year]
    return " AND ".join(f"({clause})" for clause in clauses), params


def fetch_candidates(conn: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
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
            d.legal_status, d.notes
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
                %(ingestion_run_id)s, %(source_id)s, 'pdf_text_extraction_to_pages',
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
                        "force": args.force,
                        "include_empty_page_docs": args.include_empty_page_docs,
                        "allow_non_pdf": args.allow_non_pdf,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: ExtractionSummary) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET status = %(status)s,
                completed_at = now(),
                document_count = %(document_count)s,
                page_count = %(page_count)s,
                error_count = %(error_count)s,
                output = CAST(%(output)s AS jsonb),
                updated_at = now()
            WHERE ingestion_run_id = %(ingestion_run_id)s
            """,
            {
                "status": "failed" if summary.failed_count else "complete",
                "document_count": summary.processed_count,
                "page_count": summary.pages_upserted,
                "error_count": summary.failed_count,
                "ingestion_run_id": ingestion_run_id,
                "output": json.dumps(
                    {
                        "candidate_count": summary.candidate_count,
                        "processed_count": summary.processed_count,
                        "extracted_count": summary.extracted_count,
                        "empty_count": summary.empty_count,
                        "skipped_count": summary.skipped_count,
                        "failed_count": summary.failed_count,
                        "pages_upserted": summary.pages_upserted,
                        "chars_extracted": summary.chars_extracted,
                        "status_counts": summary.status_counts or {},
                    },
                    ensure_ascii=False,
                ),
            },
        )


def quality_flags_for_page(text_value: str, error: str) -> list[str]:
    flags: list[str] = []
    if error:
        flags.append("page_extraction_error")
    if not text_value.strip():
        flags.append("empty_page_text")
    if len(text_value.strip()) < 25:
        flags.append("very_short_page_text")
    return flags


def iter_page_artifact(pages_path: str) -> Iterable[dict[str, Any]]:
    path = resolve_local_path(pages_path)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                raw = json.loads(line)
                text_value = normalize_text(str(raw.get("text") or ""))
                yield {
                    "page_number": int(raw.get("page") or raw.get("page_number") or 0),
                    "text": text_value,
                    "error": str(raw.get("error") or ""),
                }


def upsert_pages(conn: Any, result: ExtractionResult) -> int:
    if not result.pages_path:
        return 0
    rows = []
    for page in iter_page_artifact(result.pages_path):
        page_number = int(page["page_number"])
        if page_number <= 0:
            continue
        page_text = str(page["text"] or "")
        rows.append(
            {
                "page_id": stable_page_id(result.document_id, "text", page_number),
                "document_id": result.document_id,
                "page_number": page_number,
                "text": page_text,
                "text_hash": stable_hash(page_text),
                "extraction_method": "text",
                "quality_flags": quality_flags_for_page(page_text, str(page.get("error") or "")),
            }
        )
    if not rows:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO pages (
                page_id, document_id, page_number, text, text_hash,
                extraction_method, quality_flags, layout
            )
            VALUES (
                %(page_id)s, %(document_id)s, %(page_number)s, %(text)s, %(text_hash)s,
                %(extraction_method)s, %(quality_flags)s, '{}'::jsonb
            )
            ON CONFLICT (document_id, page_number, extraction_method) DO UPDATE SET
                text = EXCLUDED.text,
                text_hash = EXCLUDED.text_hash,
                quality_flags = EXCLUDED.quality_flags
            """,
            rows,
        )
    return len(rows)


def update_document_and_event(
    conn: Any,
    *,
    row: dict[str, Any],
    result: ExtractionResult,
    ingestion_run_id: str,
    pages_upserted: int,
) -> None:
    metadata = {
        "text_path": result.text_path,
        "pages_path": result.pages_path,
        "char_count": result.char_count,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }
    note = ""
    if result.stage_status == "extracted":
        note = (
            f"text_path={result.text_path}; pages_path={result.pages_path}; "
            f"pages={result.page_count}; chars={result.char_count}; "
            f"extractor={result.extraction_method}; db_ingestion_run={ingestion_run_id}"
        )
    existing_notes = str(row.get("notes") or "")
    notes = f"{existing_notes}; {note}" if existing_notes and note and note not in existing_notes else note or existing_notes
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE documents
            SET extraction_status = %(extraction_status)s,
                ocr_required = %(ocr_required)s,
                text_quality_score = %(text_quality_score)s,
                notes = %(notes)s,
                current_ingestion_run_id = %(ingestion_run_id)s,
                last_ingested_at = now(),
                last_checked = now(),
                updated_at = now()
            WHERE document_id = %(document_id)s
            """,
            {
                "document_id": result.document_id,
                "extraction_status": result.status,
                "ocr_required": result.ocr_required,
                "text_quality_score": result.text_quality_score,
                "notes": notes,
                "ingestion_run_id": ingestion_run_id,
            },
        )
        cursor.execute(
            """
            INSERT INTO document_ingestion_events (
                ingestion_run_id, document_id, source_id, source_document_id,
                local_path, file_hash, stage, status, extraction_method,
                ocr_required, page_count, text_hash, text_quality_score,
                quality_flags, error_code, error_message, metadata
            )
            VALUES (
                %(ingestion_run_id)s, %(document_id)s, %(source_id)s, %(source_document_id)s,
                %(local_path)s, %(file_hash)s, 'pdf_text_extraction',
                %(stage_status)s, %(extraction_method)s, %(ocr_required)s,
                %(page_count)s, %(text_hash)s, %(text_quality_score)s,
                %(quality_flags)s, %(error_code)s, %(error_message)s,
                CAST(%(metadata)s AS jsonb)
            )
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "document_id": result.document_id,
                "source_id": result.source_id,
                "source_document_id": result.source_document_id,
                "local_path": result.local_path,
                "file_hash": row.get("file_hash"),
                "stage_status": result.stage_status,
                "extraction_method": result.extraction_method or None,
                "ocr_required": result.ocr_required,
                "page_count": pages_upserted,
                "text_hash": result.text_hash or None,
                "text_quality_score": result.text_quality_score,
                "quality_flags": list(result.quality_flags),
                "error_code": result.error_code or None,
                "error_message": result.error_message or None,
                "metadata": json.dumps(metadata, ensure_ascii=False),
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


def write_report(report: TextIO | None, result: ExtractionResult, pages_upserted: int) -> None:
    if report is None:
        return
    report.write(json.dumps(asdict(result) | {"pages_upserted": pages_upserted}, ensure_ascii=False) + "\n")
    report.flush()


def print_progress(summary: ExtractionSummary, *, final: bool = False) -> None:
    print(
        json.dumps(
            {
                "event": "final" if final else "progress",
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "extracted_count": summary.extracted_count,
                "empty_count": summary.empty_count,
                "skipped_count": summary.skipped_count,
                "failed_count": summary.failed_count,
                "pages_upserted": summary.pages_upserted,
                "chars_extracted": summary.chars_extracted,
                "status_counts": summary.status_counts or {},
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def submit_bounded(
    executor: ProcessPoolExecutor,
    rows: list[dict[str, Any]],
    *,
    allow_non_pdf: bool,
    max_pending: int,
):
    iterator = iter(rows)
    pending = {}
    for _ in range(max_pending):
        try:
            row = next(iterator)
        except StopIteration:
            break
        pending[executor.submit(extract_document, row, allow_non_pdf=allow_non_pdf)] = row
    while pending:
        done, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            row = pending.pop(future)
            yield row, future.result()
            try:
                next_row = next(iterator)
            except StopIteration:
                continue
            pending[executor.submit(extract_document, next_row, allow_non_pdf=allow_non_pdf)] = next_row


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        candidates = fetch_candidates(conn, args)
        summary = ExtractionSummary(candidate_count=len(candidates))
        if not args.execute:
            counts: dict[str, int] = {}
            for row in candidates:
                counts[str(row.get("source_id") or "")] = counts.get(str(row.get("source_id") or ""), 0) + 1
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "candidate_count": len(candidates),
                        "source_counts": dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:30]),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        ingestion_run_id = f"pdf_text_extract_pages_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        start_ingestion_run(conn, args=args, ingestion_run_id=ingestion_run_id)
        conn.commit()
        report = open_report(args.report_path)
        try:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                for row, result in submit_bounded(
                    executor,
                    candidates,
                    allow_non_pdf=args.allow_non_pdf,
                    max_pending=max(args.workers * 2, 1),
                ):
                    pages_upserted = 0
                    if result.stage_status == "extracted":
                        pages_upserted = upsert_pages(conn, result)
                    update_document_and_event(
                        conn,
                        row=row,
                        result=result,
                        ingestion_run_id=ingestion_run_id,
                        pages_upserted=pages_upserted,
                    )
                    summary.add(result, pages_upserted=pages_upserted)
                    write_report(report, result, pages_upserted)
                    if summary.processed_count % args.batch_size == 0:
                        conn.commit()
                    if args.progress_every and summary.processed_count % args.progress_every == 0:
                        print_progress(summary)
            finish_ingestion_run(conn, ingestion_run_id=ingestion_run_id, summary=summary)
            conn.commit()
        finally:
            if report is not None:
                report.close()

    print_progress(summary, final=True)
    print(
        json.dumps(
            {
                "ingestion_run_id": ingestion_run_id if args.execute else None,
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "extracted_count": summary.extracted_count,
                "empty_count": summary.empty_count,
                "skipped_count": summary.skipped_count,
                "failed_count": summary.failed_count,
                "pages_upserted": summary.pages_upserted,
                "chars_extracted": summary.chars_extracted,
                "status_counts": summary.status_counts or {},
                "results_preview": summary.results_preview or [],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
