from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import text

from .config import RagSettings, settings
from .adverse_retrieval import expand_for_against_queries, query_intent_trace, tag_hits_for_query_intent
from .db import session_scope
from .exact_citation import parse_exact_citation_signals, resolve_exact_citation_hits
from .models import LegalResearchPack, QueryClass, ResearchQueryRequest, RetrievalFilters
from .research_pack import seal_research_pack
from .retrieval import SearchHit, build_research_pack, reciprocal_rank_fusion, rerank_with_legal_quality


class RetrievalServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HybridRetrievalConfig:
    opensearch_url: str
    opensearch_index: str
    qdrant_url: str
    qdrant_collection: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    candidate_size: int

    @classmethod
    def from_settings(cls, runtime_settings: RagSettings = settings) -> "HybridRetrievalConfig":
        return cls(
            opensearch_url=runtime_settings.opensearch_url,
            opensearch_index=runtime_settings.opensearch_index,
            qdrant_url=runtime_settings.qdrant_url,
            qdrant_collection=runtime_settings.qdrant_collection,
            embedding_provider=runtime_settings.embedding_provider,
            embedding_model=runtime_settings.embedding_model,
            embedding_dimensions=runtime_settings.embedding_dimensions,
            candidate_size=runtime_settings.retrieval_candidate_size,
        )


