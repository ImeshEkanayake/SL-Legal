#!/usr/bin/env python3
"""Build citable RAG chunks from the corpus manifest and extracted/OCR pages.

This is the first executable step of the LLM layer. It does not call an LLM and
does not index into external services yet; it creates a stable JSONL chunk file
that can be loaded into PostgreSQL, OpenSearch, and Qdrant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.chunking import (  # noqa: E402
    PRIORITY_SOURCE_IDS,
    chunk_pages,
    pages_for_manifest_row,
    read_manifest,
    read_ocr_register,
)


MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
OCR_REGISTER_PATH = PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks.jsonl"
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build legal RAG chunks.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSONL path.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum documents with chunks to write. 0 means no limit.")
    parser.add_argument("--source-id", action="append", help="Only include these source IDs.")
    parser.add_argument("--document-id", action="append", help="Only include these document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--document-type", action="append", help="Only include these document types.")
    parser.add_argument("--include-gazettes", action="store_true", help="Include gazettes in this run.")
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


def row_is_eligible(row: dict[str, str], args: argparse.Namespace) -> bool:
    if row.get("acquisition_status") != "downloaded":
        return False
    if row.get("language") and row.get("language").lower() not in SUPPORTED_LANGUAGES:
        return False
    if row.get("extraction_status") not in SUPPORTED_EXTRACTION_STATUSES:
        return False
    if parse_bool(row.get("ocr_required")):
        return False
    if parse_quality_score(row.get("text_quality_score")) < MIN_TEXT_QUALITY_SCORE:
        return False
    if args.source_id and row.get("source_id") not in set(args.source_id):
        return False
    if args.document_ids_filter and row.get("document_id") not in args.document_ids_filter:
        return False
    if args.document_type and row.get("document_type") not in set(args.document_type):
        return False
    if not args.include_gazettes and "GAZETTE" in row.get("source_id", ""):
        return False
    if not args.source_id and row.get("source_id") not in PRIORITY_SOURCE_IDS and "GAZETTE" not in row.get("source_id", ""):
        # Keep first-pass indexing focused on the legal priority corpus.
        return False
    return True


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = read_manifest(MANIFEST_PATH)
    ocr_register = read_ocr_register(OCR_REGISTER_PATH)

    documents_considered = 0
    documents_chunked = 0
    chunks_written = 0
    skipped_without_pages = 0

    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if not row_is_eligible(row, args):
                continue
            documents_considered += 1
            pages = pages_for_manifest_row(row, ocr_register)
            pages = [page for page in pages if page.text.strip()]
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
                if args.limit and documents_chunked >= args.limit:
                    break

    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "documents_considered": documents_considered,
                "documents_chunked": documents_chunked,
                "skipped_without_pages": skipped_without_pages,
                "chunks_written": chunks_written,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
