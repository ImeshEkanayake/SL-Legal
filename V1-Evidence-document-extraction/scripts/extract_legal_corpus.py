#!/usr/bin/env python3
"""Bootstrap extractor for the Sri Lankan legal corpus.

This script is intentionally conservative:
- official/source metadata is saved before deeper parsing;
- every document gets a manifest row;
- missing or unverified files are represented explicitly;
- generated indexes summarize what has been collected so far.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXTRACTED_DIR = DATA_DIR / "extracted"
MANIFEST_DIR = DATA_DIR / "manifests"
INDEX_DIR = DATA_DIR / "indexes"

USER_AGENT = (
    "SL-Legal-Assist-Corpus-Bootstrap/0.1 "
    "(metadata extraction; contact project owner)"
)


SOURCE_REGISTRY_FIELDS = [
    "source_id",
    "source_name",
    "source_url",
    "source_owner",
    "reliability_tier",
    "legal_authority_type",
    "jurisdiction",
    "languages",
    "coverage_start",
    "coverage_end",
    "coverage_confidence",
    "licence_status",
    "access_method",
    "refresh_frequency",
    "known_gaps",
    "notes",
    "last_checked",
]

DOCUMENT_MANIFEST_FIELDS = [
    "document_id",
    "source_id",
    "source_document_id",
    "document_type",
    "title",
    "year",
    "number",
    "date",
    "language",
    "source_url",
    "download_url",
    "local_path",
    "file_hash",
    "acquisition_status",
    "extraction_status",
    "ocr_required",
    "text_quality_score",
    "legal_status",
    "missing_reason",
    "next_action",
    "last_checked",
    "notes",
]

LEGAL_INSTRUMENT_FIELDS = [
    "instrument_id",
    "instrument_type",
    "short_title",
    "number",
    "year",
    "certified_date",
    "commencement_date",
    "current_status",
    "source_document_id",
    "source_url",
    "download_url",
    "amends",
    "amended_by",
    "repeals",
    "repealed_by",
    "related_bills",
    "related_gazettes",
    "related_cases",
    "notes",
    "last_checked",
]

MISSING_DATA_FIELDS = [
    "missing_id",
    "data_category",
    "expected_coverage",
    "known_available_coverage",
    "missing_description",
    "legal_importance",
    "risk_if_missing",
    "probable_source",
    "next_action",
    "owner",
    "status",
    "last_checked",
    "notes",
]

EXTRACTION_RUN_FIELDS = [
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

MISSING_ACT_PDF_REPORT_FIELDS = [
    "document_id",
    "year",
    "number",
    "title",
    "source_document_id",
    "acquisition_status",
    "extraction_status",
    "source_url",
    "download_url",
    "missing_reason",
    "next_action",
    "last_checked",
]


@dataclass
class FetchResult:
    url: str
    status: int | None
    content_type: str
    content_length: int | None
    data: bytes
    error: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    dirs = [
        RAW_DIR / "official" / "parliament" / "acts_listing",
        RAW_DIR / "official" / "parliament" / "acts_pdfs" / "english",
        RAW_DIR / "official" / "government_printing",
        RAW_DIR / "official" / "supreme_court",
        RAW_DIR / "official" / "court_of_appeal",
        RAW_DIR / "official" / "lawnet",
        RAW_DIR / "law_reports",
        RAW_DIR / "archives",
        RAW_DIR / "licensed",
        RAW_DIR / "firm_uploads",
        EXTRACTED_DIR / "text",
        EXTRACTED_DIR / "ocr",
        EXTRACTED_DIR / "layout",
        EXTRACTED_DIR / "tables",
        EXTRACTED_DIR / "citations",
        MANIFEST_DIR,
        INDEX_DIR,
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def merge_rows(
    path: Path,
    fieldnames: list[str],
    new_rows: Iterable[dict[str, str]],
    key_fields: tuple[str, ...],
) -> list[dict[str, str]]:
    existing = read_csv(path)
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    order: list[tuple[str, ...]] = []
    for row in existing:
        key = tuple(row.get(field, "") for field in key_fields)
        if key not in merged:
            order.append(key)
        merged[key] = row
    for row in new_rows:
        key = tuple(row.get(field, "") for field in key_fields)
        if key not in merged:
            order.append(key)
        prior = merged.get(key, {})
        updated = {**prior, **{k: v for k, v in row.items() if v != ""}}
        merged[key] = updated
    rows = [merged[key] for key in order]
    write_csv(path, fieldnames, rows)
    return rows


def refresh_acts_missing_register(now: str | None = None) -> None:
    """Keep the high-level Acts missing-data row aligned with the live manifest."""
    now = now or utc_now()
    docs = read_csv(MANIFEST_DIR / "document_manifest.csv")
    acts = [
        row
        for row in docs
        if row.get("source_id") == "PARL_ACTS" and row.get("document_type") == "Act"
    ]
    years = sorted({int(row["year"]) for row in acts if row.get("year", "").isdigit()})
    coverage = f"{years[0]}-{years[-1]}" if years else "unknown"

    def count(field: str, value: str) -> int:
        return sum(1 for row in acts if row.get(field) == value)

    downloaded = count("acquisition_status", "downloaded")
    metadata_only = count("acquisition_status", "metadata_extracted")
    pdf_not_found = count("acquisition_status", "metadata_extracted_pdf_not_found")
    pdf_not_discoverable = count("acquisition_status", "metadata_extracted_pdf_not_discoverable")
    download_failed = count("acquisition_status", "download_failed")
    download_timeout = count("acquisition_status", "download_timeout")
    text_extracted = count("extraction_status", "text_extracted")
    text_empty = count("extraction_status", "text_empty_needs_ocr")
    text_failed = count("extraction_status", "text_extraction_failed")

    notes = (
        f"Parliament Acts corpus has {len(acts)} metadata rows ({coverage}); "
        f"{downloaded} official PDFs downloaded; "
        f"{text_extracted} PDFs have extracted text; "
        f"{text_empty} downloaded PDFs need OCR; "
        f"{pdf_not_found} predictable official PDFs were not found; "
        f"{pdf_not_discoverable} PDF URLs are not discoverable; "
        f"{metadata_only} Acts remain metadata-only/unattempted; "
        f"{download_failed + download_timeout} acquisition attempts need retry; "
        f"{text_failed} text extraction attempts failed."
    )
    merge_rows(
        MANIFEST_DIR / "missing_data_register.csv",
        MISSING_DATA_FIELDS,
        [
            {
                "missing_id": "M003",
                "known_available_coverage": (
                    f"Parliament metadata {coverage}; official PDFs downloaded for "
                    f"{downloaded} Acts; text attempted for {text_extracted + text_empty} PDFs."
                ),
                "next_action": (
                    "Continue decade-by-decade PDF acquisition; OCR text_empty_needs_ocr "
                    "files; resolve pdf_not_found via detail pages, Government Printing, "
                    "LawNet, National Archives, or licensed sources."
                ),
                "status": "open",
                "notes": notes,
                "last_checked": now,
            }
        ],
        ("missing_id",),
    )
    write_missing_act_pdf_report(acts)


def write_missing_act_pdf_report(acts: list[dict[str, str]]) -> None:
    missing_rows = [
        {
            "document_id": row.get("document_id", ""),
            "year": row.get("year", ""),
            "number": row.get("number", ""),
            "title": row.get("title", ""),
            "source_document_id": row.get("source_document_id", ""),
            "acquisition_status": row.get("acquisition_status", ""),
            "extraction_status": row.get("extraction_status", ""),
            "source_url": row.get("source_url", ""),
            "download_url": row.get("download_url", ""),
            "missing_reason": row.get("missing_reason", ""),
            "next_action": row.get("next_action", ""),
            "last_checked": row.get("last_checked", ""),
        }
        for row in acts
        if row.get("acquisition_status") != "downloaded"
    ]
    missing_rows.sort(
        key=lambda row: (
            int(row["year"]) if row.get("year", "").isdigit() else 9999,
            int(row["number"]) if row.get("number", "").isdigit() else 9999,
            row.get("title", ""),
        )
    )
    write_csv(
        MANIFEST_DIR / "missing_act_pdf_report.csv",
        MISSING_ACT_PDF_REPORT_FIELDS,
        missing_rows,
    )


def request_url(url: str, *, method: str = "GET", timeout: int = 30) -> FetchResult:
    req = Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = response.read() if method != "HEAD" else b""
            length = response.headers.get("Content-Length")
            return FetchResult(
                url=url,
                status=response.status,
                content_type=response.headers.get("Content-Type", ""),
                content_length=int(length) if length and length.isdigit() else None,
                data=data,
            )
    except HTTPError as exc:
        return FetchResult(
            url=url,
            status=exc.code,
            content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
            content_length=None,
            data=b"",
            error=str(exc),
        )
    except URLError as exc:
        return FetchResult(
            url=url,
            status=None,
            content_type="",
            content_length=None,
            data=b"",
            error=str(exc.reason),
        )


def save_bytes(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
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


def act_number_parts(act_no: str, fallback_year: int) -> tuple[str, str]:
    match = re.match(r"\s*0*([0-9]+)\s*/\s*([0-9]{4})\s*", act_no or "")
    if not match:
        return "", str(fallback_year)
    return match.group(1), match.group(2)


def source_registry_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "source_id": "PARL_ACTS",
            "source_name": "Parliament of Sri Lanka Acts Listing",
            "source_url": "https://www.parliament.lk/en/business-of-parliament/acts-listing",
            "source_owner": "Parliament of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_legislation_metadata",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil where available",
            "coverage_start": "1948",
            "coverage_end": "",
            "coverage_confidence": "metadata_available_year_filter_to_verify",
            "licence_status": "to_review",
            "access_method": "web_csv_export",
            "refresh_frequency": "weekly",
            "known_gaps": "PDF availability varies by year; older detail pages may not expose downloads",
            "notes": "CSV endpoint discovered from official page download control.",
            "last_checked": now,
        },
        {
            "source_id": "GOV_PRINT",
            "source_name": "Department of Government Printing",
            "source_url": "https://www.documents.gov.lk/",
            "source_owner": "Department of Government Printing",
            "reliability_tier": "A",
            "legal_authority_type": "official_publications",
            "jurisdiction": "Sri Lanka",
            "languages": "Sinhala; Tamil; English",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_discovery",
            "licence_status": "to_review",
            "access_method": "web",
            "refresh_frequency": "daily_or_weekly",
            "known_gaps": "Home page may be under construction; specific archives need direct mapping",
            "notes": "Gazettes, Extra-Gazettes, Acts, Bills, Forms, Notices.",
            "last_checked": now,
        },
        {
            "source_id": "GOV_GAZETTES",
            "source_name": "Department of Government Printing Gazette Archive",
            "source_url": "https://www.documents.gov.lk/view/gazettes/find_gazette.html",
            "source_owner": "Department of Government Printing",
            "reliability_tier": "A",
            "legal_authority_type": "official_gazette_archive",
            "jurisdiction": "Sri Lanka",
            "languages": "Sinhala; Tamil; English",
            "coverage_start": "2004",
            "coverage_end": "",
            "coverage_confidence": "visible_archive_years_to_verify",
            "licence_status": "to_review",
            "access_method": "web_archive",
            "refresh_frequency": "daily_or_weekly",
            "known_gaps": "Pre-2004 online coverage not visible in initial source page",
            "notes": "Direct curl to www host returned 404 on initial check; browser/search saw archive page.",
            "last_checked": now,
        },
        {
            "source_id": "SC_OFFICIAL",
            "source_name": "Supreme Court of Sri Lanka",
            "source_url": "https://supremecourt.lk/",
            "source_owner": "Supreme Court of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_court_material",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil where available",
            "coverage_start": "2020_visible_for_judgments",
            "coverage_end": "",
            "coverage_confidence": "partial_visible_online",
            "licence_status": "to_review",
            "access_method": "web",
            "refresh_frequency": "weekly",
            "known_gaps": "Historical judgments prior to visible online years require law reports or archives",
            "notes": "Judgments menu exposes 2020-2026 and special determinations.",
            "last_checked": now,
        },
        {
            "source_id": "CA_OFFICIAL",
            "source_name": "Court of Appeal of Sri Lanka",
            "source_url": "https://courtofappeal.lk/",
            "source_owner": "Court of Appeal of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_court_material",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil where available",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_discovery",
            "licence_status": "to_review",
            "access_method": "web",
            "refresh_frequency": "weekly",
            "known_gaps": "Historical and unreported coverage unknown",
            "notes": "Site exposes Judgments and Orders links.",
            "last_checked": now,
        },
        {
            "source_id": "LAWNET_MOJ",
            "source_name": "LawNet / Ministry of Justice",
            "source_url": "https://www.lawnet.gov.lk/",
            "source_owner": "Ministry of Justice",
            "reliability_tier": "B",
            "legal_authority_type": "government_hosted_legal_portal",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil where available",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_discovery",
            "licence_status": "to_review",
            "access_method": "web",
            "refresh_frequency": "monthly",
            "known_gaps": "Completeness and redirects must be validated",
            "notes": "Lists legislative enactments, core laws, NLR, SLR, SC and CA judgment links.",
            "last_checked": now,
        },
        {
            "source_id": "PARL_HANSARD",
            "source_name": "Parliament Hansard Department",
            "source_url": "https://beta.parliament.lk/en/secretariat/department/handsard",
            "source_owner": "Parliament of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_parliamentary_proceedings",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_discovery",
            "licence_status": "to_review",
            "access_method": "web_and_archival",
            "refresh_frequency": "weekly",
            "known_gaps": "Historical volume download structure not yet mapped",
            "notes": "Department prepares proceedings and verbatim reports.",
            "last_checked": now,
        },
    ]


def initial_missing_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "missing_id": "M001",
            "data_category": "Ordinary Gazettes",
            "expected_coverage": "1948-present",
            "known_available_coverage": "2004-present visible in official archive during source research",
            "missing_description": "Older official gazettes are not yet mapped to machine-downloadable official files.",
            "legal_importance": "critical",
            "risk_if_missing": "Cannot reliably verify commencement notices, regulations, appointments, orders, and delegated legislation.",
            "probable_source": "Department of Government Printing; National Archives; libraries; licensed collections",
            "next_action": "Map official archive paths and identify pre-2004 acquisition route.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
        {
            "missing_id": "M002",
            "data_category": "Extraordinary Gazettes",
            "expected_coverage": "1948-present",
            "known_available_coverage": "Department site exposes Extra-Gazettes link; full coverage unverified",
            "missing_description": "Historical extraordinary gazette coverage is not yet mapped.",
            "legal_importance": "critical",
            "risk_if_missing": "Missing delegated legislation, urgent regulations, orders, and commencement notices.",
            "probable_source": "Department of Government Printing; National Archives",
            "next_action": "Map available years and create per-year manifest.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
        {
            "missing_id": "M003",
            "data_category": "Acts PDFs",
            "expected_coverage": "1948-present",
            "known_available_coverage": "Parliament Acts metadata has year filters from 1948 onward",
            "missing_description": "PDF availability varies by Act; older Act detail pages may not expose a downloadable PDF.",
            "legal_importance": "critical",
            "risk_if_missing": "Metadata alone is insufficient for citation-backed statutory retrieval.",
            "probable_source": "Parliament; Government Printing; LawNet; National Archives; licensed consolidated sources",
            "next_action": "Probe official PDF URLs and record missing PDFs by Act.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
        {
            "missing_id": "M004",
            "data_category": "Supreme Court historical judgments",
            "expected_coverage": "1948-present",
            "known_available_coverage": "Official site exposes recent judgment years and special determinations",
            "missing_description": "Historical Supreme Court judgments before visible online years are not yet acquired.",
            "legal_importance": "critical",
            "risk_if_missing": "Research may miss binding authority.",
            "probable_source": "Supreme Court; LawNet; law reports; National Archives; licensed databases",
            "next_action": "Extract current official site, then map NLR/SLR and archive coverage.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
        {
            "missing_id": "M005",
            "data_category": "Court of Appeal historical judgments and orders",
            "expected_coverage": "1971-present",
            "known_available_coverage": "Official site exposes Judgments and Orders links",
            "missing_description": "Historical and unreported Court of Appeal coverage is not yet mapped.",
            "legal_importance": "critical",
            "risk_if_missing": "Research may miss persuasive or binding appellate material depending on context.",
            "probable_source": "Court of Appeal; LawNet; law reports; National Archives; licensed databases",
            "next_action": "Extract official pages and identify historical gaps.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
        {
            "missing_id": "M006",
            "data_category": "Hansard historical volumes",
            "expected_coverage": "1948-present",
            "known_available_coverage": "Hansard Department exists and prepares official proceedings",
            "missing_description": "Historical Hansard download coverage and OCR quality are not yet mapped.",
            "legal_importance": "high",
            "risk_if_missing": "Legislative history and constitutional debates may be incomplete.",
            "probable_source": "Parliament; National Archives; libraries",
            "next_action": "Map online Hansard and corrected-volume endpoints.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "",
        },
    ]


def bootstrap_registries(now: str) -> None:
    merge_rows(
        MANIFEST_DIR / "source_registry.csv",
        SOURCE_REGISTRY_FIELDS,
        source_registry_rows(now),
        ("source_id",),
    )
    merge_rows(
        MANIFEST_DIR / "missing_data_register.csv",
        MISSING_DATA_FIELDS,
        initial_missing_rows(now),
        ("missing_id",),
    )


def parliament_acts_csv_url(year: int) -> str:
    return (
        "https://www.parliament.lk/en/business-of-parliament/"
        f"download-acts-listing/csv?year={year}"
    )


def candidate_act_pdf_url(detail_url: str) -> str:
    match = re.search(r"/act-details/G([0-9]+)", detail_url)
    if not match:
        return ""
    return f"https://www.parliament.lk/uploads/acts/gbills/english/{match.group(1)}.pdf"


def probe_pdf(url: str) -> tuple[bool, str, int | None]:
    if not url:
        return False, "", None
    result = request_url(url, method="HEAD", timeout=20)
    if result.status == 200 and "pdf" in result.content_type.lower():
        return True, result.content_type, result.content_length
    return False, result.content_type, result.content_length


def download_pdf(url: str, path: Path) -> tuple[bool, str, str]:
    result = request_url(url, timeout=60)
    if result.status == 200 and result.data and "pdf" in result.content_type.lower():
        digest = save_bytes(path, result.data)
        return True, digest, ""
    return False, "", result.error or f"status={result.status} content_type={result.content_type}"


def parse_parliament_acts_csv(csv_bytes: bytes) -> list[dict[str, str]]:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    rows: list[dict[str, str]] = []
    for row in reader:
        if not row.get("Act No.") and not row.get("Act Title"):
            continue
        rows.append(row)
    return rows


def extract_parliament_acts(
    start_year: int,
    end_year: int,
    *,
    probe_pdfs: bool,
    download_pdfs: bool,
    pdf_limit: int,
    sleep_seconds: float,
) -> dict[str, object]:
    now = utc_now()
    document_rows: list[dict[str, str]] = []
    instrument_rows: list[dict[str, str]] = []
    errors: list[str] = []
    documents_found = 0
    documents_downloaded = 0
    pdfs_available = 0
    pdfs_missing = 0
    yearly_counts: dict[str, int] = {}

    for year in range(start_year, end_year + 1):
        url = parliament_acts_csv_url(year)
        result = request_url(url)
        if result.status != 200 or not result.data:
            errors.append(f"{year}: failed to fetch CSV ({result.status}) {result.error}")
            yearly_counts[str(year)] = 0
            continue

        raw_path = RAW_DIR / "official" / "parliament" / "acts_listing" / f"{year}.csv"
        save_bytes(raw_path, result.data)
        acts = parse_parliament_acts_csv(result.data)
        yearly_counts[str(year)] = len(acts)
        documents_found += len(acts)

        for act in acts:
            act_no = (act.get("Act No.") or "").strip()
            title = (act.get("Act Title") or "").strip()
            endorsed_date = (act.get("Endorsed Date") or "").strip()
            detail_url = (act.get("Link to Act") or "").strip()
            number, act_year = act_number_parts(act_no, year)
            detail_id_match = re.search(r"/act-details/(G[0-9]+)", detail_url)
            source_document_id = detail_id_match.group(1) if detail_id_match else ""
            unique_suffix = source_document_id.lower() if source_document_id else safe_slug(title)
            number_part = number.zfill(3) if number else "unknown"
            doc_id = f"parl_act_{act_year}_{number_part}_{unique_suffix}"
            instrument_id = f"act_{act_year}_{number_part}_{unique_suffix}"

            candidate_pdf = candidate_act_pdf_url(detail_url)
            download_url = ""
            acquisition_status = "metadata_extracted"
            missing_reason = ""
            next_action = "Fetch official Act PDF or alternate official text."
            local_path = ""
            file_hash = ""
            notes = f"Detail ID: {source_document_id}" if source_document_id else ""

            if probe_pdfs and candidate_pdf:
                exists, content_type, content_length = probe_pdf(candidate_pdf)
                if exists:
                    pdfs_available += 1
                    download_url = candidate_pdf
                    acquisition_status = "official_pdf_available"
                    next_action = "Download PDF and extract text."
                    notes = f"{notes}; pdf_content_length={content_length or ''}".strip("; ")
                    if download_pdfs and (pdf_limit <= 0 or documents_downloaded < pdf_limit):
                        pdf_path = (
                            RAW_DIR
                            / "official"
                            / "parliament"
                            / "acts_pdfs"
                            / "english"
                            / act_year
                            / f"{number.zfill(3) if number else safe_slug(title)}_{safe_slug(title)[:80]}.pdf"
                        )
                        ok, digest, error = download_pdf(candidate_pdf, pdf_path)
                        if ok:
                            documents_downloaded += 1
                            acquisition_status = "downloaded"
                            local_path = str(pdf_path.relative_to(PROJECT_ROOT))
                            file_hash = digest
                            next_action = "Extract text and segment Act."
                        else:
                            acquisition_status = "official_pdf_available_download_failed"
                            missing_reason = error
                            next_action = "Retry download."
                else:
                    pdfs_missing += 1
                    acquisition_status = "metadata_extracted_pdf_not_found"
                    missing_reason = (
                        f"Candidate official PDF did not resolve: status/content={content_type or 'unknown'}"
                    )
                    next_action = "Locate PDF via detail page, LawNet, Government Printing, or archive."
            elif probe_pdfs and not candidate_pdf:
                acquisition_status = "metadata_extracted_pdf_not_discoverable"
                missing_reason = "No predictable candidate PDF URL could be derived."

            document_rows.append(
                {
                    "document_id": doc_id,
                    "source_id": "PARL_ACTS",
                    "source_document_id": source_document_id,
                    "document_type": "Act",
                    "title": title,
                    "year": act_year,
                    "number": number,
                    "date": endorsed_date,
                    "language": "English",
                    "source_url": detail_url,
                    "download_url": download_url,
                    "local_path": local_path,
                    "file_hash": file_hash,
                    "acquisition_status": acquisition_status,
                    "extraction_status": "not_started",
                    "ocr_required": "",
                    "text_quality_score": "",
                    "legal_status": "to_verify",
                    "missing_reason": missing_reason,
                    "next_action": next_action,
                    "last_checked": now,
                    "notes": notes,
                }
            )
            instrument_rows.append(
                {
                    "instrument_id": instrument_id,
                    "instrument_type": "Act",
                    "short_title": title,
                    "number": number,
                    "year": act_year,
                    "certified_date": endorsed_date,
                    "commencement_date": "",
                    "current_status": "to_verify",
                    "source_document_id": source_document_id,
                    "source_url": detail_url,
                    "download_url": download_url,
                    "amends": "",
                    "amended_by": "",
                    "repeals": "",
                    "repealed_by": "",
                    "related_bills": "",
                    "related_gazettes": "",
                    "related_cases": "",
                    "notes": "Imported from Parliament Acts listing.",
                    "last_checked": now,
                }
            )

            if sleep_seconds:
                time.sleep(sleep_seconds)

    merge_rows(
        MANIFEST_DIR / "document_manifest.csv",
        DOCUMENT_MANIFEST_FIELDS,
        document_rows,
        ("document_id",),
    )
    merge_rows(
        MANIFEST_DIR / "legal_instrument_registry.csv",
        LEGAL_INSTRUMENT_FIELDS,
        instrument_rows,
        ("instrument_id",),
    )

    refresh_acts_missing_register(now)

    return {
        "documents_found": documents_found,
        "documents_downloaded": documents_downloaded,
        "pdfs_available": pdfs_available,
        "pdfs_missing": pdfs_missing,
        "yearly_counts": yearly_counts,
        "errors": errors,
    }


def snapshot_source_pages() -> dict[str, object]:
    now = utc_now()
    pages = [
        ("PARL_ACTS_HOME", "PARL_ACTS", "https://www.parliament.lk/en/business-of-parliament/acts-listing"),
        ("GOV_PRINT_HOME", "GOV_PRINT", "https://www.documents.gov.lk/"),
        ("GOV_GAZETTES_ARCHIVE", "GOV_GAZETTES", "https://www.documents.gov.lk/view/gazettes/find_gazette.html"),
        ("SC_OFFICIAL_HOME", "SC_OFFICIAL", "https://supremecourt.lk/"),
        ("SC_OFFICIAL_JUDGMENTS", "SC_OFFICIAL", "https://supremecourt.lk/judgements/"),
        ("CA_OFFICIAL_HOME", "CA_OFFICIAL", "https://courtofappeal.lk/"),
        ("LAWNET_MOJ_HOME", "LAWNET_MOJ", "https://www.lawnet.gov.lk/"),
        ("PARL_HANSARD_DEPT", "PARL_HANSARD", "https://beta.parliament.lk/en/secretariat/department/handsard"),
    ]
    snapshot_rows: list[dict[str, str]] = []
    errors: list[str] = []

    for snapshot_key, source_id, url in pages:
        result = request_url(url)
        parsed = urlparse(url)
        filename = safe_slug(snapshot_key) + ".html"
        path = RAW_DIR / "official" / "_source_pages" / filename
        digest = ""
        local_path = ""
        status = "failed"
        if result.status == 200 and result.data:
            digest = save_bytes(path, result.data)
            local_path = str(path.relative_to(PROJECT_ROOT))
            status = "saved"
        else:
            errors.append(f"{source_id}: {url} ({result.status}) {result.error}")
        snapshot_rows.append(
            {
                "snapshot_id": f"{snapshot_key}_{safe_slug(parsed.netloc)}",
                "source_id": source_id,
                "url": url,
                "status": status,
                "http_status": str(result.status or ""),
                "content_type": result.content_type,
                "local_path": local_path,
                "file_hash": digest,
                "fetched_at": now,
                "notes": result.error,
            }
        )
    write_csv(
        MANIFEST_DIR / "source_snapshots.csv",
        [
            "snapshot_id",
            "source_id",
            "url",
            "status",
            "http_status",
            "content_type",
            "local_path",
            "file_hash",
            "fetched_at",
            "notes",
        ],
        snapshot_rows,
    )
    return {"snapshots": len(snapshot_rows), "errors": errors}


def append_run_log(row: dict[str, str]) -> None:
    rows = read_csv(MANIFEST_DIR / "extraction_run_log.csv")
    rows.append(row)
    write_csv(MANIFEST_DIR / "extraction_run_log.csv", EXTRACTION_RUN_FIELDS, rows)


def build_corpus_index(extra: dict[str, object] | None = None) -> None:
    docs = read_csv(MANIFEST_DIR / "document_manifest.csv")
    sources = read_csv(MANIFEST_DIR / "source_registry.csv")
    missing = read_csv(MANIFEST_DIR / "missing_data_register.csv")
    instruments = read_csv(MANIFEST_DIR / "legal_instrument_registry.csv")

    def count_by(rows: list[dict[str, str]], field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            key = row.get(field) or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    acts_by_year: dict[str, int] = {}
    for row in docs:
        if row.get("document_type") == "Act":
            year = row.get("year") or "unknown"
            acts_by_year[year] = acts_by_year.get(year, 0) + 1

    index = {
        "generated_at": utc_now(),
        "project_root": str(PROJECT_ROOT),
        "totals": {
            "sources": len(sources),
            "documents": len(docs),
            "legal_instruments": len(instruments),
            "missing_data_items": len(missing),
        },
        "documents_by_source": count_by(docs, "source_id"),
        "documents_by_type": count_by(docs, "document_type"),
        "documents_by_acquisition_status": count_by(docs, "acquisition_status"),
        "missing_by_status": count_by(missing, "status"),
        "acts_by_year": dict(sorted(acts_by_year.items())),
        "latest_run": extra or {},
    }
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (INDEX_DIR / "corpus_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Sri Lankan legal corpus metadata.")
    parser.add_argument("--start-year", type=int, default=1948)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument("--skip-acts", action="store_true")
    parser.add_argument("--skip-snapshots", action="store_true")
    parser.add_argument("--probe-pdfs", action="store_true")
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument(
        "--pdf-limit",
        type=int,
        default=0,
        help="Maximum PDFs to download in this run. 0 means no limit.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Optional delay between per-document PDF probes/downloads.",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit with status 1 if source warnings or extraction errors occurred.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ensure_dirs()
    started_at = utc_now()
    bootstrap_registries(started_at)

    latest: dict[str, object] = {
        "started_at": started_at,
        "end_year": args.end_year,
        "start_year": args.start_year,
    }
    all_errors: list[str] = []
    documents_found = 0
    documents_downloaded = 0

    if not args.skip_snapshots:
        snapshot_result = snapshot_source_pages()
        latest["source_snapshots"] = snapshot_result
        all_errors.extend(snapshot_result.get("errors", []))

    if not args.skip_acts:
        acts_result = extract_parliament_acts(
            args.start_year,
            args.end_year,
            probe_pdfs=args.probe_pdfs or args.download_pdfs,
            download_pdfs=args.download_pdfs,
            pdf_limit=args.pdf_limit,
            sleep_seconds=args.sleep,
        )
        latest["parliament_acts"] = acts_result
        documents_found += int(acts_result["documents_found"])
        documents_downloaded += int(acts_result["documents_downloaded"])
        all_errors.extend(acts_result.get("errors", []))

    ended_at = utc_now()
    latest["ended_at"] = ended_at
    latest["errors"] = all_errors
    build_corpus_index(latest)
    append_run_log(
        {
            "run_id": f"run_{started_at.replace(':', '').replace('-', '').replace('+', 'z')}",
            "source_id": "BOOTSTRAP",
            "run_type": "source_snapshots_and_parliament_acts",
            "started_at": started_at,
            "ended_at": ended_at,
            "documents_found": str(documents_found),
            "documents_downloaded": str(documents_downloaded),
            "errors": json.dumps(all_errors, ensure_ascii=False),
            "new_missing_items": "",
            "notes": "Bootstrap extraction run.",
        }
    )

    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 1 if args.fail_on_errors and all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
