from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetrievalSignal(StrEnum):
    EXACT_CITATION = "exact_citation"
    BM25 = "bm25"
    PHRASE = "phrase"
    FUZZY = "fuzzy"
    DENSE_VECTOR = "dense_vector"
    LEARNED_SPARSE = "learned_sparse"
    CITATION_GRAPH = "citation_graph"
    RERANKER = "reranker"
    AUTHORITY_MODEL = "authority_model"


@dataclass(frozen=True)
class AccuracyGate:
    name: str
    metric: str
    target: str
    blocks_strategy_generation: bool = True


@dataclass(frozen=True)
class RetrievalStage:
    name: str
    purpose: str
    signals: tuple[RetrievalSignal, ...]
    required_for_production: bool = True


ACCURACY_FIRST_STAGES: tuple[RetrievalStage, ...] = (
    RetrievalStage(
        name="query_planning",
        purpose="Classify legal task, extract citations/provisions/names/dates, and build metadata filters.",
        signals=(RetrievalSignal.EXACT_CITATION,),
    ),
    RetrievalStage(
        name="parallel_candidate_retrieval",
        purpose="Maximize recall before any LLM sees context.",
        signals=(
            RetrievalSignal.EXACT_CITATION,
            RetrievalSignal.BM25,
            RetrievalSignal.PHRASE,
            RetrievalSignal.FUZZY,
            RetrievalSignal.DENSE_VECTOR,
            RetrievalSignal.LEARNED_SPARSE,
            RetrievalSignal.CITATION_GRAPH,
        ),
    ),
    RetrievalStage(
        name="fusion",
        purpose="Use rank-based fusion so scores from different retrievers do not distort results.",
        signals=(RetrievalSignal.BM25, RetrievalSignal.DENSE_VECTOR, RetrievalSignal.LEARNED_SPARSE),
    ),
    RetrievalStage(
        name="reranking",
        purpose="Improve precision with cross-encoder or late-interaction scoring over the candidate pool.",
        signals=(RetrievalSignal.RERANKER, RetrievalSignal.AUTHORITY_MODEL),
    ),
    RetrievalStage(
        name="pack_validation",
        purpose="Build a citable Legal Research Pack and reject unsupported legal claims.",
        signals=(RetrievalSignal.AUTHORITY_MODEL,),
    ),
)


PRODUCTION_ACCURACY_GATES: tuple[AccuracyGate, ...] = (
    AccuracyGate("exact_lookup", "citation/provision lookup accuracy", "near-perfect on golden citations"),
    AccuracyGate("recall", "Recall@20", "all known supporting authorities retrieved"),
    AccuracyGate("ranking", "nDCG@10 and MRR", "correct authority appears near the top"),
    AccuracyGate("citation_safety", "unsupported legal claim rate", "zero tolerated"),
    AccuracyGate("citation_hallucination", "fabricated citation rate", "zero tolerated"),
    AccuracyGate("ocr_safety", "low-confidence selected OCR passages", "excluded or flagged"),
    AccuracyGate("missing_sources", "missing-source detection", "missing authorities surfaced"),
)
