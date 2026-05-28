#!/usr/bin/env python3
"""Sync corpus originals and extracted text into S3-compatible object storage."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import csv
import hashlib
import json
import mimetypes
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.data_registry import normalize_document_row  # noqa: E402


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
SLUG_RE = re.compile(r"[^a-zA-Z0-9._=-]+")


@dataclass(frozen=True)
class StorageConfig:
    provider: str
    endpoint_url: str
    bucket: str
    region: str
    access_key: str
    secret_key: str
    prefix: str

    @property
    def public_uri_prefix(self) -> str:
        return f"{self.provider}://{self.bucket}"


@dataclass(frozen=True)
class AssetCandidate:
    document_id: str
    source_id: str
    source_document_id: str
    document_type: str
    title: str
    year: int | None
    number: str
    document_date: date | None
    language: str
    source_url: str
    download_url: str
    local_path: str
    file_hash: str
    acquisition_status: str
    extraction_status: str
    text_quality_score: float | None
    legal_status: str
    notes: str


@dataclass(frozen=True)
class LocalFileDigest:
    path: Path
    sha256: str
    byte_size: int
    content_type: str


@dataclass(frozen=True)
class TextVersion:
    full_text: str
    page_count: int
    char_count: int
    text_hash: str
    extraction_method: str
    ocr_confidence_mean: float | None
    ocr_confidence_band: str | None
    quality_flags: list[str]
    text_origin: str = "source"
    target_language: str | None = None
    source_language: str | None = None
    translated_from_language: str | None = None
    translation_provider: str | None = None
    translation_model: str | None = None
    translation_review_status: str | None = "not_applicable"
    source_text_version_id: str | None = None
    official_replacement_document_id: str | None = None
    superseded_by_text_version_id: str | None = None


@dataclass
class SyncSummary:
    candidate_count: int = 0
    processed_count: int = 0
    error_count: int = 0
    total_bytes: int = 0
    status_counts: dict[str, int] | None = None
    results_preview: list[dict[str, Any]] | None = None

    def add(self, result: dict[str, Any]) -> None:
        self.processed_count += 1
        status = str(result["status"])
        if self.status_counts is None:
            self.status_counts = {}
        self.status_counts[status] = self.status_counts.get(status, 0) + 1
        if status in {"missing_local_file", "hash_mismatch"}:
            self.error_count += 1
        self.total_bytes += int(result.get("byte_size") or 0)
        if self.results_preview is None:
            self.results_preview = []
        if len(self.results_preview) < 20:
            self.results_preview.append(result)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Write to object storage and PostgreSQL.")
    parser.add_argument("--scope", choices=["postgres", "manifest"], default="postgres")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--provider", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PROVIDER", "minio"))
    parser.add_argument("--endpoint-url", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"))
    parser.add_argument("--bucket", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_BUCKET", "sl-legal-corpus"))
    parser.add_argument("--region", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_REGION", "us-east-1"))
    parser.add_argument("--access-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_ACCESS_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_USER", "sl_legal_minio"))
    parser.add_argument("--secret-key", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_SECRET_KEY") or os.getenv("SL_LEGAL_MINIO_ROOT_PASSWORD", "sl_legal_minio_dev"))
    parser.add_argument("--prefix", default=os.getenv("SL_LEGAL_OBJECT_STORAGE_PREFIX", "corpus"))
    parser.add_argument("--document-id", action="append")
    parser.add_argument("--document-id-file", action="append")
    parser.add_argument("--source-id", action="append")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-to-sync", type=int, default=0, help="Stop after this many non-skipped candidates.")
    parser.add_argument("--batch-size", type=int, default=500, help="Commit every N records when executing.")
    parser.add_argument("--progress-every", type=int, default=250, help="Print progress JSON every N processed records.")
    parser.add_argument("--report-path", help="Optional JSONL path for per-document sync results.")
    parser.add_argument("--skip-existing-assets", action="store_true", help="Skip documents that already have a primary object-storage asset.")
    parser.add_argument("--include-text-versions", action="store_true")
    parser.add_argument("--skip-upload", action="store_true", help="Record database rows without uploading objects.")
    parser.add_argument("--allow-hash-mismatch", action="store_true")
    parser.add_argument("--ingestion-run-id", help="Optional existing ingestion run ID to use for traceability.")
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.progress_every < 0:
        parser.error("--progress-every must be zero or greater")
    if args.max_to_sync < 0:
        parser.error("--max-to-sync must be zero or greater")
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


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def stable_id(prefix: str, *parts: object) -> str:
    raw = "::".join("" if part is None else str(part) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]}"


def slug(value: str) -> str:
    normalized = SLUG_RE.sub("_", value.strip()).strip("._")
    return normalized or "unknown"


def resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_file(path) if path.exists() else ""


def normalize_hash(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.split(":", 1)[1]
    return normalized


def local_file_digest(path: Path) -> LocalFileDigest:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return LocalFileDigest(
        path=path,
        sha256=sha256_file(path),
        byte_size=path.stat().st_size,
        content_type=content_type,
    )


def storage_key(config: StorageConfig, candidate: AssetCandidate, digest: str, suffix: str, *, kind: str) -> str:
    return "/".join(
        part.strip("/")
        for part in (
            config.prefix,
            kind,
            slug(candidate.source_id.lower()),
            slug(candidate.document_id),
            f"{digest}{suffix.lower()}",
        )
        if part.strip("/")
    )


def text_storage_key(config: StorageConfig, candidate: AssetCandidate, text_hash: str) -> str:
    return "/".join(
        part.strip("/")
        for part in (
            config.prefix,
            "text",
            slug(candidate.source_id.lower()),
            slug(candidate.document_id),
            f"full_text_{text_hash}.txt",
        )
        if part.strip("/")
    )


def translated_text_storage_key(config: StorageConfig, candidate: AssetCandidate, target_language: str, text_hash: str) -> str:
    return "/".join(
        part.strip("/")
        for part in (
            config.prefix,
            "translations",
            slug(candidate.source_id.lower()),
            slug(candidate.document_id),
            slug(target_language.lower()),
            f"translated_text_{text_hash}.txt",
        )
        if part.strip("/")
    )


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def resolve_manifest_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def candidate_from_normalized(row: dict[str, Any]) -> AssetCandidate:
    return AssetCandidate(
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
        text_quality_score=row["text_quality_score"],
        legal_status=row["legal_status"],
        notes=row["notes"],
    )


def candidate_from_db_row(row: dict[str, Any]) -> AssetCandidate:
    return AssetCandidate(
        document_id=str(row.get("document_id") or ""),
        source_id=str(row.get("source_id") or ""),
        source_document_id=str(row.get("source_document_id") or ""),
        document_type=str(row.get("document_type") or ""),
        title=str(row.get("title") or ""),
        year=row.get("year"),
        number=str(row.get("number") or ""),
        document_date=row.get("document_date"),
        language=str(row.get("language") or ""),
        source_url=str(row.get("source_url") or ""),
        download_url=str(row.get("download_url") or ""),
        local_path=str(row.get("local_path") or ""),
        file_hash=str(row.get("file_hash") or ""),
        acquisition_status=str(row.get("acquisition_status") or ""),
        extraction_status=str(row.get("extraction_status") or ""),
        text_quality_score=float(row["text_quality_score"]) if row.get("text_quality_score") is not None else None,
        legal_status=str(row.get("legal_status") or ""),
        notes=str(row.get("notes") or ""),
    )


def filter_candidates(candidates: Iterable[AssetCandidate], args: argparse.Namespace) -> list[AssetCandidate]:
    source_ids = set(args.source_id or [])
    document_ids = args.document_ids_filter
    filtered: list[AssetCandidate] = []
    for candidate in candidates:
        if candidate.acquisition_status != "downloaded":
            continue
        if not candidate.local_path:
            continue
        if source_ids and candidate.source_id not in source_ids:
            continue
        if document_ids and candidate.document_id not in document_ids:
            continue
        filtered.append(candidate)
    if args.limit:
        return filtered[: args.limit]
    return filtered


def postgres_candidates(conn: Any, args: argparse.Namespace) -> list[AssetCandidate]:
    from psycopg.rows import dict_row

    query = """
        SELECT
            document_id, source_id, source_document_id, document_type, title,
            year, number, document_date, language, source_url, download_url,
            local_path, file_hash, acquisition_status, extraction_status,
            text_quality_score, legal_status, notes
        FROM documents
        ORDER BY source_id, document_id
    """
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        return filter_candidates((candidate_from_db_row(dict(row)) for row in cursor.fetchall()), args)


def manifest_candidates(args: argparse.Namespace) -> list[AssetCandidate]:
    path = resolve_manifest_path(args.manifest)
    rows = [candidate_from_normalized(normalize_document_row(row)) for row in read_manifest_rows(path)]
    return filter_candidates(rows, args)


def ensure_document(conn: Any, candidate: AssetCandidate, ingestion_run_id: str | None) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO documents (
                document_id, source_id, source_document_id, document_type, title,
                year, number, document_date, language, source_url, download_url,
                local_path, file_hash, acquisition_status, extraction_status,
                text_quality_score, legal_status, notes, current_ingestion_run_id,
                last_ingested_at
            )
            VALUES (
                %(document_id)s, %(source_id)s, %(source_document_id)s, %(document_type)s, %(title)s,
                %(year)s, %(number)s, %(document_date)s, %(language)s, %(source_url)s, %(download_url)s,
                %(local_path)s, %(file_hash)s, %(acquisition_status)s, %(extraction_status)s,
                %(text_quality_score)s, %(legal_status)s, %(notes)s,
                %(ingestion_run_id)s, now()
            )
            ON CONFLICT (document_id) DO UPDATE SET
                source_id = EXCLUDED.source_id,
                source_document_id = EXCLUDED.source_document_id,
                document_type = EXCLUDED.document_type,
                title = EXCLUDED.title,
                year = EXCLUDED.year,
                number = EXCLUDED.number,
                document_date = EXCLUDED.document_date,
                language = EXCLUDED.language,
                source_url = EXCLUDED.source_url,
                download_url = EXCLUDED.download_url,
                local_path = EXCLUDED.local_path,
                file_hash = EXCLUDED.file_hash,
                acquisition_status = EXCLUDED.acquisition_status,
                extraction_status = EXCLUDED.extraction_status,
                text_quality_score = EXCLUDED.text_quality_score,
                legal_status = EXCLUDED.legal_status,
                notes = EXCLUDED.notes,
                current_ingestion_run_id = EXCLUDED.current_ingestion_run_id,
                last_ingested_at = now(),
                updated_at = now()
            """,
            {**candidate.__dict__, "ingestion_run_id": ingestion_run_id},
        )


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


