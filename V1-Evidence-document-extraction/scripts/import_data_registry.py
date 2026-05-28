#!/usr/bin/env python3
"""Import corpus manifest and missing-source register into PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.data_registry import (
    build_registry_file_hash,
    document_ingestion_status,
    document_stage,
    normalize_document_row,
    normalize_missing_source_row,
    validate_document_registry,
)
from sl_legal_rag.db import LegalWorkspaceRepository, session_scope


DEFAULT_DOCUMENT_MANIFEST = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
DEFAULT_MISSING_REGISTER = PROJECT_ROOT / "data" / "manifests" / "missing_data_register.csv"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-manifest", default=str(DEFAULT_DOCUMENT_MANIFEST))
    parser.add_argument("--missing-register", default=str(DEFAULT_MISSING_REGISTER))
    parser.add_argument("--source-id", default="DATA_REGISTRY")
    parser.add_argument("--pipeline-version", default="phase2.registry.v1")
    parser.add_argument("--filter-source-id", action="append", help="Only import manifest rows from these source IDs.")
    parser.add_argument("--document-id", action="append", help="Only import these document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--year", action="append", help="Only import documents from these years.")
    parser.add_argument(
        "--include-missing-register",
        action="store_true",
        help="Import missing-source register rows even when manifest filters are active.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.document_ids_filter = load_document_ids(args)
    return args


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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


def filter_document_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    source_ids = set(args.filter_source_id or [])
    document_ids = args.document_ids_filter
    years = set(args.year or [])
    filtered = []
    for row in rows:
        if source_ids and row.get("source_id") not in source_ids:
            continue
        if document_ids and row.get("document_id") not in document_ids:
            continue
        if years and row.get("year") not in years:
            continue
        filtered.append(row)
    if args.limit:
        filtered = filtered[: args.limit]
    return filtered


def filters_active(args: argparse.Namespace) -> bool:
    return bool(args.filter_source_id or args.document_ids_filter or args.year or args.limit)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    document_manifest = Path(args.document_manifest)
    missing_register = Path(args.missing_register)
    document_rows = filter_document_rows(read_csv(document_manifest), args)
    validation = validate_document_registry(document_rows)
    if not validation.valid:
        print(
            json.dumps(
                {
                    "valid": validation.valid,
                    "row_count": validation.row_count,
                    "duplicate_document_ids": validation.duplicate_document_ids,
                    "issues": [issue.__dict__ for issue in validation.issues[:50]],
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    missing_rows = []
    if args.include_missing_register or not filters_active(args):
        missing_rows = read_csv(missing_register)
    manifest_hash = build_registry_file_hash(document_manifest) if document_manifest.exists() else None
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "document_rows": len(document_rows),
                    "downloaded_count": validation.downloaded_count,
                    "missing_count": validation.missing_count,
                    "missing_register_rows": len(missing_rows),
                    "manifest_hash": manifest_hash,
                },
                indent=2,
            )
        )
        return 0

    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        ingestion_run_id = repo.start_ingestion_run(
            source_id=args.source_id,
            pipeline_name="data_registry_import",
            pipeline_version=args.pipeline_version,
            manifest_path=str(document_manifest.relative_to(PROJECT_ROOT)) if document_manifest.exists() else None,
            corpus_root="data",
            input_manifest_hash=manifest_hash,
            config={"missing_register": str(missing_register.relative_to(PROJECT_ROOT))},
        )
        imported_documents = 0
        for raw_row in document_rows:
            row = normalize_document_row(raw_row)
            status = document_ingestion_status(row["acquisition_status"], row["extraction_status"])
            repo.record_document_ingestion_event(
                ingestion_run_id=ingestion_run_id,
                document_id=row["document_id"],
                source_id=row["source_id"],
                source_document_id=row["source_document_id"],
                document_type=row["document_type"],
                title=row["title"],
                year=row["year"],
                number=row["number"],
                document_date=row["document_date"],
                language=row["language"],
                source_url=row["source_url"],
                download_url=row["download_url"],
                local_path=row["local_path"],
                file_hash=row["file_hash"],
                acquisition_status=row["acquisition_status"],
                extraction_status=row["extraction_status"],
                stage=document_stage(row["acquisition_status"], row["extraction_status"]),
                status=status,
                ocr_required=row["ocr_required"],
                text_quality_score=row["text_quality_score"],
                legal_status=row["legal_status"],
                missing_reason=row["missing_reason"],
                next_action=row["next_action"],
                notes=row["notes"],
                metadata={"registry_last_checked": row["last_checked"].isoformat() if row["last_checked"] else None},
                version_label="registry-current",
                source_snapshot={key: value for key, value in raw_row.items() if value},
            )
            imported_documents += 1

        imported_missing = 0
        for raw_row in missing_rows:
            row = normalize_missing_source_row(raw_row)
            repo.upsert_missing_source_record(**row)
            imported_missing += 1

        summary = repo.finish_ingestion_run(
            ingestion_run_id=ingestion_run_id,
            status="complete",
            output={
                "documents_imported": imported_documents,
                "missing_sources_imported": imported_missing,
                "downloaded_count": validation.downloaded_count,
                "missing_count": validation.missing_count,
            },
        )
    print(
        json.dumps(
            {
                "ingestion_run_id": summary.ingestion_run_id,
                "status": summary.status,
                "documents_imported": imported_documents,
                "missing_sources_imported": imported_missing,
                "document_count": summary.document_count,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
