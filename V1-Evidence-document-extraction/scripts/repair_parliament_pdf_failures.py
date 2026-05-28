#!/usr/bin/env python3
"""Repair Parliament PDFs that failed extraction.

The first Parliament extraction wave exposed two kinds of failures:

1. Local parser/environment issues, which should be retried after extractor
   fixes.
2. Truncated or empty PDFs, which should be re-downloaded from the official
   Parliament URL before extraction is retried.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
RUN_LOG_PATH = PROJECT_ROOT / "data" / "manifests" / "extraction_run_log.csv"
OCR_REGISTRY_PATH = PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"
REPAIR_REPORT_PATH = PROJECT_ROOT / "data" / "manifests" / "parliament_pdf_repair_report.csv"

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

NO_REDOWNLOAD_ERROR_PREFIXES = (
    "cryptography>=3.1 is required for AES algorithm",
    "argument of type 'NullObject'",
    "'utf-8' codec can't encode character",
)

REPAIR_FIELDS = [
    "document_id",
    "source_id",
    "title",
    "year",
    "action",
    "status",
    "old_size",
    "new_size",
    "error",
    "download_url",
    "local_path",
    "last_checked",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def append_note(row: dict[str, str], note: str) -> None:
    prior = row.get("notes", "")
    row["notes"] = f"{prior}; {note}" if prior else note


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_pdf_text_errors() -> dict[str, str]:
    _fields, rows = read_csv(RUN_LOG_PATH)
    errors: dict[str, str] = {}
    for row in rows:
        if row.get("run_type") != "pdf_text_extraction":
            continue
        raw = row.get("errors", "")
        if "parl_" not in raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        errors.clear()
        for item in parsed:
            document_id, _, error = item.partition(": ")
            if document_id:
                errors[document_id] = error
    return errors


def ocr_partial_ids() -> set[str]:
    _fields, rows = read_csv(OCR_REGISTRY_PATH)
    return {row.get("document_id", "") for row in rows if row.get("ocr_status") == "ocr_partial_failed"}


def remove_ocr_rows(document_ids: set[str]) -> None:
    if not document_ids or not OCR_REGISTRY_PATH.exists():
        return
    fields, rows = read_csv(OCR_REGISTRY_PATH)
    rows = [row for row in rows if row.get("document_id") not in document_ids]
    write_csv(OCR_REGISTRY_PATH, fields, rows)


def should_redownload(row: dict[str, str], error: str, partial_ocr: bool) -> bool:
    if partial_ocr:
        return True
    path = PROJECT_ROOT / row.get("local_path", "")
    if not path.exists() or path.stat().st_size == 0:
        return True
    if any(error.startswith(prefix) for prefix in NO_REDOWNLOAD_ERROR_PREFIXES):
        return False
    return True


def validate_pdf(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("downloaded file is empty")
    with path.open("rb") as handle:
        header = handle.read(1024)
    if b"%PDF-" not in header[:128]:
        raise RuntimeError("downloaded file does not look like a PDF")


def redownload(row: dict[str, str], max_time: int) -> tuple[int, int]:
    url = row.get("download_url", "")
    if not url:
        raise RuntimeError("missing download_url")
    local_path = PROJECT_ROOT / row.get("local_path", "")
    if not row.get("local_path"):
        raise RuntimeError("missing local_path")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    old_size = local_path.stat().st_size if local_path.exists() else 0
    tmp_path = local_path.with_suffix(local_path.suffix + ".repair_tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        "6",
        "--retry-delay",
        "3",
        "--retry-all-errors",
        "--connect-timeout",
        "30",
        "--max-time",
        str(max_time),
        "--output",
        str(tmp_path),
        url,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError((completed.stderr or completed.stdout or f"curl exited {completed.returncode}").strip())
    validate_pdf(tmp_path)
    tmp_path.replace(local_path)
    return old_size, local_path.stat().st_size


def reset_for_extraction(row: dict[str, str]) -> None:
    row["extraction_status"] = "not_started"
    row["ocr_required"] = ""
    row["text_quality_score"] = ""
    row["last_checked"] = utc_now()
    row["next_action"] = "Retry text extraction after PDF repair."


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair Parliament PDFs before retrying extraction.")
    parser.add_argument("--max-time", type=int, default=2400, help="Per-PDF curl max-time in seconds.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    fields, rows = read_csv(MANIFEST_PATH)
    errors = latest_pdf_text_errors()
    partial_ids = ocr_partial_ids()
    repaired_ocr_partials: set[str] = set()
    report_rows: list[dict[str, str]] = []
    targets = [
        row
        for row in rows
        if row.get("source_id") in PARLIAMENT_SOURCES
        and (
            row.get("extraction_status") == "text_extraction_failed"
            or row.get("document_id") in partial_ids
        )
    ]
    if args.limit:
        targets = targets[: args.limit]

    for index, row in enumerate(targets, start=1):
        document_id = row.get("document_id", "")
        partial_ocr = document_id in partial_ids
        error = errors.get(document_id, "ocr_partial_failed" if partial_ocr else "")
        redownload_needed = should_redownload(row, error, partial_ocr)
        action = "redownload_and_retry" if redownload_needed else "retry_extraction_only"
        old_size = ""
        new_size = ""
        status = "planned" if args.dry_run else "ok"
        repair_error = ""
        try:
            path = PROJECT_ROOT / row.get("local_path", "")
            old_size = str(path.stat().st_size) if path.exists() else "0"
            if redownload_needed and not args.dry_run:
                old, new = redownload(row, args.max_time)
                old_size = str(old)
                new_size = str(new)
                row["file_hash"] = sha256(PROJECT_ROOT / row.get("local_path", ""))
                append_note(row, f"pdf_repair=redownloaded; old_bytes={old}; new_bytes={new}")
                if partial_ocr:
                    repaired_ocr_partials.add(document_id)
            elif not args.dry_run:
                new_size = old_size
                append_note(row, f"pdf_repair=retry_only; previous_error={error}")
            if not args.dry_run:
                reset_for_extraction(row)
        except Exception as exc:
            status = "failed"
            repair_error = str(exc)
            append_note(row, f"pdf_repair_failed={repair_error}")
            row["last_checked"] = utc_now()
        report_rows.append(
            {
                "document_id": document_id,
                "source_id": row.get("source_id", ""),
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "action": action,
                "status": status,
                "old_size": old_size,
                "new_size": new_size,
                "error": repair_error or error,
                "download_url": row.get("download_url", ""),
                "local_path": row.get("local_path", ""),
                "last_checked": utc_now(),
            }
        )
        print(
            f"repair {index}/{len(targets)} {document_id} action={action} status={status} "
            f"old={old_size} new={new_size}",
            file=sys.stderr,
            flush=True,
        )

    if not args.dry_run:
        write_csv(MANIFEST_PATH, fields, rows)
        remove_ocr_rows(repaired_ocr_partials)
    write_csv(REPAIR_REPORT_PATH, REPAIR_FIELDS, report_rows)
    print(
        json.dumps(
            {
                "targets": len(targets),
                "redownload": sum(1 for row in report_rows if row["action"] == "redownload_and_retry"),
                "retry_only": sum(1 for row in report_rows if row["action"] == "retry_extraction_only"),
                "failed": sum(1 for row in report_rows if row["status"] == "failed"),
                "report": str(REPAIR_REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0 if all(row["status"] != "failed" for row in report_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
