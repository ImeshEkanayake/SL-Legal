#!/usr/bin/env python3
"""Query Qdrant vector retrieval chunks."""

from __future__ import annotations

import argparse
import json


def embed_query(text: str, provider: str, model: str, dimensions: int) -> list[float]:
    if provider == "openai":
        from openai import OpenAI

        kwargs: dict[str, object] = {"model": model, "input": [text]}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = OpenAI().embeddings.create(**kwargs)
        return response.data[0].embedding

    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(model)
    vector = encoder.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
    return vector.tolist()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Qdrant legal chunks.")
    parser.add_argument("query")
    parser.add_argument("--url", default="http://localhost:6333")
    parser.add_argument("--collection", default="sl_legal_retrieval_chunks")
    parser.add_argument("--provider", choices=["openai", "sentence-transformers"], default="sentence-transformers")
    parser.add_argument("--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--dimensions", type=int, default=384)
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    from qdrant_client import QdrantClient

    args = parse_args()
    client = QdrantClient(url=args.url)
    query_vector = embed_query(args.query, args.provider, args.model, args.dimensions)
    hits = client.query_points(
        collection_name=args.collection,
        query=query_vector,
        limit=args.limit,
        with_payload=True,
    ).points
    results = []
    for hit in hits:
        payload = hit.payload or {}
        text = str(payload.get("text", "")).replace("\n", " ")
        results.append(
            {
                "score": hit.score,
                "chunk_id": payload.get("chunk_id"),
                "document_id": payload.get("document_id"),
                "title": payload.get("title"),
                "citation": payload.get("citation"),
                "authority_level": payload.get("authority_level"),
                "snippet": text[:500],
            }
        )
    print(json.dumps({"query": args.query, "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
