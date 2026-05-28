#!/usr/bin/env python3
"""Embed and load RAG chunks into Qdrant.

Embedding providers:
- `openai`: uses `OPENAI_API_KEY` and OpenAI embeddings.
- `sentence-transformers`: uses a local Hugging Face/SentenceTransformers model.
- `auto`: OpenAI when `OPENAI_API_KEY` is set, otherwise local BGE-M3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks.jsonl"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
QDRANT_ID_NAMESPACE = uuid.UUID("67f5110a-05d1-43fc-b5be-2bc35b99b0ef")


class Embedder(Protocol):
    provider: str
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


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


@dataclass
class OpenAIEmbedder:
    model: str
    dimensions: int
    provider: str = "openai"

    def __post_init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SystemExit("Missing dependency: install `openai` before using OpenAI embeddings.") from exc
        self._client = OpenAI()

    def embed(self, texts: list[str]) -> list[list[float]]:
        kwargs: dict[str, object] = {"model": self.model, "input": texts}
        if self.dimensions:
            kwargs["dimensions"] = self.dimensions
        response = self._client.embeddings.create(**kwargs)
        return [item.embedding for item in response.data]


@dataclass
class SentenceTransformerEmbedder:
    model: str
    dimensions: int = 0
    provider: str = "sentence-transformers"

    def __post_init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise SystemExit("Missing dependency: install `sentence-transformers` before using local embeddings.") from exc
        self._model = SentenceTransformer(self.model)
        inferred = self._model.get_sentence_embedding_dimension()
        if inferred:
            self.dimensions = int(inferred)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=min(32, max(1, len(texts))),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


def build_embedder(provider: str, model: str, dimensions: int) -> Embedder:
    if provider == "auto":
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "sentence-transformers"
    if provider == "openai":
        return OpenAIEmbedder(model=model, dimensions=dimensions)
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(model=model, dimensions=dimensions)
    raise ValueError(f"unsupported embedding provider: {provider}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load RAG chunks into Qdrant.")
    parser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH))
    parser.add_argument("--url", default="http://localhost:6333")
    parser.add_argument("--collection", default="sl_legal_retrieval_chunks")
    parser.add_argument("--provider", choices=["auto", "openai", "sentence-transformers"], default=os.getenv("SL_LEGAL_EMBEDDING_PROVIDER", "auto"))
    parser.add_argument("--model", default=os.getenv("SL_LEGAL_EMBEDDING_MODEL", ""))
    parser.add_argument("--dimensions", type=int, default=int(os.getenv("SL_LEGAL_EMBEDDING_DIMENSIONS", "0")))
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--skip-run-record", action="store_true", help="Do not write embedding_runs metadata to Postgres.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--progress-every", type=int, default=5000, help="Print progress every N loaded chunks. 0 disables progress.")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the Qdrant collection.")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Qdrant HTTP timeout for large upsert/delete operations.")
    parser.add_argument(
        "--replace-text-version-scope",
        action="store_true",
        help="Delete existing points for text_version_ids present in the input before loading replacements.",
    )
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def start_embedding_run(
    *,
    dsn: str,
    provider: str,
    model: str,
    dimensions: int,
    chunk_source_hash: str,
    chunk_source_path: Path,
    qdrant_collection: str,
) -> int | None:
    try:
        import psycopg
    except ImportError:
        return None
    with psycopg.connect(normalize_psycopg_dsn(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO embedding_runs (
                    provider, model, dimensions, chunk_source_hash, status,
                    qdrant_collection, chunk_source_path, metadata
                )
                VALUES (%s, %s, %s, %s, 'running', %s, %s, %s::jsonb)
                RETURNING embedding_run_id
                """,
                (
                    provider,
                    model,
                    dimensions,
                    chunk_source_hash,
                    qdrant_collection,
                    str(chunk_source_path.relative_to(PROJECT_ROOT)),
                    json.dumps({"loader": "scripts/load_rag_chunks_qdrant.py"}, ensure_ascii=False),
                ),
            )
            row = cursor.fetchone()
        connection.commit()
    return int(row[0]) if row else None


