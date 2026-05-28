from __future__ import annotations

from sl_legal_rag.adverse_retrieval import (
    RetrievalQueryIntent,
    adverse_relevance_score,
    expand_for_against_queries,
    query_intent_trace,
    tag_hits_for_query_intent,
)
from sl_legal_rag.retrieval import SearchHit


def sample_hit(text: str = "The claim is barred unless the threshold is met.") -> SearchHit:
    return SearchHit(
        chunk_id="chunk_1",
        document_id="doc_1",
        title="Industrial Disputes Limitation Authority",
        document_type="Act",
        source_id="PARL_ACTS",
        authority_level=2,
        citation="Industrial Disputes Act",
        text=text,
        score=1.0,
        retriever="opensearch_bm25_phrase_fuzzy",
        year=2024,
        page_start=1,
        page_end=2,
    )


def test_expands_query_into_supportive_and_adverse_intents():
    variants = expand_for_against_queries("trade union bargaining")

    assert [variant.intent for variant in variants] == [
        RetrievalQueryIntent.SUPPORTIVE,
        RetrievalQueryIntent.ADVERSE,
        RetrievalQueryIntent.LIMITATION,
        RetrievalQueryIntent.EXCEPTION,
        RetrievalQueryIntent.PROCEDURAL_RISK,
    ]
    assert all("trade union bargaining" in variant.query for variant in variants)
    assert any("contrary authority" in variant.query for variant in variants)


def test_tagged_hits_carry_query_intent_scores_and_trace_metadata():
    variant = expand_for_against_queries("trade union bargaining")[2]
    tagged = tag_hits_for_query_intent([sample_hit()], variant)

    assert tagged[0].retriever.endswith(":limitation")
    assert tagged[0].score > 1.0
    assert tagged[0].metadata["query_intent"] == "limitation"
    assert tagged[0].metadata["query_variant_id"].startswith("limitation:")
    assert tagged[0].metadata["authority_score"] > 0
    assert tagged[0].metadata["recency_score"] > 0
    assert tagged[0].metadata["exactness_score"] >= 0
    assert tagged[0].metadata["adverse_relevance_score"] > 0


def test_adverse_relevance_scores_limitation_and_exception_language():
    limitation_variant = expand_for_against_queries("trade union bargaining")[2]
    neutral_hit = sample_hit("The Act establishes a general right to bargain.")
    adverse_hit = sample_hit("The claim is barred by limitation unless jurisdiction is established.")

    assert adverse_relevance_score(hit=adverse_hit, variant=limitation_variant) > adverse_relevance_score(
        hit=neutral_hit,
        variant=limitation_variant,
    )


def test_query_intent_trace_is_auditable():
    trace = query_intent_trace(expand_for_against_queries("trade union bargaining"))

    assert trace[0]["stage"] == "query_expansion"
    assert {item["query_intent"] for item in trace} == {
        "supportive",
        "adverse",
        "limitation",
        "exception",
        "procedural_risk",
    }
