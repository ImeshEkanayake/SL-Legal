#!/usr/bin/env python3
"""Check local retrieval services and index counts."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def get_json(url: str) -> object:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}", "body": exc.read().decode("utf-8")[:500]}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    report = {
        "opensearch": get_json("http://localhost:9200"),
        "opensearch_chunks": get_json("http://localhost:9200/sl_legal_retrieval_chunks/_count"),
        "qdrant": get_json("http://localhost:6333/collections"),
        "qdrant_chunks": get_json("http://localhost:6333/collections/sl_legal_retrieval_chunks"),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
