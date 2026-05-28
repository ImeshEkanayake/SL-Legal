#!/usr/bin/env python3
"""Acquire public/free material for remaining legal corpus categories.

This wave covers small, explicit public sources discovered for:
- provincial/subnational legal material
- administrative and practice/regulatory material

It also records blocked external sources that need manual/browser/licensed
recovery. The script does not bypass paid products or access controls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
RAW_OFFICIAL_DIR = DATA_DIR / "raw" / "official"
RAW_EXTERNAL_DIR = DATA_DIR / "raw" / "external"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
ACQUISITION_REPORT_PATH = MANIFEST_DIR / "remaining_public_sources_acquisition_report.csv"

USER_AGENT = "SL-Legal-Assist-Remaining-Public-Sources/0.1"

REPORT_FIELDS = [
    "document_id",
    "source_id",
    "title",
    "category",
    "download_url",
    "status",
    "file_format",
    "content_type",
    "local_path",
    "file_hash",
    "bytes_downloaded",
    "error",
    "last_checked",
]


@dataclass(frozen=True)
class Candidate:
    source_id: str
    title: str
    document_type: str
    category: str
    source_url: str
    download_url: str
    year: str = ""
    language: str = "English"
    legal_status: str = "official_publication"
    notes: str = ""


@dataclass
class FetchResult:
    status: str
    data: bytes = b""
    content_type: str = ""
    error: str = ""


class AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._current = {key.lower(): value or "" for key, value in attrs}
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        self.anchors.append({**self._current, "text": normalize_space(" ".join(self._text))})
        self._current = None
        self._text = []


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def safe_slug(value: str, max_len: int = 120) -> str:
    value = unquote(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return (value[:max_len].strip("_") or "unknown")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def url_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def infer_year(title: str, default: str = "") -> str:
    match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", title)
    return match.group(1) if match else default


def google_drive_download_url(url: str) -> str:
    match = re.search(r"/file/d/([^/]+)/", url)
    if not match:
        return url
    return f"https://drive.google.com/uc?export=download&id={match.group(1)}"


def normalize_cbsl_pdf_url(url: str) -> str:
    return url.replace("https://www.cbsl.gov.lk/en/sites/default/files/", "https://www.cbsl.gov.lk/sites/default/files/")


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


def fetch_url(url: str, timeout: int) -> FetchResult:
    with tempfile.NamedTemporaryFile(prefix="sllegal_remaining_", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        completed = subprocess.run(
            [
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
                "__SLLEGAL_STATUS__:%{http_code}\n__SLLEGAL_TYPE__:%{content_type}\n",
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 10,
            check=False,
        )
        output = completed.stdout.decode("utf-8", errors="replace")
        status_match = re.search(r"__SLLEGAL_STATUS__:(\d+)", output)
        type_match = re.search(r"__SLLEGAL_TYPE__:(.*)", output)
        http_status = int(status_match.group(1)) if status_match else 0
        content_type = type_match.group(1).strip() if type_match else ""
        data = tmp_path.read_bytes() if tmp_path.exists() else b""
        if completed.returncode != 0:
            return FetchResult("failed", data=data, content_type=content_type, error=completed.stderr.decode("utf-8", errors="replace").strip())
        if http_status >= 400:
            return FetchResult("failed", data=data, content_type=content_type, error=f"HTTP {http_status}")
        return FetchResult("ok", data=data, content_type=content_type)
    except subprocess.TimeoutExpired as exc:
        return FetchResult("failed", error=f"timeout: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)


def fetch_text(url: str, timeout: int) -> str:
    result = fetch_url(url, timeout)
    if result.status != "ok":
        return ""
    return result.data.decode("utf-8", errors="replace")


def extract_links(url: str, timeout: int) -> list[dict[str, str]]:
    page = fetch_text(url, timeout)
    parser = AnchorExtractor()
    parser.feed(page)
    links: list[dict[str, str]] = []
    for anchor in parser.anchors:
        href = anchor.get("href", "")
        if not href:
            continue
        links.append({"url": urljoin(url, href), "text": anchor.get("text", "")})
    return links


def static_candidates() -> list[Candidate]:
    uva_health = "https://healthmin.up.gov.lk/statutes/"
    uva_psc = "https://psc.up.gov.lk/en/"
    uva_circulars = "https://psc.up.gov.lk/en/view-circular-table.php"
    return [
        Candidate("UVA_HEALTH_STATUTES", "Uva Province Social Service Statute No. 08 of 2010", "Provincial Statute", "provincial_subnational_law", uva_health, "https://drive.google.com/file/d/12iRHaCMsCFOC5DOEnfcWg0GceXIb2cVw/view?usp=sharing", "2010"),
        Candidate("UVA_HEALTH_STATUTES", "Uva Province Ayurvedic Statute No. 06 of 2011", "Provincial Statute", "provincial_subnational_law", uva_health, "https://drive.google.com/file/d/15KV5uSwmxfXMNGseY7MABipFwNoldvcn/view?usp=sharing", "2011"),
        Candidate("UVA_HEALTH_STATUTES", "Uva Province Child Development Statute No. 01 of 2013", "Provincial Statute", "provincial_subnational_law", uva_health, "https://drive.google.com/file/d/1smw3QeNqFgkrpDMQi2o7bTJqcGpaSz3p/view?usp=sharing", "2013"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Right to Information Act material", "Administrative Practice Material", "administrative_practice_materials", uva_psc, "https://drive.google.com/file/d/1Jyxzf9s7E-6wGqDIf62SehIHf-QYXh83/view", "2016"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "13th Constitutional Amendment", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1hrThPj2cYpjyQjIwFKjF4d-PGKFN7Ted/view?usp=sharing", "1987"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "The Constitution as Amended up to the 19th Amendment", "Constitution", "legislation", uva_psc, "https://drive.google.com/file/d/1eDSf3rzUM6Qs089yk94ns206TBSO5TPy/view?usp=sharing", "2015"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "20th Constitutional Amendment", "Constitution", "legislation", uva_psc, "https://drive.google.com/file/d/1Rp6bkY7RssqKkdfK5CaKATfj8by5S3tG/view?usp=sharing", "2020"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Councils Payment of Salaries and Allowances Act No. 37 of 1988", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1v7bw9k3K4U-mdau422gqzuvVfprKcvi4/view?usp=sharing", "1988"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Councils Subsidiary Provisions Act No. 12 of 1989", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1fL56vov8Qn-xlKeSnIptM_0I3fKeMUZU/view?usp=sharing", "1989"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Councils Amendment Act No. 27 of 1990", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1aKVmKnzVldAm2dS1Kxy6-pSvr7deqrAf/view?usp=sharing", "1990"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Councils Amendment Act No. 28 of 1990", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1oS9bDmi95lcMVbCAtghdREek8or9GUSZ/view?usp=sharing", "1990"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Council Amendment Act No. 13 of 2010", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1OmNkBLk9jhQNu1mtQ4AzkW7475jo35dp/view?usp=sharing", "2010"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Provincial Council Transfer of Stamp Duties Act No. 13 of 2011", "Provincial Legal Framework", "provincial_subnational_law", uva_psc, "https://drive.google.com/file/d/1NwMaTh1AQKVycE2Ap9veLUFSRNgq-2UA/view?usp=sharing", "2011"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Delegation of powers from 01.01.2013", "Administrative Practice Material", "administrative_practice_materials", uva_psc, "https://drive.google.com/file/d/1t5frwETIWBAKLjYekJWFrKx9HkeRbg3H/view?usp=sharing", "2013"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Delegation of powers from 01.01.2013 Amendment", "Administrative Practice Material", "administrative_practice_materials", uva_psc, "https://drive.google.com/file/d/1Tu_N7N5MZa6iMjYrx3y-fZebVNOmPxLS/view?usp=sharing", "2013"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Commission Circular 03/2021", "Administrative Circular", "administrative_practice_materials", uva_psc, "https://drive.google.com/file/d/1QLE-OrtRJFJlDOP6SMHx9gFiXdy0Du4R/view?usp=sharing", "2021"),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Right to Information Steps to Information", "Administrative Practice Material", "administrative_practice_materials", uva_circulars, "https://drive.google.com/file/d/1DUQpg-bcMiQ_2cKCpu9jzfH185JQqIWb/view", ""),
        Candidate("UVA_PSC_LEGAL_PROVISIONS", "Right to Information Details of Fees", "Administrative Practice Material", "administrative_practice_materials", uva_circulars, "https://drive.google.com/file/d/1A8LCZzFIBA0kgx9UmxAS2WQkrkifwSll/view", ""),
    ]


def cbsl_candidates(timeout: int) -> list[Candidate]:
    pages = [
        "https://www.cbsl.gov.lk/en/laws",
        "https://www.cbsl.gov.lk/en/laws/public-register-under-cbsl-act-rules-and-directions",
    ]
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for page in pages:
        for link in extract_links(page, timeout):
            url = normalize_cbsl_pdf_url(link["url"])
            text = link["text"] or Path(urlparse(url).path).name
            if "cbslweb_documents/laws/" not in url or not url.lower().endswith(".pdf"):
                continue
            if url in seen:
                continue
            seen.add(url)
            candidates.append(
                Candidate(
                    source_id="CBSL_RULES_DIRECTIONS",
                    title=normalize_space(text) or Path(urlparse(url).path).stem,
                    document_type="Administrative and Regulatory Direction",
                    category="administrative_practice_materials",
                    source_url=page,
                    download_url=url,
                    year=infer_year(text + " " + url),
                    legal_status="official_regulatory_material",
                    notes="Discovered from CBSL laws/rules/directions page.",
                )
            )
    return candidates


def source_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "source_id": "UVA_HEALTH_STATUTES",
            "source_name": "Uva Province Ministry of Health Statutes",
            "source_url": "https://healthmin.up.gov.lk/statutes/",
            "source_owner": "Uva Provincial Ministry of Health / Uva Provincial Council",
            "reliability_tier": "B",
            "legal_authority_type": "provincial_statutes_and_subnational_material",
            "jurisdiction": "Sri Lanka - Uva Province",
            "languages": "English",
            "coverage_start": "2010",
            "coverage_end": "2013",
            "coverage_confidence": "source_page_explicit_links",
            "licence_status": "to_review",
            "access_method": "official_web_page_google_drive_links",
            "refresh_frequency": "quarterly",
            "known_gaps": "Only visible statutes on this page acquired; other provincial statutes remain to map.",
            "notes": "Google Drive links are published from official Uva Province page.",
            "last_checked": now,
        },
        {
            "source_id": "UVA_PSC_LEGAL_PROVISIONS",
            "source_name": "Uva Provincial Public Service Commission Legal Framework",
            "source_url": "https://psc.up.gov.lk/en/",
            "source_owner": "Uva Provincial Public Service Commission",
            "reliability_tier": "B",
            "legal_authority_type": "provincial_legal_framework_and_administrative_material",
            "jurisdiction": "Sri Lanka - Uva Province",
            "languages": "English",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_page_explicit_links",
            "licence_status": "to_review",
            "access_method": "official_web_page_google_drive_links",
            "refresh_frequency": "quarterly",
            "known_gaps": "One Google Drive folder for pre-2013 delegation of powers requires separate folder traversal/manual recovery.",
            "notes": "English copies acquired where visible.",
            "last_checked": now,
        },
        {
            "source_id": "CBSL_RULES_DIRECTIONS",
            "source_name": "Central Bank of Sri Lanka Rules, Directions, Circulars and Guidelines",
            "source_url": "https://www.cbsl.gov.lk/en/laws/public-register-under-cbsl-act-rules-and-directions",
            "source_owner": "Central Bank of Sri Lanka",
            "reliability_tier": "A",
            "legal_authority_type": "official_regulatory_and_administrative_material",
            "jurisdiction": "Sri Lanka",
            "languages": "English",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "visible_public_register_links",
            "licence_status": "to_review",
            "access_method": "official_web_page_pdf_links",
            "refresh_frequency": "monthly",
            "known_gaps": "Only PDFs linked from the visible laws/public register pages in this wave.",
            "notes": "Useful as administrative/practice/regulatory material, not court precedent.",
            "last_checked": now,
        },
        {
            "source_id": "COMMONLII_SRI_LANKA",
            "source_name": "CommonLII Sri Lanka Case Law Collections",
            "source_url": "http://www.commonlii.org/lk/cases/",
            "source_owner": "CommonLII",
            "reliability_tier": "C",
            "legal_authority_type": "external_public_case_law_collection",
            "jurisdiction": "Sri Lanka",
            "languages": "English",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "known_collection_access_blocked_from_cli",
            "licence_status": "to_review",
            "access_method": "web_blocked_by_cloudflare_challenge",
            "refresh_frequency": "manual",
            "known_gaps": "CLI access received Cloudflare challenge; use browser/manual export or alternate public mirror if legally permitted.",
            "notes": "Do not bypass access controls.",
            "last_checked": now,
        },
        {
            "source_id": "LAWNET_MOJ",
            "source_name": "LawNet / Ministry of Justice legal portal",
            "source_url": "https://lawnet.gov.lk/",
            "source_owner": "Ministry of Justice / LawNet",
            "reliability_tier": "B",
            "legal_authority_type": "official_or_public_legal_portal",
            "jurisdiction": "Sri Lanka",
            "languages": "English; Sinhala; Tamil where available",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "portal_access_instability",
            "licence_status": "to_review",
            "access_method": "web_unstable",
            "refresh_frequency": "manual",
            "known_gaps": "Current root page returned a non-document root directory and old direct PDF paths returned 404.",
            "notes": "Needs portal recovery/manual mapping before bulk acquisition.",
            "last_checked": now,
        },
    ]


def local_path_for(candidate: Candidate, extension: str = ".pdf") -> Path:
    if candidate.source_id == "UVA_HEALTH_STATUTES":
        base = RAW_OFFICIAL_DIR / "provincial" / "uva" / "health_statutes"
    elif candidate.source_id == "UVA_PSC_LEGAL_PROVISIONS":
        base = RAW_OFFICIAL_DIR / "provincial" / "uva" / "public_service_commission"
    elif candidate.source_id == "CBSL_RULES_DIRECTIONS":
        base = RAW_OFFICIAL_DIR / "administrative_practice" / "cbsl_rules_directions"
    else:
        base = RAW_EXTERNAL_DIR / safe_slug(candidate.source_id.lower())
    year_part = candidate.year or "unknown_year"
    if extension not in {".pdf", ".jpg", ".jpeg", ".png"}:
        extension = ".pdf"
    return base / year_part / f"{safe_slug(candidate.title, 100)}_{url_hash(candidate.download_url)}{extension}"


def document_id_for(candidate: Candidate) -> str:
    return f"{candidate.source_id.lower()}_{safe_slug(candidate.title, 80)}_{url_hash(candidate.download_url)}"


def download_candidate(candidate: Candidate, timeout: int, force: bool) -> tuple[dict[str, str], dict[str, str]]:
    now = utc_now()
    document_id = document_id_for(candidate)
    local_path = local_path_for(candidate)
    download_url = google_drive_download_url(candidate.download_url)
    if local_path.exists() and not force:
        data_hash = sha256_bytes(local_path.read_bytes())
        report = {
            "document_id": document_id,
            "source_id": candidate.source_id,
            "title": candidate.title,
            "category": candidate.category,
            "download_url": candidate.download_url,
            "status": "already_downloaded",
            "file_format": local_path.suffix.lower().lstrip("."),
            "content_type": "",
            "local_path": str(local_path.relative_to(PROJECT_ROOT)),
            "file_hash": data_hash,
            "bytes_downloaded": str(local_path.stat().st_size),
            "error": "",
            "last_checked": now,
        }
        return manifest_row(candidate, report, "downloaded", now), report

    result = fetch_url(download_url, timeout)
    is_pdf = result.data.startswith(b"%PDF") or "pdf" in result.content_type.lower() or "octet-stream" in result.content_type.lower()
    is_jpeg = result.data.startswith(b"\xff\xd8\xff") or "image/jpeg" in result.content_type.lower()
    is_png = result.data.startswith(b"\x89PNG") or "image/png" in result.content_type.lower()
    if result.status != "ok" or not (is_pdf or is_jpeg or is_png):
        error = result.error or f"not_pdf content_type={result.content_type} first_bytes={result.data[:24]!r}"
        report = {
            "document_id": document_id,
            "source_id": candidate.source_id,
            "title": candidate.title,
            "category": candidate.category,
            "download_url": candidate.download_url,
            "status": "download_failed",
            "file_format": "",
            "content_type": result.content_type,
            "local_path": "",
            "file_hash": "",
            "bytes_downloaded": str(len(result.data)) if result.data else "",
            "error": error,
            "last_checked": now,
        }
        return manifest_row(candidate, report, "download_failed", now), report

    extension = ".pdf"
    if is_jpeg:
        extension = ".jpg"
    elif is_png:
        extension = ".png"
    local_path = local_path_for(candidate, extension)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(result.data)
    report = {
        "document_id": document_id,
        "source_id": candidate.source_id,
        "title": candidate.title,
        "category": candidate.category,
        "download_url": candidate.download_url,
        "status": "downloaded",
        "file_format": extension.lstrip("."),
        "content_type": result.content_type,
        "local_path": str(local_path.relative_to(PROJECT_ROOT)),
        "file_hash": sha256_bytes(result.data),
        "bytes_downloaded": str(len(result.data)),
        "error": "",
        "last_checked": now,
    }
    return manifest_row(candidate, report, "downloaded", now), report


def manifest_row(candidate: Candidate, report: dict[str, str], acquisition_status: str, now: str) -> dict[str, str]:
    return {
        "document_id": report["document_id"],
        "source_id": candidate.source_id,
        "source_document_id": url_hash(candidate.download_url),
        "document_type": candidate.document_type,
        "title": candidate.title,
        "year": candidate.year or infer_year(candidate.title),
        "number": "",
        "date": "",
        "language": candidate.language,
        "source_url": candidate.source_url,
        "download_url": candidate.download_url,
        "local_path": report.get("local_path", ""),
        "file_hash": report.get("file_hash", ""),
        "acquisition_status": acquisition_status,
        "extraction_status": "not_started" if acquisition_status == "downloaded" else "",
        "ocr_required": "true" if report.get("file_format") in {"jpg", "jpeg", "png"} else "",
        "text_quality_score": "",
        "legal_status": candidate.legal_status,
        "missing_reason": report.get("error", ""),
        "next_action": "Extract text and classify legal authority." if acquisition_status == "downloaded" else "Retry public source or locate alternate official copy.",
        "last_checked": now,
        "notes": (
            f"remaining_public_sources_wave=true; category={candidate.category}; "
            f"source_page={candidate.source_url}; file_format={report.get('file_format', '')}; "
            f"content_type={report.get('content_type', '')}; {candidate.notes}"
        ).strip(),
    }


def blocked_missing_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "missing_id": "M_COMMONLII_ACCESS_BLOCKED_CURRENT_WAVE",
            "data_category": "Portal Recovery and External Collections",
            "expected_coverage": "CommonLII Sri Lanka Supreme Court and Court of Appeal collections where legally accessible.",
            "known_available_coverage": "CommonLII collection URLs are known, but CLI retrieval returned a Cloudflare challenge during this wave.",
            "missing_description": "CommonLII case-law collection could not be bulk downloaded from the command line without bypassing access controls.",
            "legal_importance": "high",
            "risk_if_missing": "Historical public case-law collection may remain absent until manually recovered or acquired from another lawful source.",
            "probable_source": "CommonLII Sri Lanka case-law collections; law reports; LawNet; licensed databases",
            "next_action": "Use browser/manual export or another lawful source; do not bypass Cloudflare or access controls.",
            "owner": "Corpus lead",
            "status": "blocked_access_control",
            "last_checked": now,
            "notes": "Observed challenge on http://www.commonlii.org/lk/cases/LKSC/ and /LKCA/.",
        },
        {
            "missing_id": "M_UVA_PSC_DELEGATION_PRE_2013_FOLDER",
            "data_category": "Administrative and practice materials",
            "expected_coverage": "Uva PSC delegation of powers up to 01.01.2013.",
            "known_available_coverage": "A Google Drive folder link is published, but folder traversal was not included in this wave.",
            "missing_description": "Delegation of powers up to 01.01.2013 requires folder traversal/manual recovery.",
            "legal_importance": "medium",
            "risk_if_missing": "Administrative authority history may be incomplete for older Uva PSC delegation material.",
            "probable_source": "https://psc.up.gov.lk/en/ Google Drive folder",
            "next_action": "Open the Google Drive folder, enumerate files, and download official copies if public.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Folder URL: https://drive.google.com/drive/folders/1b82n4GCgsaBBC4kO9F78xbAJ-VOVDZFN",
        },
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire remaining public/free legal source PDFs.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    now = utc_now()
    corpus = load_corpus_module()
    candidates = static_candidates() + cbsl_candidates(args.timeout)
    # Deduplicate by source+URL.
    unique: dict[tuple[str, str], Candidate] = {}
    for candidate in candidates:
        unique[(candidate.source_id, candidate.download_url)] = candidate
    candidates = list(unique.values())

    manifest_rows: list[dict[str, str]] = []
    report_rows: list[dict[str, str]] = []
    for index, candidate in enumerate(candidates, start=1):
        row, report = download_candidate(candidate, args.timeout, args.force)
        manifest_rows.append(row)
        report_rows.append(report)
        if args.progress:
            print(f"{index}/{len(candidates)} {candidate.source_id}: {report['status']} {candidate.title}", flush=True)
        time.sleep(0.1)

    merge_by_key(SOURCE_REGISTRY_PATH, corpus.SOURCE_REGISTRY_FIELDS, source_rows(now), "source_id")
    merge_by_key(DOCUMENT_MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, manifest_rows, "document_id")
    merge_by_key(MISSING_DATA_PATH, corpus.MISSING_DATA_FIELDS, blocked_missing_rows(now), "missing_id")
    write_csv(ACQUISITION_REPORT_PATH, REPORT_FIELDS, report_rows)

    counts: dict[str, int] = {}
    for row in report_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    latest = {
        "remaining_public_sources_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "candidates": len(candidates),
            "download_counts": counts,
            "report_csv": str(ACQUISITION_REPORT_PATH.relative_to(PROJECT_ROOT)),
        }
    }
    corpus.build_corpus_index(latest)
    run_rows = read_csv(RUN_LOG_PATH)
    run_rows.append(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_remaining_public_sources",
            "source_id": "REMAINING_PUBLIC_SOURCES",
            "run_type": "remaining_public_sources_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(candidates)),
            "documents_downloaded": str(counts.get("downloaded", 0) + counts.get("already_downloaded", 0)),
            "errors": json.dumps([row for row in report_rows if row["status"] == "download_failed"], ensure_ascii=False),
            "new_missing_items": "M_COMMONLII_ACCESS_BLOCKED_CURRENT_WAVE; M_UVA_PSC_DELEGATION_PRE_2013_FOLDER",
            "notes": json.dumps(latest["remaining_public_sources_acquisition"], ensure_ascii=False),
        }
    )
    write_csv(RUN_LOG_PATH, corpus.EXTRACTION_RUN_FIELDS, run_rows)
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
