#!/usr/bin/env python3
"""Record remaining legal-corpus source gaps after public acquisition passes."""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"


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
    rows: Iterable[dict[str, str]],
    key_field: str,
) -> None:
    existing = read_csv(path)
    merged: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing:
        key = row.get(key_field, "")
        if key and key not in merged:
            order.append(key)
        if key:
            merged[key] = row
    for row in rows:
        key = row.get(key_field, "")
        if not key:
            continue
        if key not in merged:
            order.append(key)
        prior = merged.get(key, {})
        merged[key] = {**prior, **{k: v for k, v in row.items() if v != ""}}
    write_csv(path, fields, [merged[key] for key in order if key])


def source_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "source_id": "NAT_ARCHIVES",
            "source_name": "National Archives and library holdings",
            "source_url": "",
            "source_owner": "National Archives / libraries",
            "reliability_tier": "D",
            "legal_authority_type": "archival_legal_material",
            "jurisdiction": "Sri Lanka",
            "languages": "English preferred where available; Sinhala/Tamil retained only when English is absent or legally required",
            "coverage_start": "pre-1948",
            "coverage_end": "",
            "coverage_confidence": "requires_manual_acquisition",
            "licence_status": "to_review",
            "access_method": "manual_request_scanning_partnership",
            "refresh_frequency": "as_needed",
            "known_gaps": "Historical gazettes, Hansard, court material, ordinances, and indexes may require physical or library access.",
            "notes": "Use for gaps not available through official online listings.",
            "last_checked": now,
        },
        {
            "source_id": "COMMONLII_LK",
            "source_name": "CommonLII Sri Lanka collections",
            "source_url": "https://www.commonlii.org/lk/",
            "source_owner": "CommonLII",
            "reliability_tier": "B",
            "legal_authority_type": "legal_information_institute_copy",
            "jurisdiction": "Sri Lanka",
            "languages": "Mostly English where available",
            "coverage_start": "",
            "coverage_end": "",
            "coverage_confidence": "source_discovery_blocked_for_bulk_download",
            "licence_status": "to_review",
            "access_method": "web_manual_or_permissioned_bulk_access",
            "refresh_frequency": "monthly",
            "known_gaps": "Bulk downloader currently receives an anti-automation challenge; do not rely on this as acquired coverage.",
            "notes": "Potential source for older cases and legislation, but provenance must be checked against official/law-report sources.",
            "last_checked": now,
        },
        {
            "source_id": "PROVINCIAL_SOURCES",
            "source_name": "Provincial Council and local authority sources",
            "source_url": "",
            "source_owner": "Provincial councils and local authorities",
            "reliability_tier": "A/D",
            "legal_authority_type": "official_subnational_law",
            "jurisdiction": "Sri Lanka",
            "languages": "English preferred where available",
            "coverage_start": "1987",
            "coverage_end": "",
            "coverage_confidence": "not_mapped",
            "licence_status": "to_review",
            "access_method": "province_by_province_web_and_archival",
            "refresh_frequency": "monthly",
            "known_gaps": "Provincial statutes, regulations, provincial gazettes, and local by-laws are not yet source-mapped.",
            "notes": "Requires a province-by-province acquisition map.",
            "last_checked": now,
        },
        {
            "source_id": "ADMIN_PRACTICE_SOURCES",
            "source_name": "Administrative, practice, form, circular, and procedural sources",
            "source_url": "",
            "source_owner": "Courts, ministries, departments, Attorney General, registries, tribunals",
            "reliability_tier": "A/D",
            "legal_authority_type": "official_practice_and_administrative_material",
            "jurisdiction": "Sri Lanka",
            "languages": "English preferred where available",
            "coverage_start": "1948",
            "coverage_end": "",
            "coverage_confidence": "not_mapped",
            "licence_status": "to_review",
            "access_method": "web_and_manual_request",
            "refresh_frequency": "monthly",
            "known_gaps": "Court rules, practice directions, circulars, forms, notices, and procedural guides are not yet comprehensively mapped.",
            "notes": "Treat these as retrieval context; authority level varies by issuing body.",
            "last_checked": now,
        },
    ]


