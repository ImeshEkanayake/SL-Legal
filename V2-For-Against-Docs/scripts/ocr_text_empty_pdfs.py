#!/usr/bin/env python3
"""OCR downloaded PDFs that produced empty extracted text.

This script intentionally writes OCR outputs and an OCR registry first. It does
not edit document_manifest.csv while the normal text extractor is running, so
parallel OCR cannot clobber manifest checkpoints.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import tempfile
import time
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = PROJECT_ROOT / ".codex_deps" / "ocr"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

import pypdfium2 as pdfium


MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
OCR_DIR = PROJECT_ROOT / "data" / "extracted" / "ocr"
OCR_REGISTRY_PATH = PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"

PARLIAMENT_SOURCES = {
    "PARL_HANSARD_DAILY",
    "PARL_HANSARD_VOLUMES",
    "PARL_COMMITTEE_REPORTS",
    "PARL_MINISTERIAL_CONSULTATIVE_REPORTS",
    "PARL_CONSULTATIVE_MONTHLY_REPORTS",
    "PARL_MINUTES",
    "PARL_PAPERS_PRESENTED",
    "PARL_SPEAKER_PAPERS",
    "PARL_ORDER_PAPERS",
    "PARL_ORDER_BOOKS",
    "PARL_ORDER_OF_BUSINESS",
    "PARL_ADDENDUMS",
    "PARL_SC_DECISIONS_ON_BILLS",
    "PARL_PROGRESS_REPORTS",
}

OCR_FIELDS = [
    "document_id",
    "source_id",
    "document_type",
    "title",
    "year",
    "local_path",
    "ocr_status",
    "language",
    "dpi",
    "page_count",
    "pages_ocr_done",
    "char_count",
    "mean_confidence",
    "min_page_confidence",
    "low_confidence_pages",
    "confidence_band",
    "ocr_text_path",
    "ocr_pages_path",
    "error",
    "last_checked",
]


@dataclass
class OcrResult:
    document_id: str
    source_id: str
    document_type: str
    title: str
    year: str
    local_path: str
    ocr_status: str
    language: str
    dpi: int
    page_count: int = 0
    pages_ocr_done: int = 0
    char_count: int = 0
    mean_confidence: float = 0.0
    min_page_confidence: float = 0.0
    low_confidence_pages: list[int] | None = None
    confidence_band: str = ""
    ocr_text_path: str = ""
    ocr_pages_path: str = ""
    error: str = ""
    last_checked: str = ""

    def as_row(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "source_id": self.source_id,
            "document_type": self.document_type,
            "title": self.title,
            "year": self.year,
            "local_path": self.local_path,
            "ocr_status": self.ocr_status,
            "language": self.language,
            "dpi": str(self.dpi),
            "page_count": str(self.page_count),
            "pages_ocr_done": str(self.pages_ocr_done),
            "char_count": str(self.char_count),
            "mean_confidence": f"{self.mean_confidence:.2f}",
            "min_page_confidence": f"{self.min_page_confidence:.2f}",
            "low_confidence_pages": ",".join(str(page) for page in self.low_confidence_pages or []),
            "confidence_band": self.confidence_band,
            "ocr_text_path": self.ocr_text_path,
            "ocr_pages_path": self.ocr_pages_path,
            "error": self.error,
            "last_checked": self.last_checked,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_ocr_runtime() -> None:
    try:
        import PIL.Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit("Missing dependency: install Pillow before running OCR.") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def merge_registry(results: Iterable[OcrResult]) -> None:
    existing = read_csv(OCR_REGISTRY_PATH)
    merged: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing:
        document_id = row.get("document_id", "")
        if document_id and document_id not in merged:
            order.append(document_id)
        if document_id:
            merged[document_id] = row
    for result in results:
        row = result.as_row()
        document_id = row["document_id"]
        if document_id not in merged:
            order.append(document_id)
        merged[document_id] = row
    write_csv(OCR_REGISTRY_PATH, OCR_FIELDS, [merged[document_id] for document_id in order if document_id])


def completed_document_ids() -> set[str]:
    done: set[str] = set()
    for row in read_csv(OCR_REGISTRY_PATH):
        # Treat failures as processed for the normal queue so one damaged PDF
        # cannot block the OCR run forever. Use --force to retry them later.
        if row.get("ocr_status"):
            done.add(row.get("document_id", ""))
    return done


def row_requires_ocr(row: dict[str, str]) -> bool:
    if row.get("extraction_status") == "text_empty_needs_ocr":
        return True
    return row.get("ocr_required", "").strip().lower() in {"true", "1", "yes", "y"}


def tmux_session_exists(name: str) -> bool:
    if not name:
        return False
    return subprocess.run(
        ["tmux", "has-session", "-t", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def discover_tasks(args: argparse.Namespace, already_done: set[str]) -> list[dict[str, str]]:
    source_ids = set(args.source_id or [])
    document_ids = set(args.document_id or [])
    years = set(args.year or [])
    if args.parliament:
        source_ids |= PARLIAMENT_SOURCES
    rows = []
    for row in read_csv(MANIFEST_PATH):
        if row.get("acquisition_status") != "downloaded":
            continue
        if not row_requires_ocr(row):
            continue
        if source_ids and row.get("source_id") not in source_ids:
            continue
        if document_ids and row.get("document_id") not in document_ids:
            continue
        if years and row.get("year") not in years:
            continue
        if row.get("document_id") in already_done:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (row.get("source_id", ""), row.get("year", ""), row.get("document_id", "")))
    if args.limit:
        rows = rows[: args.limit]
    return rows


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
    return "\n".join(text_lines).strip(), mean_confidence, len(confidences)


def confidence_band(mean_confidence: float, low_confidence_pages: list[int], char_count: int) -> str:
    if char_count == 0:
        return "empty"
    if mean_confidence >= 85 and not low_confidence_pages:
        return "high"
    if mean_confidence >= 70:
        return "medium"
    return "low"


def ocr_page(image_path: Path, language: str, timeout: int) -> tuple[str, float, int]:
    completed = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", language, "--psm", "1", "tsv"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"tesseract exited {completed.returncode}")
    return tsv_to_text_and_confidence(completed.stdout)


def ocr_document(row: dict[str, str], args: argparse.Namespace) -> OcrResult:
    now = utc_now()
    document_id = row.get("document_id", "")
    result = OcrResult(
        document_id=document_id,
        source_id=row.get("source_id", ""),
        document_type=row.get("document_type", ""),
        title=row.get("title", ""),
        year=row.get("year", ""),
        local_path=row.get("local_path", ""),
        ocr_status="ocr_failed",
        language=args.language,
        dpi=args.dpi,
        low_confidence_pages=[],
        last_checked=now,
    )
    try:
        pdf_path = PROJECT_ROOT / row.get("local_path", "")
        if not pdf_path.exists():
            raise FileNotFoundError(str(pdf_path))
        pdf = pdfium.PdfDocument(str(pdf_path))
        page_count = len(pdf)
        result.page_count = page_count
        scale = args.dpi / 72
        pages: list[dict[str, object]] = []
        page_texts: list[str] = []
        page_confidences: list[float] = []
        with tempfile.TemporaryDirectory(prefix=f"sllegal_ocr_{document_id}_") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            for page_index in range(page_count):
                page_number = page_index + 1
                page = pdf[page_index]
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                image_path = tmp_dir / f"page_{page_number:04d}.png"
                image.save(image_path)
                text, mean_confidence, word_count = ocr_page(image_path, args.language, args.page_timeout)
                page_texts.append(text)
                page_confidences.append(mean_confidence)
                if mean_confidence < args.low_confidence_threshold or not text.strip():
                    result.low_confidence_pages.append(page_number)
                pages.append(
                    {
                        "page": page_number,
                        "text": text,
                        "mean_confidence": round(mean_confidence, 2),
                        "word_count": word_count,
                        "requires_manual_verification": mean_confidence < args.low_confidence_threshold or not text.strip(),
                    }
                )
                result.pages_ocr_done = page_number
        combined = "\n\n".join(page_texts).strip()
        text_path = OCR_DIR / f"{document_id}.ocr.txt"
        pages_path = OCR_DIR / f"{document_id}.ocr.pages.jsonl"
        OCR_DIR.mkdir(parents=True, exist_ok=True)
        text_path.write_text(combined, encoding="utf-8")
        with pages_path.open("w", encoding="utf-8") as handle:
            for page in pages:
                handle.write(json.dumps(page, ensure_ascii=False) + "\n")
        result.char_count = len(combined)
        result.mean_confidence = statistics.mean(page_confidences) if page_confidences else 0.0
        result.min_page_confidence = min(page_confidences) if page_confidences else 0.0
        result.confidence_band = confidence_band(result.mean_confidence, result.low_confidence_pages, result.char_count)
        result.ocr_text_path = str(text_path.relative_to(PROJECT_ROOT))
        result.ocr_pages_path = str(pages_path.relative_to(PROJECT_ROOT))
        if result.confidence_band == "high":
            result.ocr_status = "ocr_completed_high_confidence"
        elif result.confidence_band in {"medium", "low"}:
            result.ocr_status = f"ocr_completed_{result.confidence_band}_confidence"
        else:
            result.ocr_status = "ocr_completed_empty"
    except Exception as exc:
        result.error = str(exc)
        if result.pages_ocr_done:
            result.ocr_status = "ocr_partial_failed"
    return result


def timeout_result(row: dict[str, str], args: argparse.Namespace, seconds: int) -> OcrResult:
    return OcrResult(
        document_id=row.get("document_id", ""),
        source_id=row.get("source_id", ""),
        document_type=row.get("document_type", ""),
        title=row.get("title", ""),
        year=row.get("year", ""),
        local_path=row.get("local_path", ""),
        ocr_status="ocr_failed",
        language=args.language,
        dpi=args.dpi,
        error=f"document_timeout_after_{seconds}_seconds",
        last_checked=utc_now(),
    )


def _ocr_document_child(row: dict[str, str], args_values: dict[str, object], queue: mp.Queue) -> None:
    try:
        result = ocr_document(row, argparse.Namespace(**args_values))
        queue.put(result)
    except BaseException as exc:
        queue.put(
            OcrResult(
                document_id=row.get("document_id", ""),
                source_id=row.get("source_id", ""),
                document_type=row.get("document_type", ""),
                title=row.get("title", ""),
                year=row.get("year", ""),
                local_path=row.get("local_path", ""),
                ocr_status="ocr_failed",
                language=str(args_values.get("language", "eng")),
                dpi=int(args_values.get("dpi", 250)),
                error=str(exc),
                last_checked=utc_now(),
            )
        )


def ocr_document_with_timeout(row: dict[str, str], args: argparse.Namespace) -> OcrResult:
    timeout = max(1, args.document_timeout)
    queue: mp.Queue = mp.Queue(maxsize=1)
    args_values = vars(args).copy()
    process = mp.Process(target=_ocr_document_child, args=(row, args_values, queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        return timeout_result(row, args, timeout)
    if not queue.empty():
        return queue.get()
    if process.exitcode == 0:
        return OcrResult(
            document_id=row.get("document_id", ""),
            source_id=row.get("source_id", ""),
            document_type=row.get("document_type", ""),
            title=row.get("title", ""),
            year=row.get("year", ""),
            local_path=row.get("local_path", ""),
            ocr_status="ocr_failed",
            language=args.language,
            dpi=args.dpi,
            error="ocr_process_returned_no_result",
            last_checked=utc_now(),
        )
    return OcrResult(
        document_id=row.get("document_id", ""),
        source_id=row.get("source_id", ""),
        document_type=row.get("document_type", ""),
        title=row.get("title", ""),
        year=row.get("year", ""),
        local_path=row.get("local_path", ""),
        ocr_status="ocr_failed",
        language=args.language,
        dpi=args.dpi,
        error=f"ocr_process_exit_{process.exitcode}",
        last_checked=utc_now(),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR PDFs marked text_empty_needs_ocr.")
    parser.add_argument("--source-id", action="append", help="Limit OCR to source IDs.")
    parser.add_argument("--document-id", action="append", help="Limit OCR to one or more document IDs.")
    parser.add_argument("--year", action="append", help="Limit OCR to one or more years.")
    parser.add_argument("--parliament", action="store_true", help="Limit OCR to Parliament wave sources.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dpi", type=int, default=250)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--page-timeout", type=int, default=180)
    parser.add_argument("--document-timeout", type=int, default=600)
    parser.add_argument("--low-confidence-threshold", type=float, default=70.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--watch", action="store_true", help="Poll for new OCR tasks until watched session exits and idle limit is reached.")
    parser.add_argument("--watch-session", default="")
    parser.add_argument("--poll-seconds", type=int, default=90)
    parser.add_argument("--max-idle-rounds", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=1)
    return parser.parse_args(argv)


def run_batch(tasks: list[dict[str, str]], args: argparse.Namespace, processed_total: int) -> int:
    completed_count = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(ocr_document_with_timeout, row, args) for row in tasks]
        for future in as_completed(futures):
            result = future.result()
            merge_registry([result])
            completed_count += 1
            processed_total += 1
            if args.progress_every and (processed_total == 1 or processed_total % args.progress_every == 0):
                print(
                    f"ocr {processed_total} latest={result.document_id} status={result.ocr_status} "
                    f"pages={result.pages_ocr_done}/{result.page_count} conf={result.mean_confidence:.2f} chars={result.char_count}",
                    file=sys.stderr,
                    flush=True,
                )
    return completed_count


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ensure_ocr_runtime()
    processed_total = 0
    idle_rounds = 0
    processed_this_run: set[str] = set()
    while True:
        done = (set() if args.force else completed_document_ids()) | processed_this_run
        tasks = discover_tasks(args, done)
        if tasks:
            idle_rounds = 0
            batch = tasks[: max(1, args.batch_size)]
            processed_total += run_batch(batch, args, processed_total)
            processed_this_run.update(row.get("document_id", "") for row in batch)
            if args.limit and processed_total >= args.limit:
                break
            continue
        if not args.watch:
            break
        watched_running = tmux_session_exists(args.watch_session)
        if not watched_running:
            idle_rounds += 1
            if idle_rounds >= max(1, args.max_idle_rounds):
                break
        print(
            f"ocr idle tasks=0 watched_running={watched_running} idle_rounds={idle_rounds}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(max(1, args.poll_seconds))
    print(json.dumps({"processed": processed_total, "registry": str(OCR_REGISTRY_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
