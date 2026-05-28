#!/usr/bin/env python3
"""Create Qdrant payload indexes used by filtered legal retrieval."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


DEFAULT_FIELDS = {
    "document_type": "keyword",
    "source_id": "keyword",
    "language": "keyword",
    "authority_level": "integer",
    "year": "integer",
    "text_version_id": "keyword",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:6333")
    parser.add_argument("--collection", default="sl_legal_retrieval_chunks")
    return parser.parse_args()


def request_json(method: str, url: str, payload: object | None = None) -> dict[str, object]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc


def main() -> int:
    args = parse_args()
    base = args.url.rstrip("/")
    created = []
    for field_name, field_schema in DEFAULT_FIELDS.items():
        request_json(
            "PUT",
            f"{base}/collections/{args.collection}/index",
            {"field_name": field_name, "field_schema": field_schema},
        )
        created.append({"field_name": field_name, "field_schema": field_schema})
    collection = request_json("GET", f"{base}/collections/{args.collection}")
    print(
        json.dumps(
            {
                "collection": args.collection,
                "created_or_verified": created,
                "payload_schema": collection.get("result", {}).get("payload_schema", {}),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
