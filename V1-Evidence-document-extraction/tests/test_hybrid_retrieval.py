from __future__ import annotations

from sl_legal_rag.hybrid_retrieval import (
    HybridRetrievalConfig,
    RetrievalServiceError,
    _assert_embedding_run_compatible,
    build_opensearch_payload,
    create_research_pack,
    hit_from_payload,
)
from sl_legal_rag.models import ResearchQueryRequest, RetrievalFilters
from sl_legal_rag.retrieval import SearchHit, reciprocal_rank_fusion


def test_opensearch_payload_includes_keyword_and_metadata_filters():
    filters = RetrievalFilters(
        document_types=["Act"],
        source_ids=["PARL_ACTS"],
        year_from=1999,
        year_to=2000,
        authority_levels=["primary", "secondary"],
        language="English",
    )

    payload = build_opensearch_payload("trade union bargaining", filters, 10)

    bool_query = payload["query"]["bool"]
    assert payload["size"] == 10
    assert len(bool_query["should"]) == 3
    assert {"terms": {"document_type": ["Act"]}} in bool_query["filter"]
    assert {"terms": {"source_id": ["PARL_ACTS"]}} in bool_query["filter"]
    assert {"terms": {"authority_level": [1, 6]}} in bool_query["filter"]
    assert {"range": {"year": {"gte": 1999, "lte": 2000}}} in bool_query["filter"]
    assert {"term": {"language": "English"}} in bool_query["filter"]


def test_hit_from_payload_normalizes_types_and_text_field():
    hit = hit_from_payload(
        {
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "title": "Title",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": "2",
            "citation": "Act No. 1",
            "text": "payload text",
            "year": "1999",
            "page_start": "1",
            "page_end": "2",
            "text_origin": "translation",
            "translated_from_language": "Sinhala",
            "translation_review_status": "machine_draft",
        },
        retriever="qdrant_dense_vector",
        score=0.5,
        rank=3,
    )

    assert hit.text == "payload text"
    assert hit.authority_level == 2
    assert hit.year == 1999
    assert hit.retriever == "qdrant_dense_vector"
    assert hit.metadata["text_origin"] == "translation"
    assert hit.metadata["translated_from_language"] == "Sinhala"


def test_create_research_pack_fuses_stubbed_retrievers(monkeypatch):
    os_hit = hit_from_payload(
        {
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "title": "Industrial Disputes",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": 2,
            "citation": "Industrial Disputes Act",
            "chunk_text": "No employer shall refuse to bargain with a qualifying trade union.",
        },
        retriever="opensearch_bm25_phrase_fuzzy",
        score=10.0,
        rank=1,
    )
    vector_hit = hit_from_payload(
        {
            "chunk_id": "chunk_2",
            "document_id": "doc_2",
            "title": "Trade Union Material",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": 3,
            "citation": "Trade Union Act",
            "chunk_text": "A trade union may represent workmen.",
        },
        retriever="qdrant_dense_vector",
        score=0.8,
        rank=1,
    )

    monkeypatch.setattr("sl_legal_rag.hybrid_retrieval.opensearch_query", lambda **_kwargs: [os_hit])
    monkeypatch.setattr("sl_legal_rag.hybrid_retrieval.qdrant_query", lambda **_kwargs: [vector_hit])

    pack = create_research_pack(
        ResearchQueryRequest(query="trade union bargaining", max_pack_items=2, max_pack_tokens=2000),
        config=HybridRetrievalConfig(
            opensearch_url="http://test",
            opensearch_index="chunks",
            qdrant_url="http://test",
            qdrant_collection="chunks",
            embedding_provider="sentence-transformers",
            embedding_model="test",
            embedding_dimensions=384,
            candidate_size=10,
        ),
    )

    assert len(pack.items) == 2
    assert pack.items[0].pack_item_id.endswith("_item_001")
    assert pack.items[0].citation == "Industrial Disputes Act"
    assert pack.retrieval_config["fusion"] == "reciprocal_rank_fusion"


