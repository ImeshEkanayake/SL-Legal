#!/usr/bin/env python3
"""Recheck Parliament Act PDF gaps and record multilingual availability.

This does two things deliberately:
- if an English PDF is found for a row previously marked missing, it updates the
  main English manifest row;
- if Sinhala or Tamil PDFs are found, it downloads them into language-specific
  folders and records them in a recheck report without pretending the English
  text was acquired.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
INSTRUMENT_PATH = PROJECT_ROOT / "data" / "manifests" / "legal_instrument_registry.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "manifests" / "act_pdf_recheck_report.csv"
RUN_LOG_PATH = PROJECT_ROOT / "data" / "manifests" / "extraction_run_log.csv"
PDF_ROOT = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "acts_pdfs"

USER_AGENT = "SL-Legal-Assist-Missing-PDF-Recheck/0.1"

LANGUAGES = ("english", "sinhala", "tamil")
REPORT_FIELDS = [
    "document_id",
    "year",
    "number",
    "title",
    "source_document_id",
    "source_url",
    "checked_at",
    "english_status",
    "english_url",
    "english_local_path",
    "sinhala_status",
    "sinhala_url",
    "sinhala_local_path",
    "tamil_status",
    "tamil_url",
    "tamil_local_path",
    "notes",
]


@dataclass
class ProbeResult:
    url: str
    status: str
    data: bytes = b""
    error: str = ""


@dataclass
class RecheckResult:
    document_id: str
    language_results: dict[str, ProbeResult]
    notes: str = ""


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
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_run_log(run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    fields = list(rows[0].keys()) if rows else [
        "run_id",
        "source_id",
        "run_type",
        "started_at",
        "ended_at",
        "documents_found",
        "documents_downloaded",
        "errors",
        "new_missing_items",
        "notes",
    ]
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def source_parts(row: dict[str, str]) -> tuple[str, str]:
    source_document_id = row.get("source_document_id", "")
    match = re.match(r"^([GP])([0-9]+)$", source_document_id)
    if match:
        return match.group(1), match.group(2)
    detail_url = row.get("source_url", "")
    match = re.search(r"/act-details/([GP])([0-9]+)", detail_url)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def candidate_urls(row: dict[str, str], language: str) -> list[str]:
    prefix, id_part = source_parts(row)
    if not id_part:
        return []
    preferred = "gbills" if prefix == "G" else "pbills"
    directories = [preferred] + [directory for directory in ("gbills", "pbills") if directory != preferred]
    return [
        f"https://www.parliament.lk/uploads/acts/{directory}/{language}/{id_part}.pdf"
        for directory in directories
    ]


def local_pdf_path(row: dict[str, str], language: str) -> Path:
    year = row.get("year") or "unknown"
    number = (row.get("number") or "unknown").zfill(3) if row.get("number", "").isdigit() else "unknown"
    title = safe_slug(row.get("title", ""))[:90]
    return PDF_ROOT / language / year / f"{number}_{title}.pdf"


def probe_pdf(url: str, timeout: int) -> ProbeResult:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
            if response.status != 200:
                return ProbeResult(url, "not_found", error=f"status={response.status}")
            if not data.startswith(b"%PDF") and "pdf" not in content_type.lower():
                return ProbeResult(
                    url,
                    "not_pdf",
                    error=f"content_type={content_type}; first_bytes={data[:20]!r}",
                )
            return ProbeResult(url, "found", data=data)
    except HTTPError as exc:
        return ProbeResult(url, "not_found", error=f"HTTP {exc.code}: {exc.reason}")
    except TimeoutError:
        return ProbeResult(url, "timeout", error=f"timeout after {timeout}s")
    except URLError as exc:
        return ProbeResult(url, "failed", error=str(exc.reason))
    except Exception as exc:
        return ProbeResult(url, "failed", error=str(exc))


def recheck_row(row: dict[str, str], timeout: int, download_alternates: bool) -> RecheckResult:
    language_results: dict[str, ProbeResult] = {}
    notes = []
    for language in LANGUAGES:
        urls = candidate_urls(row, language)
        if not urls:
            language_results[language] = ProbeResult("", "url_not_discoverable", error="No candidate URL.")
            continue
        final_result = ProbeResult(urls[0], "not_found", error="No candidate matched.")
        for url in urls:
            result = probe_pdf(url, timeout)
            final_result = result
            if result.status == "found":
                if language == "english" or download_alternates:
                    path = local_pdf_path(row, language)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(result.data)
                break
        language_results[language] = final_result
        if final_result.status == "found":
            notes.append(f"{language}_pdf_found")
    return RecheckResult(row["document_id"], language_results, "; ".join(notes))


def select_rows(rows: list[dict[str, str]], start_year: int, end_year: int, limit: int) -> list[dict[str, str]]:
    selected = []
    missing_statuses = {
        "metadata_extracted_pdf_not_found",
        "metadata_extracted_pdf_not_discoverable",
        "download_failed",
        "download_timeout",
    }
    for row in rows:
        if row.get("document_type") != "Act":
            continue
        if row.get("acquisition_status") not in missing_statuses:
            continue
        try:
            year = int(row.get("year", "0"))
        except ValueError:
            continue
        if not (start_year <= year <= end_year):
            continue
        selected.append(row)
        if limit and len(selected) >= limit:
            break
    return selected


def merge_report(report_rows: list[dict[str, str]]) -> None:
    existing = read_csv(REPORT_PATH)
    merged = {row["document_id"]: row for row in existing}
    order = [row["document_id"] for row in existing]
    for row in report_rows:
        if row["document_id"] not in merged:
            order.append(row["document_id"])
        merged[row["document_id"]] = row
    write_csv(REPORT_PATH, REPORT_FIELDS, [merged[document_id] for document_id in order])


def update_manifest(
    rows: list[dict[str, str]],
    selected: list[dict[str, str]],
    results: list[RecheckResult],
    corpus,
) -> tuple[int, int, list[dict[str, str]]]:
    now = utc_now()
    selected_by_doc = {row["document_id"]: row for row in selected}
    results_by_doc = {result.document_id: result for result in results}
    english_downloads = 0
    alternate_downloads = 0
    report_rows = []

    for row in rows:
        result = results_by_doc.get(row.get("document_id", ""))
        if not result:
            continue
        source_row = selected_by_doc[result.document_id]
        report_row = {
            "document_id": result.document_id,
            "year": source_row.get("year", ""),
            "number": source_row.get("number", ""),
            "title": source_row.get("title", ""),
            "source_document_id": source_row.get("source_document_id", ""),
            "source_url": source_row.get("source_url", ""),
            "checked_at": now,
            "notes": result.notes,
        }
        note_parts = []
        for language in LANGUAGES:
            language_result = result.language_results[language]
            local_path = ""
            if language_result.status == "found":
                path = local_pdf_path(source_row, language)
                local_path = str(path.relative_to(PROJECT_ROOT))
                if language == "english":
                    english_downloads += 1
                else:
                    alternate_downloads += 1
            report_row[f"{language}_status"] = language_result.status
            report_row[f"{language}_url"] = language_result.url
            report_row[f"{language}_local_path"] = local_path
            if language_result.status == "found" and language != "english":
                note_parts.append(f"{language}_official_pdf={language_result.url}")

        english = result.language_results["english"]
        row["last_checked"] = now
        if english.status == "found":
            path = local_pdf_path(row, "english")
            row["download_url"] = english.url
            row["local_path"] = str(path.relative_to(PROJECT_ROOT))
            row["file_hash"] = sha256_bytes(english.data)
            row["acquisition_status"] = "downloaded"
            row["extraction_status"] = "not_started"
            row["ocr_required"] = ""
            row["text_quality_score"] = ""
            row["missing_reason"] = ""
            row["next_action"] = "Extract text and segment Act."
        else:
            row["missing_reason"] = english.error or english.status
            row["next_action"] = (
                "Use alternate official language PDFs if suitable, or locate English PDF via "
                "Government Printing, LawNet, National Archives, or licensed source."
            )
        if note_parts:
            prior = row.get("notes", "")
            addition = "missing_pdf_recheck: " + "; ".join(note_parts)
            row["notes"] = f"{prior}; {addition}" if prior else addition
        report_rows.append(report_row)

    write_csv(MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, rows)

    instruments = read_csv(INSTRUMENT_PATH)
    downloaded_by_source = {
        row.get("source_document_id", ""): row.get("download_url", "")
        for row in rows
        if row.get("acquisition_status") == "downloaded" and row.get("source_document_id")
    }
    for instrument in instruments:
        url = downloaded_by_source.get(instrument.get("source_document_id", ""))
        if url:
            instrument["download_url"] = url
            instrument["last_checked"] = now
    write_csv(INSTRUMENT_PATH, corpus.LEGAL_INSTRUMENT_FIELDS, instruments)
    merge_report(report_rows)
    return english_downloads, alternate_downloads, report_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recheck missing Parliament Act PDFs.")
    parser.add_argument("--start-year", type=int, default=1948)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument(
        "--no-download-alternates",
        action="store_true",
        help="Only record alternate-language availability; do not save Sinhala/Tamil PDFs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()
    rows = read_csv(MANIFEST_PATH)
    selected = select_rows(rows, args.start_year, args.end_year, args.limit)

    results: list[RecheckResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [
            executor.submit(recheck_row, row, args.timeout, not args.no_download_alternates)
            for row in selected
        ]
        for future in as_completed(futures):
            results.append(future.result())

    english_downloads, alternate_downloads, report_rows = update_manifest(rows, selected, results, corpus)
    corpus.refresh_acts_missing_register()
    latest = {
        "missing_act_pdf_recheck": {
            "started_at": started,
            "ended_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "selected": len(selected),
            "english_downloads": english_downloads,
            "alternate_language_downloads": alternate_downloads,
            "report_path": str(REPORT_PATH.relative_to(PROJECT_ROOT)),
        }
    }
    corpus.build_corpus_index(latest)
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_missing_pdf_recheck",
            "source_id": "PARL_ACTS",
            "run_type": "missing_act_pdf_recheck",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(selected)),
            "documents_downloaded": str(english_downloads),
            "errors": "[]",
            "new_missing_items": "",
            "notes": (
                f"Rechecked missing Act PDFs for {args.start_year}-{args.end_year}; "
                f"English recovered: {english_downloads}; alternate-language PDFs saved: {alternate_downloads}; "
                f"report rows: {len(report_rows)}."
            ),
        }
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
