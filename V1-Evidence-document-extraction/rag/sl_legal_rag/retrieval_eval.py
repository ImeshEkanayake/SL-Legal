from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalEvalCase:
    query_id: str
    expected_chunk_ids: tuple[str, ...]
    ranked_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_count: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    missing_query_ids: tuple[str, ...]

    @property
    def passes_minimum_bar(self) -> bool:
        return self.recall_at_k >= 0.90 and self.mrr >= 0.75 and self.ndcg_at_k >= 0.75


def recall_at_k(expected: set[str], ranked: list[str], k: int) -> float:
    if not expected:
        return 1.0
    retrieved = set(ranked[:k])
    return len(expected.intersection(retrieved)) / len(expected)


def reciprocal_rank(expected: set[str], ranked: list[str]) -> float:
    if not expected:
        return 1.0
    for index, chunk_id in enumerate(ranked, start=1):
        if chunk_id in expected:
            return 1.0 / index
    return 0.0


def ndcg_at_k(expected: set[str], ranked: list[str], k: int) -> float:
    if not expected:
        return 1.0
    dcg = 0.0
    for index, chunk_id in enumerate(ranked[:k], start=1):
        relevance = 1.0 if chunk_id in expected else 0.0
        if relevance:
            dcg += relevance / math.log2(index + 1)
    ideal_hits = min(len(expected), k)
    ideal_dcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def evaluate_retrieval_cases(cases: list[RetrievalEvalCase], *, k: int = 20) -> RetrievalEvalResult:
    if k < 1:
        raise ValueError("k must be at least 1")
    if not cases:
        return RetrievalEvalResult(
            case_count=0,
            recall_at_k=0.0,
            mrr=0.0,
            ndcg_at_k=0.0,
            missing_query_ids=(),
        )
    recall_values: list[float] = []
    reciprocal_rank_values: list[float] = []
    ndcg_values: list[float] = []
    missing_query_ids: list[str] = []
    for case in cases:
        expected = set(case.expected_chunk_ids)
        ranked = list(case.ranked_chunk_ids)
        recall_value = recall_at_k(expected, ranked, k)
        recall_values.append(recall_value)
        reciprocal_rank_values.append(reciprocal_rank(expected, ranked))
        ndcg_values.append(ndcg_at_k(expected, ranked, k))
        if expected and not expected.intersection(set(ranked[:k])):
            missing_query_ids.append(case.query_id)
    count = len(cases)
    return RetrievalEvalResult(
        case_count=count,
        recall_at_k=round(sum(recall_values) / count, 6),
        mrr=round(sum(reciprocal_rank_values) / count, 6),
        ndcg_at_k=round(sum(ndcg_values) / count, 6),
        missing_query_ids=tuple(missing_query_ids),
    )
