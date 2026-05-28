#!/usr/bin/env python3
"""OCR downloaded PDFs that have page shells but no usable page text.

This is the DB-backed production OCR backfill path. It renders PDFs with
PDFium, falls back to PyMuPDF when PDFium cannot open an otherwise recoverable
PDF, OCRs each page with Tesseract, writes durable OCR artifacts, and upserts
canonical `pages` rows with extraction_method='ocr'. ZIP bundles containing
PDFs are treated as one logical document with continuous page numbering.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import multiprocessing as mp
import os
import statistics
import subprocess
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


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
OCR_DIR = PROJECT_ROOT / "data" / "extracted" / "ocr_postgres"
RUN_VERSION = "2026-05-26"


@dataclass(frozen=True)
class OcrResult:
    document_id: str
    source_id: str
    source_document_id: str
    local_path: str
    status: str
    stage_status: str
    language: str
    dpi: int
    page_count: int = 0
    pages_ocr_done: int = 0
    char_count: int = 0
    mean_confidence: float = 0.0
    min_page_confidence: float = 0.0
    low_confidence_pages: tuple[int, ...] = ()
    confidence_band: str = ""
    text_path: str = ""
    pages_path: str = ""
    text_hash: str = ""
    text_quality_score: float | None = None
    ocr_required: bool | None = None
    error_code: str = ""
    error_message: str = ""


@dataclass
class OcrSummary:
    candidate_count: int = 0
    processed_count: int = 0
    completed_count: int = 0
    empty_count: int = 0
    failed_count: int = 0
    pages_upserted: int = 0
    chars_extracted: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: OcrResult, *, pages_upserted: int) -> None:
        self.processed_count += 1
        self.pages_upserted += pages_upserted
        self.chars_extracted += result.char_count
        if result.stage_status == "extracted":
            if result.status == "text_empty_needs_ocr":
                self.empty_count += 1
            else:
                self.completed_count += 1
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
    parser.add_argument("--execute", action="store_true", help="Run OCR and write Postgres rows.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--year", action="append")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--tessdata-dir", help="Optional tessdata directory containing .traineddata files.")
    parser.add_argument("--page-timeout", type=int, default=180)
    parser.add_argument("--document-timeout", type=int, default=900)
    parser.add_argument("--low-confidence-threshold", type=float, default=70.0)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--report-path")
    parser.add_argument("--force", action="store_true", help="Retry selected PDFs even if OCR pages already exist.")
    parser.add_argument(
        "--include-extraction-failed",
        action="store_true",
        help="Attempt OCR on selected PDFs whose previous text-layer extraction failed.",
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


def stable_page_id(document_id: str, extraction_method: str, page_number: int) -> str:
    raw = f"{document_id}:{extraction_method}:{page_number}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"page_{document_id}_{extraction_method}_{page_number:05d}_{digest}"


def resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def ensure_runtime() -> None:
    if not shutil_which("tesseract"):
        raise SystemExit("tesseract is required for OCR and was not found on PATH")
    try:
        import PIL.Image  # noqa: F401
        import pypdfium2  # noqa: F401
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with pypdfium2 and Pillow installed.") from exc


def shutil_which(command: str) -> str:
    from shutil import which

    return which(command) or ""


def tsv_to_text_and_confidence(tsv: str) -> tuple[str, float, int]:
    lines_by_key: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for index, line in enumerate(tsv.splitlines()):
        if index == 0:
            continue
        columns = line.split("\t")
        if len(columns) < 12:
            continue
        try:
            block = int(columns[2])
            par = int(columns[3])
            line_no = int(columns[4])
            confidence = float(columns[10])
        except ValueError:
            continue
        text = columns[11].strip()
        if not text:
            continue
        if confidence >= 0:
            confidences.append(confidence)
        lines_by_key.setdefault((block, par, line_no), []).append(text)
    text_lines = [" ".join(words) for _key, words in sorted(lines_by_key.items())]
    mean_confidence = statistics.mean(confidences) if confidences else 0.0
    return normalize_text("\n".join(text_lines)), mean_confidence, len(confidences)


def ocr_page(image_path: Path, *, language: str, timeout: int, tessdata_dir: str = "") -> tuple[str, float, int]:
    env = os.environ.copy()
    if tessdata_dir:
        env["TESSDATA_PREFIX"] = tessdata_dir
    completed = subprocess.run(
        [
            "tesseract",
            str(image_path),
            "stdout",
            "-l",
            language,
            "--psm",
            "1",
            "-c",
            "tessedit_create_tsv=1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"tesseract exited {completed.returncode}")
    return tsv_to_text_and_confidence(completed.stdout)


def pdf_sources_for_ocr(path: Path, tmp_dir: Path) -> list[tuple[str, Path]]:
    if path.suffix.lower() == ".pdf":
        return [(path.name, path)]
    if path.suffix.lower() != ".zip":
        raise RuntimeError(f"unsupported file type: {path.suffix.lower() or 'unknown'}")
    sources: list[tuple[str, Path]] = []
    with zipfile.ZipFile(path) as archive:
        for index, member in enumerate(sorted(archive.infolist(), key=lambda item: item.filename), start=1):
            member_name = member.filename
            if member.is_dir() or not member_name.lower().endswith(".pdf"):
                continue
            safe_name = Path(member_name).name or f"member_{index:05d}.pdf"
            target = tmp_dir / "zip_members" / f"{index:05d}_{safe_name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as handle:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    handle.write(chunk)
            sources.append((member_name, target))
    if not sources:
        raise RuntimeError("ZIP archive does not contain PDF files")
    return sources


def _iter_pdfium_rendered_pages(source_pdf_path: Path, tmp_dir: Path, *, scale: float, start_page_number: int) -> Iterable[tuple[int, Path]]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(source_pdf_path))
    try:
        for page_index in range(len(pdf)):
            page_number = start_page_number + page_index
            page = pdf[page_index]
            try:
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                image_path = tmp_dir / f"page_{page_number:05d}.png"
                image.save(image_path)
                yield page_number, image_path
            finally:
                page.close()
    finally:
        pdf.close()


def _iter_pymupdf_rendered_pages(source_pdf_path: Path, tmp_dir: Path, *, scale: float, start_page_number: int) -> Iterable[tuple[int, Path]]:
    import fitz

    tools = getattr(fitz, "TOOLS", None)
    if tools is not None:
        for method_name in ("mupdf_display_errors", "mupdf_display_warnings"):
            method = getattr(tools, method_name, None)
            if method is not None:
                method(False)

    document = fitz.open(str(source_pdf_path))
    try:
        matrix = fitz.Matrix(scale, scale)
        for page_index in range(document.page_count):
            page_number = start_page_number + page_index
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = tmp_dir / f"page_{page_number:05d}.png"
            pixmap.save(str(image_path))
            yield page_number, image_path
    finally:
        document.close()


def iter_rendered_page_images(source_pdf_path: Path, tmp_dir: Path, *, scale: float, start_page_number: int) -> Iterable[tuple[int, Path]]:
    try:
        yield from _iter_pdfium_rendered_pages(
            source_pdf_path,
            tmp_dir,
            scale=scale,
            start_page_number=start_page_number,
        )
        return
    except Exception as pdfium_exc:
        pdfium_error = str(pdfium_exc)
    try:
        yield from _iter_pymupdf_rendered_pages(
            source_pdf_path,
            tmp_dir,
            scale=scale,
            start_page_number=start_page_number,
        )
    except Exception as pymupdf_exc:
        raise RuntimeError(
            "failed to render PDF with PDFium and PyMuPDF; "
            f"pdfium={pdfium_error}; pymupdf={pymupdf_exc}"
        ) from pymupdf_exc


def confidence_band(mean_confidence: float, low_confidence_pages: tuple[int, ...], char_count: int) -> str:
    if char_count == 0:
        return "empty"
    if mean_confidence >= 85 and not low_confidence_pages:
        return "high"
    if mean_confidence >= 70:
        return "medium"
    return "low"


def text_quality_score(mean_confidence: float, char_count: int, page_count: int) -> float:
    if char_count == 0:
        return 0.0
    density = char_count / max(1, page_count)
    confidence_component = min(1.0, max(0.0, mean_confidence / 100.0))
    density_component = 1.0 if density >= 500 else 0.6 if density >= 100 else 0.25
    return round(min(confidence_component, density_component), 4)


def ocr_document(row: dict[str, Any], args_values: dict[str, Any]) -> OcrResult:
    document_id = str(row.get("document_id") or "")
    source_id = str(row.get("source_id") or "")
    source_document_id = str(row.get("source_document_id") or "")
    local_path = str(row.get("local_path") or "")
    language = str(args_values["language"])
    dpi = int(args_values["dpi"])
    try:
        pdf_path = resolve_local_path(local_path)
        if not pdf_path.is_file():
            return OcrResult(
                document_id=document_id,
                source_id=source_id,
                source_document_id=source_document_id,
                local_path=local_path,
                status="ocr_failed",
                stage_status="failed",
                language=language,
                dpi=dpi,
                error_code="missing_local_file",
                error_message=local_path,
            )
        if pdf_path.suffix.lower() not in {".pdf", ".zip"}:
            return OcrResult(
                document_id=document_id,
                source_id=source_id,
                source_document_id=source_document_id,
                local_path=local_path,
                status="ocr_failed",
                stage_status="failed",
                language=language,
                dpi=dpi,
                error_code="unsupported_file_type",
                error_message=pdf_path.suffix.lower() or "unknown",
            )

        scale = dpi / 72
        page_rows: list[dict[str, Any]] = []
        page_texts: list[str] = []
        page_confidences: list[float] = []
        low_confidence_pages: list[int] = []
        page_count = 0
        with tempfile.TemporaryDirectory(prefix=f"sllegal_ocr_{document_id}_") as tmp_name:
            tmp_dir = Path(tmp_name)
            for source_name, source_pdf_path in pdf_sources_for_ocr(pdf_path, tmp_dir):
                for page_number, image_path in iter_rendered_page_images(
                    source_pdf_path,
                    tmp_dir,
                    scale=scale,
                    start_page_number=page_count + 1,
                ):
                    text, mean_confidence, word_count = ocr_page(
                        image_path,
                        language=language,
                        timeout=int(args_values["page_timeout"]),
                        tessdata_dir=str(args_values.get("tessdata_dir") or ""),
                    )
                    page_texts.append(text)
                    page_confidences.append(mean_confidence)
                    low_confidence = mean_confidence < float(args_values["low_confidence_threshold"]) or not text.strip()
                    if low_confidence:
                        low_confidence_pages.append(page_number)
                    page_rows.append(
                        {
                            "page": page_number,
                            "text": text,
                            "mean_confidence": round(mean_confidence, 2),
                            "word_count": word_count,
                            "source_file": source_name,
                            "requires_manual_verification": low_confidence,
                        }
                    )
                    page_count = page_number

        combined = "\n\n".join(page_texts).strip()
        text_path = OCR_DIR / f"{document_id}.ocr.txt"
        pages_path = OCR_DIR / f"{document_id}.ocr.pages.jsonl"
        OCR_DIR.mkdir(parents=True, exist_ok=True)
        text_path.write_text(combined, encoding="utf-8")
        with pages_path.open("w", encoding="utf-8") as handle:
            for page_row in page_rows:
                handle.write(json.dumps(page_row, ensure_ascii=False) + "\n")
        mean_confidence = statistics.mean(page_confidences) if page_confidences else 0.0
        min_page_confidence = min(page_confidences) if page_confidences else 0.0
        band = confidence_band(mean_confidence, tuple(low_confidence_pages), len(combined))
        score = text_quality_score(mean_confidence, len(combined), page_count)
        return OcrResult(
            document_id=document_id,
            source_id=source_id,
            source_document_id=source_document_id,
            local_path=local_path,
            status="text_extracted" if combined else "text_empty_needs_ocr",
            stage_status="extracted",
            language=language,
            dpi=dpi,
            page_count=page_count,
            pages_ocr_done=page_count,
            char_count=len(combined),
            mean_confidence=round(mean_confidence, 2),
            min_page_confidence=round(min_page_confidence, 2),
            low_confidence_pages=tuple(low_confidence_pages),
            confidence_band=band,
            text_path=relative_path(text_path),
            pages_path=relative_path(pages_path),
            text_hash=stable_hash(combined) if combined else "",
            text_quality_score=score,
            ocr_required=not bool(combined),
        )
    except Exception as exc:
        return OcrResult(
            document_id=document_id,
            source_id=source_id,
            source_document_id=source_document_id,
            local_path=local_path,
            status="ocr_failed",
            stage_status="failed",
            language=language,
            dpi=dpi,
            error_code="ocr_failed",
            error_message=str(exc),
        )


def _ocr_document_child(row: dict[str, Any], args_values: dict[str, Any], queue: mp.Queue) -> None:
    queue.put(ocr_document(row, args_values))


def timeout_result(row: dict[str, Any], args: argparse.Namespace) -> OcrResult:
    return OcrResult(
        document_id=str(row.get("document_id") or ""),
        source_id=str(row.get("source_id") or ""),
        source_document_id=str(row.get("source_document_id") or ""),
        local_path=str(row.get("local_path") or ""),
        status="ocr_failed",
        stage_status="failed",
        language=args.language,
        dpi=args.dpi,
        error_code="document_timeout",
        error_message=f"document_timeout_after_{args.document_timeout}_seconds",
    )


def ocr_document_with_timeout(row: dict[str, Any], args: argparse.Namespace) -> OcrResult:
    timeout = max(1, args.document_timeout)
    queue: mp.Queue = mp.Queue(maxsize=1)
    process = mp.Process(target=_ocr_document_child, args=(row, vars(args).copy(), queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        return timeout_result(row, args)
    if not queue.empty():
        return queue.get()
    return OcrResult(
        document_id=str(row.get("document_id") or ""),
        source_id=str(row.get("source_id") or ""),
        source_document_id=str(row.get("source_document_id") or ""),
        local_path=str(row.get("local_path") or ""),
        status="ocr_failed",
        stage_status="failed",
        language=args.language,
        dpi=args.dpi,
        error_code="ocr_process_failed",
        error_message=f"ocr_process_exit_{process.exitcode}",
    )


def candidate_filter_sql(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    clauses = [
        "d.acquisition_status = 'downloaded'",
        "d.local_path IS NOT NULL",
        "length(trim(d.local_path)) > 0",
        "(lower(d.local_path) LIKE '%%.pdf' OR lower(d.local_path) LIKE '%%.zip')",
    ]
    params: dict[str, Any] = {}
    if not args.force:
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1 FROM retrieval_chunks rc
                WHERE rc.document_id = d.document_id
            )
            """
        )
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1 FROM pages p
                WHERE p.document_id = d.document_id
                  AND p.extraction_method = 'ocr'
                  AND length(trim(coalesce(p.text, ''))) > 0
            )
            """
        )
    recovery_predicates = [
        """
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
        """,
    ]
    if args.include_extraction_failed:
        recovery_predicates.append("d.extraction_status IN ('text_extraction_failed', 'ocr_failed', 'not_started')")
    clauses.append("(" + " OR ".join(f"({predicate})" for predicate in recovery_predicates) + ")")
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
                %(ingestion_run_id)s, %(source_id)s, 'ocr_empty_pdf_pages_to_postgres',
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
                        "dpi": args.dpi,
                        "language": args.language,
                        "tessdata_dir": args.tessdata_dir,
                        "force": args.force,
                        "include_extraction_failed": args.include_extraction_failed,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: OcrSummary) -> None:
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
                "output": json.dumps(asdict(summary), ensure_ascii=False),
            },
        )


def iter_page_artifact(pages_path: str) -> Iterable[dict[str, Any]]:
    path = resolve_local_path(pages_path)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                raw = json.loads(line)
                yield {
                    "page_number": int(raw.get("page") or raw.get("page_number") or 0),
                    "text": normalize_text(str(raw.get("text") or "")),
                    "mean_confidence": float(raw.get("mean_confidence") or 0.0),
                    "requires_manual_verification": bool(raw.get("requires_manual_verification")),
                }


def quality_flags_for_page(page_text: str, confidence: float, requires_manual_verification: bool) -> list[str]:
    flags = ["ocr_text"]
    if not page_text.strip():
        flags.append("empty_page_text")
    if len(page_text.strip()) < 25:
        flags.append("very_short_page_text")
    if confidence < 70 or requires_manual_verification:
        flags.append("low_confidence_ocr")
    return flags


def upsert_pages(conn: Any, result: OcrResult) -> int:
    if not result.pages_path:
        return 0
    rows = []
    for page in iter_page_artifact(result.pages_path):
        page_number = int(page["page_number"])
        if page_number <= 0:
            continue
        page_text = str(page["text"] or "")
        confidence = float(page["mean_confidence"])
        rows.append(
            {
                "page_id": stable_page_id(result.document_id, "ocr", page_number),
                "document_id": result.document_id,
                "page_number": page_number,
                "text": page_text,
                "text_hash": stable_hash(page_text),
                "extraction_method": "ocr",
                "ocr_confidence": confidence,
                "quality_flags": quality_flags_for_page(
                    page_text,
                    confidence,
                    bool(page["requires_manual_verification"]),
                ),
            }
        )
    if not rows:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO pages (
                page_id, document_id, page_number, text, text_hash,
                extraction_method, ocr_confidence, quality_flags, layout
            )
            VALUES (
                %(page_id)s, %(document_id)s, %(page_number)s, %(text)s, %(text_hash)s,
                %(extraction_method)s, %(ocr_confidence)s, %(quality_flags)s, '{}'::jsonb
            )
            ON CONFLICT (document_id, page_number, extraction_method) DO UPDATE SET
                text = EXCLUDED.text,
                text_hash = EXCLUDED.text_hash,
                ocr_confidence = EXCLUDED.ocr_confidence,
                quality_flags = EXCLUDED.quality_flags
            """,
            rows,
        )
    return len(rows)