def build_s3_client(config: StorageConfig):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise SystemExit("Missing dependency: install boto3 before syncing object storage assets.") from exc

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name=config.region,
        config=Config(signature_version="s3v4"),
    )


def source_label(args: argparse.Namespace) -> str:
    if args.source_id:
        return ",".join(sorted(args.source_id))
    return "ALL"


def default_ingestion_run_id(args: argparse.Namespace) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = slug(args.scope)
    source = slug(source_label(args).lower())
    return f"object_asset_sync_{scope}_{source}_{timestamp}"


def manifest_hash(args: argparse.Namespace) -> str | None:
    if args.scope != "manifest":
        return None
    return sha256_path(resolve_manifest_path(args.manifest))


def start_ingestion_run(
    conn: Any,
    *,
    args: argparse.Namespace,
    config: StorageConfig,
    ingestion_run_id: str,
    input_manifest_hash: str | None,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (
                ingestion_run_id, source_id, pipeline_name, pipeline_version,
                status, manifest_path, corpus_root, input_manifest_hash, config
            )
            VALUES (
                %(ingestion_run_id)s, %(source_id)s, 'object_storage_asset_sync',
                '2026-05-26', 'running', %(manifest_path)s, %(corpus_root)s,
                %(input_manifest_hash)s, CAST(%(config)s AS jsonb)
            )
            ON CONFLICT (ingestion_run_id) DO UPDATE SET
                status = 'running',
                error = NULL,
                completed_at = NULL,
                updated_at = now(),
                config = EXCLUDED.config
            """,
            {
                "ingestion_run_id": ingestion_run_id,
                "source_id": source_label(args),
                "manifest_path": str(resolve_manifest_path(args.manifest)) if args.scope == "manifest" else None,
                "corpus_root": str(PROJECT_ROOT / "data" / "raw"),
                "input_manifest_hash": input_manifest_hash,
                "config": json.dumps(
                    {
                        "scope": args.scope,
                        "bucket": config.bucket,
                        "provider": config.provider,
                        "prefix": config.prefix,
                        "include_text_versions": args.include_text_versions,
                        "skip_upload": args.skip_upload,
                        "skip_existing_assets": args.skip_existing_assets,
                        "batch_size": args.batch_size,
                        "limit": args.limit,
                        "max_to_sync": args.max_to_sync,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def finish_ingestion_run(conn: Any, *, ingestion_run_id: str, summary: SyncSummary) -> None:
    status = "failed" if summary.error_count else "complete"
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
                "status": status,
                "document_count": summary.processed_count,
                "error_count": summary.error_count,
                "ingestion_run_id": ingestion_run_id,
                "output": json.dumps(
                    {
                        "candidate_count": summary.candidate_count,
                        "processed_count": summary.processed_count,
                        "total_bytes": summary.total_bytes,
                        "status_counts": summary.status_counts or {},
                    },
                    ensure_ascii=False,
                ),
            },
        )


def record_ingestion_event(conn: Any, *, ingestion_run_id: str, candidate: AssetCandidate, result: dict[str, Any]) -> None:
    status = str(result["status"])
    event_status = "indexed"
    if status == "skipped_existing":
        event_status = "skipped"
    elif status in {"missing_local_file", "hash_mismatch"}:
        event_status = "failed"
    elif status == "planned":
        event_status = "queued"
    error_message = None
    if event_status == "failed":
        error_message = str(result.get("local_path") or result.get("expected") or status)
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
                %(local_path)s, %(file_hash)s, 'object_storage_sync', %(status)s,
                %(text_quality_score)s, %(error_code)s, %(error_message)s,
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
                "error_message": error_message,
                "metadata": json.dumps(result, ensure_ascii=False, default=str),
            },
        )


def ensure_bucket(client: Any, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def upload_bytes_if_needed(client: Any, *, bucket: str, key: str, payload: bytes, content_type: str, sha256: str) -> str:
    try:
        existing = client.head_object(Bucket=bucket, Key=key)
        if existing.get("Metadata", {}).get("sha256") == sha256:
            return str(existing.get("ETag", "")).strip('"')
    except Exception:
        pass
    response = client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType=content_type,
        Metadata={"sha256": sha256},
    )
    return str(response.get("ETag", "")).strip('"')


def upload_file_if_needed(client: Any, *, bucket: str, key: str, digest: LocalFileDigest) -> str:
    try:
        existing = client.head_object(Bucket=bucket, Key=key)
        if existing.get("Metadata", {}).get("sha256") == digest.sha256:
            return str(existing.get("ETag", "")).strip('"')
    except Exception:
        pass
    with digest.path.open("rb") as handle:
        response = client.put_object(
            Bucket=bucket,
            Key=key,
            Body=handle,
            ContentType=digest.content_type,
            Metadata={"sha256": digest.sha256},
        )
    return str(response.get("ETag", "")).strip('"')


def object_uri(config: StorageConfig, key: str) -> str:
    return f"{config.public_uri_prefix}/{key}"


def upsert_file_asset(
    conn: Any,
    *,
    candidate: AssetCandidate,
    config: StorageConfig,
    asset_kind: str,
    key: str,
    content_type: str,
    byte_size: int,
    sha256: str,
    etag: str,
    source_local_path: str,
    is_primary: bool,
    ingestion_run_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    asset_id = stable_id("asset", config.provider, config.bucket, key)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO file_assets (
                asset_id, document_id, asset_kind, storage_provider,
                storage_bucket, storage_key, storage_region, endpoint_url,
                content_type, byte_size, sha256, etag, source_local_path,
                source_url, is_primary, created_by_ingestion_run_id, metadata
            )
            VALUES (
                %(asset_id)s, %(document_id)s, %(asset_kind)s, %(storage_provider)s,
                %(storage_bucket)s, %(storage_key)s, %(storage_region)s, %(endpoint_url)s,
                %(content_type)s, %(byte_size)s, %(sha256)s, %(etag)s, %(source_local_path)s,
                %(source_url)s, %(is_primary)s, %(ingestion_run_id)s, CAST(%(metadata)s AS jsonb)
            )
            ON CONFLICT (storage_provider, storage_bucket, storage_key) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                asset_kind = EXCLUDED.asset_kind,
                storage_region = EXCLUDED.storage_region,
                endpoint_url = EXCLUDED.endpoint_url,
                content_type = EXCLUDED.content_type,
                byte_size = EXCLUDED.byte_size,
                sha256 = EXCLUDED.sha256,
                etag = EXCLUDED.etag,
                source_local_path = EXCLUDED.source_local_path,
                source_url = EXCLUDED.source_url,
                is_primary = EXCLUDED.is_primary,
                created_by_ingestion_run_id = EXCLUDED.created_by_ingestion_run_id,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING asset_id
            """,
            {
                "asset_id": asset_id,
                "document_id": candidate.document_id,
                "asset_kind": asset_kind,
                "storage_provider": config.provider,
                "storage_bucket": config.bucket,
                "storage_key": key,
                "storage_region": config.region,
                "endpoint_url": config.endpoint_url,
                "content_type": content_type,
                "byte_size": byte_size,
                "sha256": sha256,
                "etag": etag,
                "source_local_path": source_local_path,
                "source_url": candidate.source_url,
                "is_primary": is_primary,
                "ingestion_run_id": ingestion_run_id,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False, default=str),
            },
        )
        stored_asset_id = cursor.fetchone()[0]
        if is_primary:
            cursor.execute(
                """
                UPDATE documents
                SET object_storage_provider = %(provider)s,
                    object_storage_bucket = %(bucket)s,
                    object_storage_key = %(key)s,
                    object_storage_uri = %(uri)s,
                    object_storage_synced_at = now(),
                    primary_file_asset_id = %(asset_id)s,
                    updated_at = now()
                WHERE document_id = %(document_id)s
                """,
                {
                    "provider": config.provider,
                    "bucket": config.bucket,
                    "key": key,
                    "uri": object_uri(config, key),
                    "asset_id": stored_asset_id,
                    "document_id": candidate.document_id,
                },
            )
        return str(stored_asset_id)


