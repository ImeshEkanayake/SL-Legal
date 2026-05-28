#!/usr/bin/env python3
"""Build citable RAG chunks from documents and pages already in PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.chunking import PRIORITY_SOURCE_IDS, PageRecord, chunk_pages, normalize_text  # noqa: E402


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks_from_postgres.jsonl"
SUPPORTED_EXTRACTION_STATUSES = {"text_extracted", "translated"}
MIN_TEXT_QUALITY_SCORE = 0.10
SUPPORTED_LANGUAGES = {
    "",
    "english",
    "eng",
    "en",
    "sinhala",
    "sin",
    "si",
    "tamil",
    "tam",
    "ta",
    "unknown",
}


@dataclass(frozen=True)
class PageCandidate:
    page_number: int
    text: str
    extraction_method: str
    ocr_confidence: float | None = None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSONL path.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--limit", type=int, default=0, help="Maximum documents with chunks to write. 0 means no limit.")
    parser.add_argument("--document-id", action="append", help="Only include these document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--source-id", action="append", help="Only include these source IDs.")
    parser.add_argument("--document-type", action="append", help="Only include these document types.")
    parser.add_argument("--include-gazettes", action="store_true", help="Include gazettes in this run.")
    parser.add_argument(
        "--include-translation-text-versions",
        action="store_true",
        help="Also chunk translated fallback document_text_versions with explicit translation provenance.",
    )
    parser.add_argument(
        "--only-translation-text-versions",
        action="store_true",
        help="Chunk only translated fallback document_text_versions. Implies --include-translation-text-versions.",
    )
    parser.add_argument("--target-tokens", type=int, default=650, help="Target tokens per chunk.")
    parser.add_argument("--overlap-tokens", type=int, default=80, help="Approximate overlap tokens between chunks.")
    args = parser.parse_args(argv)
    args.document_ids_filter = load_document_ids(args)
    return args


def load_document_ids(args: argparse.Namespace) -> set[str]:
    document_ids = set(args.document_id or [])
    for file_name in args.document_id_file or []:
        path = Path(file_name)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            normalized = line.strip()
            if normalized and not normalized.startswith("#"):
                document_ids.add(normalized)
    return document_ids


def parse_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_quality_score(value: object) -> float:
    try:
        return float(str(value or "0").strip() or "0")
    except ValueError:
        return 0.0


def normalize_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalize_year(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def document_row_to_chunk_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "document_id": str(row.get("document_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "source_document_id": str(row.get("source_document_id") or ""),
        "document_type": str(row.get("document_type") or ""),
        "title": str(row.get("title") or ""),
        "year": normalize_year(row.get("year")),
        "number": str(row.get("number") or ""),
        "date": normalize_date(row.get("document_date")),
        "language": str(row.get("language") or ""),
        "source_url": str(row.get("source_url") or ""),
        "download_url": str(row.get("download_url") or ""),
        "local_path": str(row.get("local_path") or ""),
        "file_hash": str(row.get("file_hash") or ""),
        "acquisition_status": str(row.get("acquisition_status") or ""),
        "extraction_status": str(row.get("extraction_status") or ""),
        "ocr_required": str(row.get("ocr_required") or ""),
        "text_quality_score": str(row.get("text_quality_score") or ""),
        "legal_status": str(row.get("legal_status") or ""),
        "missing_reason": str(row.get("missing_reason") or ""),
        "next_action": str(row.get("next_action") or ""),
        "last_checked": normalize_date(row.get("last_checked")),
        "notes": str(row.get("notes") or ""),
        "text_version_id": str(row.get("text_version_id") or ""),
        "text_origin": str(row.get("text_origin") or "source"),
        "source_language": str(row.get("source_language") or row.get("language") or ""),
        "translated_from_language": str(row.get("translated_from_language") or ""),
        "translation_review_status": str(row.get("translation_review_status") or ""),
        "page_anchor_status": str(row.get("page_anchor_status") or ""),
    }


def page_score(candidate: PageCandidate) -> tuple[int, int, int, float, str]:
    normalized = normalize_text(candidate.text)
    method_priority = {
        "ocr": 4,
        "text_layer": 3,
        "text": 2,
    }.get(candidate.extraction_method, 1)
    confidence = candidate.ocr_confidence if candidate.ocr_confidence is not None else 100.0
    return (1 if normalized else 0, len(normalized), method_priority, confidence, candidate.extraction_method)


def select_best_pages(candidates: list[PageCandidate]) -> list[PageRecord]:
    best_by_page: dict[int, PageCandidate] = {}
    for candidate in candidates:
        if candidate.page_number <= 0:
            continue
        if not normalize_text(candidate.text):
            continue
        existing = best_by_page.get(candidate.page_number)
        if existing is None or page_score(candidate) > page_score(existing):
            best_by_page[candidate.page_number] = candidate
    pages: list[PageRecord] = []
    for page_number in sorted(best_by_page):
        selected = best_by_page[page_number]
        pages.append(
            PageRecord(
                page_number=selected.page_number,
                text=normalize_text(selected.text),
                confidence=selected.ocr_confidence,
                extraction_method=selected.extraction_method,
            )
        )
    return pages


def row_is_eligible(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if row.get("acquisition_status") != "downloaded":
        return False
    if row.get("extraction_status") not in SUPPORTED_EXTRACTION_STATUSES:
        return False
    if parse_bool(row.get("ocr_required")):
        return False
    if parse_quality_score(row.get("text_quality_score")) < MIN_TEXT_QUALITY_SCORE:
        return False
    language = str(row.get("language") or "").lower()
    if language not in SUPPORTED_LANGUAGES:
        return False
    source_id = str(row.get("source_id") or "")
    if args.source_id and source_id not in set(args.source_id):
        return False
    if args.document_ids_filter and row.get("document_id") not in args.document_ids_filter:
        return False
    if args.document_type and row.get("document_type") not in set(args.document_type):
        return False
    if not args.include_gazettes and "GAZETTE" in source_id:
        return False
    if not args.source_id and source_id not in PRIORITY_SOURCE_IDS and "GAZETTE" not in source_id:
        return False
    return True


def fetch_document_rows(conn: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    query = """
        SELECT
            d.document_id, d.source_id, d.source_document_id, d.document_type,
            d.title, d.year, d.number, d.document_date, d.language,
            d.source_url, d.download_url, d.local_path, d.file_hash,
            d.acquisition_status, d.extraction_status, d.ocr_required,
            d.text_quality_score, d.legal_status, d.missing_reason,
            d.next_action, d.last_checked, d.notes,
            current_text_version.text_version_id,
            current_text_version.text_origin,
            current_text_version.source_language,
            current_text_version.translated_from_language,
            current_text_version.translation_review_status
        FROM documents d
        LEFT JOIN LATERAL (
            SELECT
                dtv.text_version_id,
                dtv.text_origin,
                dtv.source_language,
                dtv.translated_from_language,
                dtv.translation_review_status
            FROM document_text_versions dtv
            WHERE dtv.document_id = d.document_id
              AND dtv.text_origin = 'source'
            ORDER BY
                CASE WHEN dtv.version_label = 'current-pages-v1' THEN 0 ELSE 1 END,
                dtv.created_at DESC,
                dtv.text_version_id DESC
            LIMIT 1
        ) current_text_version ON true
        ORDER BY source_id, document_id
    """
    with conn.cursor() as cur:
        cur.execute(query)
        column_names = [description.name for description in cur.description]
        rows = [dict(zip(column_names, row)) for row in cur.fetchall()]
    return [row for row in rows if row_is_eligible(row, args)]


def translation_row_is_eligible(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if row.get("text_origin") != "translation":
        return False
    if parse_bool(row.get("ocr_required")):
        return False
    if parse_quality_score(row.get("text_quality_score")) < MIN_TEXT_QUALITY_SCORE:
        return False
    if not normalize_text(str(row.get("full_text") or "")):
        return False
    if row.get("translation_review_status") in {"superseded_by_official", "rejected"}:
        return False
    source_id = str(row.get("source_id") or "")
    if args.source_id and source_id not in set(args.source_id):
        return False
    if args.document_ids_filter and row.get("document_id") not in args.document_ids_filter:
        return False
    if args.document_type and row.get("document_type") not in set(args.document_type):
        return False
    if not args.include_gazettes and "GAZETTE" in source_id:
        return False
    if not args.source_id and source_id not in PRIORITY_SOURCE_IDS and "GAZETTE" not in source_id:
        return False
    return True


def fetch_translation_text_version_rows(conn: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    query = """
        SELECT
            d.document_id, d.source_id, d.source_document_id, d.document_type,
            d.title, d.year, d.number, d.document_date,
            dtv.language, d.source_url, d.download_url, d.local_path,
            d.file_hash, d.acquisition_status, 'translated' AS extraction_status,
            d.ocr_required, d.text_quality_score, d.legal_status,
            d.missing_reason, d.next_action, d.last_checked, d.notes,
            dtv.text_version_id, dtv.text_origin, dtv.source_language,
            dtv.translated_from_language, dtv.translation_review_status,
            dtv.full_text, 'translation_full_text_no_page_map' AS page_anchor_status
        FROM document_text_versions dtv
        JOIN documents d ON d.document_id = dtv.document_id
        WHERE dtv.text_origin = 'translation'
        ORDER BY d.source_id, d.document_id, dtv.created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(query)
        column_names = [description.name for description in cur.description]
        rows = [dict(zip(column_names, row)) for row in cur.fetchall()]
    return [row for row in rows if translation_row_is_eligible(row, args)]


