#!/usr/bin/env python3
"""Acquire official Parliament business-document PDFs.

This covers legislative-history material around Hansard and Bills: committee
reports, order papers/books, minutes, papers presented, addendums, and Supreme
Court decisions on Bills as exposed by the Parliament English site.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from acquire_parliament_hansards import (
    PROJECT_ROOT,
    BASE_URL,
    DownloadResult,
    download_candidate,
    extract_items,
    fetch_url,
    infer_year,
    load_corpus_module,
    local_filename,
    merge_by_key,
    parse_dotted_date,
    parse_last_page,
    parse_month_date,
    parse_yyyy_mm_dd,
    read_csv,
    safe_slug,
    update_manifest_downloads,
    url_hash,
    utc_now,
    write_csv,
)


DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
RAW_DIR = DATA_DIR / "raw" / "official" / "parliament" / "business_documents"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
BUSINESS_REGISTRY_PATH = MANIFEST_DIR / "parliament_business_docs_registry.csv"

TRACKS = {
    "committee-reports": {
        "source_id": "PARL_COMMITTEE_REPORTS",
        "label": "Committee Reports",
        "document_type": "Parliament Committee Report",
        "url": f"{BASE_URL}/en/business-of-parliament/committees/reports",
        "missing_id": "M_HANSARD_COMMITTEES_INDEXES",
    },
    "ministerial-consultative-reports": {
        "source_id": "PARL_MINISTERIAL_CONSULTATIVE_REPORTS",
        "label": "Reports of Ministerial Consultative Committees",
        "document_type": "Parliament Ministerial Consultative Committee Report",
        "url": f"{BASE_URL}/en/business-of-parliament/min-con-com-reports",
        "missing_id": "M_HANSARD_COMMITTEES_INDEXES",
    },
    "consultative-monthly-reports": {
        "source_id": "PARL_CONSULTATIVE_MONTHLY_REPORTS",
        "label": "Monthly Reports of Consultative Committees",
        "document_type": "Parliament Consultative Committee Monthly Report",
        "url": f"{BASE_URL}/en/business-of-parliament/con-com-reports",
        "missing_id": "M_HANSARD_COMMITTEES_INDEXES",
    },
    "minutes": {
        "source_id": "PARL_MINUTES",
        "label": "Minutes of Parliament",
        "document_type": "Parliament Minutes",
        "url": f"{BASE_URL}/en/business-of-parliament/minutes-of-parliament",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "papers-presented": {
        "source_id": "PARL_PAPERS_PRESENTED",
        "label": "Papers Presented",
        "document_type": "Parliament Paper Presented",
        "url": f"{BASE_URL}/en/business-of-parliament/papers-presented",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "speaker-papers": {
        "source_id": "PARL_SPEAKER_PAPERS",
        "label": "Papers Presented by the Speaker",
        "document_type": "Parliament Speaker Paper",
        "url": f"{BASE_URL}/en/business-of-parliament/papers-by-the-speaker",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "order-papers": {
        "source_id": "PARL_ORDER_PAPERS",
        "label": "Order Papers",
        "document_type": "Parliament Order Paper",
        "url": f"{BASE_URL}/en/business-of-parliament/order-papers",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "order-books": {
        "source_id": "PARL_ORDER_BOOKS",
        "label": "Order Books",
        "document_type": "Parliament Order Book",
        "url": f"{BASE_URL}/en/business-of-parliament/order-books",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "order-of-business": {
        "source_id": "PARL_ORDER_OF_BUSINESS",
        "label": "Order of Business",
        "document_type": "Parliament Order of Business",
        "url": f"{BASE_URL}/en/business-of-parliament/order-of-business",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "addendums": {
        "source_id": "PARL_ADDENDUMS",
        "label": "Addendums",
        "document_type": "Parliament Addendum",
        "url": f"{BASE_URL}/en/business-of-parliament/addendums",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "sc-decisions-on-bills": {
        "source_id": "PARL_SC_DECISIONS_ON_BILLS",
        "label": "Decisions of the Supreme Court on Bills",
        "document_type": "Supreme Court Decision on Bill",
        "url": f"{BASE_URL}/en/business-of-parliament/sc-decisions-on-bills",
        "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
    },
    "progress-reports": {
        "source_id": "PARL_PROGRESS_REPORTS",
        "label": "Progress Reports",
        "document_type": "Parliament Progress Report",
        "url": f"{BASE_URL}/en/business-of-parliament/progress-reports",
        "missing_id": "M_ADMIN_PRACTICE_MATERIALS",
    },
}

BUSINESS_REGISTRY_FIELDS = [
    "document_id",
    "source_id",
    "track",
    "listing_page",
    "title",
    "date",
    "year",
    "language",
    "download_url",
    "local_path",
    "acquisition_status",
    "file_hash",
    "last_checked",
    "notes",
]


@dataclass
class BusinessCandidate:
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
    track: str
    notes: str = ""


def append_run_log(fields: list[str], run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def infer_date(title: str, download_url: str) -> str:
    return (
        parse_yyyy_mm_dd(title)
        or parse_yyyy_mm_dd(download_url)
        or parse_month_date(title)
        or parse_dotted_date(title)
    )


def make_candidate(track: str, title: str, download_url: str, listing_url: str) -> BusinessCandidate:
    config = TRACKS[track]
    date_value = infer_date(title, download_url)
    year = date_value[:4] if date_value else infer_year(title + " " + download_url)
    doc_key = date_value.replace("-", "") if date_value else safe_slug(title, max_len=60)
    document_id = f"parl_{track.replace('-', '_')}_{doc_key}_{url_hash(download_url)}"
    local_path = RAW_DIR / track / (year or "unknown") / local_filename(download_url, title)
    return BusinessCandidate(
        document_id=document_id,
        source_id=config["source_id"],
        source_document_id=Path(unquote(urlparse(download_url).path)).name,
        document_type=config["document_type"],
        title=title,
        year=year,
        number="",
        date=date_value,
        language="English",
        source_url=listing_url,
        download_url=download_url,
        local_path=str(local_path.relative_to(PROJECT_ROOT)),
        legal_status="official_parliamentary_record",
        track=track,
        notes=f"{config['label']} from Parliament English listing.",
    )


def discover_track(track: str, item_count: int, max_pages: int, timeout: int, progress: bool) -> list[BusinessCandidate]:
    base_url = TRACKS[track]["url"]
    candidates: list[BusinessCandidate] = []
    seen_urls: set[str] = set()
    seen_page_signatures: set[tuple[str, ...]] = set()
    discovered_last_page = 0
    for page in range(1, max_pages + 1):
        listing_url = f"{base_url}?itemCount={item_count}&page={page}"
        if progress:
            print(f"discover {track} page {page}", file=sys.stderr, flush=True)
        result = fetch_url(listing_url, timeout, retries=2)
        if result.status != 200:
            break
        page_html = result.data.decode("utf-8", errors="replace")
        if page == 1:
            discovered_last_page = parse_last_page(page_html)
        items = extract_items(page_html, listing_url)
        page_signature = tuple(download_url for _title, download_url in items)
        if not page_signature or page_signature in seen_page_signatures:
            break
        seen_page_signatures.add(page_signature)
        new_on_page = 0
        for title, download_url in items:
            if download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            new_on_page += 1
            candidates.append(make_candidate(track, title, download_url, listing_url))
        if new_on_page == 0:
            break
        if discovered_last_page and page >= discovered_last_page:
            break
    return candidates


def discover_candidates(args: argparse.Namespace) -> list[BusinessCandidate]:
    tracks = args.track or ["all"]
    if "all" in tracks:
        tracks = list(TRACKS)
    candidates: list[BusinessCandidate] = []
    for track in tracks:
        candidates.extend(
            discover_track(
                track,
                item_count=args.item_count,
                max_pages=args.max_pages,
                timeout=args.timeout,
                progress=args.progress,
            )
        )
    deduped: dict[str, BusinessCandidate] = {}
    for candidate in candidates:
        deduped[candidate.document_id] = candidate
    candidates = list(deduped.values())
    if args.limit:
        candidates = candidates[: args.limit]
    return candidates


def candidate_to_manifest_row(candidate: BusinessCandidate, now: str) -> dict[str, str]:
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
        "next_action": "Download official Parliament PDF.",
        "last_checked": now,
        "notes": candidate.notes,
    }


def merge_manifest_candidates(candidates: list[BusinessCandidate], fields: list[str]) -> list[dict[str, str]]:
    now = utc_now()
    existing_rows = read_csv(DOCUMENT_MANIFEST_PATH)
    by_id = {row.get("document_id", ""): row for row in existing_rows if row.get("document_id")}
    order = [row.get("document_id", "") for row in existing_rows if row.get("document_id")]
    for candidate in candidates:
        row = candidate_to_manifest_row(candidate, now)
        prior = by_id.get(candidate.document_id)
        if prior:
            merged = {**prior}
            for key, value in row.items():
                if not value:
                    continue
                if key in {"local_path", "file_hash", "acquisition_status", "extraction_status"}:
                    continue
                if key == "next_action" and prior.get("acquisition_status") == "downloaded":
                    continue
                merged[key] = value
            by_id[candidate.document_id] = merged
        else:
            by_id[candidate.document_id] = row
            order.append(candidate.document_id)
    rows = [by_id[document_id] for document_id in order if document_id]
    write_csv(DOCUMENT_MANIFEST_PATH, fields, rows)
    return rows


def write_source_registry(fields: list[str], candidates: list[BusinessCandidate], now: str) -> None:
    active_sources = {candidate.source_id for candidate in candidates}
    rows: list[dict[str, str]] = []
    for track, config in TRACKS.items():
        if active_sources and config["source_id"] not in active_sources:
            continue
        rows.append(
            {
                "source_id": config["source_id"],
                "source_name": f"Parliament of Sri Lanka {config['label']}",
                "source_url": config["url"],
                "source_owner": "Parliament of Sri Lanka",
                "reliability_tier": "A",
                "legal_authority_type": "official_parliamentary_record",
                "jurisdiction": "Sri Lanka",
                "languages": "English listing acquired; Sinhala/Tamil not collected where English exists",
                "coverage_start": "online coverage discovered from listing",
                "coverage_end": "",
                "coverage_confidence": "official_listing_to_verify",
                "licence_status": "to_review",
                "access_method": "web_listing",
                "refresh_frequency": "weekly_or_monthly",
                "known_gaps": "Online listing may not cover full historical records.",
                "notes": f"Track key: {track}.",
                "last_checked": now,
            }
        )
    merge_by_key(SOURCE_REGISTRY_PATH, fields, rows, "source_id")


def write_business_registry(candidates: list[BusinessCandidate], results: list[DownloadResult]) -> None:
    now = utc_now()
    result_by_id = {result.document_id: result for result in results}
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
                "track": candidate.track,
                "listing_page": candidate.source_url,
                "title": candidate.title,
                "date": candidate.date,
                "year": candidate.year,
                "language": candidate.language,
                "download_url": candidate.download_url,
                "local_path": result.local_path if result else manifest.get("local_path", ""),
                "acquisition_status": result.status if result else manifest.get("acquisition_status", ""),
                "file_hash": result.file_hash if result else manifest.get("file_hash", ""),
                "last_checked": now,
                "notes": candidate.notes,
            }
        )
    merge_by_key(BUSINESS_REGISTRY_PATH, BUSINESS_REGISTRY_FIELDS, rows, "document_id")


def update_missing_register(fields: list[str], manifest_rows: list[dict[str, str]], now: str) -> None:
    def source_summary(source_ids: set[str]) -> tuple[int, int]:
        rows = [row for row in manifest_rows if row.get("source_id") in source_ids]
        return len(rows), sum(1 for row in rows if row.get("acquisition_status") == "downloaded")

    committee_sources = {
        "PARL_COMMITTEE_REPORTS",
        "PARL_MINISTERIAL_CONSULTATIVE_REPORTS",
        "PARL_CONSULTATIVE_MONTHLY_REPORTS",
    }
    business_sources = {
        "PARL_MINUTES",
        "PARL_PAPERS_PRESENTED",
        "PARL_SPEAKER_PAPERS",
        "PARL_ORDER_PAPERS",
        "PARL_ORDER_BOOKS",
        "PARL_ORDER_OF_BUSINESS",
        "PARL_ADDENDUMS",
        "PARL_SC_DECISIONS_ON_BILLS",
    }
    committee_total, committee_downloaded = source_summary(committee_sources)
    business_total, business_downloaded = source_summary(business_sources)
    rows = [
        {
            "missing_id": "M_HANSARD_COMMITTEES_INDEXES",
            "known_available_coverage": (
                f"Official Parliament committee-related listings discovered {committee_total} rows; "
                f"{committee_downloaded} downloaded. Historical committee proceedings and indexes still need archival mapping."
            ),
            "next_action": "Continue committee/report acquisition and locate corrected-volume indexes and pre-online committee proceedings.",
            "status": "open",
            "last_checked": now,
            "notes": "English preferred where available.",
        },
        {
            "missing_id": "M_PARLIAMENT_BUSINESS_DOCS",
            "data_category": "Parliament business records",
            "expected_coverage": "1948-present where available",
            "known_available_coverage": (
                f"Official online Parliament business listings discovered {business_total} rows; "
                f"{business_downloaded} downloaded."
            ),
            "missing_description": "Online business-document listings do not prove full historical coverage.",
            "legal_importance": "high",
            "risk_if_missing": "Bill history, daily business, papers presented, and procedural context may be incomplete.",
            "probable_source": "Parliament; National Archives; parliamentary library",
            "next_action": "Acquire visible online records and map pre-online parliamentary records.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "English preferred; skip Sinhala/Tamil duplicates when English exists.",
        },
    ]
    merge_by_key(MISSING_DATA_PATH, fields, rows, "missing_id")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire official Parliament business-document PDFs.")
    parser.add_argument(
        "--track",
        action="append",
        choices=["all", *TRACKS.keys()],
        default=[],
        help="Track to acquire. Repeatable. Defaults to all.",
    )
    parser.add_argument("--item-count", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()
    candidates = discover_candidates(args)
    manifest_rows = merge_manifest_candidates(candidates, corpus.DOCUMENT_MANIFEST_FIELDS)
    write_source_registry(corpus.SOURCE_REGISTRY_FIELDS, candidates, utc_now())

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
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = [executor.submit(download_candidate, candidate, args.timeout, args.force) for candidate in selected]
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1
                if args.progress and (completed == 1 or completed % 50 == 0 or completed == len(selected)):
                    print(
                        f"downloaded/checked {completed}/{len(selected)} "
                        f"(latest {result.document_id}: {result.status})",
                        file=sys.stderr,
                        flush=True,
                    )
                if result.status != "downloaded":
                    errors.append(f"{result.document_id}: {result.status}: {result.error}")
        counts = update_manifest_downloads(results, corpus.DOCUMENT_MANIFEST_FIELDS)
        manifest_rows = read_csv(DOCUMENT_MANIFEST_PATH)

    write_business_registry(candidates, results)
    update_missing_register(corpus.MISSING_DATA_FIELDS, manifest_rows, utc_now())
    latest = {
        "parliament_business_docs_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "tracks": args.track or ["all"],
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
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_parliament_business_docs",
            "source_id": ";".join(sorted({candidate.source_id for candidate in candidates})),
            "run_type": "parliament_business_docs_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(candidates)),
            "documents_downloaded": str(counts.get("downloaded", 0)),
            "errors": json.dumps(errors[:200], ensure_ascii=False),
            "new_missing_items": "M_HANSARD_COMMITTEES_INDEXES;M_PARLIAMENT_BUSINESS_DOCS",
            "notes": json.dumps(latest["parliament_business_docs_acquisition"], ensure_ascii=False),
        },
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
