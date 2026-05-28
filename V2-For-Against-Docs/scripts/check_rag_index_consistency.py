#!/usr/bin/env python3
"""Check that PostgreSQL retrieval chunks are synced to OpenSearch and Qdrant."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--opensearch-url", default="http://localhost:9200")
    parser.add_argument("--opensearch-index", default="sl_legal_retrieval_chunks")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--qdrant-collection", default="sl_legal_retrieval_chunks")
    parser.add_argument("--embedding-provider", default=os.getenv("SL_LEGAL_EMBEDDING_PROVIDER", "sentence-transformers"))
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("SL_LEGAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    )
    parser.add_argument("--embedding-dimensions", type=int, default=int(os.getenv("SL_LEGAL_EMBEDDING_DIMENSIONS", "384")))
    parser.add_argument("--skip-embedding-run-check", action="store_true")
    parser.add_argument("--export-missing-to", help="Write JSONL chunks missing from either search index.")
    parser.add_argument("--allow-mismatch", action="store_true", help="Return success even when mismatches are found.")
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def request_json(method: str, url: str, payload: object | None = None) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {raw[:1000]}") from exc
    return json.loads(raw)


def postgres_chunks(dsn: str) -> dict[str, dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    query = """
        SELECT
            chunk_id, document_id, source_id, document_type, title, year,
            authority_level, page_start, page_end, chunk_index, chunk_text,
            token_estimate, language, citation, source_url, local_path,
            text_hash, quality_flags, metadata
        FROM retrieval_chunks
        ORDER BY chunk_id
    """
    chunks: dict[str, dict[str, Any]] = {}
    with psycopg.connect(normalize_psycopg_dsn(dsn), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            for row in cursor:
                payload = dict(row)
                payload["quality_flags"] = list(payload.get("quality_flags") or [])
                payload["metadata"] = dict(payload.get("metadata") or {})
                chunks[str(payload["chunk_id"])] = payload
    return chunks


def latest_embedding_run(dsn: str, qdrant_collection: str) -> dict[str, Any] | None:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    with psycopg.connect(normalize_psycopg_dsn(dsn), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    embedding_run_id, provider, model, dimensions, status,
                    qdrant_collection, chunk_count, chunk_source_hash,
                    completed_at, metadata
                FROM embedding_runs
                WHERE status = 'complete'
                  AND (qdrant_collection = %s OR qdrant_collection IS NULL)
                ORDER BY completed_at DESC NULLS LAST, embedding_run_id DESC
                LIMIT 1
                """,
                (qdrant_collection,),
            )
            row = cursor.fetchone()
    return dict(row) if row else None


def opensearch_chunk_ids(base_url: str, index: str) -> set[str]:
    ids: set[str] = set()
    search = request_json(
        "POST",
        f"{base_url.rstrip('/')}/{index}/_search?scroll=1m",
        {"size": 5000, "_source": ["chunk_id"], "query": {"match_all": {}}},
    )
    scroll_id = search.get("_scroll_id")
    try:
        while True:
            hits = search.get("hits", {}).get("hits", [])
            if not hits:
                break
            for hit in hits:
                chunk_id = hit.get("_source", {}).get("chunk_id")
                if chunk_id:
                    ids.add(str(chunk_id))
            search = request_json(
                "POST",
                f"{base_url.rstrip('/')}/_search/scroll",
                {"scroll": "1m", "scroll_id": scroll_id},
            )
            scroll_id = search.get("_scroll_id")
    finally:
        if scroll_id:
            try:
                request_json("DELETE", f"{base_url.rstrip('/')}/_search/scroll", {"scroll_id": [scroll_id]})
            except RuntimeError:
                pass
    return ids


def qdrant_chunk_ids(base_url: str, collection: str) -> set[str]:
    ids: set[str] = set()
    offset: str | int | None = None
    while True:
        payload: dict[str, Any] = {"limit": 5000, "with_payload": ["chunk_id"], "with_vector": False}
        if offset is not None:
            payload["offset"] = offset
        body = request_json("POST", f"{base_url.rstrip('/')}/collections/{collection}/points/scroll", payload)
        result = body.get("result", {})
        for point in result.get("points", []):
            chunk_id = point.get("payload", {}).get("chunk_id")
            if chunk_id:
                ids.add(str(chunk_id))
        offset = result.get("next_page_offset")
        if offset is None:
            break
    return ids


def write_missing_chunks(path: Path, chunks: dict[str, dict[str, Any]], missing_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk_id in sorted(missing_ids):
            handle.write(json.dumps(chunks[chunk_id], ensure_ascii=False, default=str) + "\n")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    chunks = postgres_chunks(args.dsn)
    postgres_ids = set(chunks)
    opensearch_ids = opensearch_chunk_ids(args.opensearch_url, args.opensearch_index)
    qdrant_ids = qdrant_chunk_ids(args.qdrant_url, args.qdrant_collection)
    embedding_run = None if args.skip_embedding_run_check else latest_embedding_run(args.dsn, args.qdrant_collection)

    missing_from_opensearch = postgres_ids - opensearch_ids
    missing_from_qdrant = postgres_ids - qdrant_ids
    extra_in_opensearch = opensearch_ids - postgres_ids
    extra_in_qdrant = qdrant_ids - postgres_ids
    missing_anywhere = missing_from_opensearch | missing_from_qdrant
    embedding_mismatches: list[str] = []
    if not args.skip_embedding_run_check:
        if embedding_run is None:
            embedding_mismatches.append("no completed embedding_runs row found for Qdrant collection")
        else:
            if str(embedding_run["provider"]) != args.embedding_provider:
                embedding_mismatches.append(f"provider {embedding_run['provider']} != {args.embedding_provider}")
            if str(embedding_run["model"]) != args.embedding_model:
                embedding_mismatches.append(f"model {embedding_run['model']} != {args.embedding_model}")
            if int(embedding_run["dimensions"]) != args.embedding_dimensions:
                embedding_mismatches.append(f"dimensions {embedding_run['dimensions']} != {args.embedding_dimensions}")

    export_path = None
    if args.export_missing_to and missing_anywhere:
        export_path = Path(args.export_missing_to)
        if not export_path.is_absolute():
            export_path = PROJECT_ROOT / export_path
        write_missing_chunks(export_path, chunks, missing_anywhere)

    report = {
        "postgres_chunks": len(postgres_ids),
        "opensearch_chunks": len(opensearch_ids),
        "qdrant_chunks": len(qdrant_ids),
        "missing_from_opensearch": sorted(missing_from_opensearch),
        "missing_from_qdrant": sorted(missing_from_qdrant),
        "extra_in_opensearch": sorted(extra_in_opensearch),
        "extra_in_qdrant": sorted(extra_in_qdrant),
        "embedding_run": embedding_run,
        "embedding_mismatches": embedding_mismatches,
        "export_missing_to": str(export_path.relative_to(PROJECT_ROOT)) if export_path else None,
    }
    print(json.dumps(report, indent=2, default=str))
    has_mismatch = bool(missing_anywhere or extra_in_opensearch or extra_in_qdrant or embedding_mismatches)
    return 0 if args.allow_mismatch or not has_mismatch else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