def upsert_digest(
    conn: Any,
    *,
    document_id: str,
    digest_type: str,
    digest_value: str,
    byte_size: int | None = None,
    page_count: int | None = None,
    file_asset_id: str | None = None,
    text_version_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    digest_id = stable_id("digest", document_id, digest_type, "sha256", digest_value)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document_digests (
                digest_id, document_id, file_asset_id, text_version_id,
                digest_type, algorithm, digest_value, byte_size, page_count, metadata
            )
            VALUES (
                %(digest_id)s, %(document_id)s, %(file_asset_id)s, %(text_version_id)s,
                %(digest_type)s, 'sha256', %(digest_value)s, %(byte_size)s,
                %(page_count)s, CAST(%(metadata)s AS jsonb)
            )
            ON CONFLICT (document_id, digest_type, algorithm, digest_value) DO UPDATE SET
                file_asset_id = EXCLUDED.file_asset_id,
                text_version_id = EXCLUDED.text_version_id,
                byte_size = EXCLUDED.byte_size,
                page_count = EXCLUDED.page_count,
                metadata = EXCLUDED.metadata
            RETURNING digest_id
            """,
            {
                "digest_id": digest_id,
                "document_id": document_id,
                "file_asset_id": file_asset_id,
                "text_version_id": text_version_id,
                "digest_type": digest_type,
                "digest_value": digest_value,
                "byte_size": byte_size,
                "page_count": page_count,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False, default=str),
            },
        )
        return str(cursor.fetchone()[0])


def best_page_key(page: dict[str, Any]) -> tuple[int, int, float, str]:
    text = str(page.get("text") or "").strip()
    method = str(page.get("extraction_method") or "")
    priority = {"text_layer": 4, "ocr": 3, "text": 2}.get(method, 1)
    confidence = page.get("ocr_confidence")
    confidence_value = float(confidence) if confidence is not None else 100.0
    return (1 if text else 0, len(text), priority, confidence_value, method)


def build_text_version(conn: Any, candidate: AssetCandidate) -> TextVersion | None:
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT page_number, text, extraction_method, ocr_confidence, quality_flags
            FROM pages
            WHERE document_id = %(document_id)s
            ORDER BY page_number, extraction_method
            """,
            {"document_id": candidate.document_id},
        )
        rows = [dict(row) for row in cursor.fetchall()]
    best_by_page: dict[int, dict[str, Any]] = {}
    for row in rows:
        page_number = int(row["page_number"])
        if page_number not in best_by_page or best_page_key(row) > best_page_key(best_by_page[page_number]):
            best_by_page[page_number] = row
    selected = [best_by_page[page_number] for page_number in sorted(best_by_page)]
    text_parts = [str(row.get("text") or "").strip() for row in selected if str(row.get("text") or "").strip()]
    if not text_parts:
        return None
    full_text = "\n\n".join(text_parts)
    text_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    methods = sorted({str(row.get("extraction_method") or "") for row in selected if row.get("extraction_method")})
    ocr_confidences = [
        float(row["ocr_confidence"])
        for row in selected
        if row.get("ocr_confidence") is not None and str(row.get("extraction_method") or "") == "ocr"
    ]
    quality_flags = sorted(
        {
            str(flag)
            for row in selected
            for flag in (row.get("quality_flags") or [])
            if flag
        }
    )
    mean_confidence = round(sum(ocr_confidences) / len(ocr_confidences), 2) if ocr_confidences else None
    confidence_band = None
    if mean_confidence is not None:
        confidence_band = "high" if mean_confidence >= 85 else "medium" if mean_confidence >= 70 else "low"
    return TextVersion(
        full_text=full_text,
        page_count=len(selected),
        char_count=len(full_text),
        text_hash=text_hash,
        extraction_method="+".join(methods) if methods else "unknown",
        ocr_confidence_mean=mean_confidence,
        ocr_confidence_band=confidence_band,
        quality_flags=quality_flags,
    )


