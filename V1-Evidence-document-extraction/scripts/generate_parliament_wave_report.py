#!/usr/bin/env python3
"""Generate coverage reports for the Parliament acquisition wave."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
DOCS_DIR = PROJECT_ROOT / "Docs"
MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
SUMMARY_CSV = MANIFEST_DIR / "parliament_wave_coverage_report.csv"
FAILURE_CSV = MANIFEST_DIR / "parliament_failed_download_report.csv"
SUMMARY_MD = DOCS_DIR / "parliament_corpus_wave_status.md"

PARLIAMENT_SOURCES = {
    "PARL_HANSARD_DAILY": "Hansard Daily",
    "PARL_HANSARD_VOLUMES": "Hansard Corrected Volumes",
    "PARL_COMMITTEE_REPORTS": "Committee Reports",
    "PARL_MINISTERIAL_CONSULTATIVE_REPORTS": "Ministerial Consultative Committee Reports",
    "PARL_CONSULTATIVE_MONTHLY_REPORTS": "Consultative Committee Monthly Reports",
    "PARL_MINUTES": "Minutes of Parliament",
    "PARL_PAPERS_PRESENTED": "Papers Presented",
    "PARL_SPEAKER_PAPERS": "Papers Presented by the Speaker",
    "PARL_ORDER_PAPERS": "Order Papers",
    "PARL_ORDER_BOOKS": "Order Books",
    "PARL_ORDER_OF_BUSINESS": "Order of Business",
    "PARL_ADDENDUMS": "Addendums",
    "PARL_SC_DECISIONS_ON_BILLS": "Supreme Court Decisions on Bills",
    "PARL_PROGRESS_REPORTS": "Progress Reports",
}

SUMMARY_FIELDS = [
    "source_id",
    "source_label",
    "total_rows",
    "downloaded",
    "download_failed",
    "other_acquisition_status",
    "text_extracted",
    "text_empty_needs_ocr",
    "text_extraction_failed",
    "not_started",
    "ocr_required_true",
    "first_year",
    "last_year",
    "last_checked",
]

FAILURE_FIELDS = [
    "document_id",
    "source_id",
    "document_type",
    "title",
    "year",
    "date",
    "download_url",
    "acquisition_status",
    "missing_reason",
    "next_action",
    "last_checked",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_corpus_module():
    script = PROJECT_ROOT / "scripts" / "extract_legal_corpus.py"
    spec = importlib.util.spec_from_file_location("extract_legal_corpus", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def append_run_log(fields: list[str], run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def source_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        source_id = row.get("source_id", "")
        if source_id in PARLIAMENT_SOURCES:
            grouped[source_id].append(row)

    report_rows: list[dict[str, str]] = []
    for source_id in sorted(PARLIAMENT_SOURCES):
        source_docs = grouped.get(source_id, [])
        acquisition = Counter(row.get("acquisition_status", "") or "unknown" for row in source_docs)
        extraction = Counter(row.get("extraction_status", "") or "unknown" for row in source_docs)
        years = sorted(
            int(row["year"])
            for row in source_docs
            if row.get("year", "").isdigit() and 1800 <= int(row["year"]) <= 2100
        )
        other_acq = sum(
            count
            for status, count in acquisition.items()
            if status not in {"downloaded", "download_failed"}
        )
        report_rows.append(
            {
                "source_id": source_id,
                "source_label": PARLIAMENT_SOURCES[source_id],
                "total_rows": str(len(source_docs)),
                "downloaded": str(acquisition.get("downloaded", 0)),
                "download_failed": str(acquisition.get("download_failed", 0)),
                "other_acquisition_status": str(other_acq),
                "text_extracted": str(extraction.get("text_extracted", 0)),
                "text_empty_needs_ocr": str(extraction.get("text_empty_needs_ocr", 0)),
                "text_extraction_failed": str(extraction.get("text_extraction_failed", 0)),
                "not_started": str(extraction.get("not_started", 0)),
                "ocr_required_true": str(sum(1 for row in source_docs if row.get("ocr_required") == "true")),
                "first_year": str(years[0]) if years else "",
                "last_year": str(years[-1]) if years else "",
                "last_checked": utc_now(),
            }
        )
    return report_rows


def failure_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for row in rows:
        if row.get("source_id", "") not in PARLIAMENT_SOURCES:
            continue
        if row.get("acquisition_status") == "downloaded":
            continue
        failures.append(
            {
                "document_id": row.get("document_id", ""),
                "source_id": row.get("source_id", ""),
                "document_type": row.get("document_type", ""),
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "date": row.get("date", ""),
                "download_url": row.get("download_url", ""),
                "acquisition_status": row.get("acquisition_status", ""),
                "missing_reason": row.get("missing_reason", ""),
                "next_action": row.get("next_action", ""),
                "last_checked": row.get("last_checked", ""),
            }
        )
    failures.sort(key=lambda row: (row["source_id"], row["year"], row["title"], row["document_id"]))
    return failures


def write_markdown(summary_rows: list[dict[str, str]], failures: list[dict[str, str]], now: str) -> None:
    total_rows = sum(int(row["total_rows"]) for row in summary_rows)
    downloaded = sum(int(row["downloaded"]) for row in summary_rows)
    failed = sum(int(row["download_failed"]) for row in summary_rows)
    text_extracted = sum(int(row["text_extracted"]) for row in summary_rows)
    text_empty = sum(int(row["text_empty_needs_ocr"]) for row in summary_rows)
    text_failed = sum(int(row["text_extraction_failed"]) for row in summary_rows)
    not_started = sum(int(row["not_started"]) for row in summary_rows)
    ocr_required = sum(int(row["ocr_required_true"]) for row in summary_rows)

    lines = [
        "# Parliament Corpus Wave Status",
        "",
        f"Generated: {now}",
        "",
        "## Totals",
        "",
        f"- Manifest rows: {total_rows}",
        f"- Downloaded: {downloaded}",
        f"- Download failed / still missing: {failed}",
        f"- Text extracted: {text_extracted}",
        f"- Text empty and OCR required: {text_empty}",
        f"- Text extraction failed: {text_failed}",
        f"- Extraction not started: {not_started}",
        f"- OCR required flag: {ocr_required}",
        "",
        "## By Source",
        "",
        "| Source | Rows | Downloaded | Failed | Text extracted | OCR needed | Years |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        years = ""
        if row["first_year"] and row["last_year"]:
            years = f"{row['first_year']}-{row['last_year']}"
        lines.append(
            "| {source_label} | {total_rows} | {downloaded} | {download_failed} | "
            "{text_extracted} | {text_empty_needs_ocr} | {years} |".format(
                **row,
                years=years,
            )
        )
    lines.extend(
        [
            "",
            "## Failure Report",
            "",
            f"Detailed failed/non-downloaded rows are in `{FAILURE_CSV.relative_to(PROJECT_ROOT)}`.",
            f"Failure rows currently listed: {len(failures)}",
            "",
            "## Notes",
            "",
            "- English-first policy applies: do not duplicate Sinhala/Tamil records where official English exists.",
            "- Strategy generation must use only retrieved, cited Legal Research Pack material.",
            "- `text_empty_needs_ocr` rows should be queued for OCR after this report stabilizes.",
        ]
    )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    now = utc_now()
    corpus = load_corpus_module()
    rows = read_csv(MANIFEST_PATH)
    summary_rows = source_rows(rows)
    failures = failure_rows(rows)
    write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary_rows)
    write_csv(FAILURE_CSV, FAILURE_FIELDS, failures)
    write_markdown(summary_rows, failures, now)
    corpus.build_corpus_index(
        {
            "parliament_wave_report": {
                "generated_at": now,
                "summary_csv": str(SUMMARY_CSV.relative_to(PROJECT_ROOT)),
                "failure_csv": str(FAILURE_CSV.relative_to(PROJECT_ROOT)),
                "summary_md": str(SUMMARY_MD.relative_to(PROJECT_ROOT)),
            }
        }
    )
    append_run_log(
        corpus.EXTRACTION_RUN_FIELDS,
        {
            "run_id": "run_" + now.replace(":", "").replace("-", "").replace("+", "z") + "_parliament_wave_report",
            "source_id": "PARLIAMENT_WAVE",
            "run_type": "coverage_report",
            "started_at": now,
            "ended_at": utc_now(),
            "documents_found": str(sum(int(row["total_rows"]) for row in summary_rows)),
            "documents_downloaded": str(sum(int(row["downloaded"]) for row in summary_rows)),
            "errors": json.dumps([row["document_id"] for row in failures[:200]], ensure_ascii=False),
            "new_missing_items": "",
            "notes": "Generated Parliament acquisition, extraction, OCR, and failure coverage reports.",
        },
    )
    print(
        json.dumps(
            {
                "summary_csv": str(SUMMARY_CSV),
                "failure_csv": str(FAILURE_CSV),
                "summary_md": str(SUMMARY_MD),
                "failure_rows": len(failures),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