def test_embedding_run_compatibility_rejects_model_drift(monkeypatch):
    monkeypatch.setattr(
        "sl_legal_rag.hybrid_retrieval._latest_embedding_run",
        lambda _collection: ("sentence-transformers", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 384),
    )

    try:
        _assert_embedding_run_compatible(
            HybridRetrievalConfig(
                opensearch_url="http://test",
                opensearch_index="chunks",
                qdrant_url="http://test",
                qdrant_collection="chunks",
                embedding_provider="sentence-transformers",
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_dimensions=384,
                candidate_size=10,
            )
        )
    except RetrievalServiceError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("embedding model drift should fail before querying Qdrant")


def test_create_research_pack_applies_legal_quality_reranking(monkeypatch):
    clean_hit = hit_from_payload(
        {
            "chunk_id": "chunk_clean",
            "document_id": "doc_clean",
            "title": "Clean Act",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": 2,
            "citation": "Clean Act",
            "chunk_text": "Clean official text.",
        },
        retriever="opensearch_bm25_phrase_fuzzy",
        score=1.0,
        rank=2,
    )
    low_quality_hit = hit_from_payload(
        {
            "chunk_id": "chunk_low_quality",
            "document_id": "doc_low",
            "title": "Low OCR Act",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": 2,
            "citation": "Low OCR Act",
            "chunk_text": "Low OCR text.",
            "quality_flags": ["low_confidence_ocr", "machine_translation_unreviewed"],
        },
        retriever="opensearch_bm25_phrase_fuzzy",
        score=1.0,
        rank=1,
    )

    monkeypatch.setattr("sl_legal_rag.hybrid_retrieval.opensearch_query", lambda **_kwargs: [low_quality_hit, clean_hit])
    monkeypatch.setattr("sl_legal_rag.hybrid_retrieval.qdrant_query", lambda **_kwargs: [])

    pack = create_research_pack(
        ResearchQueryRequest(query="quality-sensitive query", max_pack_items=2, max_pack_tokens=2000),
        config=HybridRetrievalConfig(
            opensearch_url="http://test",
            opensearch_index="chunks",
            qdrant_url="http://test",
            qdrant_collection="chunks",
            embedding_provider="sentence-transformers",
            embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            embedding_dimensions=384,
            candidate_size=10,
        ),
    )

    assert pack.items[0].chunk_id == "chunk_clean"
    assert pack.items[1].scoring_breakdown["legal_quality_multiplier"] < 1


def test_rrf_preserves_all_retrieval_evidence_and_boosts_exact_match():
    exact_hit = SearchHit(
        chunk_id="chunk_exact",
        document_id="doc_1",
        title="Act",
        document_type="Act",
        source_id="PARL_ACTS",
        authority_level=2,
        citation="Act, No. 1 of 1999",
        text="section text",
        score=1000.0,
        retriever="exact_citation_provision",
        metadata={"exact_citation_match": True},
    )
    exact_duplicate = SearchHit(
        chunk_id="chunk_exact",
        document_id="doc_1",
        title="Act",
        document_type="Act",
        source_id="PARL_ACTS",
        authority_level=2,
        citation="Act, No. 1 of 1999",
        text="section text",
        score=9.0,
        retriever="opensearch_bm25_phrase_fuzzy",
    )
    semantic_hit = SearchHit(
        chunk_id="chunk_semantic",
        document_id="doc_2",
        title="Other",
        document_type="Act",
        source_id="PARL_ACTS",
        authority_level=2,
        citation="Other Act",
        text="semantic text",
        score=10.0,
        retriever="qdrant_dense_vector",
    )

    fused = reciprocal_rank_fusion([[semantic_hit], [exact_hit], [exact_duplicate]])

    assert fused[0].chunk_id == "chunk_exact"
    assert fused[0].metadata["retrieval_evidence"] == [
        "exact_citation_provision rank 1",
        "opensearch_bm25_phrase_fuzzy rank 1",
    ]
