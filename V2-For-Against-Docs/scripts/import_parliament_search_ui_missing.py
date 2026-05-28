#!/usr/bin/env python3
"""Import rows found by the Parliament search UI audit but missing from manifest."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
AUDIT_CSV = MANIFEST_DIR / "parliament_search_ui_audit.csv"
DOCUMENT_MANIFEST = MANIFEST_DIR / "document_manifest.csv"
LEGAL_INSTRUMENT_REGISTRY = MANIFEST_DIR / "legal_instrument_registry.csv"
GOV_BILL_REGISTRY = MANIFEST_DIR / "government_bill_registry.csv"
RUN_LOG = MANIFEST_DIR / "extraction_run_log.csv"
ACT_PDF_ROOT = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "acts_pdfs" / "english"
GOV_BILL_PDF_ROOT = PROJECT_ROOT / "data" / "raw" / "official" / "parliament" / "government_bills_pdfs" / "english"
USER_AGENT = "SL-Legal-Assist-Search-UI-Missing-Importer/0.1"


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


def append_run_log(row: dict[str, str], corpus) -> None:
    rows = read_csv(RUN_LOG)
    fields = list(rows[0].keys()) if rows else corpus.EXTRACTION_RUN_FIELDS
    rows.append(row)
    write_csv(RUN_LOG, fields, rows)


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, timeout: int = 20) -> tuple[int | None, dict[str, str], bytes, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read(), ""
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, b"", str(exc)
    except URLError as exc:
        return None, {}, b"", str(exc.reason)
    except Exception as exc:
        return None, {}, b"", str(exc)


def html_text_title(page_html: str) -> str:
    match = re.search(r"<title>\s*Parliament of Sri Lanka\s*-\s*(.*?)\s*</title>", page_html, re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title


def detail_date(page_html: str, label: str) -> str:
    match = re.search(label + r" Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", page_html)
    if not match:
        return ""
    return "" if match.group(1) == "0000-00-00" else match.group(1)


def detail_stage(page_html: str) -> str:
    match = re.search(r"<small>Current Stage</small>.*?<b>(.*?)</b>", page_html, re.DOTALL)
    if not match:
        return "to_verify"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip() or "to_verify"


def first_pdf_url(page_html: str, kind: str) -> str:
    folder = "acts" if kind == "Act" else "bills"
    match = re.search(
        rf"https://www\.parliament\.lk/uploads/{folder}/(?:g|p)bills/english/[0-9]+\.pdf",
        page_html,
    )
    return match.group(0) if match else ""


def local_pdf_path(row: dict[str, str], source_id: str) -> Path:
    root = ACT_PDF_ROOT if source_id == "PARL_ACTS" else GOV_BILL_PDF_ROOT
    number = row["number"].zfill(3) if row.get("number", "").isdigit() else "unknown"
    return root / row["year"] / f"{number}_{safe_slug(row.get('title') or row['source_document_id'])[:90]}.pdf"


def download_pdf(url: str, path: Path) -> tuple[str, str, str]:
    if not url:
        return "", "", "No PDF URL on detail page."
    status, headers, data, error = fetch(url, timeout=40)
    content_type = headers.get("Content-Type", "")
    if status == 200 and data.startswith(b"%PDF") and "pdf" in content_type.lower():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path.relative_to(PROJECT_ROOT)), sha256_bytes(data), ""
    return "", "", error or f"status={status} content_type={content_type}"


def merge_by_key(path: Path, fields: list[str], new_rows: list[dict[str, str]], key: str) -> None:
    rows = read_csv(path)
    by_key = {row.get(key, ""): row for row in rows}
    order = [row.get(key, "") for row in rows]
    for row in new_rows:
        value = row.get(key, "")
        if value not in by_key:
            order.append(value)
        prior = by_key.get(value, {})
        by_key[value] = {**prior, **{k: v for k, v in row.items() if v != ""}}
    write_csv(path, fields, [by_key[value] for value in order if value])


def main() -> int:
    started = utc_now()
    corpus = load_corpus_module()
    audit_rows = [
        row
        for row in read_csv(AUDIT_CSV)
        if row.get("issue") == "listing_row_missing_from_manifest"
    ]
    existing = {row["document_id"] for row in read_csv(DOCUMENT_MANIFEST)}
    document_rows = []
    instrument_rows = []
    bill_rows = []
    imported = 0
    downloaded = 0
    errors = []

    for audit in audit_rows:
        source_id = audit["source_id"]
        doc_type = "Act" if source_id == "PARL_ACTS" else "Government Bill"
        detail_url = audit["source_url"]
        source_doc = audit["source_document_id"]
        status, _headers, data, error = fetch(detail_url)
        if status != 200 or not data:
            errors.append(f"{source_doc}: detail fetch failed {status} {error}")
            continue
        page_html = data.decode("utf-8", errors="replace")
        title = audit.get("title", "").strip(" :") or html_text_title(page_html) or "unknown"
        number = audit.get("number", "").strip()
        if number == ":":
            number = ""
        year = audit["year"]
        date_label = "Endorsed" if doc_type == "Act" else "Presented"
        date = detail_date(page_html, date_label)
        pdf_url = first_pdf_url(page_html, doc_type)
        number_part = number.zfill(3) if number.isdigit() else "unknown"
        prefix = "parl_act" if doc_type == "Act" else "parl_gov_bill"
        document_id = f"{prefix}_{year}_{number_part}_{source_doc.lower()}"
        if document_id in existing:
            continue
        local_path = ""
        file_hash = ""
        missing_reason = ""
        acquisition_status = "metadata_extracted_pdf_not_found"
        extraction_status = "not_started"
        next_action = "Locate official PDF or alternate official source."
        if pdf_url:
            path = local_pdf_path({"year": year, "number": number, "title": title, "source_document_id": source_doc}, source_id)
            local_path, file_hash, missing_reason = download_pdf(pdf_url, path)
            if local_path:
                acquisition_status = "downloaded"
                next_action = "Extract text and segment document."
                downloaded += 1
            else:
                next_action = "Retry detail-page PDF download or alternate official source."
        else:
            missing_reason = "Search UI/detail page did not expose an English PDF link."
        document_rows.append(
            {
                "document_id": document_id,
                "source_id": source_id,
                "source_document_id": source_doc,
                "document_type": doc_type,
                "title": title,
                "year": year,
                "number": number,
                "date": date,
                "language": "English",
                "source_url": detail_url,
                "download_url": pdf_url,
                "local_path": local_path,
                "file_hash": file_hash,
                "acquisition_status": acquisition_status,
                "extraction_status": extraction_status,
                "ocr_required": "",
                "text_quality_score": "",
                "legal_status": "to_verify" if doc_type == "Act" else "bill_to_verify",
                "missing_reason": missing_reason,
                "next_action": next_action,
                "last_checked": utc_now(),
                "notes": "Imported from Parliament search UI audit; absent from CSV endpoint.",
            }
        )
        if doc_type == "Act":
            instrument_id = f"act_{year}_{number_part}_{source_doc.lower()}"
            instrument_rows.append(
                {
                    "instrument_id": instrument_id,
                    "instrument_type": "Act",
                    "short_title": title,
                    "number": number,
                    "year": year,
                    "certified_date": date,
                    "commencement_date": "",
                    "current_status": "to_verify",
                    "source_document_id": source_doc,
                    "source_url": detail_url,
                    "download_url": pdf_url,
                    "amends": "",
                    "amended_by": "",
                    "repeals": "",
                    "repealed_by": "",
                    "related_bills": "",
                    "related_gazettes": "",
                    "related_cases": "",
                    "notes": "Imported from Parliament search UI audit; absent from CSV endpoint.",
                    "last_checked": utc_now(),
                }
            )
        else:
            bill_rows.append(
                {
                    "bill_id": f"gov_bill_{year}_{number_part}_{source_doc.lower()}",
                    "bill_type": "Government Bill",
                    "short_title": title,
                    "number": number,
                    "year": year,
                    "presented_date": date,
                    "current_status": detail_stage(page_html),
                    "source_document_id": source_doc,
                    "source_url": detail_url,
                    "download_url": pdf_url,
                    "related_act": "",
                    "notes": "Imported from Parliament search UI audit; absent from CSV endpoint.",
                    "last_checked": utc_now(),
                }
            )
        imported += 1

    merge_by_key(DOCUMENT_MANIFEST, corpus.DOCUMENT_MANIFEST_FIELDS, document_rows, "document_id")
    if instrument_rows:
        merge_by_key(LEGAL_INSTRUMENT_REGISTRY, corpus.LEGAL_INSTRUMENT_FIELDS, instrument_rows, "instrument_id")
    if bill_rows:
        # Import field list from the government-bills extractor without making it a runtime dependency.
        bill_fields = [
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
        merge_by_key(GOV_BILL_REGISTRY, bill_fields, bill_rows, "bill_id")
    corpus.refresh_acts_missing_register()
    corpus.build_corpus_index(
        {
            "search_ui_missing_import": {
                "started_at": started,
                "ended_at": utc_now(),
                "imported": imported,
                "downloaded": downloaded,
                "errors": errors,
            }
        }
    )
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_search_ui_import",
            "source_id": "PARL_SEARCH_UI",
            "run_type": "search_ui_missing_import",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(imported),
            "documents_downloaded": str(downloaded),
            "errors": json.dumps(errors, ensure_ascii=False),
            "new_missing_items": "",
            "notes": "Imported listing rows found in search UI but absent from CSV endpoint.",
        },
        corpus,
    )
    print(json.dumps({"imported": imported, "downloaded": downloaded, "errors": errors}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
