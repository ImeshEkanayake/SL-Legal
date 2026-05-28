#!/usr/bin/env python3
"""Catalog and acquire publicly downloadable LankaLaw library products.

LankaLaw is treated as a third-party/library source, not an official source.
The script downloads only products exposed as free public downloads by the
visible "Download Now" form. Paid products are cataloged and marked as
licensed_purchase_required.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import importlib.util
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zipfile import BadZipFile, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
INDEX_DIR = DATA_DIR / "indexes"
RAW_DIR = DATA_DIR / "raw" / "licensed" / "lankalaw_net"
DOCUMENT_MANIFEST_PATH = MANIFEST_DIR / "document_manifest.csv"
SOURCE_REGISTRY_PATH = MANIFEST_DIR / "source_registry.csv"
MISSING_DATA_PATH = MANIFEST_DIR / "missing_data_register.csv"
RUN_LOG_PATH = MANIFEST_DIR / "extraction_run_log.csv"
PRODUCT_REGISTRY_PATH = MANIFEST_DIR / "lankalaw_product_registry.csv"

SOURCE_ID = "LANKALAW_NET"
USER_AGENT = "SL-Legal-Assist-LankaLaw-Acquirer/0.1"
STORE_API = "https://lankalaw.net/wp-json/wc/store/v1/products"

PRODUCT_FIELDS = [
    "product_id",
    "name",
    "slug",
    "permalink",
    "price_minor",
    "currency",
    "is_free",
    "categories",
    "download_form_found",
    "download_status",
    "document_id",
    "local_path",
    "package_path",
    "file_hash",
    "package_hash",
    "bytes_downloaded",
    "content_type",
    "content_disposition_filename",
    "extracted_pdf_count",
    "extracted_pdf_paths",
    "last_checked",
    "notes",
]


@dataclass
class Product:
    product_id: str
    name: str
    slug: str
    permalink: str
    price_minor: int
    currency: str
    categories: list[str]
    short_description: str


@dataclass
class DownloadResult:
    product: Product
    document_id: str
    status: str
    local_path: str = ""
    file_hash: str = ""
    bytes_downloaded: int = 0
    content_type: str = ""
    filename: str = ""
    error: str = ""
    form_found: bool = False
    package_path: str = ""
    package_hash: str = ""
    extracted_files: list[dict[str, str]] = field(default_factory=list)


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, object]] = []
        self._form: dict[str, object] | None = None
        self._button_text: list[str] = []
        self._in_button = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form":
            self._form = {"attrs": attr_map, "inputs": [], "button_text": ""}
        elif self._form is not None and tag.lower() == "input":
            self._form["inputs"].append(attr_map)
        elif self._form is not None and tag.lower() == "button":
            self._form["inputs"].append(attr_map)
            self._button_text = []
            self._in_button = True

    def handle_data(self, data: str) -> None:
        if self._in_button:
            self._button_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "button" and self._form is not None:
            self._form["button_text"] = normalize_space(" ".join(self._button_text))
            self._in_button = False
        elif tag.lower() == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return normalize_space(re.sub(r"<[^>]+>", " ", value or ""))


def safe_slug(value: str, max_len: int = 100) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return (value[:max_len].strip("_") or "unknown")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def fetch_json(url: str, timeout: int) -> tuple[object, dict[str, str]]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with build_opener().open(req, timeout=timeout) as response:
        data = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        return json.loads(data.decode("utf-8")), headers


def fetch_products(timeout: int, max_pages: int = 20) -> list[Product]:
    products: list[Product] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"{STORE_API}?per_page=100&page={page}"
        items, _headers = fetch_json(url, timeout)
        if not isinstance(items, list) or not items:
            break
        for item in items:
            product_id = str(item.get("id", ""))
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            prices = item.get("prices") or {}
            price_raw = prices.get("price") or "0"
            try:
                price_minor = int(price_raw)
            except (TypeError, ValueError):
                price_minor = 0
            categories = [
                str(category.get("name", "")).strip()
                for category in item.get("categories", [])
                if category.get("name")
            ]
            products.append(
                Product(
                    product_id=product_id,
                    name=strip_tags(item.get("name", "")),
                    slug=str(item.get("slug", "")),
                    permalink=str(item.get("permalink", "")),
                    price_minor=price_minor,
                    currency=str(prices.get("currency_code", "")),
                    categories=categories,
                    short_description=strip_tags(item.get("short_description", "")),
                )
            )
    return products


def document_type_for(product: Product) -> str:
    categories = {category.lower() for category in product.categories}
    if "new law reports" in categories:
        return "New Law Report"
    if "sri lanka law reports" in categories:
        return "Sri Lanka Law Report"
    if "ceylon law reports" in categories:
        return "Ceylon Law Report"
    if "ceylon law recorder" in categories:
        return "Ceylon Law Recorder"
    if "supreme court judgements" in categories:
        return "Supreme Court Judgment"
    if "case digest" in categories or "lanka law digest" in categories:
        return "Case Digest"
    if "consolidated acts (2024)" in categories:
        return "Consolidated Act"
    if "core legislations" in categories:
        return "Core Legislation"
    if "legislative enactments" in categories:
        return "Legislative Enactment"
    if "acts and ordinances" in categories:
        return "Acts and Ordinances Compilation"
    if "legislations" in categories:
        return "Legislation"
    if "publications" in categories:
        return "Publication"
    return "LankaLaw Library Product"


def infer_year(product: Product) -> str:
    match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", product.name)
    return match.group(1) if match else ""


def document_id_for(product: Product) -> str:
    return f"lankalaw_{product.product_id}_{safe_slug(product.slug or product.name, 80)}"


def local_path_for(product: Product, extension: str = ".pdf") -> Path:
    doc_type = safe_slug(document_type_for(product), 60)
    if extension not in {".pdf", ".zip"}:
        extension = ".pdf"
    name = safe_slug(product.slug or product.name, 90)
    return RAW_DIR / "free_downloads" / doc_type / f"{product.product_id}_{name}{extension}"


def package_extract_dir_for(product: Product) -> Path:
    doc_type = safe_slug(document_type_for(product), 60)
    name = safe_slug(product.slug or product.name, 90)
    return RAW_DIR / "free_downloads" / doc_type / f"{product.product_id}_{name}"


def extracted_pdf_path_for(product: Product, member_name: str, index: int) -> Path:
    stem = safe_slug(Path(member_name).stem, 90)
    return package_extract_dir_for(product) / f"{index:03d}_{stem}.pdf"


def collect_existing_extracted_pdfs(product: Product) -> list[dict[str, str]]:
    directory = package_extract_dir_for(product)
    extracted: list[dict[str, str]] = []
    if not directory.exists():
        return extracted
    for path in sorted(directory.glob("*.pdf")):
        extracted.append(
            {
                "member_name": path.name,
                "local_path": str(path.relative_to(PROJECT_ROOT)),
                "file_hash": sha256_file(path),
                "bytes_downloaded": str(path.stat().st_size),
            }
        )
    return extracted


def save_zip_package(product: Product, data: bytes) -> tuple[Path, list[dict[str, str]]]:
    package_path = local_path_for(product, ".zip")
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path.write_bytes(data)

    extracted: list[dict[str, str]] = []
    with ZipFile(io.BytesIO(data)) as archive:
        pdf_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".pdf")
        ]
        for index, info in enumerate(pdf_infos, start=1):
            pdf_data = archive.read(info)
            if not pdf_data.startswith(b"%PDF"):
                continue
            target_path = extracted_pdf_path_for(product, info.filename, index)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(pdf_data)
            extracted.append(
                {
                    "member_name": info.filename,
                    "local_path": str(target_path.relative_to(PROJECT_ROOT)),
                    "file_hash": sha256_bytes(pdf_data),
                    "bytes_downloaded": str(len(pdf_data)),
                }
            )
    return package_path, extracted


def parse_download_form(page_html: str) -> dict[str, str] | None:
    parser = FormParser()
    parser.feed(page_html)
    for form in parser.forms:
        attrs = form.get("attrs", {})
        classes = " ".join(attrs.get("class", []) if isinstance(attrs.get("class"), list) else str(attrs.get("class", "")).split())
        inputs = form.get("inputs", [])
        values = {
            item.get("name", ""): item.get("value", "")
            for item in inputs
            if isinstance(item, dict) and item.get("name")
        }
        if values.get("action") == "somdn_download_single" and values.get("somdn_product"):
            return values
        if "somdn-download-form" in classes and values.get("somdn_product"):
            return values
    return None


def content_disposition_filename(headers: Message) -> str:
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition, flags=re.I)
    if not match:
        return ""
    return quote(match.group(1), safe="").replace("%", "_") if "/" in match.group(1) else match.group(1)


def download_product(product: Product, timeout: int, force: bool) -> DownloadResult:
    document_id = document_id_for(product)
    if product.price_minor > 0:
        return DownloadResult(
            product=product,
            document_id=document_id,
            status="licensed_purchase_required",
            error=f"Product price is {product.price_minor} minor units {product.currency}.",
        )

    target_path = local_path_for(product)
    package_path = local_path_for(product, ".zip")
    if target_path.exists() and not force:
        return DownloadResult(
            product=product,
            document_id=document_id,
            status="downloaded",
            local_path=str(target_path.relative_to(PROJECT_ROOT)),
            file_hash=sha256_file(target_path),
            bytes_downloaded=target_path.stat().st_size,
            form_found=True,
        )
    if package_path.exists() and not force:
        extracted = collect_existing_extracted_pdfs(product)
        return DownloadResult(
            product=product,
            document_id=document_id,
            status="downloaded",
            local_path=str(package_path.relative_to(PROJECT_ROOT)),
            package_path=str(package_path.relative_to(PROJECT_ROOT)),
            file_hash=sha256_file(package_path),
            package_hash=sha256_file(package_path),
            bytes_downloaded=package_path.stat().st_size,
            content_type="application/zip",
            filename=package_path.name,
            error=f"zip_extracted_pdf_count={len(extracted)}",
            form_found=True,
            extracted_files=extracted,
        )

    cookiejar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookiejar))
    try:
        page_req = Request(product.permalink, headers={"User-Agent": USER_AGENT})
        with opener.open(page_req, timeout=timeout) as response:
            page_html = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        return DownloadResult(product, document_id, "product_page_failed", error=str(exc))

    form = parse_download_form(page_html)
    if not form:
        return DownloadResult(product, document_id, "download_form_not_found", form_found=False)

    post_data = urlencode(form).encode("utf-8")
    try:
        req = Request(
            product.permalink,
            data=post_data,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": product.permalink,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with opener.open(req, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
            filename = content_disposition_filename(response.headers)
    except (HTTPError, URLError, TimeoutError) as exc:
        return DownloadResult(product, document_id, "download_failed", error=str(exc), form_found=True)

    is_pdf = data.startswith(b"%PDF") or "pdf" in content_type.lower()
    is_zip = data.startswith(b"PK\x03\x04") or "zip" in content_type.lower() or Path(filename).suffix.lower() == ".zip"
    if is_zip:
        try:
            package_path, extracted = save_zip_package(product, data)
        except BadZipFile as exc:
            return DownloadResult(
                product,
                document_id,
                "download_failed_bad_zip",
                content_type=content_type,
                bytes_downloaded=len(data),
                filename=filename,
                error=str(exc),
                form_found=True,
            )
        if not extracted:
            return DownloadResult(
                product,
                document_id,
                "download_failed_no_pdf_in_zip",
                local_path=str(package_path.relative_to(PROJECT_ROOT)),
                package_path=str(package_path.relative_to(PROJECT_ROOT)),
                file_hash=sha256_bytes(data),
                package_hash=sha256_bytes(data),
                content_type=content_type,
                bytes_downloaded=len(data),
                filename=filename,
                error="ZIP package contained no extractable PDFs.",
                form_found=True,
            )
        package_hash = sha256_bytes(data)
        return DownloadResult(
            product=product,
            document_id=document_id,
            status="downloaded",
            local_path=str(package_path.relative_to(PROJECT_ROOT)),
            package_path=str(package_path.relative_to(PROJECT_ROOT)),
            file_hash=package_hash,
            package_hash=package_hash,
            bytes_downloaded=len(data),
            content_type=content_type,
            filename=filename,
            error=f"zip_extracted_pdf_count={len(extracted)}",
            form_found=True,
            extracted_files=extracted,
        )

    if not is_pdf:
        return DownloadResult(
            product,
            document_id,
            "download_failed_not_pdf",
            content_type=content_type,
            bytes_downloaded=len(data),
            error=f"first_bytes={data[:24]!r}",
            form_found=True,
        )

    extension = Path(filename).suffix.lower() if filename else ".pdf"
    local_path = local_path_for(product, extension)
    if local_path.exists() and not force:
        return DownloadResult(
            product=product,
            document_id=document_id,
            status="downloaded",
            local_path=str(local_path.relative_to(PROJECT_ROOT)),
            file_hash=sha256_file(local_path),
            bytes_downloaded=local_path.stat().st_size,
            content_type=content_type,
            filename=filename,
            form_found=True,
        )

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    return DownloadResult(
        product=product,
        document_id=document_id,
        status="downloaded",
        local_path=str(local_path.relative_to(PROJECT_ROOT)),
        file_hash=sha256_bytes(data),
        bytes_downloaded=len(data),
        content_type=content_type,
        filename=filename,
        form_found=True,
    )


def product_registry_row(product: Product, result: DownloadResult | None, now: str) -> dict[str, str]:
    result = result or DownloadResult(
        product=product,
        document_id=document_id_for(product),
        status="metadata_extracted",
    )
    return {
        "product_id": product.product_id,
        "name": product.name,
        "slug": product.slug,
        "permalink": product.permalink,
        "price_minor": str(product.price_minor),
        "currency": product.currency,
        "is_free": "true" if product.price_minor == 0 else "false",
        "categories": "; ".join(product.categories),
        "download_form_found": "true" if result.form_found else "false",
        "download_status": result.status,
        "document_id": result.document_id,
        "local_path": result.local_path,
        "package_path": result.package_path,
        "file_hash": result.file_hash,
        "package_hash": result.package_hash,
        "bytes_downloaded": str(result.bytes_downloaded) if result.bytes_downloaded else "",
        "content_type": result.content_type,
        "content_disposition_filename": result.filename,
        "extracted_pdf_count": str(len(result.extracted_files)) if result.extracted_files else "",
        "extracted_pdf_paths": json.dumps(
            [item.get("local_path", "") for item in result.extracted_files],
            ensure_ascii=False,
        )
        if result.extracted_files
        else "",
        "last_checked": now,
        "notes": result.error,
    }


def manifest_row(product: Product, result: DownloadResult | None, now: str) -> dict[str, str]:
    document_id = document_id_for(product)
    result = result or DownloadResult(
        product=product,
        document_id=document_id,
        status="metadata_extracted",
    )
    if result.status == "downloaded":
        acquisition_status = "downloaded"
        missing_reason = ""
        next_action = (
            "Extract text from extracted package PDFs and compare against official corpus gaps."
            if result.extracted_files
            else "Extract text and compare against official corpus gaps."
        )
    elif product.price_minor > 0:
        acquisition_status = "licensed_purchase_required"
        missing_reason = f"Paid LankaLaw product ({product.price_minor} minor units {product.currency})."
        next_action = "Purchase/license if needed, or locate equivalent official source."
    else:
        acquisition_status = result.status
        missing_reason = result.error
        next_action = "Retry public LankaLaw download or inspect product page."

    return {
        "document_id": document_id,
        "source_id": SOURCE_ID,
        "source_document_id": product.product_id,
        "document_type": document_type_for(product),
        "title": product.name,
        "year": infer_year(product),
        "number": "",
        "date": "",
        "language": "English",
        "source_url": product.permalink,
        "download_url": product.permalink if product.price_minor == 0 else "",
        "local_path": result.local_path,
        "file_hash": result.file_hash,
        "acquisition_status": acquisition_status,
        "extraction_status": (
            "package_extracted" if result.extracted_files else "not_started" if result.status == "downloaded" else ""
        ),
        "ocr_required": "",
        "text_quality_score": "",
        "legal_status": "third_party_reference_not_official",
        "missing_reason": missing_reason,
        "next_action": next_action,
        "last_checked": now,
        "notes": (
            f"categories={'; '.join(product.categories)}; "
            f"price_minor={product.price_minor}; currency={product.currency}; "
            f"short_description={product.short_description}; "
            f"download_note={result.error}"
        ),
    }


def extracted_manifest_rows(product: Product, result: DownloadResult | None, now: str) -> list[dict[str, str]]:
    if not result or not result.extracted_files:
        return []
    rows: list[dict[str, str]] = []
    parent_document_id = document_id_for(product)
    for index, item in enumerate(result.extracted_files, start=1):
        member_name = item.get("member_name", "")
        member_stem = normalize_space(Path(member_name).stem.replace("_", " ").replace("-", " "))
        rows.append(
            {
                "document_id": f"{parent_document_id}__pdf_{index:03d}_{safe_slug(member_stem, 50)}",
                "source_id": SOURCE_ID,
                "source_document_id": f"{product.product_id}:{member_name}",
                "document_type": document_type_for(product),
                "title": f"{product.name} - {member_stem}" if member_stem else f"{product.name} - PDF {index}",
                "year": infer_year(product),
                "number": "",
                "date": "",
                "language": "English",
                "source_url": product.permalink,
                "download_url": product.permalink,
                "local_path": item.get("local_path", ""),
                "file_hash": item.get("file_hash", ""),
                "acquisition_status": "downloaded",
                "extraction_status": "not_started",
                "ocr_required": "",
                "text_quality_score": "",
                "legal_status": "third_party_reference_not_official",
                "missing_reason": "",
                "next_action": "Extract text and compare against official corpus gaps.",
                "last_checked": now,
                "notes": (
                    f"extracted_from_document_id={parent_document_id}; "
                    f"package_path={result.package_path or result.local_path}; "
                    f"member_name={member_name}; "
                    f"categories={'; '.join(product.categories)}"
                ),
            }
        )
    return rows


def write_source_registry(fields: list[str], now: str) -> None:
    merge_by_key(
        SOURCE_REGISTRY_PATH,
        fields,
        [
            {
                "source_id": SOURCE_ID,
                "source_name": "LankaLaw eLaw Library",
                "source_url": "https://lankalaw.net/shop/",
                "source_owner": "LankaLaw",
                "reliability_tier": "C",
                "legal_authority_type": "third_party_legal_library_and_compilation",
                "jurisdiction": "Sri Lanka",
                "languages": "English",
                "coverage_start": "",
                "coverage_end": "",
                "coverage_confidence": "product_catalog_extracted",
                "licence_status": "mixed_free_and_paid; review before production use",
                "access_method": "public_woocommerce_store_api_and_visible_download_form",
                "refresh_frequency": "monthly",
                "known_gaps": "Paid products require purchase/licence; source is not official government/court publication.",
                "notes": "Downloaded only free public products exposed by visible Download Now form.",
                "last_checked": now,
            }
        ],
        "source_id",
    )


def update_missing_register(fields: list[str], products: list[Product], results: list[DownloadResult], now: str) -> None:
    paid = [product for product in products if product.price_minor > 0]
    free = [product for product in products if product.price_minor == 0]
    downloaded = [result for result in results if result.status == "downloaded"]
    failed_free = [
        result
        for result in results
        if result.product.price_minor == 0 and result.status != "downloaded"
    ]
    merge_by_key(
        MISSING_DATA_PATH,
        fields,
        [
            {
                "missing_id": "M_LANKALAW_LICENSED_PRODUCTS",
                "data_category": "LankaLaw paid/licensed legal library products",
                "expected_coverage": "All LankaLaw shop products relevant to Sri Lankan law",
                "known_available_coverage": (
                    f"{len(products)} products cataloged; {len(free)} free products identified; "
                    f"{len(downloaded)} free products downloaded; {len(paid)} paid products require license."
                ),
                "missing_description": "Paid LankaLaw products are cataloged but not downloaded without purchase/licence.",
                "legal_importance": "medium",
                "risk_if_missing": "May miss useful third-party compilations, but official-source corpus remains authoritative.",
                "probable_source": "LankaLaw eLaw Library; official government/court alternatives",
                "next_action": "Purchase/license paid products if needed; otherwise recover equivalent official documents.",
                "owner": "Corpus lead",
                "status": "open" if paid else "complete",
                "last_checked": now,
                "notes": "Do not treat LankaLaw copies as official authority unless verified against official source.",
            }
        ]
        + [
            {
                "missing_id": "M_LANKALAW_PUBLIC_DOWNLOAD_FAILURES",
                "data_category": "LankaLaw public/free product download failures",
                "expected_coverage": "All free public LankaLaw shop products relevant to Sri Lankan law",
                "known_available_coverage": (
                    f"{len(free)} free products identified; {len(downloaded)} acquired; "
                    f"{len(failed_free)} still failed."
                ),
                "missing_description": "Some public LankaLaw products did not return an accessible PDF or ZIP package.",
                "legal_importance": "medium",
                "risk_if_missing": "May miss useful third-party compilations; official-source corpus remains authoritative.",
                "probable_source": "LankaLaw eLaw Library; official government/court alternatives",
                "next_action": "Retry failed public products manually or recover equivalent official documents.",
                "owner": "Corpus lead",
                "status": "open" if failed_free else "complete",
                "last_checked": now,
                "notes": json.dumps(
                    [
                        {
                            "product_id": result.product.product_id,
                            "name": result.product.name,
                            "status": result.status,
                            "error": result.error,
                            "url": result.product.permalink,
                        }
                        for result in failed_free
                    ],
                    ensure_ascii=False,
                ),
            }
        ],
        "missing_id",
    )


def append_run_log(fields: list[str], run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire public/free LankaLaw library PDFs.")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--free-only", action="store_true", default=True)
    parser.add_argument("--include-paid-metadata", action="store_true", default=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    now = utc_now()
    corpus = load_corpus_module()
    products = fetch_products(args.timeout)
    if args.limit:
        products = products[: args.limit]

    results: list[DownloadResult] = []
    result_by_product: dict[str, DownloadResult] = {}
    if not args.metadata_only:
        candidates = [product for product in products if product.price_minor == 0]
        if args.progress:
            print(f"Cataloged {len(products)} products; downloading {len(candidates)} free products.", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
            futures = [executor.submit(download_product, product, args.timeout, args.force) for product in candidates]
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                result_by_product[result.product.product_id] = result
                completed += 1
                if args.progress and (completed == 1 or completed % 10 == 0 or completed == len(candidates)):
                    print(
                        f"downloaded/checked {completed}/{len(candidates)} "
                        f"({result.product.name}: {result.status})",
                        file=sys.stderr,
                        flush=True,
                    )
        for product in products:
            if product.price_minor > 0:
                result = download_product(product, args.timeout, args.force)
                results.append(result)
                result_by_product[product.product_id] = result

    product_rows = [
        product_registry_row(product, result_by_product.get(product.product_id), now)
        for product in products
    ]
    merge_by_key(PRODUCT_REGISTRY_PATH, PRODUCT_FIELDS, product_rows, "product_id")

    manifest_rows = []
    for product in products:
        if args.include_paid_metadata or product.price_minor == 0:
            result = result_by_product.get(product.product_id)
            manifest_rows.append(manifest_row(product, result, now))
            manifest_rows.extend(extracted_manifest_rows(product, result, now))
    merge_by_key(DOCUMENT_MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, manifest_rows, "document_id")

    write_source_registry(corpus.SOURCE_REGISTRY_FIELDS, now)
    update_missing_register(corpus.MISSING_DATA_FIELDS, products, results, now)

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    latest = {
        "lankalaw_acquisition": {
            "started_at": started,
            "ended_at": utc_now(),
            "products_cataloged": len(products),
            "free_products": sum(1 for product in products if product.price_minor == 0),
            "paid_products": sum(1 for product in products if product.price_minor > 0),
            "download_counts": counts,
        }
    }
    corpus.build_corpus_index(latest)
    append_run_log(
        corpus.EXTRACTION_RUN_FIELDS,
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_lankalaw",
            "source_id": SOURCE_ID,
            "run_type": "lankalaw_acquisition",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(len(products)),
            "documents_downloaded": str(counts.get("downloaded", 0)),
            "errors": json.dumps(
                [
                    f"{result.product.product_id}: {result.status}: {result.error}"
                    for result in results
                    if result.status not in {"downloaded", "licensed_purchase_required"}
                ],
                ensure_ascii=False,
            ),
            "new_missing_items": "M_LANKALAW_LICENSED_PRODUCTS",
            "notes": json.dumps(latest["lankalaw_acquisition"], ensure_ascii=False),
        },
    )
    print(json.dumps(latest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