def request_json(method: str, url: str, payload: object | None = None) -> dict[str, Any]:
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
        raise RetrievalServiceError(f"{url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RetrievalServiceError(f"{url} is not reachable: {exc}") from exc


def opensearch_filter_clauses(filters: RetrievalFilters) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if filters.document_types:
        clauses.append({"terms": {"document_type": filters.document_types}})
    if filters.source_ids:
        clauses.append({"terms": {"source_id": filters.source_ids}})
    if filters.authority_levels:
        clauses.append({"terms": {"authority_level": filters.authority_levels}})
    if filters.years:
        clauses.append({"terms": {"year": filters.years}})
    if filters.year_from is not None or filters.year_to is not None:
        range_filter: dict[str, int] = {}
        if filters.year_from is not None:
            range_filter["gte"] = filters.year_from
        if filters.year_to is not None:
            range_filter["lte"] = filters.year_to
        clauses.append({"range": {"year": range_filter}})
    if filters.language:
        clauses.append({"term": {"language": filters.language}})
    return clauses


def build_opensearch_payload(query: str, filters: RetrievalFilters, size: int) -> dict[str, Any]:
    bool_query: dict[str, Any] = {
        "should": [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "citation^3", "chunk_text"],
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
    filter_clauses = opensearch_filter_clauses(filters)
    if filter_clauses:
        bool_query["filter"] = filter_clauses
    return {"size": size, "query": {"bool": bool_query}}


def coerce_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def hit_from_payload(payload: dict[str, Any], *, retriever: str, score: float, rank: int) -> SearchHit:
    text = str(payload.get("chunk_text") or payload.get("text") or "")
    metadata = dict(payload.get("metadata") or {})
    for key in (
        "quality_flags",
        "text_version_id",
        "text_origin",
        "source_language",
        "translated_from_language",
        "translation_review_status",
    ):
        if payload.get(key) is not None and key not in metadata:
            metadata[key] = payload.get(key)
    return SearchHit(
        chunk_id=str(payload.get("chunk_id") or ""),
        document_id=str(payload.get("document_id") or ""),
        title=str(payload.get("title") or ""),
        document_type=str(payload.get("document_type") or ""),
        source_id=str(payload.get("source_id") or ""),
        authority_level=coerce_int(payload.get("authority_level"), 9) or 9,
        citation=str(payload.get("citation") or ""),
        text=text,
        score=score,
        retriever=retriever,
        year=coerce_int(payload.get("year")),
        page_start=coerce_int(payload.get("page_start")),
        page_end=coerce_int(payload.get("page_end")),
        source_url=str(payload.get("source_url") or "") or None,
        local_path=str(payload.get("local_path") or "") or None,
        metadata=metadata,
    )


def opensearch_query(
    *,
    query: str,
    filters: RetrievalFilters,
    config: HybridRetrievalConfig,
    size: int,
) -> list[SearchHit]:
    payload = build_opensearch_payload(query, filters, size)
    body = request_json("POST", f"{config.opensearch_url.rstrip('/')}/{config.opensearch_index}/_search", payload)
    hits = ((body.get("hits") or {}).get("hits") or [])
    results: list[SearchHit] = []
    for rank, hit in enumerate(hits, start=1):
        source = dict(hit.get("_source") or {})
        results.append(
            hit_from_payload(
                source,
                retriever="opensearch_bm25_phrase_fuzzy",
                score=float(hit.get("_score") or 0.0),
                rank=rank,
            )
        )
    return [hit for hit in results if hit.chunk_id and hit.text]


@lru_cache(maxsize=4)
def sentence_transformer_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_query(query: str, *, provider: str, model: str, dimensions: int) -> list[float]:
    if provider == "auto":
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "sentence-transformers"
    if provider == "openai":
        from openai import OpenAI

        kwargs: dict[str, object] = {"model": model, "input": [query]}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = OpenAI().embeddings.create(**kwargs)
        return response.data[0].embedding
    if provider == "sentence-transformers":
        encoder = sentence_transformer_model(model)
        vector = encoder.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        return vector.tolist()
    raise RetrievalServiceError(f"unsupported embedding provider: {provider}")


def qdrant_filter(filters: RetrievalFilters):
    from qdrant_client.http import models

    must = []
    if filters.document_types:
        must.append(models.FieldCondition(key="document_type", match=models.MatchAny(any=filters.document_types)))
    if filters.source_ids:
        must.append(models.FieldCondition(key="source_id", match=models.MatchAny(any=filters.source_ids)))
    if filters.authority_levels:
        must.append(models.FieldCondition(key="authority_level", match=models.MatchAny(any=filters.authority_levels)))
    if filters.years:
        must.append(models.FieldCondition(key="year", match=models.MatchAny(any=filters.years)))
    if filters.year_from is not None or filters.year_to is not None:
        must.append(
            models.FieldCondition(
                key="year",
                range=models.Range(gte=filters.year_from, lte=filters.year_to),
            )
        )
    if filters.language:
        must.append(models.FieldCondition(key="language", match=models.MatchValue(value=filters.language)))
    if not must:
        return None
    return models.Filter(must=must)


def qdrant_query(
    *,
    query: str,
    filters: RetrievalFilters,
    config: HybridRetrievalConfig,
    size: int,
) -> list[SearchHit]:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RetrievalServiceError("Missing qdrant-client dependency.") from exc

    _assert_embedding_run_compatible(config)
    client = QdrantClient(url=config.qdrant_url, timeout=120, check_compatibility=False)
    query_vector = embed_query(
        query,
        provider=config.embedding_provider,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
    )
    points = client.query_points(
        collection_name=config.qdrant_collection,
        query=query_vector,
        query_filter=qdrant_filter(filters),
        limit=size,
        with_payload=True,
    ).points
    results: list[SearchHit] = []
    for rank, point in enumerate(points, start=1):
        payload = dict(point.payload or {})
        results.append(
            hit_from_payload(
                payload,
                retriever="qdrant_dense_vector",
                score=float(point.score),
                rank=rank,
            )
        )
    return [hit for hit in results if hit.chunk_id and hit.text]


@lru_cache(maxsize=16)
def _latest_embedding_run(collection: str) -> tuple[str, str, int] | None:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    SELECT provider, model, dimensions
                    FROM embedding_runs
                    WHERE status = 'complete'
                      AND (qdrant_collection = :collection OR qdrant_collection IS NULL)
                    ORDER BY completed_at DESC NULLS LAST, embedding_run_id DESC
                    LIMIT 1
                    """
                ),
                {"collection": collection},
            ).mappings().first()
    except Exception:
        return None
    if row is None:
        return None
    return str(row["provider"]), str(row["model"]), int(row["dimensions"])


def _assert_embedding_run_compatible(config: HybridRetrievalConfig) -> None:
    latest = _latest_embedding_run(config.qdrant_collection)
    if latest is None:
        return
    provider, model, dimensions = latest
    mismatches = []
    if provider != config.embedding_provider:
        mismatches.append(f"provider {provider!r} != {config.embedding_provider!r}")
    if model != config.embedding_model:
        mismatches.append(f"model {model!r} != {config.embedding_model!r}")
    if dimensions != config.embedding_dimensions:
        mismatches.append(f"dimensions {dimensions} != {config.embedding_dimensions}")
    if mismatches:
        raise RetrievalServiceError(
            "Configured embedding model does not match the latest completed Qdrant embedding run: "
            + "; ".join(mismatches)
        )


def create_research_pack(
    request: ResearchQueryRequest,
    *,
    config: HybridRetrievalConfig | None = None,
) -> LegalResearchPack:
    runtime_config = config or HybridRetrievalConfig.from_settings()
    candidate_size = max(runtime_config.candidate_size, request.max_pack_items)
    exact_signals = parse_exact_citation_signals(request.query)
    exact_hits: list[SearchHit] = []
    if exact_signals.has_signals:
        with session_scope() as session:
            exact_hits = resolve_exact_citation_hits(query=request.query, filters=request.filters, session=session)
    query_variants = expand_for_against_queries(request.query)
    keyword_result_sets: list[list[SearchHit]] = []
    vector_result_sets: list[list[SearchHit]] = []
    for variant in query_variants:
        keyword_result_sets.append(
            tag_hits_for_query_intent(
                opensearch_query(query=variant.query, filters=request.filters, config=runtime_config, size=candidate_size),
                variant,
            )
        )
        vector_result_sets.append(
            tag_hits_for_query_intent(
                qdrant_query(query=variant.query, filters=request.filters, config=runtime_config, size=candidate_size),
                variant,
            )
        )
    keyword_hits = [hit for result_set in keyword_result_sets for hit in result_set]
    vector_hits = [hit for result_set in vector_result_sets for hit in result_set]
    result_sets = [exact_hits, *keyword_result_sets, *vector_result_sets]
    fused = reciprocal_rank_fusion(result_sets)
    reranked = rerank_with_legal_quality(fused)
    missing_source_summary = None
    if not reranked:
        missing_source_summary = "No matching chunks were found in the current OpenSearch/Qdrant indexes."
    pack = build_research_pack(
        query=request.query,
        query_class=request.query_class or QueryClass.GENERAL_RESEARCH,
        filters=request.filters,
        hits=reranked,
        max_items=request.max_pack_items,
        max_tokens=request.max_pack_tokens,
        missing_source_summary=missing_source_summary,
    )
    retrieval_config = dict(pack.retrieval_config)
    retrieval_config.update(
        {
            "opensearch": "BM25 + phrase + fuzzy",
            "qdrant": "dense vector",
            "embedding_provider": runtime_config.embedding_provider,
            "embedding_model": runtime_config.embedding_model,
            "embedding_dimensions": runtime_config.embedding_dimensions,
            "candidate_size": candidate_size,
            "query_expansion": "supportive_adverse_limitation_exception_procedural_risk",
            "reranker": "legal_quality_plus_query_intent_multiplier",
            "query_variants": [
                {
                    "query_variant_id": variant.query_id,
                    "query_intent": variant.intent.value,
                    "query": variant.query,
                    "purpose": variant.purpose,
                    "expansion_terms": list(variant.expansion_terms),
                }
                for variant in query_variants
            ],
            "retriever_counts": {
                "exact_citation_provision": len(exact_hits),
                "opensearch_bm25_phrase_fuzzy": len(keyword_hits),
                "qdrant_dense_vector": len(vector_hits),
            },
            "query_intent_counts": {
                variant.intent.value: sum(
                    1
                    for hit in [*keyword_hits, *vector_hits]
                    if (hit.metadata or {}).get("query_intent") == variant.intent.value
                )
                for variant in query_variants
            },
        }
    )
    return seal_research_pack(
        pack.model_copy(update={"retrieval_config": retrieval_config}),
        parent_pack_id=request.parent_pack_id,
        retrieval_trace=[
            {
                "stage": "request",
                "query": request.query,
                "query_class": (request.query_class or QueryClass.GENERAL_RESEARCH).value,
                "purpose": request.purpose,
                "filters": request.filters.model_dump(mode="json"),
                "max_items": request.max_pack_items,
                "max_tokens": request.max_pack_tokens,
            },
            *query_intent_trace(query_variants),
            {
                "stage": "candidate_retrieval",
                "retriever_counts": retrieval_config["retriever_counts"],
                "query_intent_counts": retrieval_config["query_intent_counts"],
            },
            {
                "stage": "fusion",
                "method": retrieval_config["fusion"],
                "selected_items": len(pack.items),
                "reranker": retrieval_config["reranker"],
            },
        ],
    )
