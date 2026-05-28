#!/usr/bin/env python3
"""Acquire official Parliament Hansard PDFs.

This collector uses the public English Parliament listing pages, so it prefers
English records and does not collect Sinhala/Tamil alternatives from these
endpoints. Historical gaps are kept in the missing-data register.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urljoin, urlparse, urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
INDEX_DIR = DATA_DIR / "indexes"
RAW_DIR = DATA_DIR / "raw" / "official" / "parliament" / "hansards"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
HANSARD_REGISTRY_PATH = MANIFEST_DIR / "hansard_registry.csv"

USER_AGENT = "SL-Legal-Assist-Hansard-Acquirer/0.1"
BASE_URL = "https://www.parliament.lk"
DAILY_LISTING_URL = f"{BASE_URL}/en/business-of-parliament/hansards"
VOLUME_LISTING_URL = f"{BASE_URL}/en/business-of-parliament/hansard-volumes"

HANSARD_REGISTRY_FIELDS = [
    "document_id",
    "source_id",
    "listing_page",
    "title",
    "date",
    "year",
    "volume_number",
    "date_range",
    "language",
    "download_url",
    "local_path",
    "acquisition_status",
    "file_hash",
    "last_checked",
    "notes",
]


@dataclass
class FetchResult:
    url: str
    status: int | None
    content_type: str
    data: bytes
    error: str = ""


@dataclass
class HansardCandidate:
    document_id: str
    source_id: str
    source_document_id: str
    document_type: str
    title: str
    year: str
    number: str
    date: str
    language: str
    source_url: str
    download_url: str
    local_path: str
    legal_status: str
    date_range: str = ""
    notes: str = ""


@dataclass
class DownloadResult:
    document_id: str
    status: str
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
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def merge_by_key(
    path: Path,
    fields: list[str],
    new_rows: Iterable[dict[str, str]],
    key_field: str,
) -> list[dict[str, str]]:
    existing = read_csv(path)
    merged: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing:
        key = row.get(key_field, "")
        if key and key not in merged:
            order.append(key)
        if key:
            merged[key] = row
    for row in new_rows:
        key = row.get(key_field, "")
        if not key:
            continue
        if key not in merged:
            order.append(key)
        prior = merged.get(key, {})
        merged[key] = {**prior, **{k: v for k, v in row.items() if v != ""}}
    rows = [merged[key] for key in order if key]
    write_csv(path, fields, rows)
    return rows


def append_run_log(fields: list[str], run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return normalize_space(re.sub(r"<[^>]+>", " ", value or ""))


def safe_slug(value: str, *, max_len: int = 90) -> str:
    value = unquote(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return (value[:max_len].strip("_") or "unknown")


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_url(url: str, timeout: int, *, retries: int = 1) -> FetchResult:
    request_url = normalize_request_url(url)
    last_error = ""
    for attempt in range(retries + 1):
        try:
            result = fetch_url_with_curl(request_url, timeout)
            result.url = url
            return result
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    return FetchResult(url=url, status=None, content_type="", data=b"", error=last_error)


def normalize_request_url(url: str) -> str:
    """Encode unsafe characters in Parliament PDF URLs while preserving existing escapes."""
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%")
    query = quote(parts.query, safe="=&;%+/:")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def fetch_url_with_curl(url: str, timeout: int) -> FetchResult:
    with tempfile.NamedTemporaryFile(prefix="sllegal_hansard_", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        command = [
            "curl",
            "-L",
            "--compressed",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-sS",
            "-o",
            str(tmp_path),
            "-w",
            "__SLLEGAL_HTTP_STATUS__:%{http_code}\n__SLLEGAL_CONTENT_TYPE__:%{content_type}\n",
            url,
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 5,
            check=False,
        )
        output = completed.stdout.decode("utf-8", errors="replace")
        status_match = re.search(r"__SLLEGAL_HTTP_STATUS__:(\d+)", output)
        content_type_match = re.search(r"__SLLEGAL_CONTENT_TYPE__:(.*)", output)
        status = int(status_match.group(1)) if status_match else None
        content_type = content_type_match.group(1).strip() if content_type_match else ""
        data = tmp_path.read_bytes() if tmp_path.exists() else b""
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 and not error:
            error = f"curl exited {completed.returncode}"
        return FetchResult(url=url, status=status, content_type=content_type, data=data, error=error)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def parse_yyyy_mm_dd(value: str) -> str:
    match = re.search(r"(?<!\d)(20\d{2}|19\d{2})-(\d{2})-(\d{2})(?!\d)", value)
    if match:
        return match.group(0)
    return ""


def parse_month_date(value: str) -> str:
    cleaned = re.sub(r",(?=\d{4})", ", ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s*(19\d{2}|20\d{2})",
        cleaned,
        flags=re.I,
    )
    if not match:
        return ""
    month_name, day, year = match.groups()
    try:
        parsed = datetime.strptime(f"{month_name} {int(day):02d} {year}", "%B %d %Y")
    except ValueError:
        return ""
    return parsed.strftime("%Y-%m-%d")


def parse_dotted_date(value: str) -> str:
    match = re.search(r"(?<!\d)(\d{2})\.(\d{2})\.(19\d{2}|20\d{2})(?!\d)", value)
    if not match:
        return ""
    day, month, year = match.groups()
    try:
        parsed = datetime(int(year), int(month), int(day))
    except ValueError:
        return ""
    return parsed.strftime("%Y-%m-%d")


def infer_year(value: str) -> str:
    years = re.findall(r"(?<!\d)(19[4-9]\d|20\d{2})(?!\d)", value or "")
    return years[0] if years else ""


def local_filename(download_url: str, title: str) -> str:
    original = Path(unquote(urlparse(download_url).path)).name
    suffix = Path(original).suffix.lower() or ".pdf"
    original_stem = Path(original).stem
    stem = safe_slug(f"{title}_{original_stem}", max_len=120)
    return f"{stem}_{url_hash(download_url)}{suffix}"


def extract_items(page_html: str, source_url: str) -> list[tuple[str, str]]:
    title_pattern = re.compile(
        r"<h1[^>]*class=['\"][^'\"]*sub_heading[^'\"]*mb-[01][^'\"]*['\"][^>]*>(.*?)</h1>",
        flags=re.I | re.S,
    )
    matches = list(title_pattern.finditer(page_html))
    items: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = strip_tags(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_html)
        chunk = page_html[match.end() : end]
        href_match = re.search(r"href=['\"]([^'\"]+\.pdf(?:\?[^'\"]*)?)['\"]", chunk, flags=re.I)
        if not title or not href_match:
            continue
        download_url = urljoin(source_url, html.unescape(href_match.group(1)))
        items.append((title, download_url))
    return items


def parse_last_page(page_html: str) -> int:
    pages = [int(value) for value in re.findall(r"acquire_query_params\((\d+)\)", page_html)]
    return max(pages) if pages else 0


def make_daily_candidate(title: str, download_url: str, listing_url: str) -> HansardCandidate:
    date_value = parse_yyyy_mm_dd(title) or parse_month_date(title) or parse_yyyy_mm_dd(download_url)
    year = date_value[:4] if date_value else infer_year(title + " " + download_url)
    doc_key = date_value.replace("-", "") if date_value else safe_slug(title, max_len=60)
    document_id = f"parl_hansard_daily_{doc_key}_{url_hash(download_url)}"
    local_path = RAW_DIR / "daily" / (year or "unknown") / local_filename(download_url, title)
    return HansardCandidate(
        document_id=document_id,
        source_id="PARL_HANSARD_DAILY",
        source_document_id=Path(unquote(urlparse(download_url).path)).name,
        document_type="Hansard Daily",
        title=title,
        year=year,
        number="",
        date=date_value,
        language="English",
        source_url=listing_url,
        download_url=download_url,
        local_path=str(local_path.relative_to(PROJECT_ROOT)),
        legal_status="official_parliamentary_record",
        notes="English-language listing; language to verify during text extraction.",
    )


def make_volume_candidate(title: str, download_url: str, listing_url: str) -> HansardCandidate:
    volume_match = re.search(r"Volume\s+(\d+)", title, flags=re.I)
    number = volume_match.group(1) if volume_match else ""
    dates = [parse_dotted_date(match) for match in re.findall(r"\d{2}\.\d{2}\.(?:19|20)\d{2}", title)]
    dates = [value for value in dates if value]
    start_date = dates[0] if dates else parse_yyyy_mm_dd(download_url)
    year = start_date[:4] if start_date else infer_year(title + " " + download_url)
    date_range = " - ".join(dates)
    doc_key = number or safe_slug(title, max_len=60)
    if start_date:
        doc_key = f"{doc_key}_{start_date.replace('-', '')}"
    document_id = f"parl_hansard_volume_{doc_key}_{url_hash(download_url)}"
    local_path = RAW_DIR / "volumes" / (year or "unknown") / local_filename(download_url, title)
    return HansardCandidate(
        document_id=document_id,
        source_id="PARL_HANSARD_VOLUMES",
        source_document_id=Path(unquote(urlparse(download_url).path)).name,
        document_type="Hansard Corrected Volume",
        title=title,
        year=year,
        number=number,
        date=start_date,
        language="English",
        source_url=listing_url,
        download_url=download_url,
        local_path=str(local_path.relative_to(PROJECT_ROOT)),
        legal_status="official_parliamentary_record",
        date_range=date_range,
        notes="Corrected-volume listing from Parliament English endpoint.",
    )


def discover_track(
    *,
    track: str,
    base_url: str,
    item_count: int,
    max_pages: int,
    timeout: int,
    progress: bool,
) -> list[HansardCandidate]:
    candidates: list[HansardCandidate] = []
    seen_urls: set[str] = set()
    seen_page_signatures: set[tuple[str, ...]] = set()
    discovered_last_page = 0

    for page in range(1, max_pages + 1):
        listing_url = f"{base_url}?itemCount={item_count}&page={page}"
        if progress:
            print(f"discover {track} page {page}", file=sys.stderr, flush=True)
        result = fetch_url(listing_url, timeout, retries=2)
        if result.status != 200:
            if progress:
                print(f"stop {track} page {page}: status={result.status} error={result.error}", file=sys.stderr, flush=True)
            break
        page_html = result.data.decode("utf-8", errors="replace")
        if page == 1:
            discovered_last_page = parse_last_page(page_html)
        items = extract_items(page_html, listing_url)
        page_signature = tuple(download_url for _title, download_url in items)
        if not page_signature:
            break
        if page_signature in seen_page_signatures:
            break
        seen_page_signatures.add(page_signature)

        new_on_page = 0
        for title, download_url in items:
            if download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            new_on_page += 1
            if track == "daily":
                candidates.append(make_daily_candidate(title, download_url, listing_url))
            else:
                candidates.append(make_volume_candidate(title, download_url, listing_url))
        if new_on_page == 0:
            break
        if discovered_last_page and page >= discovered_last_page:
            break

    return candidates


def discover_candidates(args: argparse.Namespace) -> list[HansardCandidate]:
    enabled = set(args.source)
    if "all" in enabled or not enabled:
        enabled = {"daily", "volumes"}

    candidates: list[HansardCandidate] = []
    if "daily" in enabled:
        candidates.extend(
            discover_track(
                track="daily",
                base_url=DAILY_LISTING_URL,
                item_count=args.item_count,
                max_pages=args.max_pages,
                timeout=args.timeout,
                progress=args.progress,
            )
        )
    if "volumes" in enabled:
        candidates.extend(
            discover_track(
                track="volumes",
                base_url=VOLUME_LISTING_URL,
                item_count=args.item_count,
                max_pages=args.max_pages,
                timeout=args.timeout,
                progress=args.progress,
            )
        )

    deduped: dict[str, HansardCandidate] = {}
    for candidate in candidates:
        deduped[candidate.document_id] = candidate
    candidates = list(deduped.values())
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates


def candidate_to_manifest_row(candidate: HansardCandidate, now: str) -> dict[str, str]:
    return {
        "document_id": candidate.document_id,
        "source_id": candidate.source_id,
        "source_document_id": candidate.source_document_id,
        "document_type": candidate.document_type,
        "title": candidate.title,
        "year": candidate.year,
        "number": candidate.number,
        "date": candidate.date,
        "language": candidate.language,
        "source_url": candidate.source_url,
        "download_url": candidate.download_url,
        "local_path": "",
        "file_hash": "",
        "acquisition_status": "metadata_extracted",
        "extraction_status": "not_started",
        "ocr_required": "",
        "text_quality_score": "",
        "legal_status": candidate.legal_status,
        "missing_reason": "",
        "next_action": "Download official Hansard PDF.",
        "last_checked": now,
        "notes": candidate.notes,
    }


def merge_manifest_candidates(candidates: list[HansardCandidate], fields: list[str]) -> list[dict[str, str]]:
    now = utc_now()
    existing_rows = read_csv(DOCUMENT_MANIFEST_PATH)
    by_id = {row.get("document_id", ""): row for row in existing_rows if row.get("document_id")}
    order = [row.get("document_id", "") for row in existing_rows if row.get("document_id")]
    for candidate in candidates:
        new_row = candidate_to_manifest_row(candidate, now)
        prior = by_id.get(candidate.document_id)
        if prior:
            merged = {**prior}
            for key, value in new_row.items():
                if not value:
                    continue
                if key in {"local_path", "file_hash", "acquisition_status", "extraction_status"}:
                    continue
                if key == "next_action" and prior.get("acquisition_status") == "downloaded":
                    continue
                merged[key] = value
            by_id[candidate.document_id] = merged
        else:
            by_id[candidate.document_id] = new_row
            order.append(candidate.document_id)
    rows = [by_id[document_id] for document_id in order if document_id]
    write_csv(DOCUMENT_MANIFEST_PATH, fields, rows)
    return rows


def download_candidate(candidate: HansardCandidate, timeout: int, force: bool) -> DownloadResult:
    path = PROJECT_ROOT / candidate.local_path
    if path.exists() and not force:
        return DownloadResult(
            document_id=candidate.document_id,
            status="downloaded",
            local_path=candidate.local_path,
            file_hash=sha256_file(path),
            bytes_downloaded=path.stat().st_size,
        )

    result = fetch_url(candidate.download_url, timeout, retries=2)
    if result.status != 200:
        return DownloadResult(
            document_id=candidate.document_id,
            status="download_failed",
            error=result.error or f"status={result.status}",
        )
    if not result.data.startswith(b"%PDF") and "pdf" not in result.content_type.lower():
        return DownloadResult(
            document_id=candidate.document_id,
            status="download_failed_not_pdf",
            error=f"content_type={result.content_type}; first_bytes={result.data[:16]!r}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.data)
    return DownloadResult(
        document_id=candidate.document_id,
        status="downloaded",
        local_path=candidate.local_path,
        file_hash=sha256_bytes(result.data),
        bytes_downloaded=len(result.data),
    )


def update_manifest_downloads(results: list[DownloadResult], fields: list[str]) -> dict[str, int]:
    now = utc_now()
    result_by_id = {result.document_id: result for result in results}
    rows = read_csv(DOCUMENT_MANIFEST_PATH)
    counts: dict[str, int] = {}
    for row in rows:
        result = result_by_id.get(row.get("document_id", ""))
        if not result:
            continue
        counts[result.status] = counts.get(result.status, 0) + 1
        row["last_checked"] = now
        if result.status == "downloaded":
            row["local_path"] = result.local_path
            row["file_hash"] = result.file_hash
            row["acquisition_status"] = "downloaded"
            if row.get("extraction_status") in {"", "not_started"}:
                row["extraction_status"] = "not_started"
            row["missing_reason"] = ""
            row["next_action"] = "Extract text and OCR if needed."
        else:
            row["acquisition_status"] = result.status
            row["missing_reason"] = result.error
            row["next_action"] = "Retry download or inspect Parliament source manually."
        note = f"hansard_acquire_status={result.status}; bytes={result.bytes_downloaded}"
        if result.error:
            note += f"; error={result.error}"
        prior = row.get("notes", "")
        row["notes"] = f"{prior}; {note}" if prior else note
    write_csv(DOCUMENT_MANIFEST_PATH, fields, rows)
    return counts


def write_hansard_registry(candidates: list[HansardCandidate], results: list[DownloadResult] | None) -> None:
    now = utc_now()
    result_by_id = {result.document_id: result for result in results or []}
    manifest_by_id = {
        row.get("document_id", ""): row
        for row in read_csv(DOCUMENT_MANIFEST_PATH)
        if row.get("document_id")
    }
    rows: list[dict[str, str]] = []
    for candidate in candidates:
        result = result_by_id.get(candidate.document_id)
        manifest = manifest_by_id.get(candidate.document_id, {})
        rows.append(
            {
                "document_id": candidate.document_id,
                "source_id": candidate.source_id,
                "listing_page": candidate.source_url,
                "title": candidate.title,
                "date": candidate.date,
                "year": candidate.year,
                "volume_number": candidate.number,
                "date_range": candidate.date_range,
                "language": candidate.language,
                "download_url": candidate.download_url,
                "local_path": result.local_path if result else manifest.get("local_path", ""),
                "acquisition_status": result.status if result else manifest.get("acquisition_status", ""),
                "file_hash": result.file_hash if result else manifest.get("file_hash", ""),
                "last_checked": now,
                "notes": candidate.notes,
            }
        )
    merge_by_key(HANSARD_REGISTRY_PATH, HANSARD_REGISTRY_FIELDS, rows, "document_id")


def write_source_registry(fields: list[str], now: str) -> None:
    rows = [
        {
            "source_id": "PARL_HANSARD_DAILY",
            "source_name": "Parliament of Sri Lanka Hansards",
            "source_url": DAILY_LISTING_URL,
            "source_owner": "Parliament of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_parliamentary_proceedings",
            "jurisdiction": "Sri Lanka",
            "languages": "English listing acquired; Sinhala/Tamil not collected where English exists",
            "coverage_start": "online coverage discovered from listing",
            "coverage_end": "",
            "coverage_confidence": "official_listing_to_verify",
            "licence_status": "to_review",
            "access_method": "web_listing",
            "refresh_frequency": "weekly",
            "known_gaps": "Online listing does not cover all Hansards back to 1948.",
            "notes": "English endpoint used because English availability is sufficient for this corpus policy.",
            "last_checked": now,
        },
        {
            "source_id": "PARL_HANSARD_VOLUMES",
            "source_name": "Parliament of Sri Lanka Corrected Hansards (Volumes)",
            "source_url": VOLUME_LISTING_URL,
            "source_owner": "Parliament of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_parliamentary_proceedings",
            "jurisdiction": "Sri Lanka",
            "languages": "English listing acquired; Sinhala/Tamil not collected where English exists",
            "coverage_start": "online coverage discovered from listing",
            "coverage_end": "",
            "coverage_confidence": "official_listing_to_verify",
            "licence_status": "to_review",
            "access_method": "web_listing",
            "refresh_frequency": "monthly",
            "known_gaps": "Corrected online volumes do not cover all Hansards back to 1948.",
            "notes": "Corrected volumes are valuable for legislative-history retrieval and citation-backed packs.",
            "last_checked": now,
        },
    ]
    merge_by_key(SOURCE_REGISTRY_PATH, fields, rows, "source_id")


def summarize_source(rows: list[dict[str, str]], source_id: str) -> tuple[int, int, str]:
    docs = [row for row in rows if row.get("source_id") == source_id]
    downloaded = sum(1 for row in docs if row.get("acquisition_status") == "downloaded")
    years = sorted({int(row["year"]) for row in docs if row.get("year", "").isdigit()})
    coverage = f"{years[0]}-{years[-1]}" if years else "unknown"
    return len(docs), downloaded, coverage


def update_missing_register(fields: list[str], manifest_rows: list[dict[str, str]], now: str) -> None:
    daily_total, daily_downloaded, daily_coverage = summarize_source(manifest_rows, "PARL_HANSARD_DAILY")
    volume_total, volume_downloaded, volume_coverage = summarize_source(manifest_rows, "PARL_HANSARD_VOLUMES")
    rows = [
        {
            "missing_id": "M006",
            "data_category": "Hansard historical volumes and daily proceedings",
            "expected_coverage": "1948-present",
            "known_available_coverage": (
                f"Official online daily Hansard discovered {daily_total} rows, {daily_downloaded} downloaded, "
                f"coverage {daily_coverage}; corrected volumes discovered {volume_total} rows, "
                f"{volume_downloaded} downloaded, coverage {volume_coverage}."
            ),
            "missing_description": "Online Parliament listings do not cover the full 1948-present Hansard corpus.",
            "legal_importance": "high",
            "risk_if_missing": "Legislative history, parliamentary intent, and constitutional debates may be incomplete.",
            "probable_source": "Parliament; National Archives; parliamentary library; university libraries",
            "next_action": "Acquire pre-online Hansards, committee proceedings, indexes, and OCR-quality scans from archival sources.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "English is preferred; Sinhala/Tamil copies are not needed when English official PDFs are available.",
        },
        {
            "missing_id": "M_HANSARD_COMMITTEES_INDEXES",
            "data_category": "Hansard committee proceedings and indexes",
            "expected_coverage": "1948-present",
            "known_available_coverage": "Not yet downloaded or mapped.",
            "missing_description": "Committee proceedings, corrected-volume indexes, and related parliamentary indexes are not yet mapped.",
            "legal_importance": "medium",
            "risk_if_missing": "Legislative-history retrieval may miss committee-stage context and index-led discovery paths.",
            "probable_source": "Parliament; National Archives; parliamentary library",
            "next_action": "Identify official or archival listing pages, then create a separate acquisition script.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Do not collect alternate-language duplicates if English copies are available.",
        },
    ]
    merge_by_key(MISSING_DATA_PATH, fields, rows, "missing_id")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire official Parliament Hansard PDFs.")
    parser.add_argument(
        "--source",
        action="append",
        choices=["all", "daily", "volumes"],
        default=[],
        help="Hansard source track. Repeatable. Defaults to all.",
    )
    parser.add_argument("--item-count", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()

    candidates = discover_candidates(args)
    manifest_rows = merge_manifest_candidates(candidates, corpus.DOCUMENT_MANIFEST_FIELDS)
    write_source_registry(corpus.SOURCE_REGISTRY_FIELDS, utc_now())

    results: list[DownloadResult] = []
    counts: dict[str, int] = {}
    errors: list[str] = []
    if not args.metadata_only:
        existing = {
            row.get("document_id", ""): row
            for row in manifest_rows
            if row.get("document_id")
        }
        selected = [
            candidate
            for candidate in candidates
            if args.force or existing.get(candidate.document_id, {}).get("acquisition_status") != "downloaded"
        ]
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = [
                executor.submit(download_candidate, candidate, args.timeout, args.force)
                for candidate in selected
            ]
            completed_count = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed_count += 1
                if args.progress and (
                    completed_count == 1
                    or completed_count % 50 == 0
                    or completed_count == len(selected)
                ):
                    print(
                        f"downloaded/checked {completed_count}/{len(selected)} "
                        f"(latest {result.document_id}: {result.status})",
                        file=sys.stderr,
                        flush=True,
                    )
                if result.status != "downloaded":
                    errors.append(f"{result.document_id}: {result.status}: {result.error}")
        counts = update_manifest_downloads(results, corpus.DOCUMENT_MANIFEST_FIELDS)
        manifest_rows = read_csv(DOCUMENT_MANIFEST_PATH)

    write_hansard_registry(candidates, results)
    update_missing_register(corpus.MISSING_DATA_FIELDS, manifest_rows, utc_now())

    latest = {
        "hansard_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "sources": args.source or ["all"],
            "metadata_only": args.metadata_only,
            "candidates_found": len(candidates),
            "download_counts": counts,
            "errors": errors[:200],
            "errors_truncated": max(0, len(errors) - 200),
        }
    }
    corpus.build_corpus_index(latest)
    append_run_log(
        corpus.EXTRACTION_RUN_FIELDS,
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_hansards",
            "source_id": "PARL_HANSARD_DAILY;PARL_HANSARD_VOLUMES",
            "run_type": "parliament_hansard_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(candidates)),
            "documents_downloaded": str(counts.get("downloaded", 0)),
            "errors": json.dumps(errors[:200], ensure_ascii=False),
            "new_missing_items": "M006;M_HANSARD_COMMITTEES_INDEXES",
            "notes": json.dumps(latest["hansard_acquisition"], ensure_ascii=False),
        },
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
