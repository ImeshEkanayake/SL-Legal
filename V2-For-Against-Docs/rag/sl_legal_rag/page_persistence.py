from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from .chunking import PageRecord, is_low_confidence_ocr_page, pages_for_manifest_row, read_manifest, read_ocr_register, stable_hash


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
OCR_REGISTER_PATH = PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"


@dataclass(frozen=True)
class PageLoadResult:
    documents_considered: int
    documents_with_pages: int
    pages_upserted: int
    skipped_missing_document: int
    skipped_without_pages: int


def stable_page_id(document_id: str, extraction_method: str, page_number: int) -> str:
    raw = f"{document_id}:{extraction_method}:{page_number}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"page_{document_id}_{extraction_method}_{page_number:05d}_{digest}"


def quality_flags_for_page(page: PageRecord) -> list[str]:
    flags: list[str] = []
    if page.error:
        flags.append("page_extraction_error")
    if not page.text.strip():
        flags.append("empty_page_text")
    if is_low_confidence_ocr_page(page):
        flags.append("low_confidence_ocr")
    if len(page.text.strip()) < 25:
        flags.append("very_short_page_text")
    return flags


def existing_document_ids(session: Session, document_ids: Iterable[str]) -> set[str]:
    ids = sorted(set(document_ids))
    if not ids:
        return set()
    rows = session.execute(
        text("SELECT document_id FROM documents WHERE document_id = ANY(:document_ids)"),
        {"document_ids": ids},
    ).scalars()
    return {str(row) for row in rows}


def upsert_document_pages(session: Session, *, document_id: str, pages: list[PageRecord]) -> int:
    upserted = 0
    for page in pages:
        page_text = page.text or ""
        session.execute(
            text(
                """
                INSERT INTO pages (
                    page_id, document_id, page_number, text, text_hash,
                    extraction_method, ocr_confidence, quality_flags, layout
                )
                VALUES (
                    :page_id, :document_id, :page_number, :text, :text_hash,
                    :extraction_method, :ocr_confidence, :quality_flags, '{}'::jsonb
                )
                ON CONFLICT (document_id, page_number, extraction_method) DO UPDATE SET
                    text = EXCLUDED.text,
                    text_hash = EXCLUDED.text_hash,
                    ocr_confidence = EXCLUDED.ocr_confidence,
                    quality_flags = EXCLUDED.quality_flags
                """
            ),
            {
                "page_id": stable_page_id(document_id, page.extraction_method, page.page_number),
                "document_id": document_id,
                "page_number": page.page_number,
                "text": page_text,
                "text_hash": stable_hash(page_text),
                "extraction_method": page.extraction_method,
                "ocr_confidence": page.confidence,
                "quality_flags": quality_flags_for_page(page),
            },
        )
        upserted += 1
    session.flush()
    return upserted


def load_pages_from_manifest(
    *,
    session: Session,
    manifest_path: Path = MANIFEST_PATH,
    ocr_register_path: Path = OCR_REGISTER_PATH,
    document_ids: set[str] | None = None,
    source_ids: set[str] | None = None,
    limit_documents: int = 0,
    require_existing_documents: bool = True,
) -> PageLoadResult:
    rows = read_manifest(manifest_path)
    ocr_register = read_ocr_register(ocr_register_path)
    filtered_rows = []
    for row in rows:
        if row.get("acquisition_status") != "downloaded":
            continue
        if row.get("extraction_status") not in {"text_extracted", "text_empty_needs_ocr"}:
            continue
        if document_ids and row.get("document_id") not in document_ids:
            continue
        if source_ids and row.get("source_id") not in source_ids:
            continue
        filtered_rows.append(row)

    allowed_document_ids = None
    if require_existing_documents:
        allowed_document_ids = existing_document_ids(session, (row["document_id"] for row in filtered_rows))

    documents_considered = 0
    documents_with_pages = 0
    pages_upserted = 0
    skipped_missing_document = 0
    skipped_without_pages = 0

    for row in filtered_rows:
        if limit_documents and documents_with_pages >= limit_documents:
            break
        document_id = row["document_id"]
        documents_considered += 1
        if allowed_document_ids is not None and document_id not in allowed_document_ids:
            skipped_missing_document += 1
            continue
        pages = [page for page in pages_for_manifest_row(row, ocr_register) if page.page_number > 0]
        if not pages:
            skipped_without_pages += 1
            continue
        pages_upserted += upsert_document_pages(session, document_id=document_id, pages=pages)
        documents_with_pages += 1

    return PageLoadResult(
        documents_considered=documents_considered,
        documents_with_pages=documents_with_pages,
        pages_upserted=pages_upserted,
        skipped_missing_document=skipped_missing_document,
        skipped_without_pages=skipped_without_pages,
    )