def finish_embedding_run(
    *,
    dsn: str,
    embedding_run_id: int | None,
    status: str,
    chunk_count: int,
    metadata: dict[str, object] | None = None,
    notes: str | None = None,
) -> None:
    if embedding_run_id is None:
        return
    try:
        import psycopg
    except ImportError:
        return
    with psycopg.connect(normalize_psycopg_dsn(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE embedding_runs
                SET status = %s,
                    completed_at = %s,
                    chunk_count = %s,
                    metadata = metadata || %s::jsonb,
                    notes = %s
                WHERE embedding_run_id = %s
                """,
                (
                    status,
                    datetime.now(timezone.utc),
                    chunk_count,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    notes,
                    embedding_run_id,
                ),
            )
        connection.commit()


def delete_by_text_version_scope(client: object, *, models_module: object, collection: str, text_version_ids: list[str]) -> int:
    deleted_batches = 0
    for start in range(0, len(text_version_ids), 256):
        batch = text_version_ids[start : start + 256]
        if not batch:
            continue
        selector = models_module.FilterSelector(
            filter=models_module.Filter(
                must=[
                    models_module.FieldCondition(
                        key="text_version_id",
                        match=models_module.MatchAny(any=batch),
                    )
                ]
            )
        )
        try:
            client.delete(collection_name=collection, points_selector=selector, wait=False)
        except TypeError:
            client.delete(collection_name=collection, points_selector=selector)
        except Exception as exc:
            if "wait_timeout" not in str(exc):
                raise
        deleted_batches += 1
    return deleted_batches


def main(argv: list[str]) -> int:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models
    except ImportError as exc:
        raise SystemExit("Missing dependency: install requirements-rag.txt before loading Qdrant.") from exc

    args = parse_args(argv)
    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path

    provider = args.provider
    if provider == "auto":
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "sentence-transformers"
    model = args.model
    dimensions = args.dimensions
    if not model:
        if provider == "openai":
            model = "text-embedding-3-small"
            dimensions = dimensions or 1536
        else:
            model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedder = build_embedder(provider, model, dimensions)
    chunk_source_hash = file_sha256(chunks_path)
    embedding_run_id = None
    if not args.skip_run_record:
        embedding_run_id = start_embedding_run(
            dsn=args.dsn,
            provider=embedder.provider,
            model=embedder.model,
            dimensions=embedder.dimensions,
            chunk_source_hash=chunk_source_hash,
            chunk_source_path=chunks_path,
            qdrant_collection=args.collection,
        )

    client = QdrantClient(url=args.url, timeout=args.timeout_seconds, check_compatibility=False)
    loaded = 0
    deleted_batches = 0
    try:
        existing = {collection.name for collection in client.get_collections().collections}
        if args.collection in existing and args.recreate:
            client.delete_collection(collection_name=args.collection)
            existing.remove(args.collection)
        if args.collection not in existing:
            client.create_collection(
                collection_name=args.collection,
                vectors_config=models.VectorParams(size=embedder.dimensions, distance=models.Distance.COSINE),
            )
        if args.replace_text_version_scope:
            deleted_batches = delete_by_text_version_scope(
                client,
                models_module=models,
                collection=args.collection,
                text_version_ids=collect_text_version_ids(chunks_path),
            )

        batch: list[dict[str, object]] = []
        for chunk in load_chunks(chunks_path):
            batch.append(chunk)
            if len(batch) >= args.batch_size:
                vectors = embedder.embed([str(item["chunk_text"]) for item in batch])
                points = [
                    models.PointStruct(
                        id=str(uuid.uuid5(QDRANT_ID_NAMESPACE, str(item["chunk_id"]))),
                        vector=vector,
                        payload={key: value for key, value in item.items() if key != "chunk_text"} | {"text": item["chunk_text"]},
                    )
                    for item, vector in zip(batch, vectors)
                ]
                client.upsert(collection_name=args.collection, points=points)
                loaded += len(batch)
                if args.progress_every and loaded % args.progress_every < len(batch):
                    print(json.dumps({"event": "progress", "chunks_loaded": loaded}, indent=2), flush=True)
                batch = []

        if batch:
            vectors = embedder.embed([str(item["chunk_text"]) for item in batch])
            points = [
                models.PointStruct(
                    id=str(uuid.uuid5(QDRANT_ID_NAMESPACE, str(item["chunk_id"]))),
                    vector=vector,
                    payload={key: value for key, value in item.items() if key != "chunk_text"} | {"text": item["chunk_text"]},
                )
                for item, vector in zip(batch, vectors)
            ]
            client.upsert(collection_name=args.collection, points=points)
            loaded += len(batch)
            if args.progress_every:
                print(json.dumps({"event": "progress", "chunks_loaded": loaded}, indent=2), flush=True)
    except Exception as exc:
        finish_embedding_run(
            dsn=args.dsn,
            embedding_run_id=embedding_run_id,
            status="failed",
            chunk_count=loaded,
            metadata={"qdrant_url": args.url, "collection": args.collection},
            notes=str(exc)[:2000],
        )
        raise
    finish_embedding_run(
        dsn=args.dsn,
        embedding_run_id=embedding_run_id,
        status="complete",
        chunk_count=loaded,
        metadata={
            "qdrant_url": args.url,
            "collection": args.collection,
            "chunks_path": str(chunks_path.relative_to(PROJECT_ROOT)),
            "chunk_source_hash": chunk_source_hash,
        },
    )

    print(
        json.dumps(
            {
                "collection": args.collection,
                "chunks_loaded": loaded,
                "embedding_provider": embedder.provider,
                "embedding_model": embedder.model,
                "dimensions": embedder.dimensions,
                "embedding_run_id": embedding_run_id,
                "chunk_source_hash": chunk_source_hash,
                "delete_batches": deleted_batches,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
