#!/usr/bin/env python3
"""Hybrid retrieval CLI: OpenSearch + Qdrant + RRF -> research pack JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "indexes" / "sample_hybrid_research_pack.json"
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.hybrid_retrieval import HybridRetrievalConfig, create_research_pack  # noqa: E402
from sl_legal_rag.models import QueryClass, ResearchQueryRequest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hybrid legal retrieval.")
    parser.add_argument("query")
    parser.add_argument("--opensearch-url", default="http://localhost:9200")
    parser.add_argument("--opensearch-index", default="sl_legal_retrieval_chunks")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--qdrant-collection", default="sl_legal_retrieval_chunks")
    parser.add_argument("--embedding-provider", choices=["openai", "sentence-transformers"], default="sentence-transformers")
    parser.add_argument("--embedding-model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--embedding-dimensions", type=int, default=384)
    parser.add_argument("--candidate-size", type=int, default=20)
    parser.add_argument("--max-items", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = HybridRetrievalConfig(
        opensearch_url=args.opensearch_url,
        opensearch_index=args.opensearch_index,
        qdrant_url=args.qdrant_url,
        qdrant_collection=args.qdrant_collection,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.embedding_dimensions,
        candidate_size=args.candidate_size,
    )
    request = ResearchQueryRequest(
        query=args.query,
        query_class=QueryClass.GENERAL_RESEARCH,
        max_pack_items=args.max_items,
        max_pack_tokens=args.max_tokens,
    )
    pack = create_research_pack(request, config=config)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pack.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "items": len(pack.items),
                "top_citation": pack.items[0].citation if pack.items else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
