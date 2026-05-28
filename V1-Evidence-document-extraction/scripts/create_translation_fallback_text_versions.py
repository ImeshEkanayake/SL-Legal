#!/usr/bin/env python3
"""Create labelled English translation fallback text versions.

This pipeline preserves the original Sinhala/Tamil source text and adds a
separate machine-translation text version with explicit provenance. It never
overwrites source text, and it stores translated text as an object-storage asset
plus a `document_text_versions` row suitable for retrieval chunking.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from sl_legal_rag.llm.azure_openai import AzureChatClient, load_azure_chat_config  # noqa: E402
from sync_corpus_assets_to_object_storage import (  # noqa: E402
    AssetCandidate,
    StorageConfig,
    TextVersion,
    build_s3_client,
    candidate_from_db_row,
    ensure_bucket,
    translated_text_storage_key,
    upload_bytes_if_needed,
    upsert_digest,
    upsert_file_asset,
    upsert_text_version,
)


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
SUPPORTED_SOURCE_LANGUAGES = {"sinhala", "sin", "si", "tamil", "tam", "ta"}
RUN_VERSION = "2026-05-26"


@dataclass
class TranslationSummary:
    candidate_count: int = 0
    processed_count: int = 0
    translated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    source_chars: int = 0
    translated_chars: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: dict[str, Any]) -> None:
        self.processed_count += 1
        status = str(result["status"])
        if self.status_counts is None:
            self.status_counts = {}
        self.status_counts[status] = self.status_counts.get(status, 0) + 1
        if status == "translated":
            self.translated_count += 1
            self.source_chars += int(result.get("source_char_count") or 0)
            self.translated_chars += int(result.get("translated_char_count") or 0)
        elif status.startswith("skipped") or status in {"planned", "missing_source_asset"}:
            self.skipped_count += 1
        elif status == "error":
            self.error_count += 1
        if self.results_preview is None:
            self.results_preview = []
        if len(self.results_preview) < 20:
            self.results_preview.append(result)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Call the translation model and write database rows.")
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--provider", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PROVIDER", "minio"))
    parser.add_argument("--endpoint-url", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"))
    parser.add_argument("--bucket", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_BUCKET", "sl-legal-corpus"))
    parser.add_argument("--region", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_REGION", "us-east-1"))
    parser.add_argument("--access-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ACCESS_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_USER", "sl_legal_minio"))
    parser.add_argument("--secret-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_SECRET_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_PASSWORD", "sl_legal_minio_dev"))
    parser.add_argument("--prefix", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PREFIX", "corpus"))
    parser.add_argument("--azure-env-file", default=str(PROJECT_ROOT / ".env.azure-openai"))
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--language", action="append", help="Restrict to Sinhala/Tamil aliases. Defaults to both.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum documents to process in this batch. Use 0 for all queued candidates.")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--report-path", help="Optional JSONL path for per-document results.")
    parser.add_argument("--skip-upload", action="store_true", help="Record database rows without uploading translated text assets.")
    parser.add_argument("--force", action="store_true", help="Regenerate even when a current English translation fallback exists.")
    parser.add_argument("--target-language", default="English")
    parser.add_argument("--translation-provider", default="azure_openai")
    parser.add_argument("--translation-review-status", default="machine_draft", choices=["machine_draft", "needs_legal_review", "lawyer_approved"])
    parser.add_argument("--max-chunk-chars", type=int, default=12000)
    parser.add_argument("--max-completion-tokens", type=int, default=8192)
    parser.add_argument("--sleep-between-calls", type=float, default=0.0)
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.max_chunk_chars < 1000:
        parser.error("--max-chunk-chars must be at least 1000")
    if args.max_completion_tokens < 512:
        parser.error("--max-completion-tokens must be at least 512")
    if args.sleep_between_calls < 0:
        parser.error("--sleep-between-calls must be zero or greater")
    args.document_ids_filter = load_document_ids(args)
    args.language_filter = normalize_language_filter(args.language)
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


def normalize_language_filter(values: list[str] | None) -> list[str]:
    if not values:
        return sorted(SUPPORTED_SOURCE_LANGUAGES)
    normalized = sorted({value.strip().lower() for value in values if value.strip()})
    unsupported = sorted(set(normalized) - SUPPORTED_SOURCE_LANGUAGES)
    if unsupported:
        raise SystemExit(f"Unsupported translation source languages: {', '.join(unsupported)}")
    return normalized


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def build_storage_config(args: argparse.Namespace) -> StorageConfig:
    return StorageConfig(
        provider=args.provider,
        endpoint_url=args.endpoint_url,
        bucket=args.bucket,
        region=args.region,
        access_key=args.access_key,
        secret_key=args.secret_key,
        prefix=args.prefix.strip("/"),
    )


def default_ingestion_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"translation_fallback_text_versions_{stamp}"


def source_label(args: argparse.Namespace) -> str:
    return ",".join(sorted(args.source_id)) if args.source_id else "ALL"


def start_ingestion_run(conn: Any, *, args: argparse.Namespace, config: StorageConfig, ingestion_run_id: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (
                ingestion_run_id, source_id, pipeline_name, pipeline_version,
                status, corpus_root, config
            )
            VALUES (
                %(ingestion_run_id)s, %(source_id)s, 'translation_fallback_text_versions',
                %(pipeline_version)s, 'running', %(corpus_root)s, CAST(%(config)s AS jsonb)
            )
            ON CONFLICT (ingestion_run_id) DO UPDATE SET
                status = 'running',
                completed_at = NULL,
                error = NULL,
                updated_at = now(),
                config = EXCLUDED.config
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "source_id": source_label(args),
                "pipeline_version": RUN_VERSION,
                "corpus_root": str(PROJECT_ROOT / "data" / "raw"),
                "config": json.dumps(
                    {
                        "provider": config.provider,
                        "bucket": config.bucket,
                        "prefix": config.prefix,
                        "limit": args.limit,
                        "batch_size": args.batch_size,
                        "language_filter": args.language_filter,
                        "force": args.force,
                        "target_language": args.target_language,
                        "translation_provider": args.translation_provider,
                        "translation_review_status": args.translation_review_status,
                        "skip_upload": args.skip_upload,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: TranslationSummary) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET status = %(status)s,
                completed_at = now(),
                document_count = %(document_count)s,
                error_count = %(error_count)s,
                output = CAST(%(output)s AS jsonb),
                updated_at = now()
            WHERE ingestion_run_id = %(ingestion_run_id)s
            """,
            {
                "status": "failed" if summary.error_count else "complete",
                "document_count": summary.processed_count,
                "error_count": summary.error_count,
                "ingestion_run_id": ingestion_run_id,
                "output": json.dumps(
                    {
                        "candidate_count": summary.candidate_count,
                        "processed_count": summary.processed_count,
                        "translated_count": summary.translated_count,
                        "skipped_count": summary.skipped_count,
                        "source_chars": summary.source_chars,
                        "translated_chars": summary.translated_chars,
                        "status_counts": summary.status_counts or {},
                    },
                    ensure_ascii=False,
                ),
            },
        )