def fetch_page_candidates(conn: Any, document_id: str) -> list[PageCandidate]:
    query = """
        SELECT page_number, text, extraction_method, ocr_confidence
        FROM pages
        WHERE document_id = %s
        ORDER BY page_number, extraction_method
    """
    with conn.cursor() as cur:
        cur.execute(query, (document_id,))
        candidates = []
        for page_number, text, extraction_method, ocr_confidence in cur.fetchall():
            confidence = None
            if ocr_confidence is not None:
                confidence = float(ocr_confidence) if isinstance(ocr_confidence, Decimal) else float(ocr_confidence)
            candidates.append(
                PageCandidate(
                    page_number=int(page_number),
                    text=str(text or ""),
                    extraction_method=str(extraction_method or ""),
                    ocr_confidence=confidence,
                )
            )
    return candidates


def pages_for_translation_text_version(row: dict[str, Any]) -> list[PageRecord]:
    text = normalize_text(str(row.get("full_text") or ""))
    if not text:
        return []
    return [PageRecord(page_number=0, text=text, extraction_method="translation")]


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: install psycopg before building chunks from Postgres.") from exc

    documents_considered = 0
    documents_chunked = 0
    translation_versions_considered = 0
    translation_versions_chunked = 0
    chunks_written = 0
    skipped_without_pages = 0

    with psycopg.connect(args.dsn) as conn, output_path.open("w", encoding="utf-8") as handle:
        chunk_source_rows = []
        if not args.only_translation_text_versions:
            chunk_source_rows.extend((document_row, False) for document_row in fetch_document_rows(conn, args))
        if args.include_translation_text_versions or args.only_translation_text_versions:
            chunk_source_rows.extend((row, True) for row in fetch_translation_text_version_rows(conn, args))

        for document_row, is_translation_version in chunk_source_rows:
            documents_considered += 1
            if is_translation_version:
                translation_versions_considered += 1
            row = document_row_to_chunk_row(document_row)
            pages = (
                pages_for_translation_text_version(document_row)
                if is_translation_version
                else select_best_pages(fetch_page_candidates(conn, row["document_id"]))
            )
            if not pages:
                skipped_without_pages += 1
                continue
            written_for_doc = 0
            for chunk in chunk_pages(
                row,
                pages,
                target_tokens=args.target_tokens,
                overlap_tokens=args.overlap_tokens,
            ):
                handle.write(json.dumps(chunk.to_json(), ensure_ascii=False) + "\n")
                chunks_written += 1
                written_for_doc += 1
            if written_for_doc:
                documents_chunked += 1
                if is_translation_version:
                    translation_versions_chunked += 1
                if args.limit and documents_chunked >= args.limit:
                    break

    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "documents_considered": documents_considered,
                "documents_chunked": documents_chunked,
                "translation_versions_considered": translation_versions_considered,
                "translation_versions_chunked": translation_versions_chunked,
                "skipped_without_pages": skipped_without_pages,
                "chunks_written": chunks_written,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