def update_document_and_event(
    conn: Any,
    *,
    row: dict[str, Any],
    result: OcrResult,
    ingestion_run_id: str,
    pages_upserted: int,
) -> None:
    note = ""
    if result.stage_status == "extracted":
        note = (
            f"ocr_text_path={result.text_path}; ocr_pages_path={result.pages_path}; "
            f"ocr_pages={result.page_count}; ocr_chars={result.char_count}; "
            f"ocr_confidence={result.mean_confidence}; ocr_band={result.confidence_band}; "
            f"ocr_ingestion_run={ingestion_run_id}"
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
                ocr_required, ocr_engine, page_count, text_hash, text_quality_score,
                quality_flags, error_code, error_message, metadata
            )
            VALUES (
                %(ingestion_run_id)s, %(document_id)s, %(source_id)s, %(source_document_id)s,
                %(local_path)s, %(file_hash)s, 'ocr_text_recovery',
                %(stage_status)s, 'ocr', %(ocr_required)s, 'tesseract',
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
                "ocr_required": result.ocr_required,
                "page_count": pages_upserted,
                "text_hash": result.text_hash or None,
                "text_quality_score": result.text_quality_score,
                "quality_flags": ["ocr_text", *(["low_confidence_ocr"] if result.confidence_band == "low" else [])],
                "error_code": result.error_code or None,
                "error_message": result.error_message or None,
                "metadata": json.dumps(
                    {
                        "ocr_text_path": result.text_path,
                        "ocr_pages_path": result.pages_path,
                        "char_count": result.char_count,
                        "language": result.language,
                        "dpi": result.dpi,
                        "low_confidence_pages": list(result.low_confidence_pages),
                    },
                    ensure_ascii=False,
                ),
            },
        )


