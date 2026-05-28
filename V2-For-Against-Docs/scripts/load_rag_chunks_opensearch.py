#!/usr/bin/env python3
"""Load RAG chunks into OpenSearch for BM25, phrase, fuzzy, and filtered search."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks.jsonl"


INDEX_MAPPING = {
    "settings": {
        "index": {"number_of_shards": 1, "number_of_replicas": 0},
        "analysis": {
            "analyzer": {
                "legal_english": {
                    "type": "standard",
                    "stopwords": "_english_",
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "document_type": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "legal_english", "fields": {"keyword": {"type": "keyword"}}},
            "year": {"type": "integer"},
            "authority_level": {"type": "integer"},
            "page_start": {"type": "integer"},
            "page_end": {"type": "integer"},
            "chunk_text": {"type": "text", "analyzer": "legal_english"},
            "citation": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "source_url": {"type": "keyword"},
            "local_path": {"type": "keyword"},
            "language": {"type": "keyword"},
            "metadata": {"type": "object", "enabled": True},
            "text_version_id": {"type": "keyword"},
            "text_origin": {"type": "keyword"},
            "source_language": {"type": "keyword"},
            "translated_from_language": {"type": "keyword"},
            "translation_review_status": {"type": "keyword"},
        }
    },
}


def request(method: str, url: str, payload: object | str | None = None) -> tuple[int, str]:
    data: bytes | None = None
    headers = {}
    if payload is not None:
        if isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def load_chunks(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def collect_text_version_ids(path: Path) -> list[str]:
    text_version_ids: set[str] = set()
    for chunk in load_chunks(path):
        text_version_id = str(chunk.get("text_version_id") or "").strip()
        if text_version_id:
            text_version_ids.add(text_version_id)
    return sorted(text_version_ids)


def sanitize_document(doc: dict[str, object]) -> dict[str, object]:
    sanitized = dict(doc)
    if sanitized.get("date") in {"", None}:
        sanitized.pop("date", None)
    return sanitized


def ensure_index(base_url: str, index_name: str) -> None:
    status, _ = request("HEAD", f"{base_url}/{index_name}")
    if status == 404:
        status, body = request("PUT", f"{base_url}/{index_name}", INDEX_MAPPING)
        if status >= 300:
            raise RuntimeError(f"failed to create index {index_name}: {status} {body}")
    elif status >= 300:
        raise RuntimeError(f"failed to check index {index_name}: HTTP {status}")


def bulk_index(base_url: str, index_name: str, docs: list[dict[str, object]]) -> None:
    lines: list[str] = []
    for doc in docs:
        sanitized = sanitize_document(doc)
        lines.append(json.dumps({"index": {"_index": index_name, "_id": sanitized["chunk_id"]}}, ensure_ascii=False))
        lines.append(json.dumps(sanitized, ensure_ascii=False))
    payload = "\n".join(lines) + "\n"
    status, body = request("POST", f"{base_url}/_bulk", payload)
    if status >= 300:
        raise RuntimeError(f"bulk index failed: HTTP {status} {body}")
    parsed = json.loads(body)
    if parsed.get("errors"):
        raise RuntimeError(f"bulk index returned item errors: {body[:2000]}")


def delete_by_text_version_scope(base_url: str, index_name: str, text_version_ids: list[str]) -> int:
    deleted = 0
    for start in range(0, len(text_version_ids), 1000):
        batch = text_version_ids[start : start + 1000]
        status, body = request(
            "POST",
            f"{base_url}/{index_name}/_delete_by_query?conflicts=proceed&refresh=true",
            {"query": {"terms": {"text_version_id": batch}}},
        )
        if status >= 300:
            raise RuntimeError(f"delete_by_query failed: HTTP {status} {body}")
        deleted += int(json.loads(body).get("deleted") or 0)
    return deleted


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load RAG chunks into OpenSearch.")
    parser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH))
    parser.add_argument("--url", default="http://localhost:9200")
    parser.add_argument("--index", default="sl_legal_retrieval_chunks")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the OpenSearch index before loading.")
    parser.add_argument(
        "--replace-text-version-scope",
        action="store_true",
        help="Delete existing indexed chunks for text_version_ids present in the input before loading replacements.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path
    base_url = args.url.rstrip("/")
    if args.recreate:
        status, body = request("DELETE", f"{base_url}/{args.index}")
        if status not in {200, 202, 404}:
            raise RuntimeError(f"failed to delete index {args.index}: HTTP {status} {body}")
    ensure_index(base_url, args.index)
    deleted = 0
    if args.replace_text_version_scope:
        deleted = delete_by_text_version_scope(base_url, args.index, collect_text_version_ids(chunks_path))

    batch: list[dict[str, object]] = []
    indexed = 0
    for chunk in load_chunks(chunks_path):
        batch.append(chunk)
        if len(batch) >= args.batch_size:
            bulk_index(base_url, args.index, batch)
            indexed += len(batch)
            batch = []
    if batch:
        bulk_index(base_url, args.index, batch)
        indexed += len(batch)

    print(json.dumps({"index": args.index, "chunks_indexed": indexed, "chunks_deleted": deleted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
