#!/usr/bin/env python3
"""Query OpenSearch retrieval chunks with BM25, phrase, and fuzzy matching."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def request(method: str, url: str, payload: object | None = None) -> tuple[int, str]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def build_query(query: str, size: int) -> dict[str, object]:
    return {
        "size": size,
        "query": {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^3", "citation^3", "chunk_text"],
                            "type": "best_fields",
                            "operator": "and",
                            "boost": 3,
                        }
                    },
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^2", "citation^2", "chunk_text"],
                            "type": "phrase",
                            "boost": 5,
                        }
                    },
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^2", "citation^2", "chunk_text"],
                            "fuzziness": "AUTO",
                            "prefix_length": 2,
                            "boost": 0.8,
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
        "_source": [
            "chunk_id",
            "document_id",
            "source_id",
            "document_type",
            "title",
            "year",
            "authority_level",
            "page_start",
            "page_end",
            "citation",
            "source_url",
            "local_path",
            "chunk_text",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query OpenSearch legal chunks.")
    parser.add_argument("query")
    parser.add_argument("--url", default="http://localhost:9200")
    parser.add_argument("--index", default="sl_legal_retrieval_chunks")
    parser.add_argument("--size", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status, body = request("GET", f"{args.url.rstrip('/')}/{args.index}/_search", build_query(args.query, args.size))
    if status >= 300:
        raise RuntimeError(f"OpenSearch query failed: HTTP {status}: {body}")
    payload = json.loads(body)
    results = []
    for hit in payload["hits"]["hits"]:
        source = hit["_source"]
        text = str(source.get("chunk_text", "")).replace("\n", " ")
        results.append(
            {
                "score": hit["_score"],
                "chunk_id": source["chunk_id"],
                "document_id": source["document_id"],
                "title": source["title"],
                "citation": source["citation"],
                "authority_level": source["authority_level"],
                "snippet": text[:500],
            }
        )
    print(json.dumps({"query": args.query, "total": payload["hits"]["total"], "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
