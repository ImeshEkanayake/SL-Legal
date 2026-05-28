from __future__ import annotations

import pytest

from sl_legal_rag.models import LegalResearchPack
from sl_legal_rag.research_pack import (
    build_expansion_query_request,
    estimate_pack_tokens,
    research_pack_hash,
    seal_research_pack,
    validate_research_pack_contract,
)


def sample_pack(**updates) -> LegalResearchPack:
    payload = {
        "pack_id": "pack_contract",
        "query": "trade union bargaining",
        "query_class": "general_research",
        "filters": {},
        "retrieval_config": {
            "fusion": "reciprocal_rank_fusion",
            "max_tokens": 12000,
            "retriever_counts": {
                "opensearch_bm25_phrase_fuzzy": 1,
                "qdrant_dense_vector": 1,
            },
        },
        "items": [
            {
                "pack_item_id": "pack_contract_item_001",
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "title": "Industrial Disputes Act",
                "document_type": "Act",
                "source_id": "PARL_ACTS",
                "authority_level": 2,
                "citation": "Industrial Disputes Act s 1",
                "text": "No employer shall refuse to bargain with a qualifying trade union.",
                "fused_score": 0.92,
                "selection_reason": "opensearch rank 1; new source document",
                "metadata": {"retrieval_evidence": ["opensearch rank 1"]},
            }
        ],
    }
    payload.update(updates)
    return LegalResearchPack.model_validate(payload)


def test_seal_research_pack_adds_hash_trace_tokens_and_warnings():
    sealed = seal_research_pack(sample_pack())

    assert sealed.schema_version == "legal_research_pack.v1"
    assert sealed.pack_hash == research_pack_hash(sealed)
    assert sealed.token_count == estimate_pack_tokens(sealed)
    assert sealed.retrieval_trace
    assert sealed.items[0].token_estimate is not None
    assert sealed.items[0].retrieval_trace
    assert sealed.items[0].scoring_breakdown["fused_score"] == pytest.approx(0.92)
    assert validate_research_pack_contract(sealed) == []


def test_research_pack_contract_rejects_non_canonical_item_id_and_budget_overflow():
    pack = sample_pack(
        retrieval_config={"fusion": "reciprocal_rank_fusion", "max_tokens": 1},
        items=[
            {
                "pack_item_id": "wrong_item_id",
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "title": "Industrial Disputes Act",
                "document_type": "Act",
                "source_id": "PARL_ACTS",
                "authority_level": 2,
                "citation": "Industrial Disputes Act s 1",
                "text": "No employer shall refuse to bargain with a qualifying trade union.",
                "fused_score": 0.92,
                "selection_reason": "opensearch rank 1",
            }
        ],
    )

    issues = validate_research_pack_contract(pack)

    assert {issue.code for issue in issues} >= {"non_canonical_pack_item_id", "token_budget_exceeded"}


def test_research_pack_contract_rejects_empty_pack_without_missing_source_warning():
    pack = sample_pack(items=[])

    issues = validate_research_pack_contract(pack)

    assert "empty_pack_without_missing_source_warning" in {issue.code for issue in issues}


def test_expansion_query_request_preserves_parent_filters_and_budget():
    parent = seal_research_pack(sample_pack())

    request = build_expansion_query_request(parent_pack=parent, query="find adverse authority")

    assert request.parent_pack_id == parent.pack_id
    assert request.query == "find adverse authority"
    assert request.filters == parent.filters
    assert request.max_pack_tokens == 12000