def upsert_text_version(
    conn: Any,
    *,
    candidate: AssetCandidate,
    source_asset_id: str,
    text_asset_id: str,
    text_version: TextVersion,
    ingestion_run_id: str | None,
) -> str:
    if text_version.text_origin == "translation":
        missing_fields = [
            field_name
            for field_name, value in {
                "target_language": text_version.target_language,
                "source_language": text_version.source_language,
                "translated_from_language": text_version.translated_from_language,
                "translation_provider": text_version.translation_provider,
                "translation_review_status": text_version.translation_review_status,
                "source_text_version_id": text_version.source_text_version_id,
            }.items()
            if not value
        ]
        if missing_fields:
            raise ValueError(f"translation text versions require: {', '.join(missing_fields)}")
    stored_language = text_version.target_language or candidate.language
    version_label = (
        "current-pages-v1"
        if text_version.text_origin != "translation"
        else f"translation-{slug((text_version.source_language or candidate.language or 'source').lower())}-to-{slug((stored_language or 'english').lower())}-v1"
    )
    text_version_id = stable_id("dtv", candidate.document_id, version_label, text_version.text_hash)
    token_estimate = max(1, len(text_version.full_text.split()) * 4 // 3)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO document_text_versions (
                text_version_id, document_id, source_asset_id, text_asset_id,
                version_label, extraction_method, language, page_count,
                char_count, token_estimate, text_hash, full_text,
                ocr_confidence_mean, ocr_confidence_band, text_quality_score,
                quality_flags, text_origin, source_language, translated_from_language,
                translation_provider, translation_model, translation_review_status,
                source_text_version_id, official_replacement_document_id,
                superseded_by_text_version_id, created_by_ingestion_run_id, metadata
            )
            VALUES (
                %(text_version_id)s, %(document_id)s, %(source_asset_id)s, %(text_asset_id)s,
                %(version_label)s, %(extraction_method)s, %(language)s, %(page_count)s,
                %(char_count)s, %(token_estimate)s, %(text_hash)s, %(full_text)s,
                %(ocr_confidence_mean)s, %(ocr_confidence_band)s, %(text_quality_score)s,
                %(quality_flags)s, %(text_origin)s, %(source_language)s,
                %(translated_from_language)s, %(translation_provider)s,
                %(translation_model)s, %(translation_review_status)s,
                %(source_text_version_id)s, %(official_replacement_document_id)s,
                %(superseded_by_text_version_id)s, %(ingestion_run_id)s,
                CAST(%(metadata)s AS jsonb)
            )
            ON CONFLICT (document_id, version_label) DO UPDATE SET
                source_asset_id = EXCLUDED.source_asset_id,
                text_asset_id = EXCLUDED.text_asset_id,
                extraction_method = EXCLUDED.extraction_method,
                language = EXCLUDED.language,
                page_count = EXCLUDED.page_count,
                char_count = EXCLUDED.char_count,
                token_estimate = EXCLUDED.token_estimate,
                text_hash = EXCLUDED.text_hash,
                full_text = EXCLUDED.full_text,
                ocr_confidence_mean = EXCLUDED.ocr_confidence_mean,
                ocr_confidence_band = EXCLUDED.ocr_confidence_band,
                text_quality_score = EXCLUDED.text_quality_score,
                quality_flags = EXCLUDED.quality_flags,
                text_origin = EXCLUDED.text_origin,
                source_language = EXCLUDED.source_language,
                translated_from_language = EXCLUDED.translated_from_language,
                translation_provider = EXCLUDED.translation_provider,
                translation_model = EXCLUDED.translation_model,
                translation_review_status = EXCLUDED.translation_review_status,
                source_text_version_id = EXCLUDED.source_text_version_id,
                official_replacement_document_id = EXCLUDED.official_replacement_document_id,
                superseded_by_text_version_id = EXCLUDED.superseded_by_text_version_id,
                created_by_ingestion_run_id = EXCLUDED.created_by_ingestion_run_id,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING text_version_id
            """,
            {
                "text_version_id": text_version_id,
                "document_id": candidate.document_id,
                "source_asset_id": source_asset_id,
                "text_asset_id": text_asset_id,
                "version_label": version_label,
                "extraction_method": text_version.extraction_method,
                "language": stored_language,
                "page_count": text_version.page_count,
                "char_count": text_version.char_count,
                "token_estimate": token_estimate,
                "text_hash": text_version.text_hash,
                "full_text": text_version.full_text,
                "ocr_confidence_mean": text_version.ocr_confidence_mean,
                "ocr_confidence_band": text_version.ocr_confidence_band,
                "text_quality_score": candidate.text_quality_score,
                "quality_flags": text_version.quality_flags,
                "text_origin": text_version.text_origin,
                "source_language": text_version.source_language or candidate.language,
                "translated_from_language": text_version.translated_from_language,
                "translation_provider": text_version.translation_provider,
                "translation_model": text_version.translation_model,
                "translation_review_status": text_version.translation_review_status,
                "source_text_version_id": text_version.source_text_version_id,
                "official_replacement_document_id": text_version.official_replacement_document_id,
                "superseded_by_text_version_id": text_version.superseded_by_text_version_id,
                "ingestion_run_id": ingestion_run_id,
                "metadata": json.dumps(
                    {
                        "source": "pages_table" if text_version.text_origin != "translation" else "translation_pipeline",
                        "text_origin": text_version.text_origin,
                        "source_text_version_id": text_version.source_text_version_id,
                        "translated_from_language": text_version.translated_from_language,
                        "translation_review_status": text_version.translation_review_status,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        return str(cursor.fetchone()[0])


def upsert_case_document_relevance(conn: Any, document_id: str) -> int:
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT case_document_id, case_id, document_id, document_role
            FROM case_documents
            WHERE document_id = %(document_id)s
            ORDER BY case_id, case_document_id
            """,
            {"document_id": document_id},
        )
        rows = [dict(row) for row in cursor.fetchall()]
    upserted = 0
    with conn.cursor() as cursor:
        for row in rows:
            relevance_id = stable_id("rel", row["case_id"], row["case_document_id"], "case_attachment")
            cursor.execute(
                """
                INSERT INTO case_document_relevance (
                    relevance_id, case_id, case_document_id, document_id,
                    relevance_score, confidence_score, relevance_band,
                    source, status, rationale, metadata
                )
                VALUES (
                    %(relevance_id)s, %(case_id)s, %(case_document_id)s, %(document_id)s,
                    1.0, 1.0, 'direct', 'case_attachment', 'included',
                    %(rationale)s, CAST(%(metadata)s AS jsonb)
                )
                ON CONFLICT (case_id, case_document_id, source) WHERE case_document_id IS NOT NULL DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    relevance_score = EXCLUDED.relevance_score,
                    confidence_score = EXCLUDED.confidence_score,
                    relevance_band = EXCLUDED.relevance_band,
                    status = EXCLUDED.status,
                    rationale = EXCLUDED.rationale,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                {
                    "relevance_id": relevance_id,
                    "case_id": row["case_id"],
                    "case_document_id": row["case_document_id"],
                    "document_id": row["document_id"],
                    "rationale": "Document is attached to the case workspace and should be considered directly relevant unless reviewed otherwise.",
                    "metadata": json.dumps({"document_role": row.get("document_role")}, ensure_ascii=False),
                },
            )
            upserted += 1
    return upserted


def load_existing_asset_document_ids(conn: Any) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id
            FROM documents
            WHERE primary_file_asset_id IS NOT NULL
              AND object_storage_provider IS NOT NULL
              AND object_storage_bucket IS NOT NULL
              AND object_storage_key IS NOT NULL
            """
        )
        return {str(row[0]) for row in cursor.fetchall()}


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