def missing_rows(now: str) -> list[dict[str, str]]:
    return [
        {
            "missing_id": "M_HISTORICAL_COURT_MATERIAL",
            "data_category": "Historical court material",
            "expected_coverage": "1948-present plus still-cited pre-1948 material",
            "known_available_coverage": "Current official Supreme Court and Court of Appeal directories downloaded; older online coverage is incomplete.",
            "missing_description": "Pre-online Supreme Court, Court of Appeal, unreported appellate cases, and predecessor court material are not complete.",
            "legal_importance": "critical",
            "risk_if_missing": "Research may miss binding or persuasive authorities that remain cited.",
            "probable_source": "Supreme Court; Court of Appeal; LawNet; law reports; National Archives; libraries; licensed databases",
            "next_action": "Map law reports and archival sources, then reconcile by case citation and court/date.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "English copies are sufficient where available.",
        },
        {
            "missing_id": "M_PRIVY_COUNCIL_CEYLON_APPELLATE",
            "data_category": "Privy Council and Ceylon appellate authorities",
            "expected_coverage": "Still-cited pre- and post-1948 appellate authorities",
            "known_available_coverage": "Not yet downloaded or citation-reconciled.",
            "missing_description": "Privy Council/Ceylon appellate authorities that remain relevant after 1948 need a dedicated source map.",
            "legal_importance": "critical",
            "risk_if_missing": "Research may miss older binding or highly persuasive authorities still used in Sri Lankan law.",
            "probable_source": "Law reports; CommonLII; BAILII; libraries; National Archives; licensed databases",
            "next_action": "Build a citation list from NLR/SLR and acquire public or licensed report copies.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Track source reliability separately from citation usefulness.",
        },
        {
            "missing_id": "M_LAW_REPORTS_COMPLETE",
            "data_category": "Complete law report coverage",
            "expected_coverage": "NLR, SLR, Ceylon Law Reports, Ceylon Law Recorder, Lanka Law Reporter where licensed/public",
            "known_available_coverage": "LankaLaw public/free material downloaded where accessible; 76 LankaLaw products require licence; official/current court PDFs downloaded separately.",
            "missing_description": "Complete verified report-series coverage is not yet proven.",
            "legal_importance": "critical",
            "risk_if_missing": "Reported authorities, headnotes, report citations, and historical case coverage may be incomplete.",
            "probable_source": "LawNet; LankaLaw; court libraries; National Archives; licensed databases",
            "next_action": "Verify each report series volume/part against a chronological checklist and recover missing public/licensed copies.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Do not treat third-party report copies as official court material without provenance flags.",
        },
        {
            "missing_id": "M_LOWER_COURT_TRIBUNALS",
            "data_category": "High Court, Commercial High Court, Provincial High Court, tribunals, and lower-court decisions",
            "expected_coverage": "Available public, licensed, or firm-provided decisions",
            "known_available_coverage": "Not yet source-mapped comprehensively.",
            "missing_description": "Specialist and lower-court decisions are not available from one comprehensive official public source.",
            "legal_importance": "high",
            "risk_if_missing": "Research may miss persuasive trial or specialist authorities in areas where appellate guidance is thin.",
            "probable_source": "Court registries; specialist tribunals; licensed databases; law-firm uploads; reported decisions",
            "next_action": "Create court/tribunal-by-court/tribunal source map and separate public, licensed, and firm-confidential materials.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Firm uploads must never be treated as public authority unless backed by a citable source.",
        },
        {
            "missing_id": "M_PROVINCIAL_SUBNATIONAL_LAW",
            "data_category": "Provincial and subnational law",
            "expected_coverage": "Provincial Council statutes, regulations, provincial gazettes, and local authority by-laws from 1987-present",
            "known_available_coverage": "Not yet downloaded or province-mapped.",
            "missing_description": "Provincial and local legal instruments are not yet represented as a complete source track.",
            "legal_importance": "high",
            "risk_if_missing": "Land, local government, planning, tax/levy, and devolved-subject research may be incomplete.",
            "probable_source": "Provincial councils; provincial gazettes; local authorities; LawNet links; National Archives",
            "next_action": "Build province-by-province and local-authority source registry, then acquire English copies where available.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Do not duplicate Sinhala/Tamil where official English exists.",
        },
        {
            "missing_id": "M_ADMIN_PRACTICE_MATERIALS",
            "data_category": "Administrative and practice materials",
            "expected_coverage": "Court rules, practice directions, circulars, AG/public materials, forms, notices, and procedural guides",
            "known_available_coverage": "Not yet comprehensively source-mapped.",
            "missing_description": "Practice and administrative materials remain scattered across courts, ministries, departments, and gazettes.",
            "legal_importance": "high",
            "risk_if_missing": "Procedure, filing, deadline, and registry guidance may be incomplete or stale.",
            "probable_source": "Supreme Court; Court of Appeal; Judicial Service Commission; Ministry of Justice; AG Department; Government Printing; court registries",
            "next_action": "Map issuing bodies and separate legally binding rules from administrative guidance.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Authority level must be encoded per issuing body and document type.",
        },
        {
            "missing_id": "M_LAWNET_ACCESS_INSTABILITY",
            "data_category": "LawNet / Ministry of Justice portal recovery",
            "expected_coverage": "Legislation, core laws, NLR, SLR, Supreme Court, Court of Appeal, and local-law links exposed by LawNet",
            "known_available_coverage": "Portal identified as relevant; automated PDF paths tested so far are unstable or unavailable from the downloader.",
            "missing_description": "LawNet needs manual or alternate-access verification before bulk acquisition can be trusted.",
            "legal_importance": "high",
            "risk_if_missing": "Older legislation and report coverage may remain harder to recover.",
            "probable_source": "LawNet / Ministry of Justice; official alternatives; licensed libraries",
            "next_action": "Re-test with browser/manual access, record working collections, and avoid assuming LawNet coverage until files are acquired.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Use as discovery until documents are downloaded and provenance is verified.",
        },
        {
            "missing_id": "M_COMMONLII_BULK_ACCESS_BLOCKED",
            "data_category": "CommonLII Sri Lanka public collection access",
            "expected_coverage": "Sri Lankan case-law and legislation collections where available",
            "known_available_coverage": "Not downloaded; automated access currently blocked by an anti-automation challenge.",
            "missing_description": "CommonLII cannot currently be bulk-downloaded from this environment.",
            "legal_importance": "medium",
            "risk_if_missing": "Potential older case and legislation copies may be unavailable until alternate access is arranged.",
            "probable_source": "CommonLII; official/law-report alternatives",
            "next_action": "Use manual verification or seek permissioned access; recover equivalent official/law-report copies where possible.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": now,
            "notes": "Do not count as acquired coverage until files are in the manifest.",
        },
    ]


def main() -> int:
    now = utc_now()
    corpus = load_corpus_module()
    merge_by_key(SOURCE_REGISTRY_PATH, corpus.SOURCE_REGISTRY_FIELDS, source_rows(now), "source_id")
    merge_by_key(MISSING_DATA_PATH, corpus.MISSING_DATA_FIELDS, missing_rows(now), "missing_id")
    corpus.build_corpus_index({"remaining_source_gap_update": {"updated_at": now}})
    print(f"updated remaining source gaps at {now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
