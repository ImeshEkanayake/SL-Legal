#!/usr/bin/env python3
"""Create a lightweight data tracking folder from corpus manifests.

The tracker intentionally stores CSVs and category READMEs only. It does not
copy the raw corpus PDFs, which are referenced by their existing local paths.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
TRACKING_DIR = PROJECT_ROOT / "data_tracking"
TRACKERS_DIR = TRACKING_DIR / "trackers"
CATEGORIES_DIR = TRACKING_DIR / "categories"

DOCUMENT_MANIFEST = MANIFEST_DIR / "document_manifest.csv"
MISSING_REGISTER = MANIFEST_DIR / "missing_data_register.csv"
SOURCE_REGISTRY = MANIFEST_DIR / "source_registry.csv"
OCR_REGISTER = MANIFEST_DIR / "ocr_results_register.csv"


CATEGORY_DEFINITIONS = [
    ("01_ordinary_gazettes", "Ordinary Gazettes"),
    ("02_extraordinary_gazettes", "Extraordinary Gazettes"),
    ("03_legislation_acts_constitution", "Legislation, Acts, Ordinances, and Constitution"),
    ("04_government_bills", "Government Bills"),
    ("05_supreme_court", "Supreme Court and Special Determinations"),
    ("06_court_of_appeal", "Court of Appeal"),
    ("07_hansard", "Hansard and Parliamentary Debates"),
    ("08_parliament_business_records", "Parliament Business Records"),
    ("09_law_reports", "Law Reports"),
    ("10_historical_court_material", "Historical Court Material"),
    ("11_privy_council_ceylon_appellate", "Privy Council and Ceylon Appellate Authorities"),
    ("12_lower_courts_tribunals", "High Court, Tribunals, and Lower Courts"),
    ("13_provincial_subnational_law", "Provincial and Subnational Law"),
    ("14_administrative_practice_materials", "Administrative and Practice Materials"),
    ("15_lankalaw_library", "LankaLaw Library"),
    ("16_portal_recovery_and_external_collections", "Portal Recovery and External Collections"),
    ("99_other", "Other / To Classify"),
]

CATEGORY_LABELS = dict(CATEGORY_DEFINITIONS)

LEGISLATION_TYPES = {
    "Act",
    "Acts and Ordinances",
    "Consolidated Act",
    "Constitution",
    "Core Legislation",
    "Legislation",
    "Legislative Enactments",
}

LAW_REPORT_TYPES = {
    "Ceylon Law Recorder",
    "Ceylon Law Reports",
    "Lanka Law Reporter",
    "New Law Report",
    "Sri Lanka Law Report",
}

PARLIAMENT_BUSINESS_SOURCES = {
    "PARL_ADDENDUMS",
    "PARL_COMMITTEE_REPORTS",
    "PARL_CONSULTATIVE_MONTHLY_REPORTS",
    "PARL_MINISTERIAL_CONSULTATIVE_REPORTS",
    "PARL_MINUTES",
    "PARL_ORDER_BOOKS",
    "PARL_ORDER_OF_BUSINESS",
    "PARL_ORDER_PAPERS",
    "PARL_PAPERS_PRESENTED",
    "PARL_PROGRESS_REPORTS",
    "PARL_SPEAKER_PAPERS",
}

HAVE_STATUSES = {"downloaded"}
MISSING_STATUSES = {
    "download_failed",
    "metadata_extracted",
    "metadata_extracted_pdf_not_found",
    "licensed_purchase_required",
}

HAVE_FIELDS = [
    "category_id",
    "category_name",
    "source_id",
    "source_name",
    "reliability_tier",
    "document_id",
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
    "ocr_status",
    "ocr_confidence_band",
    "ocr_text_path",
    "text_path",
    "pages_path",
    "text_quality_score",
    "legal_status",
    "next_action",
    "last_checked",
    "notes",
]

NEED_FIELDS = [
    "tracker_type",
    "category_id",
    "category_name",
    "missing_id",
    "document_id",
    "source_id",
    "document_type",
    "title",
    "year",
    "number",
    "date",
    "language",
    "expected_coverage",
    "known_available_coverage",
    "source_url",
    "download_url",
    "local_path",
    "acquisition_status",
    "extraction_status",
    "missing_reason",
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

SUMMARY_FIELDS = [
    "category_id",
    "category_name",
    "manifest_rows",
    "downloaded",
    "missing_document_rows",
    "missing_register_rows",
    "download_failed",
    "metadata_extracted",
    "metadata_extracted_pdf_not_found",
    "licensed_purchase_required",
    "text_extracted",
    "text_empty_needs_ocr",
    "package_extracted",
    "extraction_not_started",
    "ocr_completed_high",
    "ocr_completed_medium",
    "ocr_completed_low",
    "english_rows",
    "sinhala_rows",
    "tamil_rows",
    "unknown_language_rows",
]

SOURCE_SUMMARY_FIELDS = [
    "source_id",
    "source_name",
    "category_id",
    "category_name",
    "manifest_rows",
    "downloaded",
    "missing_document_rows",
    "download_failed",
    "metadata_extracted",
    "metadata_extracted_pdf_not_found",
    "licensed_purchase_required",
    "text_extracted",
    "text_empty_needs_ocr",
    "package_extracted",
    "extraction_not_started",
    "first_year",
    "last_year",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def parse_note_values(notes: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in (notes or "").split(";"):
        item = part.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def category_for_document(row: dict[str, str]) -> str:
    source_id = row.get("source_id", "")
    document_type = row.get("document_type", "")
    title = row.get("title", "")

    if source_id == "GOV_GAZETTES":
        return "01_ordinary_gazettes"
    if source_id == "GOV_EXTRA_GAZETTES":
        return "02_extraordinary_gazettes"
    if source_id == "PARL_GOV_BILLS":
        return "04_government_bills"
    if source_id in {"SC_OFFICIAL", "PARL_SC_DECISIONS_ON_BILLS"} or "Supreme Court" in document_type:
        return "05_supreme_court"
    if source_id == "CA_OFFICIAL" or "Court of Appeal" in document_type:
        return "06_court_of_appeal"
    if source_id.startswith("PARL_HANSARD"):
        return "07_hansard"
    if document_type in LAW_REPORT_TYPES:
        return "09_law_reports"
    if source_id == "UVA_HEALTH_STATUTES" or document_type == "Provincial Statute":
        return "13_provincial_subnational_law"
    if source_id == "UVA_PSC_LEGAL_PROVISIONS":
        if "Constitution" in document_type:
            return "03_legislation_acts_constitution"
        if "Provincial" in document_type or "Provincial" in title:
            return "13_provincial_subnational_law"
        return "14_administrative_practice_materials"
    if source_id == "CBSL_RULES_DIRECTIONS":
        return "14_administrative_practice_materials"
    if source_id == "PARL_ACTS" or document_type in LEGISLATION_TYPES:
        return "03_legislation_acts_constitution"
    if source_id in PARLIAMENT_BUSINESS_SOURCES:
        return "08_parliament_business_records"
    if source_id == "LANKALAW_NET":
        return "15_lankalaw_library"
    return "99_other"


def category_for_missing(row: dict[str, str]) -> str:
    category = row.get("data_category", "").lower()
    if "extraordinary gazette" in category:
        return "02_extraordinary_gazettes"
    if "ordinary gazette" in category:
        return "01_ordinary_gazettes"
    if "acts" in category or "constitution" in category or "legislation" in category or "ordinance" in category:
        return "03_legislation_acts_constitution"
    if "government bills" in category or "bill" in category:
        return "04_government_bills"
    if "supreme court" in category:
        return "05_supreme_court"
    if "court of appeal" in category:
        return "06_court_of_appeal"
    if "hansard" in category or "parliamentary debates" in category:
        return "07_hansard"
    if "parliament business" in category or "papers presented" in category or "committee proceedings" in category:
        return "08_parliament_business_records"
    if "law report" in category or "nlr" in category or "slr" in category:
        return "09_law_reports"
    if "historical court" in category:
        return "10_historical_court_material"
    if "privy council" in category or "ceylon appellate" in category:
        return "11_privy_council_ceylon_appellate"
    if "high court" in category or "tribunal" in category or "lower-court" in category or "lower court" in category:
        return "12_lower_courts_tribunals"
    if "provincial" in category or "subnational" in category or "local authority" in category:
        return "13_provincial_subnational_law"
    if "practice" in category or "administrative" in category or "circular" in category or "forms" in category:
        return "14_administrative_practice_materials"
    if "lankalaw" in category:
        return "15_lankalaw_library"
    if "lawnet" in category or "commonlii" in category or "portal" in category:
        return "16_portal_recovery_and_external_collections"

    text = " ".join(
        [
            row.get("data_category", ""),
            row.get("missing_description", ""),
            row.get("probable_source", ""),
            row.get("notes", ""),
        ]
    ).lower()
    if "lankalaw" in text:
        return "15_lankalaw_library"
    if "lawnet" in text or "commonlii" in text or "portal" in text:
        return "16_portal_recovery_and_external_collections"
    if "privy council" in text or "ceylon appellate" in text:
        return "11_privy_council_ceylon_appellate"
    if "historical court" in text:
        return "10_historical_court_material"
    if "high court" in text or "tribunal" in text or "lower-court" in text or "lower court" in text:
        return "12_lower_courts_tribunals"
    if "provincial" in text or "subnational" in text or "local authority" in text:
        return "13_provincial_subnational_law"
    if "practice" in text or "administrative" in text or "circular" in text or "forms" in text:
        return "14_administrative_practice_materials"
    if "extraordinary gazette" in text:
        return "02_extraordinary_gazettes"
    if "ordinary gazette" in text:
        return "01_ordinary_gazettes"
    if "government bills" in text or "bill" in text:
        return "04_government_bills"
    if "hansard" in text or "parliamentary debates" in text:
        return "07_hansard"
    if "parliament business" in text or "papers presented" in text or "committee proceedings" in text:
        return "08_parliament_business_records"
    if "supreme court" in text:
        return "05_supreme_court"
    if "court of appeal" in text:
        return "06_court_of_appeal"
    if "law report" in text or "nlr" in text or "slr" in text:
        return "09_law_reports"
    if "acts" in text or "constitution" in text or "legislation" in text or "ordinance" in text:
        return "03_legislation_acts_constitution"
    return "99_other"


def normalise_year(value: str) -> int | None:
    if value and value.isdigit():
        year = int(value)
        if 1800 <= year <= 2100:
            return year
    return None


def make_have_row(
    row: dict[str, str],
    source_info: dict[str, dict[str, str]],
    ocr_info: dict[str, dict[str, str]],
) -> dict[str, str]:
    category_id = category_for_document(row)
    source = source_info.get(row.get("source_id", ""), {})
    notes = parse_note_values(row.get("notes", ""))
    ocr = ocr_info.get(row.get("document_id", ""), {})
    return {
        "category_id": category_id,
        "category_name": CATEGORY_LABELS[category_id],
        "source_id": row.get("source_id", ""),
        "source_name": source.get("source_name", ""),
        "reliability_tier": source.get("reliability_tier", ""),
        "document_id": row.get("document_id", ""),
        "source_document_id": row.get("source_document_id", ""),
        "document_type": row.get("document_type", ""),
        "title": row.get("title", ""),
        "year": row.get("year", ""),
        "number": row.get("number", ""),
        "date": row.get("date", ""),
        "language": row.get("language", ""),
        "source_url": row.get("source_url", ""),
        "download_url": row.get("download_url", ""),
        "local_path": row.get("local_path", ""),
        "file_hash": row.get("file_hash", ""),
        "acquisition_status": row.get("acquisition_status", ""),
        "extraction_status": row.get("extraction_status", ""),
        "ocr_required": row.get("ocr_required", ""),
        "ocr_status": ocr.get("ocr_status", ""),
        "ocr_confidence_band": ocr.get("confidence_band", ""),
        "ocr_text_path": ocr.get("ocr_text_path", ""),
        "text_path": notes.get("text_path", ""),
        "pages_path": notes.get("pages_path", ""),
        "text_quality_score": row.get("text_quality_score", ""),
        "legal_status": row.get("legal_status", ""),
        "next_action": row.get("next_action", ""),
        "last_checked": row.get("last_checked", ""),
        "notes": row.get("notes", ""),
    }


def make_missing_doc_row(row: dict[str, str]) -> dict[str, str]:
    category_id = category_for_document(row)
    return {
        "tracker_type": "manifest_document_gap",
        "category_id": category_id,
        "category_name": CATEGORY_LABELS[category_id],
        "missing_id": "DOC_" + row.get("document_id", ""),
        "document_id": row.get("document_id", ""),
        "source_id": row.get("source_id", ""),
        "document_type": row.get("document_type", ""),
        "title": row.get("title", ""),
        "year": row.get("year", ""),
        "number": row.get("number", ""),
        "date": row.get("date", ""),
        "language": row.get("language", ""),
        "expected_coverage": "",
        "known_available_coverage": "",
        "source_url": row.get("source_url", ""),
        "download_url": row.get("download_url", ""),
        "local_path": row.get("local_path", ""),
        "acquisition_status": row.get("acquisition_status", ""),
        "extraction_status": row.get("extraction_status", ""),
        "missing_reason": row.get("missing_reason", ""),
        "missing_description": row.get("missing_reason", ""),
        "legal_importance": "",
        "risk_if_missing": "",
        "probable_source": row.get("source_url", ""),
        "next_action": row.get("next_action", ""),
        "owner": "Corpus lead",
        "status": "open" if row.get("acquisition_status") != "licensed_purchase_required" else "license_required",
        "last_checked": row.get("last_checked", ""),
        "notes": row.get("notes", ""),
    }


def make_missing_register_row(row: dict[str, str]) -> dict[str, str]:
    category_id = category_for_missing(row)
    return {
        "tracker_type": "missing_register_gap",
        "category_id": category_id,
        "category_name": CATEGORY_LABELS[category_id],
        "missing_id": row.get("missing_id", ""),
        "document_id": "",
        "source_id": "",
        "document_type": row.get("data_category", ""),
        "title": row.get("data_category", ""),
        "year": "",
        "number": "",
        "date": "",
        "language": "",
        "expected_coverage": row.get("expected_coverage", ""),
        "known_available_coverage": row.get("known_available_coverage", ""),
        "source_url": "",
        "download_url": "",
        "local_path": "",
        "acquisition_status": "",
        "extraction_status": "",
        "missing_reason": row.get("missing_description", ""),
        "missing_description": row.get("missing_description", ""),
        "legal_importance": row.get("legal_importance", ""),
        "risk_if_missing": row.get("risk_if_missing", ""),
        "probable_source": row.get("probable_source", ""),
        "next_action": row.get("next_action", ""),
        "owner": row.get("owner", ""),
        "status": row.get("status", ""),
        "last_checked": row.get("last_checked", ""),
        "notes": row.get("notes", ""),
    }


def source_summary_rows(document_rows: list[dict[str, str]], source_info: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in document_rows:
        grouped[row.get("source_id", "")].append(row)

    rows: list[dict[str, str]] = []
    for source_id, items in sorted(grouped.items()):
        acq = Counter(row.get("acquisition_status", "") for row in items)
        ext = Counter(row.get("extraction_status", "") for row in items)
        categories = Counter(category_for_document(row) for row in items)
        category_id = categories.most_common(1)[0][0]
        years = sorted(year for row in items if (year := normalise_year(row.get("year", ""))) is not None)
        rows.append(
            {
                "source_id": source_id,
                "source_name": source_info.get(source_id, {}).get("source_name", ""),
                "category_id": category_id,
                "category_name": CATEGORY_LABELS[category_id],
                "manifest_rows": str(len(items)),
                "downloaded": str(acq.get("downloaded", 0)),
                "missing_document_rows": str(sum(acq.get(status, 0) for status in MISSING_STATUSES)),
                "download_failed": str(acq.get("download_failed", 0)),
                "metadata_extracted": str(acq.get("metadata_extracted", 0)),
                "metadata_extracted_pdf_not_found": str(acq.get("metadata_extracted_pdf_not_found", 0)),
                "licensed_purchase_required": str(acq.get("licensed_purchase_required", 0)),
                "text_extracted": str(ext.get("text_extracted", 0)),
                "text_empty_needs_ocr": str(ext.get("text_empty_needs_ocr", 0)),
                "package_extracted": str(ext.get("package_extracted", 0)),
                "extraction_not_started": str(ext.get("not_started", 0)),
                "first_year": str(years[0]) if years else "",
                "last_year": str(years[-1]) if years else "",
            }
        )
    return rows


def category_summary_rows(
    document_rows: list[dict[str, str]],
    missing_rows: list[dict[str, str]],
    ocr_info: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    docs_by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    missing_register_counts = Counter(row["category_id"] for row in missing_rows if row["tracker_type"] == "missing_register_gap")

    for row in document_rows:
        docs_by_category[category_for_document(row)].append(row)

    rows: list[dict[str, str]] = []
    for category_id, category_name in CATEGORY_DEFINITIONS:
        docs = docs_by_category.get(category_id, [])
        acq = Counter(row.get("acquisition_status", "") for row in docs)
        ext = Counter(row.get("extraction_status", "") for row in docs)
        lang = Counter(row.get("language", "") or "unknown" for row in docs)
        ocr_band = Counter()
        for row in docs:
            ocr_row = ocr_info.get(row.get("document_id", ""), {})
            band = ocr_row.get("confidence_band", "")
            if band:
                ocr_band[band] += 1
        rows.append(
            {
                "category_id": category_id,
                "category_name": category_name,
                "manifest_rows": str(len(docs)),
                "downloaded": str(acq.get("downloaded", 0)),
                "missing_document_rows": str(sum(acq.get(status, 0) for status in MISSING_STATUSES)),
                "missing_register_rows": str(missing_register_counts.get(category_id, 0)),
                "download_failed": str(acq.get("download_failed", 0)),
                "metadata_extracted": str(acq.get("metadata_extracted", 0)),
                "metadata_extracted_pdf_not_found": str(acq.get("metadata_extracted_pdf_not_found", 0)),
                "licensed_purchase_required": str(acq.get("licensed_purchase_required", 0)),
                "text_extracted": str(ext.get("text_extracted", 0)),
                "text_empty_needs_ocr": str(ext.get("text_empty_needs_ocr", 0)),
                "package_extracted": str(ext.get("package_extracted", 0)),
                "extraction_not_started": str(ext.get("not_started", 0)),
                "ocr_completed_high": str(ocr_band.get("high", 0)),
                "ocr_completed_medium": str(ocr_band.get("medium", 0)),
                "ocr_completed_low": str(ocr_band.get("low", 0)),
                "english_rows": str(lang.get("English", 0)),
                "sinhala_rows": str(lang.get("Sinhala", 0)),
                "tamil_rows": str(lang.get("Tamil", 0)),
                "unknown_language_rows": str(lang.get("unknown", 0) + lang.get("", 0)),
            }
        )
    return rows


def write_root_readme(now: str, have_count: int, need_count: int, summary_rows: list[dict[str, str]]) -> None:
    downloaded = sum(int(row["downloaded"]) for row in summary_rows)
    missing_doc_rows = sum(int(row["missing_document_rows"]) for row in summary_rows)
    missing_register_rows = sum(int(row["missing_register_rows"]) for row in summary_rows)
    lines = [
        "# Data Tracking",
        "",
        f"Generated: {now}",
        "",
        "This folder tracks what is already in the corpus and what still needs to be obtained.",
        "It does not duplicate raw PDFs or OCR outputs. Tracker rows point back to files under `data/`.",
        "",
        "## Main Trackers",
        "",
        "- `trackers/what_we_have.csv` - downloaded corpus records with source, local path, hash, extraction, and OCR status.",
        "- `trackers/what_we_need.csv` - document-level acquisition gaps plus high-level missing-data register gaps.",
        "- `trackers/category_summary.csv` - category-level counts.",
        "- `trackers/source_summary.csv` - source-level counts.",
        "- `tracking_manifest.json` - generation metadata and file locations.",
        "",
        "## Current Totals",
        "",
        f"- Downloaded rows tracked: {downloaded}",
        f"- Rows in `what_we_have.csv`: {have_count}",
        f"- Document rows still to obtain: {missing_doc_rows}",
        f"- High-level missing register rows: {missing_register_rows}",
        f"- Rows in `what_we_need.csv`: {need_count}",
        "",
        "## Category Folders",
        "",
        "Each folder in `categories/` contains category-specific `what_we_have.csv`, `what_we_need.csv`, and a short README.",
        "",
        "## Update Rule",
        "",
        "After new downloads or OCR, rerun:",
        "",
        "```bash",
        "python3 scripts/create_data_tracking.py",
        "```",
        "",
    ]
    (TRACKING_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_category_readme(
    category_dir: Path,
    now: str,
    category_id: str,
    category_name: str,
    summary: dict[str, str],
) -> None:
    lines = [
        f"# {category_name}",
        "",
        f"Generated: {now}",
        "",
        "This folder contains tracker slices for this document category only.",
        "Raw documents remain in the main `data/` corpus tree.",
        "",
        "## Counts",
        "",
        f"- Manifest rows: {summary['manifest_rows']}",
        f"- Downloaded: {summary['downloaded']}",
        f"- Document rows still to obtain: {summary['missing_document_rows']}",
        f"- High-level missing register rows: {summary['missing_register_rows']}",
        f"- Text extracted: {summary['text_extracted']}",
        f"- OCR-needed rows in manifest: {summary['text_empty_needs_ocr']}",
        f"- OCR completed high/medium/low: {summary['ocr_completed_high']} / {summary['ocr_completed_medium']} / {summary['ocr_completed_low']}",
        "",
        "## Files",
        "",
        "- `what_we_have.csv`",
        "- `what_we_need.csv`",
        "",
        f"Category ID: `{category_id}`",
        "",
    ]
    (category_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    now = utc_now()
    document_rows = read_csv(DOCUMENT_MANIFEST)
    missing_register = read_csv(MISSING_REGISTER)
    source_info = {row.get("source_id", ""): row for row in read_csv(SOURCE_REGISTRY)}
    ocr_info = {row.get("document_id", ""): row for row in read_csv(OCR_REGISTER) if row.get("document_id")}

    TRACKERS_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)

    have_rows = [
        make_have_row(row, source_info, ocr_info)
        for row in document_rows
        if row.get("acquisition_status", "") in HAVE_STATUSES
    ]
    missing_doc_rows = [
        make_missing_doc_row(row)
        for row in document_rows
        if row.get("acquisition_status", "") in MISSING_STATUSES
    ]
    missing_register_rows = [make_missing_register_row(row) for row in missing_register]
    need_rows = missing_doc_rows + missing_register_rows

    summary_rows = category_summary_rows(document_rows, need_rows, ocr_info)
    source_rows = source_summary_rows(document_rows, source_info)

    write_csv(TRACKERS_DIR / "what_we_have.csv", HAVE_FIELDS, have_rows)
    write_csv(TRACKERS_DIR / "what_we_need.csv", NEED_FIELDS, need_rows)
    write_csv(TRACKERS_DIR / "category_summary.csv", SUMMARY_FIELDS, summary_rows)
    write_csv(TRACKERS_DIR / "source_summary.csv", SOURCE_SUMMARY_FIELDS, source_rows)

    have_by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    need_by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in have_rows:
        have_by_category[row["category_id"]].append(row)
    for row in need_rows:
        need_by_category[row["category_id"]].append(row)

    summary_by_category = {row["category_id"]: row for row in summary_rows}
    for category_id, category_name in CATEGORY_DEFINITIONS:
        category_dir = CATEGORIES_DIR / category_id
        category_dir.mkdir(parents=True, exist_ok=True)
        write_csv(category_dir / "what_we_have.csv", HAVE_FIELDS, have_by_category.get(category_id, []))
        write_csv(category_dir / "what_we_need.csv", NEED_FIELDS, need_by_category.get(category_id, []))
        write_category_readme(category_dir, now, category_id, category_name, summary_by_category[category_id])

    write_root_readme(now, len(have_rows), len(need_rows), summary_rows)

    tracking_manifest = {
        "generated_at": now,
        "project_root": str(PROJECT_ROOT),
        "source_manifests": {
            "document_manifest": str(DOCUMENT_MANIFEST.relative_to(PROJECT_ROOT)),
            "missing_data_register": str(MISSING_REGISTER.relative_to(PROJECT_ROOT)),
            "source_registry": str(SOURCE_REGISTRY.relative_to(PROJECT_ROOT)),
            "ocr_results_register": str(OCR_REGISTER.relative_to(PROJECT_ROOT)),
        },
        "outputs": {
            "what_we_have": str((TRACKERS_DIR / "what_we_have.csv").relative_to(PROJECT_ROOT)),
            "what_we_need": str((TRACKERS_DIR / "what_we_need.csv").relative_to(PROJECT_ROOT)),
            "category_summary": str((TRACKERS_DIR / "category_summary.csv").relative_to(PROJECT_ROOT)),
            "source_summary": str((TRACKERS_DIR / "source_summary.csv").relative_to(PROJECT_ROOT)),
            "categories_dir": str(CATEGORIES_DIR.relative_to(PROJECT_ROOT)),
        },
        "counts": {
            "document_manifest_rows": len(document_rows),
            "what_we_have_rows": len(have_rows),
            "what_we_need_rows": len(need_rows),
            "missing_document_rows": len(missing_doc_rows),
            "missing_register_rows": len(missing_register_rows),
        },
        "category_definitions": [
            {"category_id": category_id, "category_name": category_name}
            for category_id, category_name in CATEGORY_DEFINITIONS
        ],
    }
    (TRACKING_DIR / "tracking_manifest.json").write_text(
        json.dumps(tracking_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(tracking_manifest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