def open_report(path_value: str | None) -> TextIO | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def write_report(report: TextIO | None, result: dict[str, Any]) -> None:
    if report is None:
        return
    report.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    report.flush()


def print_progress(summary: TranslationSummary, *, final: bool = False) -> None:
    print(
        json.dumps(
            {
                "event": "final" if final else "progress",
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "translated_count": summary.translated_count,
                "error_count": summary.error_count,
                "status_counts": summary.status_counts or {},
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def candidate_filter_sql(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    clauses = [
        "d.acquisition_status = 'downloaded'",
        "lower(coalesce(d.language, '')) = ANY(%(languages)s)",
        "length(btrim(source_version.full_text)) > 0",
    ]
    params: dict[str, Any] = {"languages": args.language_filter}
    if args.document_ids_filter:
        clauses.append("d.document_id = ANY(%(document_ids)s)")
        params["document_ids"] = sorted(args.document_ids_filter)
    if args.source_id:
        clauses.append("d.source_id = ANY(%(source_ids)s)")
        params["source_ids"] = sorted(args.source_id)
    if not args.force:
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM document_text_versions existing_translation
                WHERE existing_translation.document_id = d.document_id
                  AND existing_translation.text_origin = 'translation'
                  AND lower(coalesce(existing_translation.language, '')) IN ('english', 'en')
                  AND coalesce(existing_translation.translation_review_status, '') NOT IN ('rejected', 'superseded_by_official')
            )
            """
        )
    return " AND ".join(f"({clause})" for clause in clauses), params


def candidate_count(conn: Any, args: argparse.Namespace) -> int:
    where_sql, params = candidate_filter_sql(args)
    query = f"""
        SELECT count(*)
        FROM documents d
        JOIN LATERAL (
            SELECT dtv.full_text
            FROM document_text_versions dtv
            WHERE dtv.document_id = d.document_id
              AND dtv.text_origin = 'source'
            ORDER BY
                CASE WHEN dtv.version_label = 'current-pages-v1' THEN 0 ELSE 1 END,
                dtv.created_at DESC,
                dtv.text_version_id DESC
            LIMIT 1
        ) source_version ON true
        WHERE {where_sql}
    """
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        return int(cursor.fetchone()[0])


def stream_candidates(conn: Any, args: argparse.Namespace):
    from psycopg.rows import dict_row

    where_sql, params = candidate_filter_sql(args)
    limit_sql = "LIMIT %(limit)s" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    query = f"""
        SELECT
            d.document_id, d.source_id, d.source_document_id, d.document_type,
            d.title, d.year, d.number, d.document_date, d.language,
            d.source_url, d.download_url, d.local_path, d.file_hash,
            d.acquisition_status, d.extraction_status, d.text_quality_score,
            d.legal_status, d.notes, d.primary_file_asset_id,
            source_version.text_version_id AS source_text_version_id,
            source_version.source_asset_id,
            source_version.full_text AS source_full_text,
            source_version.page_count AS source_page_count,
            source_version.text_hash AS source_text_hash
        FROM documents d
        JOIN LATERAL (
            SELECT
                dtv.text_version_id, dtv.source_asset_id, dtv.full_text,
                dtv.page_count, dtv.text_hash, dtv.created_at
            FROM document_text_versions dtv
            WHERE dtv.document_id = d.document_id
              AND dtv.text_origin = 'source'
            ORDER BY
                CASE WHEN dtv.version_label = 'current-pages-v1' THEN 0 ELSE 1 END,
                dtv.created_at DESC,
                dtv.text_version_id DESC
            LIMIT 1
        ) source_version ON true
        WHERE {where_sql}
        ORDER BY d.source_id, d.year NULLS LAST, d.document_id
        {limit_sql}
    """
    with conn.cursor(name="translation_candidates", row_factory=dict_row) as cursor:
        cursor.itersize = args.batch_size
        cursor.execute(query, params)
        for row in cursor:
            yield dict(row)


def split_text_for_translation(text: str, max_chunk_chars: int) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = normalized.split("\n\n")
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > max_chunk_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), max_chunk_chars):
                chunks.append(paragraph[start : start + max_chunk_chars])
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chunk_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def build_translation_messages(*, source_language: str, target_language: str, chunk_text: str, chunk_index: int, chunk_count: int) -> list[dict[str, str]]:
    system = (
        "You are a legal translation engine for Sri Lankan legal materials. "
        "Translate faithfully and completely. Preserve section numbers, dates, Gazette numbers, case names, citations, "
        "party names, headings, tables, lists, defined terms, and legal qualifiers. Do not summarize, omit, modernize, "
        "or add commentary. If a token cannot be translated confidently, keep the original token in brackets."
    )
    user = (
        f"Translate this {source_language} legal document chunk into {target_language}.\n"
        f"Chunk {chunk_index} of {chunk_count}. Return only the translated text.\n\n"
        f"{chunk_text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("Azure OpenAI response did not include choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Azure OpenAI response was empty")
    return content


def translate_text(
    *,
    client: AzureChatClient,
    source_language: str,
    target_language: str,
    text: str,
    max_chunk_chars: int,
    max_completion_tokens: int,
    sleep_between_calls: float,
) -> tuple[str, int]:
    chunks = split_text_for_translation(text, max_chunk_chars)
    translated_chunks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        response = client.complete(
            messages=build_translation_messages(
                source_language=source_language,
                target_language=target_language,
                chunk_text=chunk,
                chunk_index=index,
                chunk_count=len(chunks),
            ),
            max_completion_tokens=max_completion_tokens,
        )
        translated_chunks.append(extract_message_content(response))
        if sleep_between_calls and index < len(chunks):
            time.sleep(sleep_between_calls)
    return "\n\n".join(translated_chunks).strip(), len(chunks)


def build_translation_text_version(
    *,
    row: dict[str, Any],
    translated_text: str,
    target_language: str,
    translation_provider: str,
    translation_model: str,
    translation_review_status: str,
    chunk_count: int,
) -> TextVersion:
    text_hash = hashlib.sha256(translated_text.encode("utf-8")).hexdigest()
    source_language = str(row.get("language") or "").strip()
    return TextVersion(
        full_text=translated_text,
        page_count=int(row.get("source_page_count") or 0),
        char_count=len(translated_text),
        text_hash=text_hash,
        extraction_method="machine_translation",
        ocr_confidence_mean=None,
        ocr_confidence_band=None,
        quality_flags=[
            "translated_text_fallback",
            "machine_translation_unreviewed",
            "replace_when_official_english_available",
        ],
        text_origin="translation",
        target_language=target_language,
        source_language=source_language,
        translated_from_language=source_language,
        translation_provider=translation_provider,
        translation_model=translation_model,
        translation_review_status=translation_review_status,
        source_text_version_id=str(row.get("source_text_version_id") or ""),
    )


def record_translation_event(
    conn: Any,
    *,
    ingestion_run_id: str,
    candidate: AssetCandidate,
    result: dict[str, Any],
) -> None:
    status = str(result["status"])
    event_status = "indexed" if status == "translated" else "skipped" if status.startswith("skipped") or status == "planned" else "failed"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document_ingestion_events (
                ingestion_run_id, document_id, source_id, source_document_id,
                local_path, file_hash, stage, status, text_quality_score,
                error_code, error_message, metadata
            )
            VALUES (
                %(ingestion_run_id)s, %(document_id)s, %(source_id)s, %(source_document_id)s,
                %(local_path)s, %(file_hash)s, 'translation_fallback_text_versions',
                %(status)s, %(text_quality_score)s, %(error_code)s, %(error_message)s,
                CAST(%(metadata)s AS jsonb)
            )
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "document_id": candidate.document_id,
                "source_id": candidate.source_id,
                "source_document_id": candidate.source_document_id,
                "local_path": candidate.local_path,
                "file_hash": candidate.file_hash,
                "status": event_status,
                "text_quality_score": candidate.text_quality_score,
                "error_code": status if event_status == "failed" else None,
                "error_message": result.get("error_message"),
                "metadata": json.dumps(result, ensure_ascii=False, default=str),
            },
        )


def process_candidate(
    conn: Any,
    *,
    row: dict[str, Any],
    config: StorageConfig,
    client: AzureChatClient | None,
    model_name: str,
    args: argparse.Namespace,
    ingestion_run_id: str,
    object_client: Any,
) -> dict[str, Any]:
    candidate = candidate_from_db_row(row)
    source_asset_id = str(row.get("source_asset_id") or row.get("primary_file_asset_id") or "")
    source_text = str(row.get("source_full_text") or "").strip()
    result = {
        "document_id": candidate.document_id,
        "source_id": candidate.source_id,
        "language": candidate.language,
        "source_text_version_id": row.get("source_text_version_id"),
        "source_char_count": len(source_text),
        "status": "planned",
    }
    if not source_asset_id:
        return {**result, "status": "missing_source_asset"}
    if not source_text:
        return {**result, "status": "skipped_empty_source_text"}
    if not args.execute:
        return result
    if client is None:
        raise RuntimeError("Translation client is required in execute mode")

    translated_text, chunk_count = translate_text(
        client=client,
        source_language=candidate.language,
        target_language=args.target_language,
        text=source_text,
        max_chunk_chars=args.max_chunk_chars,
        max_completion_tokens=args.max_completion_tokens,
        sleep_between_calls=args.sleep_between_calls,
    )
    if not translated_text:
        return {**result, "status": "error", "error_message": "translation returned empty text"}
    text_version = build_translation_text_version(
        row=row,
        translated_text=translated_text,
        target_language=args.target_language,
        translation_provider=args.translation_provider,
        translation_model=model_name,
        translation_review_status=args.translation_review_status,
        chunk_count=chunk_count,
    )
    payload = text_version.full_text.encode("utf-8")
    key = translated_text_storage_key(config, candidate, args.target_language, text_version.text_hash)
    etag = ""
    if not args.skip_upload:
        etag = upload_bytes_if_needed(
            object_client,
            bucket=config.bucket,
            key=key,
            payload=payload,
            content_type="text/plain; charset=utf-8",
            sha256=text_version.text_hash,
        )
    text_asset_id = upsert_file_asset(
        conn,
        candidate=candidate,
        config=config,
        asset_kind="translated_text",
        key=key,
        content_type="text/plain; charset=utf-8",
        byte_size=len(payload),
        sha256=text_version.text_hash,
        etag=etag,
        source_local_path="document_text_versions",
        is_primary=False,
        ingestion_run_id=ingestion_run_id,
        metadata={
            "source_text_version_id": row.get("source_text_version_id"),
            "source_text_hash": row.get("source_text_hash"),
            "target_language": args.target_language,
            "translation_provider": args.translation_provider,
            "translation_model": model_name,
            "translation_review_status": args.translation_review_status,
            "translation_chunk_count": chunk_count,
        },
    )
    text_version_id = upsert_text_version(
        conn,
        candidate=candidate,
        source_asset_id=source_asset_id,
        text_asset_id=text_asset_id,
        text_version=text_version,
        ingestion_run_id=ingestion_run_id,
    )
    digest_id = upsert_digest(
        conn,
        document_id=candidate.document_id,
        digest_type="translated_full_text",
        digest_value=text_version.text_hash,
        byte_size=len(payload),
        page_count=text_version.page_count,
        file_asset_id=text_asset_id,
        text_version_id=text_version_id,
        metadata={
            "source_text_version_id": row.get("source_text_version_id"),
            "source_text_hash": row.get("source_text_hash"),
            "target_language": args.target_language,
            "translation_provider": args.translation_provider,
            "translation_model": model_name,
            "translation_review_status": args.translation_review_status,
            "translation_chunk_count": chunk_count,
        },
    )
    return {
        **result,
        "status": "translated",
        "translated_char_count": len(translated_text),
        "translation_chunk_count": chunk_count,
        "text_hash": text_version.text_hash,
        "text_asset_id": text_asset_id,
        "text_version_id": text_version_id,
        "digest_id": digest_id,
        "storage_key": key,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    config = build_storage_config(args)
    azure_config = None
    translation_client = None
    if args.execute:
        azure_config = load_azure_chat_config(args.azure_env_file)
        translation_client = AzureChatClient(azure_config)
    model_name = azure_config.deployment_name if azure_config is not None else "dry_run"
    object_client = None
    if args.execute and not args.skip_upload:
        object_client = build_s3_client(config)
        ensure_bucket(object_client, config.bucket)

    ingestion_run_id = default_ingestion_run_id()
    report_cm = open_report(args.report_path) if args.report_path else nullcontext(None)
    summary = TranslationSummary()

    with (
        psycopg.connect(normalize_psycopg_dsn(args.dsn)) as read_conn,
        psycopg.connect(normalize_psycopg_dsn(args.dsn)) as write_conn,
        report_cm as report,
    ):
        summary.candidate_count = candidate_count(read_conn, args)
        if args.execute:
            start_ingestion_run(write_conn, args=args, config=config, ingestion_run_id=ingestion_run_id)
            write_conn.commit()

        for row in stream_candidates(read_conn, args):
            candidate = candidate_from_db_row(row)
            try:
                result = process_candidate(
                    write_conn,
                    row=row,
                    config=config,
                    client=translation_client,
                    model_name=model_name,
                    args=args,
                    ingestion_run_id=ingestion_run_id,
                    object_client=object_client,
                )
            except Exception as exc:
                result = {
                    "document_id": candidate.document_id,
                    "source_id": candidate.source_id,
                    "language": candidate.language,
                    "source_text_version_id": row.get("source_text_version_id"),
                    "status": "error",
                    "error_message": str(exc),
                }
            if args.execute:
                record_translation_event(write_conn, ingestion_run_id=ingestion_run_id, candidate=candidate, result=result)
                write_conn.commit()
            summary.add(result)
            write_report(report, result)
            if args.progress_every and summary.processed_count % args.progress_every == 0:
                print_progress(summary)

        if args.execute:
            finish_ingestion_run(write_conn, ingestion_run_id=ingestion_run_id, summary=summary)
            write_conn.commit()

    print_progress(summary, final=True)
    print(
        json.dumps(
            {
                "ingestion_run_id": ingestion_run_id,
                "candidate_count": summary.candidate_count,
                "processed_count": summary.processed_count,
                "translated_count": summary.translated_count,
                "skipped_count": summary.skipped_count,
                "error_count": summary.error_count,
                "source_chars": summary.source_chars,
                "translated_chars": summary.translated_chars,
                "status_counts": summary.status_counts or {},
                "results_preview": summary.results_preview or [],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 1 if summary.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
