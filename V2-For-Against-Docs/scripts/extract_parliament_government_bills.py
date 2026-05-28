#!/usr/bin/env python3
"""Extract Government Bills from the official Parliament listing.

The listing page exposes a CSV download endpoint:
  /en/business-of-parliament/download-bills-listing/csv?billType=G&year=YYYY

This script records every bill row in the corpus manifest and optionally probes
the predictable official bill PDF path.
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
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "government_bills_listing"
PDF_ROOT = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "government_bills_pdfs" / "english"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_REGISTER_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
BILL_REGISTRY_PATH = MANIFEST_DIR / "government_bill_registry.csv"

USER_AGENT = "SL-Legal-Assist-Government-Bills-Extractor/0.1"
SOURCE_ID = "PARL_GOV_BILLS"

BILL_REGISTRY_FIELDS = [
    "bill_id",
    "bill_type",
    "short_title",
    "number",
    "year",
    "presented_date",
    "current_status",
    "source_document_id",
    "source_url",
    "download_url",
    "related_act",
    "notes",
    "last_checked",
]


@dataclass
class ProbeResult:
    document_id: str
    status: str
    download_url: str
    content_type: str = ""
    content_length: str = ""
    error: str = ""
    local_path: str = ""
    file_hash: str = ""


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


def merge_rows(
    path: Path,
    fields: list[str],
    new_rows: list[dict[str, str]],
    key_field: str,
) -> list[dict[str, str]]:
    existing = read_csv(path)
    merged = {row.get(key_field, ""): row for row in existing}
    order = [row.get(key_field, "") for row in existing]
    for row in new_rows:
        key = row.get(key_field, "")
        if key not in merged:
            order.append(key)
        prior = merged.get(key, {})
        merged[key] = {**prior, **{k: v for k, v in row.items() if v != ""}}
    rows = [merged[key] for key in order if key]
    write_csv(path, fields, rows)
    return rows


def append_run_log(run: dict[str, str], corpus) -> None:
    rows = read_csv(RUN_LOG_PATH)
    fields = list(rows[0].keys()) if rows else corpus.EXTRACTION_RUN_FIELDS
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def government_bills_csv_url(year: int) -> str:
    return (
        "https://www.parliament.lk/en/business-of-parliament/"
        f"download-bills-listing/csv?billType=G&year={year}"
    )


def fetch_url(url: str, *, method: str = "GET", timeout: int = 30) -> tuple[int | None, dict[str, str], bytes, str]:
    req = Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = response.read() if method != "HEAD" else b""
            return response.status, dict(response.headers.items()), data, ""
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, b"", str(exc)
    except URLError as exc:
        return None, {}, b"", str(exc.reason)
    except TimeoutError:
        return None, {}, b"", f"timeout after {timeout}s"
    except Exception as exc:
        return None, {}, b"", str(exc)


def parse_bills_csv(data: bytes) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig", errors="replace")
    rows = []
    for row in csv.DictReader(text.splitlines()):
        if not row.get("Bill No.") and not row.get("Bill Title"):
            continue
        rows.append(row)
    return rows


def bill_number_parts(bill_no: str, fallback_year: int) -> tuple[str, str]:
    number = (bill_no or "").strip()
    if number.isdigit():
        return str(int(number)), str(fallback_year)
    match = re.match(r"\s*0*([0-9]+)\s*/\s*([0-9]{4})\s*", number)
    if match:
        return match.group(1), match.group(2)
    return number, str(fallback_year)


def source_document_id(detail_url: str) -> str:
    match = re.search(r"/bill-details/([GP][0-9]+)", detail_url)
    return match.group(1) if match else ""


def candidate_bill_pdf_url(detail_url: str) -> str:
    source_id = source_document_id(detail_url)
    match = re.match(r"([GP])([0-9]+)", source_id)
    if not match:
        return ""
    directory = "gbills" if match.group(1) == "G" else "pbills"
    return f"https://www.parliament.lk/uploads/bills/{directory}/english/{match.group(2)}.pdf"


def local_bill_pdf_path(row: dict[str, str]) -> Path:
    year = row.get("year") or "unknown"
    number = (row.get("number") or "unknown").zfill(3) if row.get("number", "").isdigit() else "unknown"
    title = safe_slug(row.get("title", ""))[:90]
    return PDF_ROOT / year / f"{number}_{title}.pdf"


def probe_or_download_pdf(row: dict[str, str], timeout: int, download: bool) -> ProbeResult:
    document_id = row["document_id"]
    url = row.get("download_url", "")
    if not url:
        return ProbeResult(document_id, "metadata_extracted_pdf_not_discoverable", "", error="No candidate URL.")

    method = "GET" if download else "HEAD"
    status, headers, data, error = fetch_url(url, method=method, timeout=timeout)
    content_type = headers.get("Content-Type", "")
    content_length = headers.get("Content-Length", "")
    if status == 200 and "pdf" in content_type.lower():
        result = ProbeResult(
            document_id=document_id,
            status="official_pdf_available",
            download_url=url,
            content_type=content_type,
            content_length=content_length,
        )
        if download:
            if not data.startswith(b"%PDF"):
                return ProbeResult(document_id, "metadata_extracted_pdf_not_found", url, error="Response was not PDF bytes.")
            path = local_bill_pdf_path(row)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            result.status = "downloaded"
            result.local_path = str(path.relative_to(PROJECT_ROOT))
            result.file_hash = sha256_bytes(data)
        return result
    return ProbeResult(
        document_id=document_id,
        status="metadata_extracted_pdf_not_found",
        download_url=url,
        content_type=content_type,
        content_length=content_length,
        error=error or f"status={status} content_type={content_type}",
    )


def source_registry_row(now: str) -> dict[str, str]:
    return {
        "source_id": SOURCE_ID,
        "source_name": "Parliament of Sri Lanka Government Bills Listing",
        "source_url": "https://www.parliament.lk/en/business-of-parliament/government-bills-listing",
        "source_owner": "Parliament of Sri Lanka",
        "reliability_tier": "A",
        "legal_authority_type": "official_bill_metadata",
        "jurisdiction": "Sri Lanka",
        "languages": "English; Sinhala; Tamil where available",
        "coverage_start": "1948",
        "coverage_end": "",
        "coverage_confidence": "metadata_available_year_filter_to_verify",
        "licence_status": "to_review",
        "access_method": "web_csv_export",
        "refresh_frequency": "weekly",
        "known_gaps": "PDF availability varies; older bill PDFs may not be available from predictable paths",
        "notes": "CSV endpoint discovered from official page download control.",
        "last_checked": now,
    }


def update_missing_register(now: str, total: int, available: int, missing: int, undiscoverable: int, corpus) -> None:
    row = {
        "missing_id": "M007",
        "data_category": "Government Bills",
        "expected_coverage": "1948-present",
        "known_available_coverage": (
            f"Parliament Government Bills metadata {total} rows; "
            f"{available} predictable English PDFs available."
        ),
        "missing_description": "Government Bills PDF availability and enacted-Act linkage are not yet complete.",
        "legal_importance": "high",
        "risk_if_missing": "Legislative history and bill-to-act tracing may be incomplete.",
        "probable_source": "Parliament Government Bills listing; Parliament detail pages; Hansard; Gazette supplements",
        "next_action": "Download available PDFs, extract text, and link bills to enacted Acts where possible.",
        "owner": "Corpus lead",
        "status": "open" if missing or undiscoverable else "complete",
        "last_checked": now,
        "notes": (
            f"Government Bills corpus has {total} metadata rows; "
            f"{available} predictable English PDFs available; "
            f"{missing} predictable English PDFs not found; "
            f"{undiscoverable} PDF URLs not discoverable."
        ),
    }
    merge_rows(MISSING_REGISTER_PATH, corpus.MISSING_DATA_FIELDS, [row], "missing_id")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Parliament Government Bills listing.")
    parser.add_argument("--start-year", type=int, default=1948)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--probe-pdfs", action="store_true")
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    merge_rows(SOURCE_REGISTRY_PATH, corpus.SOURCE_REGISTRY_FIELDS, [source_registry_row(started)], "source_id")

    document_rows: list[dict[str, str]] = []
    bill_rows: list[dict[str, str]] = []
    yearly_counts: dict[str, int] = {}
    errors: list[str] = []

    for year in range(args.start_year, args.end_year + 1):
        url = government_bills_csv_url(year)
        status, _headers, data, error = fetch_url(url, timeout=args.timeout)
        if status != 200 or not data:
            errors.append(f"{year}: failed to fetch CSV ({status}) {error}")
            yearly_counts[str(year)] = 0
            continue
        raw_path = RAW_DIR / f"{year}.csv"
        raw_path.write_bytes(data)
        bills = parse_bills_csv(data)
        yearly_counts[str(year)] = len(bills)

        for bill in bills:
            bill_year = str(year)
            number, parsed_year = bill_number_parts(bill.get("Bill No.", ""), year)
            bill_year = parsed_year or bill_year
            title = (bill.get("Bill Title") or "").strip()
            presented_date = (bill.get("Presented Date") or "").strip()
            detail_url = (bill.get("Link to Bill") or "").strip()
            source_doc = source_document_id(detail_url)
            suffix = source_doc.lower() if source_doc else safe_slug(title)
            number_part = number.zfill(3) if number.isdigit() else safe_slug(number)
            document_id = f"parl_gov_bill_{bill_year}_{number_part}_{suffix}"
            bill_id = f"gov_bill_{bill_year}_{number_part}_{suffix}"
            candidate_pdf = candidate_bill_pdf_url(detail_url)
            row = {
                "document_id": document_id,
                "source_id": SOURCE_ID,
                "source_document_id": source_doc,
                "document_type": "Government Bill",
                "title": title,
                "year": bill_year,
                "number": number,
                "date": presented_date,
                "language": "English",
                "source_url": detail_url,
                "download_url": candidate_pdf,
                "local_path": "",
                "file_hash": "",
                "acquisition_status": "metadata_extracted",
                "extraction_status": "not_started",
                "ocr_required": "",
                "text_quality_score": "",
                "legal_status": "bill_to_verify",
                "missing_reason": "",
                "next_action": "Probe/download official Bill PDF and link to enacted Act if applicable.",
                "last_checked": started,
                "notes": f"Detail ID: {source_doc}" if source_doc else "",
            }
            document_rows.append(row)
            bill_rows.append(
                {
                    "bill_id": bill_id,
                    "bill_type": "Government Bill",
                    "short_title": title,
                    "number": number,
                    "year": bill_year,
                    "presented_date": presented_date,
                    "current_status": "to_verify",
                    "source_document_id": source_doc,
                    "source_url": detail_url,
                    "download_url": candidate_pdf,
                    "related_act": "",
                    "notes": "Imported from Parliament Government Bills listing.",
                    "last_checked": started,
                }
            )

    probe_counts = {
        "official_pdf_available": 0,
        "metadata_extracted_pdf_not_found": 0,
        "metadata_extracted_pdf_not_discoverable": 0,
        "downloaded": 0,
    }
    if args.probe_pdfs or args.download_pdfs:
        results: list[ProbeResult] = []
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = [
                executor.submit(probe_or_download_pdf, row, args.timeout, args.download_pdfs)
                for row in document_rows
            ]
            for future in as_completed(futures):
                results.append(future.result())

        by_doc = {result.document_id: result for result in results}
        for row in document_rows:
            result = by_doc.get(row["document_id"])
            if not result:
                continue
            probe_counts[result.status] = probe_counts.get(result.status, 0) + 1
            row["acquisition_status"] = result.status
            row["download_url"] = result.download_url or row["download_url"]
            row["local_path"] = result.local_path
            row["file_hash"] = result.file_hash
            row["missing_reason"] = result.error
            row["last_checked"] = utc_now()
            if result.status == "downloaded":
                row["next_action"] = "Extract text and link Bill to enacted Act if applicable."
            elif result.status == "official_pdf_available":
                row["next_action"] = "Download official Bill PDF and extract text."
            else:
                row["next_action"] = "Inspect bill detail page or alternate official source."
            note = f"bill_pdf_probe_status={result.status}; content_length={result.content_length}"
            prior = row.get("notes", "")
            row["notes"] = f"{prior}; {note}" if prior else note

        download_by_doc = {row["document_id"]: row.get("download_url", "") for row in document_rows}
        for bill_row in bill_rows:
            matching = next(
                (
                    row
                    for row in document_rows
                    if row.get("source_document_id") == bill_row.get("source_document_id")
                ),
                None,
            )
            if matching:
                bill_row["download_url"] = download_by_doc.get(matching["document_id"], bill_row["download_url"])
                bill_row["last_checked"] = matching["last_checked"]

    merge_rows(DOCUMENT_MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, document_rows, "document_id")
    merge_rows(BILL_REGISTRY_PATH, BILL_REGISTRY_FIELDS, bill_rows, "bill_id")
    update_missing_register(
        utc_now(),
        len(document_rows),
        probe_counts.get("official_pdf_available", 0) + probe_counts.get("downloaded", 0),
        probe_counts.get("metadata_extracted_pdf_not_found", 0),
        probe_counts.get("metadata_extracted_pdf_not_discoverable", 0),
        corpus,
    )

    latest = {
        "parliament_government_bills": {
            "started_at": started,
            "ended_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "documents_found": len(document_rows),
            "yearly_counts": yearly_counts,
            "probe_counts": probe_counts,
            "errors": errors,
        }
    }
    corpus.build_corpus_index(latest)
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_gov_bills",
            "source_id": SOURCE_ID,
            "run_type": "government_bills_listing",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(document_rows)),
            "documents_downloaded": str(probe_counts.get("downloaded", 0)),
            "errors": json.dumps(errors, ensure_ascii=False),
            "new_missing_items": "M007",
            "notes": f"Extracted Parliament Government Bills listing. Probe counts: {probe_counts}",
        },
        corpus,
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
