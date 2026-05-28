#!/usr/bin/env python3
"""Create a local Legal Research Pack from `data/indexes/rag_chunks.jsonl`.

This is a smoke-test retriever for development before OpenSearch/Qdrant loaders
are wired. It uses a small built-in BM25 scorer plus legal authority boosts and
emits the same kind of pack the LLM layer will consume.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks.jsonl"

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9()./-]*")
AUTHORITY_BOOSTS = {
    1: 1.35,
    2: 1.30,
    3: 1.25,
    4: 1.15,
    5: 1.05,
    6: 1.00,
    7: 0.95,
    8: 0.90,
    9: 0.80,
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1]


def load_chunks(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def bm25_scores(query: str, chunks: list[dict[str, object]]) -> list[tuple[float, dict[str, object]]]:
    query_terms = tokenize(query)
    if not query_terms:
        return []
    docs = [tokenize(str(chunk["chunk_text"])) for chunk in chunks]
    doc_freq: Counter[str] = Counter()
    for doc in docs:
        doc_freq.update(set(doc))

    total_docs = len(docs)
    avg_len = sum(len(doc) for doc in docs) / max(1, total_docs)
    k1 = 1.5
    b = 0.75
    scored: list[tuple[float, dict[str, object]]] = []

    for chunk, doc_tokens in zip(chunks, docs):
        freqs = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        score = 0.0
        for term in query_terms:
            if not freqs[term]:
                continue
            idf = math.log(1 + (total_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denom = freqs[term] + k1 * (1 - b + b * doc_len / max(1, avg_len))
            score += idf * (freqs[term] * (k1 + 1)) / denom

        title_blob = f"{chunk.get('title', '')} {chunk.get('citation', '')}".lower()
        title_hits = sum(1 for term in set(query_terms) if term in title_blob)
        if title_hits:
            score += 0.4 * title_hits

        authority = int(chunk.get("authority_level") or 9)
        score *= AUTHORITY_BOOSTS.get(authority, 0.85)
        if score > 0:
            scored.append((score, chunk))

    return sorted(scored, key=lambda item: item[0], reverse=True)


def build_pack(query: str, scored: list[tuple[float, dict[str, object]]], max_items: int, max_tokens: int) -> dict[str, object]:
    items: list[dict[str, object]] = []
    used_tokens = 0
    for score, chunk in scored:
        token_estimate = int(chunk.get("token_estimate") or 0)
        if items and used_tokens + token_estimate > max_tokens:
            continue
        pack_item_id = f"pack_item_{len(items) + 1:03d}"
        items.append(
            {
                "pack_item_id": pack_item_id,
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "title": chunk["title"],
                "document_type": chunk["document_type"],
                "source_id": chunk["source_id"],
                "authority_level": chunk["authority_level"],
                "year": chunk.get("year"),
                "citation": chunk["citation"],
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "text": chunk["chunk_text"],
                "fused_score": round(score, 6),
                "selection_reason": "local_bm25_smoke_test; authority_boosted",
                "source_url": chunk.get("source_url"),
                "local_path": chunk.get("local_path"),
            }
        )
        used_tokens += token_estimate
        if len(items) >= max_items:
            break

    return {
        "pack_id": f"local_pack_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "query": query,
        "query_class": "general_research",
        "retrieval_config": {
            "mode": "local_bm25_smoke_test",
            "production_mode": "OpenSearch BM25/fuzzy + Qdrant dense vector + RRF",
            "max_items": max_items,
            "max_tokens": max_tokens,
        },
        "items": items,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "warnings": [
            "This local pack is a development smoke test, not the final production hybrid retriever.",
            "Strategy generation must still use only the returned pack_item_id citations.",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query local legal RAG chunks.")
    parser.add_argument("query", help="Legal search query.")
    parser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH), help="Chunk JSONL file.")
    parser.add_argument("--max-items", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path
    chunks = load_chunks(chunks_path)
    scored = bm25_scores(args.query, chunks)
    pack = build_pack(args.query, scored, args.max_items, args.max_tokens)
    payload = json.dumps(pack, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
