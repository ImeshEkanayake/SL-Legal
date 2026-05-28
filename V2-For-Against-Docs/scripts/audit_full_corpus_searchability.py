#!/usr/bin/env python3
"""Audit which corpus documents are fully searchable and what remains."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_TRACKING_DIR = PROJECT_ROOT / "data" / "tracking" / "rag_searchability"


MISSING_FIELDS = [
    "document_id",
    "source_id",
    "document_type",
    "title",
    "year",
    "language",
    "acquisition_status",
    "extraction_status",
    "page_count",
    "text_page_count",
    "text_version_count",
    "source_text_version_count",
    "english_text_version_count",
    "translation_text_version_count",
    "chunk_count",
    "classification",
    "recovery_priority",
    "next_action",
    "language_recovery_plan",
    "local_path",
    "source_url",
    "download_url",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--output-dir", default=str(DEFAULT_TRACKING_DIR))
    parser.add_argument("--stamp", help="Optional timestamp/file suffix for reproducible test output.")
    parser.add_argument("--sync-missing-source-registry", action="store_true", help="Upsert missing/searchability gaps into missing_sources.")
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def document_language(row: dict[str, Any]) -> str:
    return str(row.get("language") or "").strip().lower()


def is_english_language(row: dict[str, Any]) -> bool:
    return document_language(row) in {"english", "en", ""}


def requires_translation_fallback(row: dict[str, Any]) -> bool:
    """Only known non-English source languages should be auto-queued for translation.

    Many historical court records were imported with language='unknown' even though
    their extracted text is English. Those need language detection, not blind
    machine translation.
    """

    return document_language(row) in {"sinhala", "sin", "si", "tamil", "tam", "ta"}


def classify_document(row: dict[str, Any]) -> tuple[str, str, str, str]:
    language_recovery_plan = "Use original English source text."
    if requires_translation_fallback(row):
        language_recovery_plan = (
            "Keep original source-language text; create an explicitly labelled English translation text version "
            "until an official English document is acquired."
        )
    elif not is_english_language(row):
        language_recovery_plan = "Detect the source language before deciding whether an English translation fallback is required."
    if int(row.get("original_asset_count") or 0) == 0:
        return "needs_original_asset", "critical", "Sync the original document into object storage and record a primary file asset.", language_recovery_plan
    if int(row.get("page_count") or 0) == 0:
        return "needs_page_extraction", "high", "Run PDF text-layer extraction; if it produces empty pages, route the document to OCR.", language_recovery_plan
    if int(row.get("text_page_count") or 0) == 0:
        return "needs_ocr_or_text_recovery", "high", "Run OCR or manual text recovery, then reload pages and rebuild text versions/chunks.", language_recovery_plan
    if int(row.get("text_version_count") or 0) == 0:
        return "needs_text_version", "high", "Build current-pages-v1 document_text_versions and extracted-text assets from pages.", language_recovery_plan
    if requires_translation_fallback(row) and int(row.get("english_text_version_count") or 0) == 0:
        return (
            "needs_translation_fallback",
            "normal",
            "Generate an English translation document_text_versions row with text_origin='translation' and machine-review status before English-only drafting uses it.",
            language_recovery_plan,
        )
    if int(row.get("chunk_count") or 0) == 0:
        return "needs_chunk_indexing", "normal", "Build retrieval chunks from pages and load them into Postgres/OpenSearch/Qdrant.", language_recovery_plan
    return "fully_searchable", "none", "No action required.", language_recovery_plan


def fetch_rows(conn: Any) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    query = """
        WITH page_stats AS (
            SELECT
                document_id,
                count(*) AS page_count,
                count(*) FILTER (WHERE length(trim(text)) > 0) AS text_page_count
            FROM pages
            GROUP BY document_id
        ),
        chunk_stats AS (
            SELECT document_id, count(*) AS chunk_count
            FROM retrieval_chunks
            GROUP BY document_id
        ),
        text_version_stats AS (
            SELECT
                document_id,
                count(*) FILTER (WHERE version_label = 'current-pages-v1') AS text_version_count,
                count(*) FILTER (WHERE text_origin = 'source') AS source_text_version_count,
                count(*) FILTER (
                    WHERE lower(COALESCE(language, '')) IN ('english', 'en')
                       OR lower(COALESCE(source_language, '')) IN ('english', 'en')
                ) AS english_text_version_count,
                count(*) FILTER (WHERE text_origin = 'translation') AS translation_text_version_count
            FROM document_text_versions
            GROUP BY document_id
        ),
        original_asset_stats AS (
            SELECT document_id, count(*) AS original_asset_count
            FROM file_assets
            WHERE asset_kind = 'original' AND is_primary = true
            GROUP BY document_id
        )
        SELECT
            d.document_id, d.source_id, d.document_type, d.title, d.year,
            d.language, d.acquisition_status, d.extraction_status, d.local_path,
            d.source_url, d.download_url,
            COALESCE(ps.page_count, 0) AS page_count,
            COALESCE(ps.text_page_count, 0) AS text_page_count,
            COALESCE(tvs.text_version_count, 0) AS text_version_count,
            COALESCE(tvs.source_text_version_count, 0) AS source_text_version_count,
            COALESCE(tvs.english_text_version_count, 0) AS english_text_version_count,
            COALESCE(tvs.translation_text_version_count, 0) AS translation_text_version_count,
            COALESCE(cs.chunk_count, 0) AS chunk_count,
            COALESCE(oas.original_asset_count, 0) AS original_asset_count
        FROM documents d
        LEFT JOIN page_stats ps ON ps.document_id = d.document_id
        LEFT JOIN chunk_stats cs ON cs.document_id = d.document_id
        LEFT JOIN text_version_stats tvs ON tvs.document_id = d.document_id
        LEFT JOIN original_asset_stats oas ON oas.document_id = d.document_id
        ORDER BY d.source_id, d.document_id
    """
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def upsert_missing_source_registry(conn: Any, missing_rows: list[dict[str, Any]]) -> int:
    with conn.cursor() as cursor:
        for row in missing_rows:
            cursor.execute(
                """
                INSERT INTO missing_sources (
                    external_missing_id, document_id, category, title, year, reason,
                    next_action, priority, status, source_id, expected_coverage,
                    known_available_coverage, legal_importance, risk_if_missing,
                    probable_source, last_checked, notes, updated_at
                )
                VALUES (
                    %(external_missing_id)s, %(document_id)s, %(category)s, %(title)s, %(year)s, %(reason)s,
                    %(next_action)s, %(priority)s, 'open', %(source_id)s, %(expected_coverage)s,
                    %(known_available_coverage)s, %(legal_importance)s, %(risk_if_missing)s,
                    %(probable_source)s, now(), %(notes)s, now()
                )
                ON CONFLICT (external_missing_id)
                WHERE external_missing_id IS NOT NULL
                DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    category = EXCLUDED.category,
                    title = EXCLUDED.title,
                    year = EXCLUDED.year,
                    reason = EXCLUDED.reason,
                    next_action = EXCLUDED.next_action,
                    priority = EXCLUDED.priority,
                    status = CASE
                        WHEN missing_sources.status = 'resolved' THEN 'open'
                        ELSE missing_sources.status
                    END,
                    source_id = EXCLUDED.source_id,
                    expected_coverage = EXCLUDED.expected_coverage,
                    known_available_coverage = EXCLUDED.known_available_coverage,
                    legal_importance = EXCLUDED.legal_importance,
                    risk_if_missing = EXCLUDED.risk_if_missing,
                    probable_source = EXCLUDED.probable_source,
                    last_checked = now(),
                    notes = EXCLUDED.notes,
                    updated_at = now()
                """,
                {
                    "external_missing_id": f"unsearchable:{row['document_id']}",
                    "document_id": row["document_id"],
                    "category": "rag_searchability_gap",
                    "title": row.get("title") or row["document_id"],
                    "year": row.get("year"),
                    "reason": row["classification"],
                    "next_action": row["next_action"],
                    "priority": row["recovery_priority"] if row["recovery_priority"] != "none" else "normal",
                    "source_id": row.get("source_id"),
                    "expected_coverage": "All acquired corpus documents should be original-file tracked, extracted, text-versioned, chunked, and searchable.",
                    "known_available_coverage": (
                        f"pages={row.get('page_count', 0)}, text_pages={row.get('text_page_count', 0)}, "
                        f"text_versions={row.get('text_version_count', 0)}, chunks={row.get('chunk_count', 0)}"
                    ),
                    "legal_importance": "Required for high-recall pack-bounded legal retrieval.",
                    "risk_if_missing": "Relevant authority may be invisible to retrieval and strategy drafting.",
                    "probable_source": row.get("source_url") or row.get("download_url") or row.get("local_path") or row.get("source_id"),
                    "notes": row.get("language_recovery_plan"),
                },
            )
    conn.commit()
    return len(missing_rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MISSING_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MISSING_FIELDS})


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    json_path = output_dir / f"rag_searchability_audit_{stamp}.json"
    missing_csv_path = output_dir / f"rag_searchability_missing_{stamp}.csv"

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    synced_missing_sources = 0
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        rows = fetch_rows(conn)

    classified: list[dict[str, Any]] = []
    for row in rows:
        classification, recovery_priority, next_action, language_recovery_plan = classify_document(row)
        classified.append(
            {
                **row,
                "classification": classification,
                "recovery_priority": recovery_priority,
                "next_action": next_action,
                "language_recovery_plan": language_recovery_plan,
            }
        )

    missing_rows = [row for row in classified if row["classification"] != "fully_searchable"]
    if args.sync_missing_source_registry:
        with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
            synced_missing_sources = upsert_missing_source_registry(conn, missing_rows)
    classification_counts = Counter(row["classification"] for row in classified)
    source_gap_counts = Counter((row["source_id"], row["classification"], row["extraction_status"]) for row in missing_rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "document_count": len(classified),
        "fully_searchable_documents": classification_counts.get("fully_searchable", 0),
        "missing_or_incomplete_documents": len(missing_rows),
        "classification_counts": dict(sorted(classification_counts.items())),
        "top_source_gaps": [
            {
                "source_id": source_id,
                "classification": classification,
                "extraction_status": extraction_status,
                "count": count,
            }
            for (source_id, classification, extraction_status), count in source_gap_counts.most_common(30)
        ],
        "synced_missing_sources": synced_missing_sources,
        "missing_csv": str(missing_csv_path.relative_to(PROJECT_ROOT)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(missing_csv_path, missing_rows)
    print(json.dumps({**summary, "audit_json": str(json_path.relative_to(PROJECT_ROOT))}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