def print_progress(summary: SyncSummary, *, final: bool = False) -> None:
    payload = {
        "event": "final" if final else "progress",
        "candidate_count": summary.candidate_count,
        "processed_count": summary.processed_count,
        "error_count": summary.error_count,
        "total_bytes": summary.total_bytes,
        "status_counts": summary.status_counts or {},
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def sync_candidate(
    conn: Any,
    *,
    candidate: AssetCandidate,
    config: StorageConfig,
    client: Any,
    execute: bool,
    skip_upload: bool,
    include_text_versions: bool,
    allow_hash_mismatch: bool,
    ingestion_run_id: str | None,
) -> dict[str, Any]:
    path = resolve_local_path(candidate.local_path)
    if not path.is_file():
        return {"document_id": candidate.document_id, "status": "missing_local_file", "local_path": candidate.local_path}
    digest = local_file_digest(path)
    expected_hash = normalize_hash(candidate.file_hash)
    if expected_hash and expected_hash != digest.sha256 and not allow_hash_mismatch:
        return {
            "document_id": candidate.document_id,
            "status": "hash_mismatch",
            "expected": expected_hash,
            "actual": digest.sha256,
        }
    key = storage_key(config, candidate, digest.sha256, path.suffix, kind="original")
    etag = ""
    text_version_status = "not_requested"
    relevance_rows = 0

    if execute:
        ensure_document(conn, candidate, ingestion_run_id)
        if not skip_upload:
            etag = upload_file_if_needed(client, bucket=config.bucket, key=key, digest=digest)
        asset_id = upsert_file_asset(
            conn,
            candidate=candidate,
            config=config,
            asset_kind="original",
            key=key,
            content_type=digest.content_type,
            byte_size=digest.byte_size,
            sha256=digest.sha256,
            etag=etag,
            source_local_path=str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path),
            is_primary=True,
            ingestion_run_id=ingestion_run_id,
            metadata={"download_url": candidate.download_url, "source_document_id": candidate.source_document_id},
        )
        upsert_digest(
            conn,
            document_id=candidate.document_id,
            digest_type="original_file",
            digest_value=digest.sha256,
            byte_size=digest.byte_size,
            file_asset_id=asset_id,
            metadata={"local_path": candidate.local_path},
        )
        relevance_rows = upsert_case_document_relevance(conn, candidate.document_id)
        if include_text_versions:
            text_version = build_text_version(conn, candidate)
            if text_version:
                text_payload = text_version.full_text.encode("utf-8")
                text_key = text_storage_key(config, candidate, text_version.text_hash)
                text_etag = ""
                if not skip_upload:
                    text_etag = upload_bytes_if_needed(
                        client,
                        bucket=config.bucket,
                        key=text_key,
                        payload=text_payload,
                        content_type="text/plain; charset=utf-8",
                        sha256=text_version.text_hash,
                    )
                text_asset_id = upsert_file_asset(
                    conn,
                    candidate=candidate,
                    config=config,
                    asset_kind="extracted_text",
                    key=text_key,
                    content_type="text/plain; charset=utf-8",
                    byte_size=len(text_payload),
                    sha256=text_version.text_hash,
                    etag=text_etag,
                    source_local_path="pages",
                    is_primary=False,
                    ingestion_run_id=ingestion_run_id,
                    metadata={"version_label": "current-pages-v1", "source_asset_id": asset_id},
                )
                text_version_id = upsert_text_version(
                    conn,
                    candidate=candidate,
                    source_asset_id=asset_id,
                    text_asset_id=text_asset_id,
                    text_version=text_version,
                    ingestion_run_id=ingestion_run_id,
                )
                upsert_digest(
                    conn,
                    document_id=candidate.document_id,
                    digest_type="extracted_full_text",
                    digest_value=text_version.text_hash,
                    byte_size=len(text_payload),
                    page_count=text_version.page_count,
                    file_asset_id=text_asset_id,
                    text_version_id=text_version_id,
                    metadata={"version_label": "current-pages-v1"},
                )
                text_version_status = "synced"
            else:
                text_version_status = "no_page_text"
    return {
        "document_id": candidate.document_id,
        "status": "synced" if execute else "planned",
        "asset_key": key,
        "byte_size": digest.byte_size,
        "sha256": digest.sha256,
        "text_version_status": text_version_status,
        "case_document_relevance_rows": relevance_rows,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = build_storage_config(args)

    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    client = None
    if args.execute and not args.skip_upload:
        client = build_s3_client(config)
        ensure_bucket(client, config.bucket)

    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        candidates = postgres_candidates(conn, args) if args.scope == "postgres" else manifest_candidates(args)
        summary = SyncSummary(candidate_count=len(candidates))
        ingestion_run_id = args.ingestion_run_id
        if args.execute:
            ingestion_run_id = ingestion_run_id or default_ingestion_run_id(args)
            start_ingestion_run(
                conn,
                args=args,
                config=config,
                ingestion_run_id=ingestion_run_id,
                input_manifest_hash=manifest_hash(args),
            )
            conn.commit()
        existing_asset_document_ids = load_existing_asset_document_ids(conn) if args.skip_existing_assets else set()
        report_handle = open_report(args.report_path)
        report_context = report_handle if report_handle is not None else nullcontext(None)
        with report_context as report:
            non_skipped_count = 0
            for candidate in candidates:
                if candidate.document_id in existing_asset_document_ids:
                    result = {
                        "document_id": candidate.document_id,
                        "status": "skipped_existing",
                        "reason": "document already has a primary object-storage asset",
                    }
                else:
                    if args.max_to_sync and non_skipped_count >= args.max_to_sync:
                        break
                    result = sync_candidate(
                        conn,
                        candidate=candidate,
                        config=config,
                        client=client,
                        execute=args.execute,
                        skip_upload=args.skip_upload,
                        include_text_versions=args.include_text_versions,
                        allow_hash_mismatch=args.allow_hash_mismatch,
                        ingestion_run_id=ingestion_run_id,
                    )
                    non_skipped_count += 1
                summary.add(result)
                write_report(report, result)
                if args.execute and ingestion_run_id:
                    record_ingestion_event(conn, ingestion_run_id=ingestion_run_id, candidate=candidate, result=result)
                if args.execute and summary.processed_count % args.batch_size == 0:
                    conn.commit()
                if args.progress_every and summary.processed_count % args.progress_every == 0:
                    print_progress(summary)
            if args.execute and ingestion_run_id:
                finish_ingestion_run(conn, ingestion_run_id=ingestion_run_id, summary=summary)
                conn.commit()

    print_progress(summary, final=True)
    print(
        json.dumps(
            {
                "execute": args.execute,
                "scope": args.scope,
                "bucket": config.bucket,
                "provider": config.provider,
                "ingestion_run_id": ingestion_run_id,
                "candidate_count": len(candidates),
                "processed_count": summary.processed_count,
                "error_count": summary.error_count,
                "total_bytes": summary.total_bytes,
                "status_counts": summary.status_counts or {},
                "results_preview": summary.results_preview or [],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if summary.error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