def write_report(handle: TextIO | None, result: OcrResult, *, pages_upserted: int) -> None:
    if handle is None:
        return
    handle.write(json.dumps(asdict(result) | {"pages_upserted": pages_upserted}, ensure_ascii=False) + "\n")
    handle.flush()


def open_report(path_value: str | None) -> TextIO | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def process_batch(conn: Any, *, rows: list[dict[str, Any]], args: argparse.Namespace, ingestion_run_id: str, report: TextIO | None, summary: OcrSummary) -> None:
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(ocr_document_with_timeout, row, args): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            result = future.result()
            pages_upserted = 0
            if args.execute:
                pages_upserted = upsert_pages(conn, result)
                update_document_and_event(
                    conn,
                    row=row,
                    result=result,
                    ingestion_run_id=ingestion_run_id,
                    pages_upserted=pages_upserted,
                )
            summary.add(result, pages_upserted=pages_upserted)
            write_report(report, result, pages_upserted=pages_upserted)
            if args.progress_every and summary.processed_count % args.progress_every == 0:
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "processed": summary.processed_count,
                            "completed": summary.completed_count,
                            "empty": summary.empty_count,
                            "failed": summary.failed_count,
                            "pages_upserted": summary.pages_upserted,
                            "chars_extracted": summary.chars_extracted,
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
    ensure_runtime()
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    ingestion_run_id = "ocr_empty_pdf_pages_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        candidates = fetch_candidates(conn, args)
        summary = OcrSummary(candidate_count=len(candidates))
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
                            }
                            for row in candidates[:20]
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        if args.execute:
            start_ingestion_run(conn, args=args, ingestion_run_id=ingestion_run_id)
            conn.commit()
        report = open_report(args.report_path)
        try:
            for start in range(0, len(candidates), args.batch_size):
                batch = candidates[start : start + args.batch_size]
                process_batch(
                    conn,
                    rows=batch,
                    args=args,
                    ingestion_run_id=ingestion_run_id,
                    report=report,
                    summary=summary,
                )
        finally:
            if report is not None:
                report.close()
        if args.execute:
            finish_ingestion_run(conn, ingestion_run_id=ingestion_run_id, summary=summary)
            conn.commit()
    payload = asdict(summary) | {"ingestion_run_id": ingestion_run_id if args.execute else None}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
