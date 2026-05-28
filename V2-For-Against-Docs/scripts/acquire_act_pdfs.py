#!/usr/bin/env python3
"""Acquire official Parliament Act PDFs in controlled year batches.

Reads data/manifests/document_manifest.csv, derives the Parliament PDF URL from
the official act detail ID, downloads available PDFs, and updates the manifest
and live corpus index.
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
RUN_LOG_PATH = PROJECT_ROOT / "data" / "manifests" / "extraction_run_log.csv"
PDF_ROOT = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "acts_pdfs" / "english"

USER_AGENT = "SL-Legal-Assist-Act-PDF-Acquirer/0.1"


@dataclass
class DownloadResult:
    document_id: str
    status: str
    download_url: str
    local_path: str = ""
    file_hash: str = ""
    error: str = ""
    bytes_downloaded: int = 0


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def candidate_pdf_url(row: dict[str, str]) -> str:
    source_id = row.get("source_document_id", "")
    if source_id.startswith("G") and source_id[1:].isdigit():
        return f"https://www.parliament.lk/uploads/acts/gbills/english/{source_id[1:]}.pdf"
    if source_id.startswith("P") and source_id[1:].isdigit():
        return f"https://www.parliament.lk/uploads/acts/pbills/english/{source_id[1:]}.pdf"
    detail_url = row.get("source_url", "")
    match = re.search(r"/act-details/([GP])([0-9]+)", detail_url)
    if match:
        directory = "gbills" if match.group(1) == "G" else "pbills"
        return f"https://www.parliament.lk/uploads/acts/{directory}/english/{match.group(2)}.pdf"
    return ""


def local_pdf_path(row: dict[str, str]) -> Path:
    year = row.get("year") or "unknown"
    number = (row.get("number") or "unknown").zfill(3) if row.get("number", "").isdigit() else "unknown"
    title = safe_slug(row.get("title", ""))[:90]
    return PDF_ROOT / year / f"{number}_{title}.pdf"


def download_pdf(row: dict[str, str], timeout: int, force: bool) -> DownloadResult:
    document_id = row["document_id"]
    url = candidate_pdf_url(row)
    if not url:
        return DownloadResult(document_id, "pdf_url_not_discoverable", "", error="No candidate PDF URL.")

    path = local_pdf_path(row)
    if path.exists() and not force:
        return DownloadResult(
            document_id=document_id,
            status="downloaded",
            download_url=url,
            local_path=str(path.relative_to(PROJECT_ROOT)),
            file_hash=sha256_file(path),
            bytes_downloaded=path.stat().st_size,
        )

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
            if response.status != 200:
                return DownloadResult(document_id, "pdf_not_found", url, error=f"status={response.status}")
            if not data.startswith(b"%PDF") and "pdf" not in content_type.lower():
                return DownloadResult(
                    document_id,
                    "pdf_not_found",
                    url,
                    error=f"content_type={content_type}; first_bytes={data[:20]!r}",
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return DownloadResult(
                document_id=document_id,
                status="downloaded",
                download_url=url,
                local_path=str(path.relative_to(PROJECT_ROOT)),
                file_hash=sha256_bytes(data),
                bytes_downloaded=len(data),
            )
    except HTTPError as exc:
        return DownloadResult(document_id, "pdf_not_found", url, error=f"HTTP {exc.code}: {exc.reason}")
    except URLError as exc:
        return DownloadResult(document_id, "download_failed", url, error=str(exc.reason))
    except TimeoutError:
        return DownloadResult(document_id, "download_timeout", url, error=f"timeout after {timeout}s")
    except Exception as exc:
        return DownloadResult(document_id, "download_failed", url, error=str(exc))


def select_rows(
    rows: list[dict[str, str]],
    start_year: int,
    end_year: int,
    limit: int,
    retry_missing: bool,
    force: bool,
) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        if row.get("document_type") != "Act":
            continue
        try:
            year = int(row.get("year", "0"))
        except ValueError:
            continue
        if not (start_year <= year <= end_year):
            continue
        status = row.get("acquisition_status", "")
        if status == "downloaded" and not force:
            continue
        if status in {"metadata_extracted_pdf_not_found", "download_timeout", "download_failed"} and not retry_missing:
            continue
        selected.append(row)
        if limit and len(selected) >= limit:
            break
    return selected


def update_manifests(results: list[DownloadResult], corpus) -> dict[str, int]:
    now = utc_now()
    result_by_doc = {result.document_id: result for result in results}
    rows = read_csv(MANIFEST_PATH)
    counts: dict[str, int] = {}
    for row in rows:
        result = result_by_doc.get(row.get("document_id", ""))
        if not result:
            continue
        counts[result.status] = counts.get(result.status, 0) + 1
        row["download_url"] = result.download_url or row.get("download_url", "")
        row["last_checked"] = now
        if result.status == "downloaded":
            row["local_path"] = result.local_path
            row["file_hash"] = result.file_hash
            row["acquisition_status"] = "downloaded"
            if row.get("extraction_status") in {"", "not_started"}:
                row["extraction_status"] = "not_started"
            row["next_action"] = "Extract text and segment Act."
            row["missing_reason"] = ""
        elif result.status == "pdf_not_found":
            row["acquisition_status"] = "metadata_extracted_pdf_not_found"
            row["missing_reason"] = result.error
            row["next_action"] = "Locate PDF via detail page, LawNet, Government Printing, or archive."
        elif result.status == "pdf_url_not_discoverable":
            row["acquisition_status"] = "metadata_extracted_pdf_not_discoverable"
            row["missing_reason"] = result.error
            row["next_action"] = "Inspect source detail page manually or locate alternate official source."
        else:
            row["acquisition_status"] = result.status
            row["missing_reason"] = result.error
            row["next_action"] = "Retry official PDF download or locate alternate official source."
        note = f"act_pdf_acquire_status={result.status}; bytes={result.bytes_downloaded}"
        if result.error:
            note += f"; error={result.error}"
        prior = row.get("notes", "")
        row["notes"] = f"{prior}; {note}" if prior else note
    write_csv(MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, rows)

    instruments = read_csv(INSTRUMENT_PATH)
    for row in instruments:
        source_document_id = row.get("source_document_id", "")
        match = next(
            (
                result
                for result in results
                if result.download_url and source_document_id and source_document_id[1:] in result.download_url
            ),
            None,
        )
        if match and match.status == "downloaded":
            row["download_url"] = match.download_url
            row["last_checked"] = now
    write_csv(INSTRUMENT_PATH, corpus.LEGAL_INSTRUMENT_FIELDS, instruments)
    return counts


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire official Parliament Act PDFs.")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--retry-missing", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()
    rows = read_csv(MANIFEST_PATH)
    selected = select_rows(
        rows,
        args.start_year,
        args.end_year,
        args.limit,
        args.retry_missing,
        args.force,
    )

    results: list[DownloadResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [executor.submit(download_pdf, row, args.timeout, args.force) for row in selected]
        for future in as_completed(futures):
            results.append(future.result())

    counts = update_manifests(results, corpus)
    errors = [
        f"{result.document_id}: {result.status}: {result.error}"
        for result in results
        if result.status not in {"downloaded", "pdf_not_found"}
    ]
    latest = {
        "act_pdf_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "selected": len(selected),
            "counts": counts,
            "errors": errors,
        }
    }
    corpus.refresh_acts_missing_register()
    corpus.build_corpus_index(latest)
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_act_pdfs",
            "source_id": "PARL_ACTS",
            "run_type": "act_pdf_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(selected)),
            "documents_downloaded": str(counts.get("downloaded", 0)),
            "errors": json.dumps(errors, ensure_ascii=False),
            "new_missing_items": "",
            "notes": f"Act PDF acquisition for {args.start_year}-{args.end_year}. Counts: {counts}",
        }
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
