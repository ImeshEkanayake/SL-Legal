#!/usr/bin/env python3
"""Acquire official gazette and appellate-court PDFs.

This collector is intentionally resumable. It first records every discoverable
official item in the shared document manifest, then downloads missing local
files without disturbing unrelated corpus rows.
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
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
INDEX_DIR = DATA_DIR / "indexes"
RAW_OFFICIAL_DIR = DATA_DIR / "raw" / "official"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
GAZETTE_COVERAGE_PATH = MANIFEST_DIR / "gazette_online_coverage.csv"
COURT_AUDIT_PATH = MANIFEST_DIR / "court_pdf_directory_audit.csv"

USER_AGENT = "SL-Legal-Assist-Official-Corpus-Acquirer/0.1"
CURRENT_YEAR = datetime.now().year

LANGUAGE_CODES = {
    "english": "E",
    "sinhala": "S",
    "tamil": "T",
}

CODE_LANGUAGES = {
    "E": "English",
    "S": "Sinhala",
    "T": "Tamil",
}

GAZETTE_COVERAGE_FIELDS = [
    "source_id",
    "year",
    "year_page_url",
    "year_page_status",
    "issue_pages_found",
    "documents_found",
    "downloaded",
    "missing_or_failed",
    "last_checked",
    "notes",
]

COURT_AUDIT_FIELDS = [
    "source_id",
    "document_type",
    "directory_url",
    "directory_status",
    "documents_found",
    "downloaded",
    "missing_or_failed",
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
class DocumentCandidate:
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
    notes: str = ""


@dataclass
class DownloadResult:
    document_id: str
    status: str
    local_path: str = ""
    file_hash: str = ""
    error: str = ""
    bytes_downloaded: int = 0


class AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        self._current = attr_map
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        text = normalize_space(" ".join(self._text))
        self.anchors.append({**self._current, "text": text})
        self._current = None
        self._text = []


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


def append_run_log(run: dict[str, str]) -> None:
    corpus = load_corpus_module()
    rows = read_csv(RUN_LOG_PATH)
    rows.append(run)
    write_csv(RUN_LOG_PATH, corpus.EXTRACTION_RUN_FIELDS, rows)


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
        if key not in merged:
            order.append(key)
        merged[key] = row
    for row in new_rows:
        key = row.get(key_field, "")
        if key not in merged:
            order.append(key)
        prior = merged.get(key, {})
        merged[key] = {**prior, **{k: v for k, v in row.items() if v != ""}}
    rows = [merged[key] for key in order if key]
    write_csv(path, fields, rows)
    return rows


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return normalize_space(re.sub(r"<[^>]+>", " ", value or ""))


def safe_slug(value: str, *, max_len: int = 90) -> str:
    value = unquote(value or "")
    value = value.lower()
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
    last_error = ""
    for attempt in range(retries + 1):
        try:
            return fetch_url_with_curl(url, timeout)
        except HTTPError as exc:
            data = exc.read() if hasattr(exc, "read") else b""
            return FetchResult(
                url=url,
                status=exc.code,
                content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
                data=data,
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        except (TimeoutError, URLError) as exc:
            last_error = str(getattr(exc, "reason", exc))
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    return FetchResult(url=url, status=None, content_type="", data=b"", error=last_error)


def fetch_url_with_curl(url: str, timeout: int) -> FetchResult:
    with tempfile.NamedTemporaryFile(prefix="sllegal_fetch_", delete=False) as tmp:
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


def extract_anchors(page_html: str) -> list[dict[str, str]]:
    parser = AnchorExtractor()
    parser.feed(page_html)
    return parser.anchors


def wanted_language(language: str, language_filter: set[str]) -> bool:
    if not language_filter:
        return True
    return language.lower() in language_filter


def language_from_text(text: str) -> str:
    return normalize_space(text).lower()


def language_code(language: str) -> str:
    return LANGUAGE_CODES.get(language.lower(), "U")


def local_filename_from_url(download_url: str) -> str:
    name = Path(unquote(urlparse(download_url).path)).name
    if not name:
        name = url_hash(download_url) + ".pdf"
    stem = safe_slug(Path(name).stem, max_len=110)
    suffix = Path(name).suffix.lower() or ".pdf"
    return f"{stem}_{url_hash(download_url)}{suffix}"


def infer_year_from_text(value: str, start_year: int, end_year: int) -> str:
    years = [
        int(match)
        for match in re.findall(r"(?<!\d)(19[4-9]\d|20\d{2})(?!\d)", value or "")
        if start_year <= int(match) <= end_year
    ]
    return str(years[-1]) if years else ""


def parse_ordinary_gazette_year(
    year: int,
    timeout: int,
    language_filter: set[str],
    issue_concurrency: int,
) -> tuple[list[DocumentCandidate], dict[str, str]]:
    now = utc_now()
    year_url = f"https://documents.gov.lk/view/gz/{year}.html"
    result = fetch_url(year_url, timeout)
    coverage = {
        "source_id": "GOV_GAZETTES",
        "year": str(year),
        "year_page_url": year_url,
        "year_page_status": str(result.status or "error"),
        "issue_pages_found": "0",
        "documents_found": "0",
        "downloaded": "",
        "missing_or_failed": "",
        "last_checked": now,
        "notes": result.error,
    }
    if result.status != 200:
        if year < 2004:
            coverage["notes"] = "Official online ordinary gazette year page not available; treat as archival gap."
        return [], coverage

    page_html = result.data.decode("utf-8", errors="replace")
    date_links = re.findall(
        r"<td>\s*(\d{4}-\d{2}-\d{2})\s*</td>\s*<td>\s*<a\s+href=\"([^\"]+)\"",
        page_html,
        flags=re.I | re.S,
    )
    def parse_issue(date_value: str, href: str) -> list[DocumentCandidate]:
        issue_url = urljoin(year_url, html.unescape(href))
        issue = fetch_url(issue_url, timeout)
        if issue.status != 200:
            return []
        issue_html = issue.data.decode("utf-8", errors="replace")
        chunks = re.findall(
            r"<li\s+class=\"list-group-item\"\s*>(.*?)</li>",
            issue_html,
            flags=re.I | re.S,
        )
        issue_candidates: list[DocumentCandidate] = []
        for chunk in chunks:
            part_match = re.search(r"<strong>\s*(.*?)\s*</strong>", chunk, flags=re.I | re.S)
            part_label = strip_tags(part_match.group(1)) if part_match else "Gazette Part"
            for anchor in extract_anchors(chunk):
                href = html.unescape(anchor.get("href", ""))
                if ".pdf" not in href.lower():
                    continue
                language = language_from_text(anchor.get("text", ""))
                if language not in LANGUAGE_CODES:
                    language = language_from_text(anchor.get("title", "").replace("View the document in", ""))
                if language not in LANGUAGE_CODES:
                    continue
                if not wanted_language(language, language_filter):
                    continue
                download_url = urljoin(issue_url, href)
                lang_code = language_code(language)
                part_slug = safe_slug(part_label, max_len=60)
                doc_hash = url_hash(download_url)
                document_id = f"gov_gazette_{date_value.replace('-', '')}_{part_slug}_{lang_code.lower()}_{doc_hash}"
                local_path = (
                    RAW_OFFICIAL_DIR
                    / "government_printing"
                    / "gazettes"
                    / "ordinary"
                    / str(year)
                    / date_value
                    / CODE_LANGUAGES[lang_code].lower()
                    / local_filename_from_url(download_url)
                )
                issue_candidates.append(
                    DocumentCandidate(
                        document_id=document_id,
                        source_id="GOV_GAZETTES",
                        source_document_id=f"{date_value}:{part_label}:{lang_code}",
                        document_type="Ordinary Gazette",
                        title=f"Ordinary Gazette {date_value} - {part_label} ({CODE_LANGUAGES[lang_code]})",
                        year=str(year),
                        number="",
                        date=date_value,
                        language=CODE_LANGUAGES[lang_code],
                        source_url=issue_url,
                        download_url=download_url,
                        local_path=str(local_path.relative_to(PROJECT_ROOT)),
                        legal_status="official_publication",
                        notes=f"part={part_label}; source_issue_page={issue_url}",
                    )
                )
        return issue_candidates

    candidates: list[DocumentCandidate] = []
    with ThreadPoolExecutor(max_workers=max(1, issue_concurrency)) as executor:
        futures = [executor.submit(parse_issue, date_value, href) for date_value, href in date_links]
        for future in as_completed(futures):
            candidates.extend(future.result())
    coverage["issue_pages_found"] = str(len(date_links))
    coverage["documents_found"] = str(len(candidates))
    return candidates, coverage


def parse_extraordinary_gazette_year(
    year: int,
    timeout: int,
    language_filter: set[str],
) -> tuple[list[DocumentCandidate], dict[str, str]]:
    now = utc_now()
    year_url = f"https://documents.gov.lk/view/egz/egz_{year}.html"
    result = fetch_url(year_url, timeout)
    coverage = {
        "source_id": "GOV_EXTRA_GAZETTES",
        "year": str(year),
        "year_page_url": year_url,
        "year_page_status": str(result.status or "error"),
        "issue_pages_found": "",
        "documents_found": "0",
        "downloaded": "",
        "missing_or_failed": "",
        "last_checked": now,
        "notes": result.error,
    }
    if result.status != 200:
        if year < 2004:
            coverage["notes"] = "Official online extraordinary gazette year page not available; treat as archival gap."
        return [], coverage

    page_html = result.data.decode("utf-8", errors="replace")
    candidates: list[DocumentCandidate] = []
    rows = re.findall(r"<tr>\s*(.*?)\s*</tr>", page_html, flags=re.I | re.S)
    issue_rows = 0
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        issue_rows += 1
        gazette_number = strip_tags(cells[0])
        date_value = strip_tags(cells[1])
        description = strip_tags(cells[2])
        downloads_cell = cells[3]
        for anchor in extract_anchors(downloads_cell):
            href = html.unescape(anchor.get("href", ""))
            if ".pdf" not in href.lower():
                continue
            language = language_from_text(anchor.get("text", ""))
            if language not in LANGUAGE_CODES:
                language = language_from_text(strip_tags(anchor.get("title", "")))
            if language not in LANGUAGE_CODES:
                basename = Path(unquote(urlparse(href).path)).stem.lower()
                suffix_match = re.search(r"_([est])$", basename)
                if suffix_match:
                    language = {"e": "english", "s": "sinhala", "t": "tamil"}[suffix_match.group(1)]
            if language not in LANGUAGE_CODES:
                continue
            if not wanted_language(language, language_filter):
                continue
            download_url = urljoin(year_url, href)
            lang_code = language_code(language)
            number_slug = safe_slug(gazette_number.replace("/", "_"), max_len=40)
            doc_hash = url_hash(download_url)
            document_id = f"gov_extra_gazette_{number_slug}_{lang_code.lower()}_{doc_hash}"
            local_path = (
                RAW_OFFICIAL_DIR
                / "government_printing"
                / "gazettes"
                / "extraordinary"
                / str(year)
                / CODE_LANGUAGES[lang_code].lower()
                / local_filename_from_url(download_url)
            )
            candidates.append(
                DocumentCandidate(
                    document_id=document_id,
                    source_id="GOV_EXTRA_GAZETTES",
                    source_document_id=f"{gazette_number}:{lang_code}",
                    document_type="Extraordinary Gazette",
                    title=f"Extraordinary Gazette {gazette_number} - {description} ({CODE_LANGUAGES[lang_code]})",
                    year=str(year),
                    number=gazette_number,
                    date=date_value,
                    language=CODE_LANGUAGES[lang_code],
                    source_url=year_url,
                    download_url=download_url,
                    local_path=str(local_path.relative_to(PROJECT_ROOT)),
                    legal_status="official_publication",
                    notes=f"description={description}",
                )
            )
    coverage["issue_pages_found"] = str(issue_rows)
    coverage["documents_found"] = str(len(candidates))
    return candidates, coverage


def parse_directory_listing(
    *,
    source_id: str,
    document_type: str,
    directory_url: str,
    local_subdir: Path,
    timeout: int,
    start_year: int,
    end_year: int,
    document_prefix: str,
) -> tuple[list[DocumentCandidate], dict[str, str]]:
    now = utc_now()
    result = fetch_url(directory_url, timeout)
    audit = {
        "source_id": source_id,
        "document_type": document_type,
        "directory_url": directory_url,
        "directory_status": str(result.status or "error"),
        "documents_found": "0",
        "downloaded": "",
        "missing_or_failed": "",
        "last_checked": now,
        "notes": result.error,
    }
    if result.status != 200:
        return [], audit

    page_html = result.data.decode("utf-8", errors="replace")
    candidates: list[DocumentCandidate] = []
    row_pattern = re.compile(r"<tr>(.*?)</tr>", flags=re.I | re.S)
    for row_match in row_pattern.finditer(page_html):
        row_html = row_match.group(1)
        anchor_match = re.search(r"<a\s+href=\"([^\"]+)\">(.*?)</a>", row_html, flags=re.I | re.S)
        if not anchor_match:
            continue
        href = html.unescape(anchor_match.group(1))
        if href.startswith("?") or href.startswith("/wp-content/uploads/"):
            continue
        if not re.search(r"\.(pdf|zip)$", href, flags=re.I):
            continue
        file_url = urljoin(directory_url, href)
        file_name = unquote(Path(urlparse(file_url).path).name)
        file_stem = Path(file_name).stem
        inferred_year = infer_year_from_text(file_name, start_year, end_year)
        date_cells = re.findall(r"<td[^>]*align=\"right\"[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        modified = strip_tags(date_cells[0]) if date_cells else ""
        size = strip_tags(date_cells[1]) if len(date_cells) > 1 else ""
        extension = Path(file_name).suffix.lower()
        doc_hash = url_hash(file_url)
        document_id = f"{document_prefix}_{safe_slug(file_stem, max_len=80)}_{doc_hash}"
        local_path = RAW_OFFICIAL_DIR / local_subdir / local_filename_from_url(file_url)
        title = f"{document_type}: {file_stem}"
        if extension == ".zip":
            title = f"{document_type} archive: {file_stem}"
        candidates.append(
            DocumentCandidate(
                document_id=document_id,
                source_id=source_id,
                source_document_id=file_name,
                document_type=document_type if extension == ".pdf" else f"{document_type} Archive",
                title=title,
                year=inferred_year,
                number="",
                date="",
                language="unknown",
                source_url=directory_url,
                download_url=file_url,
                local_path=str(local_path.relative_to(PROJECT_ROOT)),
                legal_status="official_court_material",
                notes=f"directory_last_modified={modified}; directory_size={size}; language_not_verified",
            )
        )
    audit["documents_found"] = str(len(candidates))
    return candidates, audit


def discover_candidates(args: argparse.Namespace) -> tuple[list[DocumentCandidate], list[dict[str, str]], list[dict[str, str]]]:
    language_filter = {value.strip().lower() for value in args.languages.split(",") if value.strip()}
    if language_filter == {"all"}:
        language_filter = set()

    candidates: list[DocumentCandidate] = []
    gazette_coverage: list[dict[str, str]] = []
    court_audits: list[dict[str, str]] = []

    enabled = set(args.source)
    if "all" in enabled:
        enabled = {"gazettes", "extra-gazettes", "supreme-court", "court-of-appeal"}

    if "gazettes" in enabled:
        for year in range(args.start_year, args.end_year + 1):
            if args.progress:
                print(f"discover ordinary gazettes {year}", file=sys.stderr, flush=True)
            found, coverage = parse_ordinary_gazette_year(
                year,
                args.timeout,
                language_filter,
                args.discovery_concurrency,
            )
            candidates.extend(found)
            gazette_coverage.append(coverage)

    if "extra-gazettes" in enabled:
        for year in range(args.start_year, args.end_year + 1):
            if args.progress:
                print(f"discover extraordinary gazettes {year}", file=sys.stderr, flush=True)
            found, coverage = parse_extraordinary_gazette_year(year, args.timeout, language_filter)
            candidates.extend(found)
            gazette_coverage.append(coverage)

    if "supreme-court" in enabled:
        for directory_url, document_type, subdir, prefix in [
            (
                "https://supremecourt.lk/wp-content/uploads/judgements/",
                "Supreme Court Judgment",
                Path("supreme_court") / "judgements",
                "sc_judgment",
            ),
            (
                "https://supremecourt.lk/wp-content/uploads/special_dt/",
                "Supreme Court Special Determination",
                Path("supreme_court") / "special_determinations",
                "sc_special_determination",
            ),
        ]:
            found, audit = parse_directory_listing(
                source_id="SC_OFFICIAL",
                document_type=document_type,
                directory_url=directory_url,
                local_subdir=subdir,
                timeout=args.timeout,
                start_year=args.start_year,
                end_year=args.end_year,
                document_prefix=prefix,
            )
            candidates.extend(found)
            court_audits.append(audit)

    if "court-of-appeal" in enabled:
        for directory_url, document_type, subdir, prefix in [
            (
                "https://courtofappeal.lk/wp-content/uploads/judgements/",
                "Court of Appeal Judgment",
                Path("court_of_appeal") / "judgements",
                "ca_judgment",
            ),
            (
                "https://courtofappeal.lk/wp-content/uploads/orders/",
                "Court of Appeal Order",
                Path("court_of_appeal") / "orders",
                "ca_order",
            ),
        ]:
            found, audit = parse_directory_listing(
                source_id="CA_OFFICIAL",
                document_type=document_type,
                directory_url=directory_url,
                local_subdir=subdir,
                timeout=args.timeout,
                start_year=args.start_year,
                end_year=args.end_year,
                document_prefix=prefix,
            )
            candidates.extend(found)
            court_audits.append(audit)

    deduped: dict[str, DocumentCandidate] = {}
    for candidate in candidates:
        deduped[candidate.document_id] = candidate
    candidates = list(deduped.values())
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates, gazette_coverage, court_audits


def candidate_to_manifest_row(candidate: DocumentCandidate, now: str) -> dict[str, str]:
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
        "next_action": "Download official file.",
        "last_checked": now,
        "notes": candidate.notes,
    }


def merge_manifest_candidates(
    candidates: list[DocumentCandidate],
    fields: list[str],
    *,
    force_metadata: bool = False,
) -> list[dict[str, str]]:
    now = utc_now()
    existing_rows = read_csv(DOCUMENT_MANIFEST_PATH)
    existing_by_id = {row.get("document_id", ""): row for row in existing_rows}
    order = [row.get("document_id", "") for row in existing_rows]
    for candidate in candidates:
        prior = existing_by_id.get(candidate.document_id)
        new_row = candidate_to_manifest_row(candidate, now)
        if prior:
            merged = {**prior}
            for key, value in new_row.items():
                if not value:
                    continue
                if key in {"local_path", "file_hash", "acquisition_status", "extraction_status"} and not force_metadata:
                    continue
                if key == "next_action" and prior.get("acquisition_status") == "downloaded":
                    continue
                merged[key] = value
            existing_by_id[candidate.document_id] = merged
        else:
            existing_by_id[candidate.document_id] = new_row
            order.append(candidate.document_id)
    rows = [existing_by_id[document_id] for document_id in order if document_id]
    write_csv(DOCUMENT_MANIFEST_PATH, fields, rows)
    return rows


def prune_stale_metadata_rows(candidates: list[DocumentCandidate], fields: list[str]) -> None:
    candidate_ids = {candidate.document_id for candidate in candidates}
    candidate_source_ids = {candidate.source_id for candidate in candidates}
    if not candidate_source_ids:
        return
    rows = read_csv(DOCUMENT_MANIFEST_PATH)
    kept: list[dict[str, str]] = []
    for row in rows:
        source_id = row.get("source_id", "")
        document_id = row.get("document_id", "")
        if source_id not in candidate_source_ids:
            kept.append(row)
            continue
        if document_id in candidate_ids:
            kept.append(row)
            continue
        if row.get("acquisition_status") == "downloaded":
            kept.append(row)
            continue
    write_csv(DOCUMENT_MANIFEST_PATH, fields, kept)


def download_candidate(candidate: DocumentCandidate, timeout: int, force: bool) -> DownloadResult:
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
    extension = Path(urlparse(candidate.download_url).path).suffix.lower()
    content_type = result.content_type.lower()
    if extension == ".pdf" and not result.data.startswith(b"%PDF") and "pdf" not in content_type:
        return DownloadResult(
            document_id=candidate.document_id,
            status="download_failed_not_pdf",
            error=f"content_type={result.content_type}; first_bytes={result.data[:16]!r}",
        )
    if extension == ".zip" and not result.data.startswith(b"PK"):
        return DownloadResult(
            document_id=candidate.document_id,
            status="download_failed_not_zip",
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
            row["next_action"] = "Retry download or inspect official source manually."
        note = f"official_bulk_acquire_status={result.status}; bytes={result.bytes_downloaded}"
        if result.error:
            note += f"; error={result.error}"
        prior = row.get("notes", "")
        row["notes"] = f"{prior}; {note}" if prior else note
    write_csv(DOCUMENT_MANIFEST_PATH, fields, rows)
    return counts


def write_source_registry(fields: list[str], now: str) -> None:
    rows = [
        {
            "source_id": "GOV_EXTRA_GAZETTES",
            "source_name": "Department of Government Printing Extraordinary Gazette Archive",
            "source_url": "https://documents.gov.lk/view/egz/",
            "source_owner": "Department of Government Printing",
            "reliability_tier": "A",
            "legal_authority_type": "official_extraordinary_gazette_archive",
            "jurisdiction": "Sri Lanka",
            "languages": "Sinhala; Tamil; English",
            "coverage_start": "online coverage discovered by year pages",
            "coverage_end": "",
            "coverage_confidence": "online_year_pages_to_verify",
            "licence_status": "to_review",
            "access_method": "web_archive",
            "refresh_frequency": "daily_or_weekly",
            "known_gaps": "Pre-online years require archival acquisition.",
            "notes": "Year pages follow /view/egz/egz_YYYY.html.",
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
    ordinary_total, ordinary_downloaded, ordinary_coverage = summarize_source(manifest_rows, "GOV_GAZETTES")
    extra_total, extra_downloaded, extra_coverage = summarize_source(manifest_rows, "GOV_EXTRA_GAZETTES")
    sc_total, sc_downloaded, sc_coverage = summarize_source(manifest_rows, "SC_OFFICIAL")
    ca_total, ca_downloaded, ca_coverage = summarize_source(manifest_rows, "CA_OFFICIAL")
    rows = [
        {
            "missing_id": "M001",
            "known_available_coverage": (
                f"Official online ordinary gazette pages discovered for {ordinary_coverage}; "
                f"{ordinary_total} document rows; {ordinary_downloaded} downloaded."
            ),
            "next_action": "Continue download retries; acquire pre-online ordinary gazettes from National Archives or official archives.",
            "status": "open",
            "last_checked": now,
            "notes": "Pre-2004 ordinary gazette pages are not visible through the current official online year-page pattern.",
        },
        {
            "missing_id": "M002",
            "known_available_coverage": (
                f"Official online extraordinary gazette pages discovered for {extra_coverage}; "
                f"{extra_total} document rows; {extra_downloaded} downloaded."
            ),
            "next_action": "Continue download retries; acquire historical extraordinary gazettes from National Archives or official archives.",
            "status": "open",
            "last_checked": now,
            "notes": "Pre-online extraordinary gazettes remain an archival acquisition task.",
        },
        {
            "missing_id": "M004",
            "known_available_coverage": (
                f"Official Supreme Court directories discovered {sc_total} document rows; "
                f"{sc_downloaded} downloaded; inferred case/document years {sc_coverage} where filename permits."
            ),
            "next_action": "Download current official directories, then map NLR/SLR, LawNet, archives, and licensed sources for 1948-present gaps.",
            "status": "open",
            "last_checked": now,
            "notes": "Official directory filenames do not always expose judgment year; language/date metadata must be enriched during text extraction.",
        },
        {
            "missing_id": "M005",
            "known_available_coverage": (
                f"Official Court of Appeal directories discovered {ca_total} document rows; "
                f"{ca_downloaded} downloaded; inferred case/document years {ca_coverage} where filename permits."
            ),
            "next_action": "Download current official directories, then map older appellate material through LawNet, reports, archives, and licensed sources.",
            "status": "open",
            "last_checked": now,
            "notes": "Court of Appeal was established after 1948; pre-establishment appellate material must be mapped through predecessor courts and law reports.",
        },
    ]
    merge_by_key(MISSING_DATA_PATH, fields, rows, "missing_id")


def update_coverage_download_counts(
    gazette_coverage: list[dict[str, str]],
    court_audits: list[dict[str, str]],
    manifest_rows: list[dict[str, str]],
) -> None:
    by_source_year: dict[tuple[str, str], tuple[int, int]] = {}
    for row in manifest_rows:
        source_id = row.get("source_id", "")
        year = row.get("year", "")
        if source_id not in {"GOV_GAZETTES", "GOV_EXTRA_GAZETTES"} or not year:
            continue
        key = (source_id, year)
        total, downloaded = by_source_year.get(key, (0, 0))
        total += 1
        if row.get("acquisition_status") == "downloaded":
            downloaded += 1
        by_source_year[key] = (total, downloaded)
    for coverage in gazette_coverage:
        total, downloaded = by_source_year.get((coverage["source_id"], coverage["year"]), (0, 0))
        if total:
            coverage["documents_found"] = str(total)
            coverage["downloaded"] = str(downloaded)
            coverage["missing_or_failed"] = str(total - downloaded)

    by_court_type: dict[tuple[str, str], tuple[int, int]] = {}
    for row in manifest_rows:
        source_id = row.get("source_id", "")
        document_type = row.get("document_type", "")
        if source_id not in {"SC_OFFICIAL", "CA_OFFICIAL"}:
            continue
        normalized_type = document_type.replace(" Archive", "")
        key = (source_id, normalized_type)
        total, downloaded = by_court_type.get(key, (0, 0))
        total += 1
        if row.get("acquisition_status") == "downloaded":
            downloaded += 1
        by_court_type[key] = (total, downloaded)
    for audit in court_audits:
        total, downloaded = by_court_type.get((audit["source_id"], audit["document_type"]), (0, 0))
        if total:
            audit["documents_found"] = str(total)
            audit["downloaded"] = str(downloaded)
            audit["missing_or_failed"] = str(total - downloaded)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire official gazettes and court PDFs.")
    parser.add_argument("--start-year", type=int, default=1948)
    parser.add_argument("--end-year", type=int, default=CURRENT_YEAR)
    parser.add_argument(
        "--source",
        action="append",
        choices=["all", "gazettes", "extra-gazettes", "supreme-court", "court-of-appeal"],
        default=[],
        help="Source track to acquire. Repeatable. Defaults to all.",
    )
    parser.add_argument(
        "--languages",
        default="all",
        help="Comma-separated gazette languages: English,Sinhala,Tamil, or all. Court language is not filtered.",
    )
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument(
        "--prune-source-metadata",
        action="store_true",
        help="Remove non-downloaded manifest rows for selected sources if they are not rediscovered.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--discovery-concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.source:
        args.source = ["all"]
    started = utc_now()
    corpus = load_corpus_module()

    candidates, gazette_coverage, court_audits = discover_candidates(args)
    if args.prune_source_metadata:
        prune_stale_metadata_rows(candidates, corpus.DOCUMENT_MANIFEST_FIELDS)
    manifest_rows = merge_manifest_candidates(candidates, corpus.DOCUMENT_MANIFEST_FIELDS)
    write_source_registry(corpus.SOURCE_REGISTRY_FIELDS, utc_now())

    counts: dict[str, int] = {}
    errors: list[str] = []
    if not args.metadata_only:
        existing = {
            row.get("document_id", ""): row
            for row in manifest_rows
            if row.get("document_id")
        }
        selected: list[DocumentCandidate] = []
        for candidate in candidates:
            existing_row = existing.get(candidate.document_id, {})
            if existing_row.get("acquisition_status") == "downloaded" and not args.force:
                continue
            selected.append(candidate)
        results: list[DownloadResult] = []
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
                if args.progress and (completed_count == 1 or completed_count % 100 == 0 or completed_count == len(selected)):
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

    update_coverage_download_counts(gazette_coverage, court_audits, manifest_rows)
    write_csv(GAZETTE_COVERAGE_PATH, GAZETTE_COVERAGE_FIELDS, gazette_coverage)
    write_csv(COURT_AUDIT_PATH, COURT_AUDIT_FIELDS, court_audits)
    update_missing_register(corpus.MISSING_DATA_FIELDS, manifest_rows, utc_now())

    latest = {
        "gazette_and_court_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "start_year": args.start_year,
            "end_year": args.end_year,
            "sources": args.source,
            "languages": args.languages,
            "metadata_only": args.metadata_only,
            "candidates_found": len(candidates),
            "download_counts": counts,
            "errors": errors[:200],
            "errors_truncated": max(0, len(errors) - 200),
        }
    }
    corpus.build_corpus_index(latest)
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_gazettes_courts",
            "source_id": "GOV_GAZETTES;GOV_EXTRA_GAZETTES;SC_OFFICIAL;CA_OFFICIAL",
            "run_type": "gazette_and_court_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(candidates)),
            "documents_downloaded": str(counts.get("downloaded", 0)),
            "errors": json.dumps(errors[:200], ensure_ascii=False),
            "new_missing_items": "",
            "notes": json.dumps(latest["gazette_and_court_acquisition"], ensure_ascii=False),
        }
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
